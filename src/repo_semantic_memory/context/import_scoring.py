"""Deterministic import classification and lightweight weighting."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from repo_semantic_memory.model import Entity, Relation

ImportClass = Literal[
    "local_package",
    "relative_local",
    "test_local",
    "third_party_common",
    "third_party_unknown",
    "stdlib",
    "unknown",
]

_COMMON_THIRD_PARTY_TOP_LEVELS: frozenset[str] = frozenset(
    {
        "click",
        "mypy",
        "numpy",
        "pandas",
        "pydantic",
        "pytest",
        "ruff",
        "typer",
    }
)
_IGNORED_LOCAL_ROOTS: frozenset[str] = frozenset(
    {
        "",
        "__main__",
        "docs",
        "examples",
        "test",
        "tests",
    }
)
_TEST_PATH_PREFIXES: tuple[str, ...] = ("tests/", "test/")
_SOURCE_PATH_PREFIXES: tuple[str, ...] = ("src/",)

IMPORT_CLASS_WEIGHTS: dict[ImportClass, float] = {
    "relative_local": 0.55,
    "local_package": 0.55,
    "test_local": 0.50,
    "third_party_unknown": 0.12,
    "unknown": 0.12,
    "third_party_common": 0.05,
    "stdlib": 0.0,
}


@dataclass(frozen=True)
class ImportScoringContext:
    """Repository-local import classification inputs."""

    first_party_roots: frozenset[str]
    qualified_name_to_entity_ids: Mapping[str, tuple[str, ...]]


def build_import_scoring_context(entities: Sequence[Entity]) -> ImportScoringContext:
    """Infer first-party roots and import target candidates from indexed entities."""
    roots: set[str] = set()
    qname_to_ids: dict[str, list[str]] = {}
    for entity in sorted(entities, key=lambda item: item.id.value):
        qname = entity.qualified_name.strip()
        if qname:
            qname_to_ids.setdefault(qname, []).append(entity.id.value)

        if entity.kind != "module":
            continue
        root = _local_root_for_entity(entity)
        if root:
            roots.add(root)

    return ImportScoringContext(
        first_party_roots=frozenset(sorted(roots)),
        qualified_name_to_entity_ids={
            qname: tuple(dict.fromkeys(ids)) for qname, ids in sorted(qname_to_ids.items())
        },
    )


def classify_import(
    imported_name: str | None,
    *,
    source_path: str = "",
    context: ImportScoringContext | None = None,
) -> ImportClass:
    """Classify an import name using deterministic repository-local signals."""
    if not imported_name:
        return "unknown"

    normalized = imported_name.strip()
    if not normalized:
        return "unknown"

    source_is_test = _is_test_path(source_path)
    if normalized.startswith("."):
        return "test_local" if source_is_test else "relative_local"

    top_level = normalized.split(".", 1)[0]
    if not top_level:
        return "unknown"

    first_party_roots = context.first_party_roots if context is not None else frozenset()
    if top_level in first_party_roots:
        return "test_local" if source_is_test else "local_package"
    if top_level in sys.stdlib_module_names:
        return "stdlib"
    if top_level in _COMMON_THIRD_PARTY_TOP_LEVELS:
        return "third_party_common"
    return "third_party_unknown"


def classify_import_relation(
    relation: Relation,
    *,
    entity_by_id: Mapping[str, Entity] | None = None,
    context: ImportScoringContext | None = None,
) -> ImportClass:
    """Classify an ``imports`` relation from its metadata and source entity path."""
    imported_name = relation.metadata.get("imported_name")
    if not isinstance(imported_name, str):
        return "unknown"
    source_path = ""
    if entity_by_id is not None:
        source = entity_by_id.get(relation.source_entity_id.value)
        if source is not None:
            source_path = source.source_range.path
    return classify_import(imported_name, source_path=source_path, context=context)


def import_relation_weight(
    relation: Relation,
    *,
    entity_by_id: Mapping[str, Entity] | None = None,
    context: ImportScoringContext | None = None,
) -> float:
    """Return the bounded graph weight for an import relation."""
    import_class = classify_import_relation(
        relation,
        entity_by_id=entity_by_id,
        context=context,
    )
    return IMPORT_CLASS_WEIGHTS[import_class]


def import_class_priority(import_class: ImportClass) -> int:
    """Return relation-ordering priority for import classes (lower is better)."""
    priorities: dict[ImportClass, int] = {
        "relative_local": 0,
        "local_package": 0,
        "test_local": 1,
        "third_party_unknown": 2,
        "unknown": 2,
        "third_party_common": 3,
        "stdlib": 4,
    }
    return priorities[import_class]


def resolve_import_target_ids(
    relation: Relation,
    *,
    context: ImportScoringContext,
) -> tuple[str, ...]:
    """Resolve an import relation to indexed entity IDs by qualified name only."""
    imported_name = relation.metadata.get("imported_name")
    if not isinstance(imported_name, str) or not imported_name:
        return ()
    if imported_name.startswith("."):
        return ()
    return context.qualified_name_to_entity_ids.get(imported_name, ())


def _local_root_for_entity(entity: Entity) -> str:
    path = entity.source_range.path.replace("\\", "/")
    qname = entity.qualified_name.strip()
    if not path or not qname or _is_test_path(path):
        return ""
    if path.startswith(("docs/", "examples/")):
        return ""
    top_level = qname.split(".", 1)[0]
    if top_level in _IGNORED_LOCAL_ROOTS:
        return ""
    if path.startswith(_SOURCE_PATH_PREFIXES):
        return _path_source_root(path) or top_level
    if path.endswith("__init__.py") or "/" not in path:
        return top_level
    return top_level


def _path_source_root(path: str) -> str:
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != "src":
        return ""
    candidate = parts[1]
    if candidate in _IGNORED_LOCAL_ROOTS or "." in candidate:
        return ""
    return candidate


def _is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    return normalized.startswith(_TEST_PATH_PREFIXES)
