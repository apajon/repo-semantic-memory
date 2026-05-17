"""Relation model definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from repo_semantic_memory.model.entity import JsonValue
from repo_semantic_memory.model.evidence import Evidence
from repo_semantic_memory.model.ids import StableId

RelationKind = Literal[
    "contains",
    "imports",
    "inherits",
    "calls",
    "uses",
    "tests",
    "documents",
    "owns",
    "requires",
    "violates",
]
RELATION_KINDS: tuple[RelationKind, ...] = (
    "contains",
    "imports",
    "inherits",
    "calls",
    "uses",
    "tests",
    "documents",
    "owns",
    "requires",
    "violates",
)


@dataclass(frozen=True)
class Relation:
    """Directed typed relation between two entities."""

    source_entity_id: StableId
    target_entity_id: StableId
    kind: RelationKind
    evidence: Evidence | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "source_entity_id": self.source_entity_id.to_dict(),
            "target_entity_id": self.target_entity_id.to_dict(),
            "kind": self.kind,
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Relation:
        """Deserialize from a dictionary payload."""
        metadata_payload = payload.get("metadata", {})
        if not isinstance(metadata_payload, dict):
            raise ValueError("Relation metadata must be a dictionary")
        kind = str(payload["kind"])
        if kind not in RELATION_KINDS:
            raise ValueError(f"Unsupported relation kind: {kind}")

        evidence_payload = payload.get("evidence")
        evidence = None
        if evidence_payload is not None:
            if not isinstance(evidence_payload, dict):
                raise ValueError("Relation evidence must be a dictionary when provided")
            evidence = Evidence.from_dict(evidence_payload)

        return cls(
            source_entity_id=StableId.from_dict(str(payload["source_entity_id"])),
            target_entity_id=StableId.from_dict(str(payload["target_entity_id"])),
            kind=kind,
            evidence=evidence,
            metadata=dict(sorted(cast(dict[str, JsonValue], metadata_payload).items())),
        )
