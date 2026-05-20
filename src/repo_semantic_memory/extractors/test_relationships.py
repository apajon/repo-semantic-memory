"""Deterministic test relationship extractor.

Infers ``tests`` relations between test entities and source entities using
static analysis only.  No test execution, runtime imports, or LLM calls are
performed.

Supported heuristics (in decreasing confidence order):

1. ``direct_import``: test module has an ``imports`` relation targeting a
   source symbol or module (confidence=high).
2. ``file_path``: test filename maps to a source module by path normalisation
   (confidence=high when directory segments align, medium otherwise).
3. ``class_name``: ``TestFoo`` maps to source class ``Foo`` by name stripping
   (confidence=high for exact match, low for token-overlap fallback).
4. ``function_name``: ``test_foo_bar`` maps to a source function/class named
   ``foo_bar`` (confidence=medium for exact match after stripping).
5. ``token_overlap``: shared name-tokens between a test class and a source
   class (confidence=low, minimum ``_MIN_TOKEN_OVERLAP`` shared tokens).

All produced relations carry ``status: inferred`` in their metadata.
Confidence is labelled ``"high"``, ``"medium"``, or ``"low"`` per heuristic.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, cast

from repo_semantic_memory.model import Entity, JsonValue, Relation
from repo_semantic_memory.model.evidence import Evidence

_EXTRACTOR = "test_relationships"

TestConfidence = Literal["high", "medium", "low"]

_CONFIDENCE_FLOAT: dict[str, float] = {
    "high": 0.85,
    "medium": 0.55,
    "low": 0.25,
}

_TEST_PATH_PREFIXES: tuple[str, ...] = ("tests/", "test/")

# Strip "Test" / "test_" prefix from class names.
_TEST_CLASS_RE = re.compile(r"^[Tt]est_?")
# Strip "test_" prefix from function/method names.
_TEST_FUNC_RE = re.compile(r"^test_")
# Split on underscores / hyphens.
_WORD_RE = re.compile(r"[_\-]+")
# Insert word boundary before camelCase uppercase transition.
_CAMEL_RE = re.compile(r"([a-z])([A-Z])")

# Minimum shared token count to accept a token-overlap relation.
_MIN_TOKEN_OVERLAP = 2


# ---------------------------------------------------------------------------
# Source entity lookup tables
# ---------------------------------------------------------------------------


class _SourceIndex:
    """Cross-reference structures built from non-test indexed entities."""

    def __init__(self) -> None:
        # Module entities keyed by qualified_name.
        self.modules_by_qname: dict[str, Entity] = {}
        # Module entities keyed by normalised filename stem (no extension).
        self.modules_by_stem: dict[str, list[Entity]] = {}
        # Class entities keyed by exact class name.
        self.classes_by_name: dict[str, list[Entity]] = {}
        # All non-test entities keyed by qualified_name for symbol matching.
        self.symbols_by_qname: dict[str, Entity] = {}
        # All non-test class entities for token-overlap search.
        self.classes: list[Entity] = []


def _build_source_index(entities: Sequence[Entity]) -> _SourceIndex:
    idx = _SourceIndex()
    for entity in entities:
        if _is_test_entity(entity):
            continue
        idx.symbols_by_qname[entity.qualified_name] = entity
        if entity.kind == "module":
            idx.modules_by_qname[entity.qualified_name] = entity
            stem = _path_stem(entity.source_range.path)
            idx.modules_by_stem.setdefault(stem, []).append(entity)
        elif entity.kind == "class":
            idx.classes_by_name.setdefault(entity.name, []).append(entity)
            idx.classes.append(entity)
    return idx


def _build_import_index(relations: Sequence[Relation]) -> dict[str, list[str]]:
    """Build a map: source_entity_id → list of imported_names from ``imports`` relations."""
    idx: dict[str, list[str]] = {}
    for rel in relations:
        if rel.kind != "imports":
            continue
        imported_name = rel.metadata.get("imported_name")
        if not isinstance(imported_name, str):
            continue
        idx.setdefault(rel.source_entity_id.value, []).append(imported_name)
    return idx


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_test_relationships(
    repo_root: Path | str,
    entities: Sequence[Entity],
    relations: Sequence[Relation] | None = None,
) -> list[Relation]:
    """Infer ``tests`` relations between test entities and source entities.

    Examines entity names, paths, and existing ``imports`` relations to
    produce ``tests`` relations with explicit confidence labels and source
    provenance.  No test files are executed and no imports are performed at
    runtime.

    Args:
        repo_root: Repository root directory (validated as an existing
            directory; not traversed by this function).
        entities: All indexed entities to cross-reference.
        relations: Existing relations used for import-based heuristics.
            Pass the combined output of ``index_python_path`` and
            ``index_python_exports`` for best coverage.

    Returns:
        Sorted list of inferred ``tests`` Relation objects.
    """
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")

    source_index = _build_source_index(entities)
    import_index = _build_import_index(relations or [])

    seen: set[tuple[str, str]] = set()
    result: list[Relation] = []

    for entity in sorted(entities, key=lambda e: e.id.value):
        if not _is_test_entity(entity):
            continue

        rels: list[Relation] = []
        if entity.kind == "module":
            rels += _import_based_relations(entity, import_index, source_index)
            rels += _path_mapping_relations(entity, source_index)
        elif entity.kind == "class":
            rels += _class_name_relations(entity, source_index)
        elif entity.kind in ("function", "method"):
            if _is_test_function_name(entity.name):
                rels += _function_name_relations(entity, source_index)

        for rel in rels:
            key = (rel.source_entity_id.value, rel.target_entity_id.value)
            if key not in seen:
                seen.add(key)
                result.append(rel)

    return _sort_relations(result)


# ---------------------------------------------------------------------------
# Heuristic extractors
# ---------------------------------------------------------------------------


def _import_based_relations(
    test_entity: Entity,
    import_index: dict[str, list[str]],
    source_index: _SourceIndex,
) -> list[Relation]:
    """High-confidence: test module imports source symbol or module."""
    imported_names = import_index.get(test_entity.id.value, [])
    result: list[Relation] = []
    for name in sorted(imported_names):
        # Try exact qualified_name match first.
        target = source_index.symbols_by_qname.get(name)
        if target is None and "." in name:
            # Fall back to module-level match: "pkg.Symbol" → "pkg".
            module_qname = name.rsplit(".", maxsplit=1)[0]
            target = source_index.modules_by_qname.get(module_qname)
        if target is None:
            continue
        result.append(
            _make_relation(
                source=test_entity,
                target=target,
                heuristic="direct_import",
                confidence="high",
                matched_terms=[name],
                note=f"test imports source: {name}",
            )
        )
    return result


def _path_mapping_relations(
    test_entity: Entity,
    source_index: _SourceIndex,
) -> list[Relation]:
    """High/medium-confidence: test_foo.py maps to foo.py by path normalisation."""
    test_path = test_entity.source_range.path.replace("\\", "/")

    # Strip the leading test-directory prefix.
    relative = test_path
    for prefix in _TEST_PATH_PREFIXES:
        if relative.startswith(prefix):
            relative = relative[len(prefix) :]
            break

    # Split into directory portion and filename.
    if "/" in relative:
        dir_part, filename = relative.rsplit("/", maxsplit=1)
    else:
        dir_part, filename = "", relative

    # Strip test_ / test prefix from filename.
    if filename.startswith("test_"):
        source_filename = filename[5:]
    elif filename.lower().startswith("test"):
        source_filename = filename[4:]
    else:
        return []

    stem = _path_stem(source_filename)
    if not stem:
        return []

    candidates = source_index.modules_by_stem.get(stem, [])
    result: list[Relation] = []
    for candidate in sorted(candidates, key=lambda e: e.id.value):
        cand_path = candidate.source_range.path.replace("\\", "/")
        cand_dir = cand_path.rsplit("/", maxsplit=1)[0] if "/" in cand_path else ""
        confidence: TestConfidence = "high" if _dirs_align(dir_part, cand_dir) else "medium"
        result.append(
            _make_relation(
                source=test_entity,
                target=candidate,
                heuristic="file_path",
                confidence=confidence,
                matched_terms=[stem],
                note=f"test path {test_path!r} maps to source {cand_path!r}",
            )
        )
    return result


def _class_name_relations(
    test_entity: Entity,
    source_index: _SourceIndex,
) -> list[Relation]:
    """TestFoo → Foo exact match (high); token overlap fallback (low)."""
    class_name = test_entity.name
    stripped = _TEST_CLASS_RE.sub("", class_name)
    if not stripped or stripped == class_name:
        return []

    # Exact class name match → high confidence.
    exact_candidates = source_index.classes_by_name.get(stripped, [])
    if exact_candidates:
        return [
            _make_relation(
                source=test_entity,
                target=candidate,
                heuristic="class_name",
                confidence="high",
                matched_terms=[stripped],
                note=f"test class {class_name!r} \u2192 source class {stripped!r}",
            )
            for candidate in sorted(exact_candidates, key=lambda e: e.id.value)
        ]

    # Token-overlap fallback → low confidence.
    test_tokens = set(_tokenize_name(stripped))
    if len(test_tokens) < _MIN_TOKEN_OVERLAP:
        return []
    result: list[Relation] = []
    for cls_entity in sorted(source_index.classes, key=lambda e: e.id.value):
        src_tokens = set(_tokenize_name(cls_entity.name))
        overlap = test_tokens & src_tokens
        if len(overlap) >= _MIN_TOKEN_OVERLAP:
            result.append(
                _make_relation(
                    source=test_entity,
                    target=cls_entity,
                    heuristic="token_overlap",
                    confidence="low",
                    matched_terms=sorted(overlap),
                    note=f"token overlap between {class_name!r} and {cls_entity.name!r}",
                )
            )
    return result


def _function_name_relations(
    test_entity: Entity,
    source_index: _SourceIndex,
) -> list[Relation]:
    """Medium-confidence: test_foo_bar → source symbol foo_bar (exact name)."""
    func_name = test_entity.name
    stripped = _TEST_FUNC_RE.sub("", func_name)
    if not stripped or stripped == func_name:
        return []

    result: list[Relation] = []
    for entity in sorted(source_index.symbols_by_qname.values(), key=lambda e: e.id.value):
        if entity.kind not in ("function", "method", "class"):
            continue
        if entity.name.lower() == stripped.lower():
            result.append(
                _make_relation(
                    source=test_entity,
                    target=entity,
                    heuristic="function_name",
                    confidence="medium",
                    matched_terms=[stripped],
                    note=f"test function {func_name!r} \u2192 source symbol {stripped!r}",
                )
            )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_test_entity(entity: Entity) -> bool:
    """Return True when the entity lives in a recognised test directory."""
    path = entity.source_range.path.replace("\\", "/")
    return any(path.startswith(prefix) for prefix in _TEST_PATH_PREFIXES)


def _is_test_function_name(name: str) -> bool:
    return _TEST_FUNC_RE.match(name) is not None


def _dirs_align(test_dir: str, source_dir: str) -> bool:
    """True when test and source directory paths share at least one segment."""
    if not test_dir and not source_dir:
        return True
    test_parts = {p for p in test_dir.split("/") if p}
    source_parts = {p for p in source_dir.split("/") if p}
    if not test_parts or not source_parts:
        return False
    return bool(test_parts & source_parts)


def _path_stem(path: str) -> str:
    """Normalised filename stem: no extension, lowercase."""
    return Path(path).stem.lower()


def _tokenize_name(name: str) -> list[str]:
    """Split a symbol name into lowercase tokens on underscores and camelCase."""
    bounded = _CAMEL_RE.sub(r"\1_\2", name)
    parts = _WORD_RE.split(bounded.lower())
    return [p for p in parts if p]


def _make_relation(
    *,
    source: Entity,
    target: Entity,
    heuristic: str,
    confidence: TestConfidence,
    matched_terms: list[str],
    note: str,
) -> Relation:
    evidence = Evidence(
        source_range=source.source_range,
        extractor=_EXTRACTOR,
        confidence=_CONFIDENCE_FLOAT[confidence],
        note=note,
    )
    metadata: dict[str, JsonValue] = {
        "confidence": confidence,
        "heuristic": heuristic,
        "matched_terms": cast(JsonValue, sorted(set(matched_terms))),
        "status": "inferred",
    }
    return Relation(
        source_entity_id=source.id,
        target_entity_id=target.id,
        kind="tests",
        evidence=evidence,
        metadata=metadata,
    )


def _sort_relations(relations: list[Relation]) -> list[Relation]:
    return sorted(
        relations,
        key=lambda r: (
            r.kind,
            r.source_entity_id.value,
            r.target_entity_id.value,
            tuple(sorted((k, str(v)) for k, v in r.metadata.items())),
        ),
    )
