"""Standalone invariants YAML import/export tests."""

from __future__ import annotations

import json
from pathlib import Path

from repo_semantic_memory.memory import (
    InvariantsDocument,
    export_invariants_yaml,
    import_invariants_yaml,
)
from repo_semantic_memory.model import Claim, Evidence, Invariant, SourceRange


def _evidence() -> Evidence:
    return Evidence(
        source_range=SourceRange(path="docs/rules.md", start_line=5, end_line=6),
        extractor="docs-parser",
        confidence=0.75,
    )


def _document() -> InvariantsDocument:
    claim = Claim(
        id="claim:001",
        subject="python:repo:indexer",
        predicate="preserves_order",
        object="entity:list_entities",
        status="confirmed",
        evidence=(_evidence(),),
        confidence=0.75,
    )
    invariant = Invariant(
        id="invariant:001",
        name="DeterministicEntityOrder",
        description="Entities must remain sorted by stable id.",
        scope="repository",
        severity="warning",
        status="active",
        evidence=(_evidence(),),
        validation_rule="entities_ordered_by_stable_id",
        related_entity_ids=("python:repo:list_entities",),
    )
    return InvariantsDocument(claims=(claim,), invariants=(invariant,))


def test_invariants_yaml_roundtrip(tmp_path: Path) -> None:
    document = _document()
    target = tmp_path / "invariants.yaml"
    export_invariants_yaml(out_path=target, claims=document.claims, invariants=document.invariants)

    imported = import_invariants_yaml(target)
    assert imported == document


def test_invariants_document_to_yaml_is_json_formatted_yaml() -> None:
    payload = json.loads(_document().to_yaml())
    assert "claims" in payload
    assert "invariants" in payload


def test_export_default_document_has_no_hardcoded_invariants(tmp_path: Path) -> None:
    target = tmp_path / "invariants.yaml"
    export_invariants_yaml(out_path=target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["claims"] == []
    assert payload["invariants"] == []
