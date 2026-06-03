"""Bounded support-file expansion for context-pack ranking.

Selects adjacent implementation files around the central selected entities,
using a priority-ordered, intent-conditioned algorithm:

1. **Import adjacency** — entities directly imported by a selected entity
   (forward ``imports`` relation) receive the strongest bonus.
2. **Export adjacency** — ``__init__.py``-style surfaces that export selected
   entities (reverse ``exports`` relation) are boosted; export targets of
   selected files also qualify.
3. **Inherits adjacency** — entities in an ``inherits`` relation with a selected
   entity receive a moderate bonus (either direction).
4. **Reverse-import** — entities that import a selected entity receive a weaker
   bonus (they depend on selected; less important than a direct dependency).
5. **Same-package proximity** — entities in the same directory as a selected
   entity receive a small positional bonus; this alone does not meet the minimum
   score threshold, requiring at least one lexical-token overlap in addition.
6. **Lexical token overlap** — weak additive bonus from ``QueryIntent.lexical_tokens``
   found in the candidate path.

Filtering:
- Already-selected entities are excluded.
- Test files (``TEST_ROLE`` or ``is_runtime_test_named_path``) are excluded; tests
  are handled by the test branch (Prompt 58.3).
- Docs and examples are excluded unless ``public_api`` or ``architecture_flow``
  intent is present.
- ``__init__.py`` files receive an extra boost when ``public_api`` intent is active.
- A minimum score threshold prevents purely proximity-based selections without any
  structural or lexical signal.

Results are deduplicated by ``source_path`` (preferring module-level entities over
class/function children) and capped at ``max_support_files``.

This is the Ranking v2 Step 4 (Prompt 58.4) implementation.
"""

from __future__ import annotations

from collections.abc import Sequence

from repo_semantic_memory.context.bm25 import tokenize_text
from repo_semantic_memory.context.path_roles import (
    DOC_ROLE,
    EXAMPLE_ROLE,
    TEST_ROLE,
    classify_path_role,
    is_public_api_file,
    is_runtime_test_named_path,
)
from repo_semantic_memory.context.query_intent import QueryIntent
from repo_semantic_memory.model import Entity, Relation

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

# Bonus when the selected entity imports the candidate (direct dependency).
# This is the strongest structural signal: if A imports B, B is a support file.
_FORWARD_IMPORT_BONUS: float = 10.0

# Bonus when the candidate is a package surface (__init__.py) that exports a
# selected entity (reverse ``exports`` relation).
_REVERSE_EXPORT_BONUS: float = 8.0

# Bonus when the selected entity exports the candidate (selected is __init__.py
# and re-exports another module as part of the public API).
_FORWARD_EXPORT_BONUS: float = 6.0

# Bonus for entities in an ``inherits`` relation with a selected entity (either
# direction: selected inherits candidate, or candidate inherits selected).
_INHERITS_BONUS: float = 5.0

# Bonus when the candidate imports a selected entity (the candidate depends on
# selected, which is a weaker signal than a direct import dependency).
_REVERSE_IMPORT_BONUS: float = 4.0

# Bonus for entities in the same directory as a selected entity.  Intentionally
# small: same-package proximity alone (_SAME_PACKAGE_BONUS = 2.0) does not meet
# _MIN_SUPPORT_SCORE (4.0), so siblings only qualify when they also have at least
# two lexical-token hits in their path.
_SAME_PACKAGE_BONUS: float = 2.0

# Extra boost for ``__init__.py`` files when ``public_api`` intent is active.
# Applied on top of any structural score already accumulated.
_PUBLIC_API_INIT_BOOST: float = 4.0

# Bonus per query lexical token found in the candidate entity's path.
# Kept small so lexical alone cannot dominate structural signals.
_LEXICAL_TOKEN_BONUS: float = 1.0

# Minimum total score required for a candidate to be included.  Set to the
# value of _REVERSE_IMPORT_BONUS so a reverse import alone just qualifies,
# while same-package proximity alone (_SAME_PACKAGE_BONUS = 2.0) does not.
_MIN_SUPPORT_SCORE: float = 4.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_support_files(
    *,
    selected_entities: Sequence[Entity],
    all_entities: Sequence[Entity],
    relations: Sequence[Relation],
    query_intent: QueryIntent,
    source_roots: Sequence[str] = (),
    max_support_files: int = 5,
) -> list[tuple[str, str]]:
    """Select adjacent support-file candidates around the selected central entities.

    Only candidates that pass the minimum score threshold (``_MIN_SUPPORT_SCORE``)
    are returned.  Already-selected entities, test files, and runtime test-named
    paths are always excluded.

    Args:
        selected_entities: Entities already selected by the main ranking and
            graph expansion passes.  Used as expansion seeds **and** excluded
            from candidates so they are never returned as support files.
        all_entities: All indexed entities for the repository.
        relations: All indexed relations for the repository.
        query_intent: Parsed intent from
            :func:`~repo_semantic_memory.context.query_intent.parse_query_intent`.
        source_roots: Inferred source-root paths forwarded to
            :func:`~repo_semantic_memory.context.path_roles.classify_path_role`.
            Defaults to ``()`` (no inferred roots).
        max_support_files: Maximum number of support file entities to return.
            Defaults to 5.

    Returns:
        List of ``(entity_id, reason_string)`` tuples ordered by descending
        priority score.  Returns an empty list when no qualifying support files
        are found.
    """
    if not selected_entities or not all_entities:
        return []
    if max_support_files <= 0:
        return []

    selected_ids: frozenset[str] = frozenset(e.id.value for e in selected_entities)
    entity_by_id: dict[str, Entity] = {e.id.value: e for e in all_entities}

    # Accumulated score and the best-bonus reason per candidate entity id.
    scores: dict[str, float] = {}
    best_delta: dict[str, float] = {}  # tracks the highest single delta per candidate
    reasons: dict[str, str] = {}

    def _accumulate(eid: str, delta: float, reason: str) -> None:
        """Add *delta* to candidate *eid*'s score; update reason if better signal."""
        if eid in selected_ids or eid not in entity_by_id:
            return
        scores[eid] = scores.get(eid, 0.0) + delta
        if best_delta.get(eid, -1.0) < delta:
            best_delta[eid] = delta
            reasons[eid] = reason

    # -----------------------------------------------------------------------
    # Step 1 — relation-based adjacency scoring
    # -----------------------------------------------------------------------
    for rel in relations:
        kind = rel.kind
        if kind == "tests":
            # ``tests`` relations are handled by the test branch (Prompt 58.3).
            continue

        src_id = rel.source_entity_id.value
        tgt_id = rel.target_entity_id.value

        if kind == "imports":
            if src_id in selected_ids:
                # selected --imports--> candidate: direct dependency (strongest signal)
                _accumulate(
                    tgt_id,
                    _FORWARD_IMPORT_BONUS,
                    f"support: imported by {_entity_path(entity_by_id, src_id)}",
                )
            elif tgt_id in selected_ids:
                # candidate --imports--> selected: reverse dependency
                _accumulate(
                    src_id,
                    _REVERSE_IMPORT_BONUS,
                    f"support: imports {_entity_path(entity_by_id, tgt_id)}",
                )

        elif kind == "exports":
            if src_id in selected_ids:
                # selected --exports--> candidate: selected is __init__.py re-exporting
                _accumulate(
                    tgt_id,
                    _FORWARD_EXPORT_BONUS,
                    f"support: exported by {_entity_path(entity_by_id, src_id)}",
                )
            elif tgt_id in selected_ids:
                # candidate --exports--> selected: candidate is the package surface
                _accumulate(
                    src_id,
                    _REVERSE_EXPORT_BONUS,
                    f"support: export surface for {_entity_path(entity_by_id, tgt_id)}",
                )

        elif kind == "inherits":
            if src_id in selected_ids:
                # selected inherits from candidate (selected depends on candidate base)
                _accumulate(
                    tgt_id,
                    _INHERITS_BONUS,
                    f"support: inherited by {_entity_path(entity_by_id, src_id)}",
                )
            elif tgt_id in selected_ids:
                # candidate inherits from selected (candidate is a subclass)
                _accumulate(
                    src_id,
                    _INHERITS_BONUS,
                    f"support: inherits {_entity_path(entity_by_id, tgt_id)}",
                )

    # -----------------------------------------------------------------------
    # Step 2 — same-package proximity (weak; does not qualify candidates alone)
    # -----------------------------------------------------------------------
    selected_dirs: set[str] = set()
    for entity in selected_entities:
        path = entity.source_range.path.replace("\\", "/")
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent:
            selected_dirs.add(parent)

    for entity in all_entities:
        eid = entity.id.value
        if eid in selected_ids:
            continue
        path = entity.source_range.path.replace("\\", "/")
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent and parent in selected_dirs:
            _accumulate(
                eid,
                _SAME_PACKAGE_BONUS,
                f"support: same package ({parent})",
            )

    # -----------------------------------------------------------------------
    # Step 3 — filter candidates; apply intent-conditioned score adjustments
    # -----------------------------------------------------------------------
    if not scores:
        return []

    lexical_set: frozenset[str] = frozenset(query_intent.lexical_tokens)
    result_scores: dict[str, float] = {}

    for eid, base_score in scores.items():
        candidate = entity_by_id.get(eid)
        if candidate is None:
            continue

        path = candidate.source_range.path.replace("\\", "/")

        # Exclude test files: handled by the test branch (Prompt 58.3).
        if is_runtime_test_named_path(path):
            continue
        role = classify_path_role(path=path, source_roots=source_roots)
        if role == TEST_ROLE:
            continue

        # Exclude docs/examples unless an intent that warrants them is present:
        # public_api (API surfaces may have docs), architecture_flow (architectural
        # diagrams/docs), or docs_examples (query explicitly asked for docs/tutorials).
        if role in (DOC_ROLE, EXAMPLE_ROLE):
            if not ({"public_api", "architecture_flow", "docs_examples"} & query_intent.intents):
                continue

        score = base_score

        # Public-API __init__.py boost: extra signal for package surfaces.
        if "public_api" in query_intent.intents and is_public_api_file(path):
            score += _PUBLIC_API_INIT_BOOST
            if eid not in reasons:
                reasons[eid] = f"support: public API surface ({path.rsplit('/', 1)[-1]})"

        # Weak lexical token overlap in the candidate's path.
        path_tokens: frozenset[str] = frozenset(tokenize_text(path))
        score += len(path_tokens & lexical_set) * _LEXICAL_TOKEN_BONUS

        if score >= _MIN_SUPPORT_SCORE:
            result_scores[eid] = score

    if not result_scores:
        return []

    # -----------------------------------------------------------------------
    # Step 4 — deduplicate by source_path; prefer module-level entities
    # -----------------------------------------------------------------------
    scored: list[tuple[Entity, float]] = []
    for entity in all_entities:
        eid = entity.id.value
        if eid in result_scores:
            scored.append((entity, result_scores[eid]))

    # Sort descending by score, then stable by entity id.
    scored.sort(key=lambda item: (-item[1], item[0].id.value))

    best_by_path: dict[str, tuple[Entity, float]] = {}
    for entity, score in scored:
        path = entity.source_range.path.replace("\\", "/")
        if path not in best_by_path:
            best_by_path[path] = (entity, score)
        else:
            existing_entity, _ = best_by_path[path]
            # Prefer module-level over class/function children for the same file.
            if entity.kind == "module" and existing_entity.kind != "module":
                best_by_path[path] = (entity, score)

    deduped = sorted(
        best_by_path.values(),
        key=lambda item: (-item[1], item[0].source_range.path),
    )

    # -----------------------------------------------------------------------
    # Step 5 — cap and build result
    # -----------------------------------------------------------------------
    result: list[tuple[str, str]] = []
    for entity, _ in deduped[:max_support_files]:
        eid = entity.id.value
        reason = reasons.get(eid, "support: structural adjacency")
        result.append((eid, reason))

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _entity_path(entity_by_id: dict[str, Entity], entity_id: str) -> str:
    """Return the source path for *entity_id*, or the id string if not found."""
    entity = entity_by_id.get(entity_id)
    if entity is None:
        return entity_id
    return entity.source_range.path.replace("\\", "/")
