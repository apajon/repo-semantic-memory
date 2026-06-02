"""Independent test-file retrieval branch for context-pack ranking.

Selects test file candidates when the query intent includes ``tests``,
using a priority-ordered algorithm:

1. **Relation-first** — test entities linked via a ``tests`` relation to any
   selected implementation (seed) entity.
2. **Test-root by proximity** — entities in a real test root (``path_role ==
   TEST_ROLE``) scored by filename-stem proximity and lexical token overlap
   with seed entity paths and ``QueryIntent.lexical_tokens``.

Runtime directories whose ``test`` segment is embedded (non-root) are
excluded via :func:`~repo_semantic_memory.context.path_roles.is_runtime_test_named_path`.

Results are deduplicated by ``source_path`` (preferring module/file-level
entities over class/function children) and capped at ``max_test_files``.

This is the Ranking v2 Step 3 (Prompt 58.3) implementation.
"""

from __future__ import annotations

from collections.abc import Sequence

from repo_semantic_memory.context.bm25 import tokenize_text
from repo_semantic_memory.context.path_roles import (
    TEST_ROLE,
    classify_path_role,
    is_runtime_test_named_path,
)
from repo_semantic_memory.context.query_intent import QueryIntent
from repo_semantic_memory.model import Entity, Relation

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

# Strong bonus for test entities linked via an explicit ``tests`` relation to a
# selected implementation entity.  Kept at 100 so relation-first candidates
# always outrank proximity-only candidates.
_RELATION_FIRST_BONUS: float = 100.0

# Bonus when the test filename stem matches the implementation filename stem.
# E.g. ``test_resolvers.py`` matches ``resolvers.py`` stem → +20.
_STEM_MATCH_BONUS: float = 20.0

# Bonus per query lexical token that appears in the test entity's path/name.
_LEXICAL_TOKEN_BONUS: float = 3.0

# Bonus per directory path segment of the test entity that also appears in
# any seed entity's directory path segments.
_PATH_SEGMENT_BONUS: float = 2.0

# Minimum score for a proximity-only candidate to be included.
# Relation-first candidates are always included (score ≥ _RELATION_FIRST_BONUS).
_MIN_PROXIMITY_SCORE: float = 1.0

# Directory segment names that are too generic to contribute to proximity
# scoring (they appear in almost every test path).
_IGNORED_PROXIMITY_SEGMENTS: frozenset[str] = frozenset(
    {"tests", "test", "units", "unit", "integration", "functional", "e2e", "src", ""}
)

# Test filename prefix/suffix patterns stripped when computing stem proximity.
_TEST_STEM_PREFIXES: tuple[str, ...] = ("test_", "tests_")
_TEST_STEM_SUFFIXES: tuple[str, ...] = ("_test", "_tests", "_spec", "_check")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_test_branch(
    *,
    entities: Sequence[Entity],
    relations: Sequence[Relation],
    query_intent: QueryIntent,
    seed_entity_ids: frozenset[str],
    source_roots: Sequence[str],
    max_test_files: int = 5,
) -> list[tuple[str, str]]:
    """Select test file candidates as an independent retrieval branch.

    Only active when ``"tests"`` is present in ``query_intent.intents``.
    When active, returns at most *max_test_files* test entity IDs (ordered
    by descending priority), together with a human-readable reason string.

    Args:
        entities: All indexed entities for the repository.
        relations: All indexed relations for the repository.
        query_intent: Parsed intent from
            :func:`~repo_semantic_memory.context.query_intent.parse_query_intent`.
        seed_entity_ids: Entity IDs of already-selected implementation entities
            (from the main ranking pass and graph expansion).  Used as anchors
            for relation-first lookup and proximity scoring.
        source_roots: Inferred source-root paths (forwarded to
            :func:`~repo_semantic_memory.context.path_roles.classify_path_role`).
        max_test_files: Maximum number of test entities to return (cap).
            Defaults to 5.

    Returns:
        List of ``(entity_id, reason_string)`` tuples ordered by descending
        priority score.  Returns an empty list when ``"tests"`` is not in
        ``query_intent.intents`` or no qualifying test entities are found.
    """
    if "tests" not in query_intent.intents:
        return []
    if max_test_files <= 0:
        return []

    entity_by_id: dict[str, Entity] = {e.id.value: e for e in entities}

    # Collect all real test-root entity IDs (path_role == TEST_ROLE and not a
    # runtime-named path).  Keyed by entity id for O(1) lookup.
    real_test_entity_ids: set[str] = set()
    for entity in entities:
        path = entity.source_range.path.replace("\\", "/")
        if _is_real_test_path(path, source_roots):
            real_test_entity_ids.add(entity.id.value)

    if not real_test_entity_ids:
        return []

    # -----------------------------------------------------------------------
    # Step 1 — relation-first: find test entities via ``tests`` relations
    # -----------------------------------------------------------------------
    # Normal direction: test_entity --tests--> impl_entity  (test_entity IS source)
    # Also handle inverted: impl_entity --tests--> test_entity (less common)

    relation_reason: dict[str, str] = {}

    for rel in relations:
        if rel.kind != "tests":
            continue
        src_id = rel.source_entity_id.value
        tgt_id = rel.target_entity_id.value

        # Normal direction: test (src) tests impl (tgt)
        if tgt_id in seed_entity_ids and src_id in real_test_entity_ids:
            if src_id not in relation_reason:
                tgt_path = _entity_path(entity_by_id, tgt_id)
                relation_reason[src_id] = f"test branch: tests relation to {tgt_path}"

        # Inverted direction: impl (src) tests test (tgt)
        if src_id in seed_entity_ids and tgt_id in real_test_entity_ids:
            if tgt_id not in relation_reason:
                src_path = _entity_path(entity_by_id, src_id)
                relation_reason[tgt_id] = f"test branch: tests relation from {src_path}"

    # -----------------------------------------------------------------------
    # Step 2 — proximity scoring for all real test entities
    # -----------------------------------------------------------------------
    seed_dir_segments, seed_stems = _build_seed_index(seed_entity_ids, entity_by_id)
    lexical_set = frozenset(query_intent.lexical_tokens)

    scores: dict[str, float] = {}

    for entity in entities:
        eid = entity.id.value
        if eid not in real_test_entity_ids:
            continue
        base = _RELATION_FIRST_BONUS if eid in relation_reason else 0.0
        proximity = _score_proximity(entity, seed_dir_segments, seed_stems, lexical_set)
        total = base + proximity
        # Always include relation-first entities; require minimum score otherwise.
        if total >= _MIN_PROXIMITY_SCORE:
            scores[eid] = total

    if not scores:
        return []

    # -----------------------------------------------------------------------
    # Step 3 — deduplicate by source_path; prefer module/file-level entities
    # -----------------------------------------------------------------------
    scored_entities: list[tuple[Entity, float]] = []
    for entity in entities:
        eid = entity.id.value
        if eid in scores:
            scored_entities.append((entity, scores[eid]))

    # Sort descending by score, then stable entity id.
    scored_entities.sort(key=lambda item: (-item[1], item[0].id.value))

    # Keep best representative per source_path.
    best_by_path: dict[str, tuple[Entity, float]] = {}
    for entity, score in scored_entities:
        path = entity.source_range.path.replace("\\", "/")
        if path not in best_by_path:
            best_by_path[path] = (entity, score)
        else:
            existing_entity, existing_score = best_by_path[path]
            # Prefer module-level over function/class children.
            if entity.kind == "module" and existing_entity.kind != "module":
                best_by_path[path] = (entity, score)

    # Re-sort the per-path representatives by (score desc, path asc) for
    # deterministic output order.
    deduped = sorted(best_by_path.values(), key=lambda item: (-item[1], item[0].source_range.path))

    # -----------------------------------------------------------------------
    # Step 4 — cap and build result
    # -----------------------------------------------------------------------
    result: list[tuple[str, str]] = []
    for entity, _score in deduped[:max_test_files]:
        eid = entity.id.value
        if eid in relation_reason:
            reason = relation_reason[eid]
        else:
            reason = _build_proximity_reason(entity, seed_stems, lexical_set)
        result.append((eid, reason))

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_real_test_path(path: str, source_roots: Sequence[str]) -> bool:
    """Return True if *path* is a real test root/file (not a runtime-named path)."""
    normalized = path.replace("\\", "/").strip("/")
    if is_runtime_test_named_path(normalized):
        return False
    role = classify_path_role(path=normalized, source_roots=source_roots)
    return role == TEST_ROLE


def _entity_path(entity_by_id: dict[str, Entity], entity_id: str) -> str:
    """Return the source path for *entity_id*, or the id if not found."""
    entity = entity_by_id.get(entity_id)
    if entity is None:
        return entity_id
    return entity.source_range.path.replace("\\", "/")


def _normalize_filename_stem(filename: str) -> str:
    """Strip test prefix/suffix and extension from a filename, return lowercase stem.

    Examples::

        _normalize_filename_stem("test_resolvers.py")  -> "resolvers"
        _normalize_filename_stem("resolvers_test.py")  -> "resolvers"
        _normalize_filename_stem("test_plugins.py")    -> "plugins"
        _normalize_filename_stem("resolvers.py")       -> "resolvers"
    """
    # Strip extension.
    if "." in filename:
        stem = filename.rsplit(".", 1)[0]
    else:
        stem = filename
    stem = stem.lower()
    # Strip test prefix.
    for prefix in _TEST_STEM_PREFIXES:
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
            break
    # Strip test suffix.
    for suffix in _TEST_STEM_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def _build_seed_index(
    seed_entity_ids: frozenset[str],
    entity_by_id: dict[str, Entity],
) -> tuple[set[str], set[str]]:
    """Build proximity index from seed entity paths.

    Returns:
        A pair ``(dir_segments, stems)`` where:
        - *dir_segments* is the set of non-generic directory path components of
          all seed entity paths (case-folded, excluding filename).
        - *stems* is the set of normalised filename stems of all seed entities.
    """
    dir_segments: set[str] = set()
    stems: set[str] = set()

    for eid in seed_entity_ids:
        entity = entity_by_id.get(eid)
        if entity is None:
            continue
        path = entity.source_range.path.replace("\\", "/").lower()
        parts = path.split("/")
        filename = parts[-1] if parts else ""
        # Directory segments (exclude filename, exclude generic names).
        for seg in parts[:-1]:
            if seg and seg not in _IGNORED_PROXIMITY_SEGMENTS:
                dir_segments.add(seg)
        # Normalised stem.
        stem = _normalize_filename_stem(filename)
        if stem:
            stems.add(stem)

    return dir_segments, stems


def _score_proximity(
    entity: Entity,
    seed_dir_segments: set[str],
    seed_stems: set[str],
    lexical_set: frozenset[str],
) -> float:
    """Compute a proximity/lexical score for a test entity relative to seed entities."""
    path = entity.source_range.path.replace("\\", "/").lower()
    parts = path.split("/")
    filename = parts[-1] if parts else ""

    score: float = 0.0

    # Stem proximity: test filename stem matches any seed entity filename stem.
    test_stem = _normalize_filename_stem(filename)
    if test_stem and test_stem in seed_stems:
        score += _STEM_MATCH_BONUS

    # Lexical token overlap: query tokens found in the test entity's path.
    path_tokens = frozenset(tokenize_text(path))
    score += len(path_tokens & lexical_set) * _LEXICAL_TOKEN_BONUS

    # Directory segment overlap with seed entity directory paths.
    test_dir_segments = {
        seg for seg in parts[:-1] if seg and seg not in _IGNORED_PROXIMITY_SEGMENTS
    }
    score += len(test_dir_segments & seed_dir_segments) * _PATH_SEGMENT_BONUS

    return score


def _build_proximity_reason(
    entity: Entity,
    seed_stems: set[str],
    lexical_set: frozenset[str],
) -> str:
    """Build a human-readable reason string for a proximity-scored test entity."""
    path = entity.source_range.path.replace("\\", "/").lower()
    parts = path.split("/")
    filename = parts[-1] if parts else ""
    test_stem = _normalize_filename_stem(filename)

    if test_stem and test_stem in seed_stems:
        return f"test branch: filename stem proximity ({test_stem!r})"

    path_tokens = frozenset(tokenize_text(path))
    matched_lex = sorted(path_tokens & lexical_set)
    if matched_lex:
        return f"test branch: lexical token overlap ({', '.join(matched_lex[:3])})"

    return "test branch: test root path proximity"
