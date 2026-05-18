"""Semantic component model tests."""

from __future__ import annotations

import pytest

from repo_semantic_memory.model import Evidence, SemanticComponent, SourceRange, StableId


def _evidence() -> Evidence:
    return Evidence(
        source_range=SourceRange(path="src/pkg/module.py", start_line=1, end_line=1),
        extractor="unit-test",
        confidence=0.7,
    )


def test_component_serialization_round_trip() -> None:
    component = SemanticComponent(
        component_type="PublicAPI",
        entity_id=StableId("python:pkg:init_export"),
        properties={"heuristic": "__init___export_relation"},
        evidence=(_evidence(),),
        confidence=0.7,
        status="inferred",
        inference_note="heuristic only",
    )

    restored = SemanticComponent.from_dict(component.to_dict())
    assert restored == component


def test_confirmed_component_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        SemanticComponent(
            component_type="PublicAPI",
            entity_id=StableId("python:pkg:api"),
            status="confirmed",
            confidence=0.9,
        )


def test_inferred_component_requires_evidence_or_note() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        SemanticComponent(
            component_type="LifecycleManaged",
            entity_id=StableId("python:pkg:lifecycle"),
            status="inferred",
            confidence=0.5,
        )


def test_needs_review_allows_missing_evidence() -> None:
    component = SemanticComponent(
        component_type="ErrorBoundary",
        entity_id=StableId("python:pkg:error_boundary"),
        status="needs_review",
        confidence=0.2,
    )
    assert component.evidence == ()


def test_component_properties_must_be_json_serializable() -> None:
    with pytest.raises(ValueError, match="JSON-serializable"):
        SemanticComponent(
            component_type="ConfigurationSurface",
            entity_id=StableId("python:pkg:cfg"),
            properties={"bad": {1, 2, 3}},
            evidence=(_evidence(),),
            status="inferred",
            confidence=0.6,
        )
