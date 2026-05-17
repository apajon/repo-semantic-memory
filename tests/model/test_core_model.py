"""Core semantic model tests."""

from __future__ import annotations

import pytest

from repo_semantic_memory.model import Entity, Evidence, Relation, SourceRange, StableId


def test_stable_id_normalization_is_deterministic() -> None:
    stable_id = StableId.from_parts([" Module  Name ", "Class@Name", "Method Name  "])
    assert stable_id.value == "module-name:class-name:method-name"


def test_stable_id_rejects_empty_normalized_part() -> None:
    with pytest.raises(ValueError, match="at least one valid character"):
        StableId.from_parts(["   "])


def test_stable_id_avoids_obvious_part_boundary_collisions() -> None:
    left = StableId.from_parts(["pkg-class", "method"])
    right = StableId.from_parts(["pkg", "class-method"])
    assert left != right


def test_source_range_valid_construction() -> None:
    source = SourceRange(
        path="src/pkg/module.py", start_line=2, end_line=5, start_col=1, end_col=10
    )
    assert source.path == "src/pkg/module.py"
    assert source.start_line == 2
    assert source.end_line == 5


def test_source_range_allows_cross_line_end_col_less_than_start_col() -> None:
    source = SourceRange(
        path="src/pkg/module.py", start_line=2, end_line=3, start_col=20, end_col=5
    )
    assert source.start_line == 2
    assert source.end_line == 3


def test_source_range_rejects_end_col_before_start_col_on_same_line() -> None:
    with pytest.raises(ValueError, match="end_col must be >= start_col on same line"):
        SourceRange(
            path="src/pkg/module.py",
            start_line=2,
            end_line=2,
            start_col=20,
            end_col=5,
        )


def test_evidence_confidence_validation() -> None:
    source = SourceRange(path="README.md", start_line=1, end_line=2)
    with pytest.raises(ValueError, match="between 0 and 1"):
        Evidence(source_range=source, extractor="doc-parser", confidence=1.1)


def test_evidence_requires_non_empty_extractor() -> None:
    source = SourceRange(path="README.md", start_line=1, end_line=2)
    with pytest.raises(ValueError, match="must not be empty"):
        Evidence(source_range=source, extractor="", confidence=0.5)


def test_entity_creation() -> None:
    source = SourceRange(path="src/pkg/module.py", start_line=10, end_line=20)
    entity = Entity(
        id=StableId.from_parts(["module", "pkg.module", "ClassName"]),
        kind="class",
        name="ClassName",
        qualified_name="pkg.module.ClassName",
        source_range=source,
        metadata={"visibility": "public"},
    )

    assert entity.kind == "class"
    assert entity.id.value == "module:pkg.module:classname"
    assert entity.metadata["visibility"] == "public"


def test_entity_metadata_is_json_serializable() -> None:
    source = SourceRange(path="src/pkg/module.py", start_line=10, end_line=20)
    with pytest.raises(ValueError, match="JSON-serializable"):
        Entity(
            id=StableId.from_parts(["module", "pkg.module", "ClassName"]),
            kind="class",
            name="ClassName",
            qualified_name="pkg.module.ClassName",
            source_range=source,
            metadata={"bad": {1, 2, 3}},
        )


def test_entity_accepts_json_serializable_metadata() -> None:
    source = SourceRange(path="src/pkg/module.py", start_line=10, end_line=20)
    entity = Entity(
        id=StableId.from_parts(["module", "pkg.module", "ClassName"]),
        kind="class",
        name="ClassName",
        qualified_name="pkg.module.ClassName",
        source_range=source,
        metadata={"tags": ["core", "typed"], "score": 1.0, "nested": {"ok": True}},
    )
    assert entity.metadata["nested"] == {"ok": True}


def test_entity_to_dict_sorts_metadata_keys() -> None:
    source = SourceRange(path="src/pkg/module.py", start_line=10, end_line=20)
    entity = Entity(
        id=StableId.from_parts(["module", "pkg.module", "ClassName"]),
        kind="class",
        name="ClassName",
        qualified_name="pkg.module.ClassName",
        source_range=source,
        metadata={"z": "last", "a": "first"},
    )
    assert list(entity.to_dict()["metadata"]) == ["a", "z"]


def test_relation_creation() -> None:
    source = SourceRange(path="src/pkg/module.py", start_line=12, end_line=14)
    evidence = Evidence(source_range=source, extractor="ast-python", confidence=0.95)

    relation = Relation(
        source_entity_id=StableId.from_parts(["function", "pkg.module.a"]),
        target_entity_id=StableId.from_parts(["function", "pkg.module.b"]),
        kind="calls",
        evidence=evidence,
        metadata={"line": 12},
    )

    assert relation.kind == "calls"
    assert relation.evidence is not None
    assert relation.evidence.confidence == 0.95


def test_relation_metadata_is_json_serializable() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        Relation(
            source_entity_id=StableId.from_parts(["function", "pkg.module.a"]),
            target_entity_id=StableId.from_parts(["function", "pkg.module.b"]),
            kind="calls",
            metadata={"bad": object()},
        )


def test_relation_accepts_json_serializable_metadata() -> None:
    relation = Relation(
        source_entity_id=StableId.from_parts(["function", "pkg.module.a"]),
        target_entity_id=StableId.from_parts(["function", "pkg.module.b"]),
        kind="calls",
        metadata={"weight": 2, "details": {"dynamic": False}, "paths": ["a", "b"]},
    )
    assert relation.metadata["weight"] == 2
