"""Incremental index executor for ``rsm index --incremental``.

Consumes an :class:`~repo_semantic_memory.indexing.incremental.IncrementalPlan`
produced by :func:`~repo_semantic_memory.indexing.incremental.plan_incremental_update`
and applies a transactional update to an existing SQLite index.

Strategy
--------
1. Extract new content for changed/added paths (outside the transaction so
   that extraction errors surface cleanly before any DB mutation).
2. Inside **one** :meth:`~repo_semantic_memory.store.SQLiteStore.apply_incremental_update`
   transaction:

   a. Purge all ``tests`` relations (global-recompute pass).
   b. Delete relations whose source entity is in the purge set.
   c. Delete entities for the purge set.
   d. Upsert freshly extracted entities and non-global relations.
   e. Re-run :func:`~repo_semantic_memory.extractors.extract_test_relationships`
      over the full post-upsert snapshot.
   f. Commit.

3. Write staleness metadata (``last_index_mode = incremental``).

If any step raises, the transaction rolls back and the previous index remains
usable.  Callers should fall back to a full rebuild on any exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from repo_semantic_memory.extractors import (
    extract_markdown_file,
    extract_python_exports,
    extract_python_file,
    extract_test_relationships,
    get_git_repository_summary,
)
from repo_semantic_memory.extractors.filesystem import (
    _build_entity,
    _classify_kind,
    _is_binary_looking,
)
from repo_semantic_memory.indexing.incremental import IncrementalPlan
from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.store import SQLiteStore
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, SCHEMA_VERSION

_MARKDOWN_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown"})
_PYTHON_EXTENSIONS: frozenset[str] = frozenset({".py"})
_GLOBAL_RECOMPUTE_KINDS: frozenset[str] = frozenset({"tests"})


@dataclass(frozen=True)
class IncrementalResult:
    """Result of an incremental index update.

    Attributes:
        used_incremental: ``True`` when the incremental path was taken,
            ``False`` when the executor fell back to a full rebuild.
        fallback_reason: Stable :class:`~repo_semantic_memory.indexing
            .incremental.IncrementalFallbackReason` string when
            ``used_incremental`` is ``False``; ``None`` otherwise.
        changed_paths: Repo-relative paths that were re-extracted.
        deleted_paths: Repo-relative paths that were purged.
        renamed_paths: ``(old, new)`` pairs from the plan.
        entity_count: Total entities in the index after the update.
        relation_count: Total relations in the index after the update.
    """

    used_incremental: bool
    fallback_reason: str | None
    changed_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]
    renamed_paths: tuple[tuple[str, str], ...]
    entity_count: int
    relation_count: int


def run_incremental_index(
    repo_root: Path,
    db_path: Path,
    plan: IncrementalPlan,
    *,
    with_git: bool = False,
) -> IncrementalResult:
    """Execute an incremental index update using *plan*.

    Performs path-scoped extraction for changed/added files, then applies a
    single atomic transaction: purge stale entries → upsert fresh extractions
    → recompute global ``tests`` relations.

    Args:
        repo_root: Absolute path to the repository working tree.
        db_path: Path to the existing SQLite index database.
        plan: Incremental plan from :func:`~repo_semantic_memory.indexing
            .incremental.plan_incremental_update`.  Must have
            ``can_incremental=True``; callers should run a full rebuild
            when it is ``False``.
        with_git: Whether git temporal metadata was requested for this index
            run.  The flag is forwarded to :func:`~repo_semantic_memory
            .extractors.get_git_repository_summary` to populate ``git_head``
            and ``git_dirty`` in the post-update metadata.  When ``True`` the
            git summary is used only for the metadata write; per-entity
            git-temporal metadata is **not** re-attached in this MVP executor
            (Prompt 50.3 scope).

    Returns:
        :class:`IncrementalResult` with ``used_incremental=True``.

    Raises:
        Any exception raised by an extractor (e.g. ``SyntaxError``,
        ``ValueError``, ``UnicodeDecodeError``) or by the SQLite transaction.
        Callers should catch and fall back to a full rebuild.
    """
    repo_root = repo_root.resolve()

    # Compute purge and re-extract sets from the plan.
    rename_old = frozenset(old for old, _ in plan.renamed_paths)
    rename_new = frozenset(new for _, new in plan.renamed_paths)

    # Everything that had index entries must be purged (changed + deleted + old rename).
    purge_paths = frozenset(plan.changed_paths) | frozenset(plan.deleted_paths) | rename_old
    # Everything that exists on disk must be re-extracted (changed + new rename targets).
    re_extract_paths = frozenset(plan.changed_paths) | rename_new

    # Extract per-file content outside the transaction so failures are clean.
    new_entities, new_relations = _extract_paths(repo_root, re_extract_paths)

    store = SQLiteStore(db_path)
    try:
        store.initialize()

        def _compute_tests(entities: list[Entity], relations: list[Relation]) -> list[Relation]:
            return list(extract_test_relationships(repo_root, entities, relations))

        entity_count, relation_count = store.apply_incremental_update(
            purge_paths=purge_paths,
            new_entities=new_entities,
            new_relations=new_relations,
            global_recompute_kinds=_GLOBAL_RECOMPUTE_KINDS,
            compute_global_relations=_compute_tests,
        )

        # Write staleness metadata.
        git_summary = get_git_repository_summary(repo_root)
        now_iso = datetime.now(tz=UTC).isoformat()
        extra_meta: dict[str, str] = {
            "indexed_at": now_iso,
            "entity_count": str(entity_count),
            "relation_count": str(relation_count),
            "schema_version": SCHEMA_VERSION,
            "context_pack_version": CONTEXT_PACK_VERSION,
            "last_index_mode": "incremental",
        }
        if git_summary.in_git_repo and git_summary.current_commit:
            extra_meta["git_head"] = git_summary.current_commit.strip()
            extra_meta["git_dirty"] = "true" if git_summary.is_dirty else "false"
        else:
            extra_meta["git_head"] = ""
            extra_meta["git_dirty"] = ""
        store.write_extra_metadata(extra_meta)
    finally:
        store.close()

    return IncrementalResult(
        used_incremental=True,
        fallback_reason=None,
        changed_paths=plan.changed_paths,
        deleted_paths=plan.deleted_paths,
        renamed_paths=plan.renamed_paths,
        entity_count=entity_count,
        relation_count=relation_count,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_paths(
    repo_root: Path,
    rel_paths: frozenset[str],
) -> tuple[list[Entity], list[Relation]]:
    """Extract entities and non-global relations for *rel_paths*.

    ``tests`` relations are intentionally excluded — they are recomputed
    globally inside the transaction by :func:`run_incremental_index`.

    Args:
        repo_root: Absolute path to the repository working tree.
        rel_paths: Repo-relative paths to extract.  Non-existent paths are
            skipped silently (they may have been deleted between planning and
            execution).

    Returns:
        ``(entities, relations)`` lists ready for upsert.
    """
    entities: list[Entity] = []
    relations: list[Relation] = []

    for rel_path in sorted(rel_paths):
        abs_path = repo_root / rel_path
        if not abs_path.exists():
            continue

        suffix = abs_path.suffix.lower()

        if suffix in _PYTHON_EXTENSIONS:
            py_ents, py_rels = extract_python_file(repo_root, abs_path)
            entities.extend(py_ents)
            relations.extend(py_rels)
            # export relations for __init__.py files (returns [] otherwise).
            relations.extend(extract_python_exports(repo_root, abs_path))

        elif suffix in _MARKDOWN_EXTENSIONS:
            md_ents, md_rels = extract_markdown_file(repo_root, abs_path)
            entities.extend(md_ents)
            relations.extend(md_rels)

        else:
            # Filesystem entity for other supported file types.
            if not _is_binary_looking(abs_path):
                kind = _classify_kind(abs_path)
                if kind is not None:
                    entities.append(_build_entity(rel_path, abs_path, kind=kind))

    return entities, relations
