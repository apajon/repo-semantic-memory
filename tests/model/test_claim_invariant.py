"""Claim and invariant model tests."""

from __future__ import annotations

import pytest

from repo_semantic_memory.model import Claim, Evidence, Invariant, SourceRange, StableId


def _evidence() -> Evidence:
    return Evidence(
        source_range=SourceRange(path="README.md", start_line=1, end_line=2),
        extractor="unit-test",
        confidence=0.8,
    )


def test_confirmed_claim_without_evidence_is_invalid() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        Claim(
            id="claim:1",
            subject="python:pkg:module",
            predicate="implements",
            object="concept:service",
            status="confirmed",
            confidence=0.9,
        )


def test_needs_review_claim_without_evidence_is_valid() -> None:
    claim = Claim(
        id=StableId("claim:needs-review"),
        subject="python:pkg:module",
        predicate="might_own",
        object="resource:cache",
        status="needs_review",
        confidence=0.2,
    )
    assert claim.evidence == ()


def test_inferred_claim_without_evidence_or_note_is_invalid() -> None:
    with pytest.raises(ValueError, match="requires evidence or note"):
        Claim(
            id="claim:inferred",
            subject="python:pkg:module",
            predicate="depends_on",
            object="external:db",
            status="inferred",
            confidence=0.5,
        )


def test_rejected_claim_preserves_rejection_note() -> None:
    claim = Claim(
        id="claim:rejected",
        subject="python:pkg:module",
        predicate="is_runtime_singleton",
        object="concept:singleton",
        status="rejected",
        confidence=0.1,
        note="Rejected after code review; no runtime singleton evidence.",
    )
    assert claim.note is not None
    assert "Rejected" in claim.note


def test_active_invariant_requires_evidence_or_origin_note() -> None:
    with pytest.raises(ValueError, match="requires evidence or origin_note"):
        Invariant(
            id="invariant:active",
            name="NoMutationInIndexer",
            description="Indexer should not mutate input payloads.",
            scope="repository",
            severity="warning",
            status="active",
        )


def test_invariant_yaml_friendly_serialization() -> None:
    invariant = Invariant(
        id="invariant:serialization",
        name="DeterministicSortOrder",
        description="Output ordering should be deterministic.",
        scope="repository",
        severity="info",
        status="draft",
        evidence=(_evidence(),),
        validation_rule="ordered_by_stable_id",
        related_entity_ids=(StableId("python:pkg:one"), "python:pkg:two"),
    )
    restored = Invariant.from_dict(invariant.to_dict())
    assert restored == invariant
