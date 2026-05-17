"""Core semantic model tests."""

from __future__ import annotations

import pytest

from repo_semantic_memory.model import Entity, Evidence, Relation, SourceRange, StableId


def test_stable_id_normalization_is_deterministic() -> None:
    stable_id = StableId.from_parts([" Module  Name ", "Class@Name", "Method Name  "])
    assert stable_id.value == "module-name:class-name:method-name"


def test_source_range_valid_construction() -> None:
    source = SourceRange(
        path="src/pkg/module.py", start_line=2, end_line=5, start_col=1, end_col=10
    )
    assert source.path == "src/pkg/module.py"
    assert source.start_line == 2
    assert source.end_line == 5


def test_evidence_confidence_validation() -> None:
    source = SourceRange(path="README.md", start_line=1, end_line=2)
    with pytest.raises(ValueError, match="between 0 and 1"):
        Evidence(source_range=source, extractor="doc-parser", confidence=1.1)


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
