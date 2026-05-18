"""Semantic component model definitions for ECS-style semantic annotations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from repo_semantic_memory.model.entity import JsonValue, validate_json_metadata
from repo_semantic_memory.model.evidence import Evidence
from repo_semantic_memory.model.ids import StableId

SemanticComponentType = Literal[
    "PublicAPI",
    "LifecycleManaged",
    "ResourceOwner",
    "ActivationGated",
    "TestTarget",
    "TestFile",
    "DocumentationNode",
    "ConfigurationSurface",
    "ErrorBoundary",
    "ExternalIntegration",
    "ROSLikeIntegration",
]
SEMANTIC_COMPONENT_TYPES: tuple[SemanticComponentType, ...] = (
    "PublicAPI",
    "LifecycleManaged",
    "ResourceOwner",
    "ActivationGated",
    "TestTarget",
    "TestFile",
    "DocumentationNode",
    "ConfigurationSurface",
    "ErrorBoundary",
    "ExternalIntegration",
    "ROSLikeIntegration",
)
SemanticComponentStatus = Literal["confirmed", "inferred", "needs_review"]
SEMANTIC_COMPONENT_STATUSES: tuple[SemanticComponentStatus, ...] = (
    "confirmed",
    "inferred",
    "needs_review",
)


@dataclass(frozen=True)
class SemanticComponent:
    """Semantic property attached to an entity with explicit provenance constraints."""

    component_type: SemanticComponentType
    entity_id: StableId
    properties: dict[str, JsonValue] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()
    confidence: float = 0.0
    status: SemanticComponentStatus = "needs_review"
    inference_note: str | None = None

    def __post_init__(self) -> None:
        if self.component_type not in SEMANTIC_COMPONENT_TYPES:
            raise ValueError(f"Unsupported semantic component type: {self.component_type}")
        if self.status not in SEMANTIC_COMPONENT_STATUSES:
            raise ValueError(f"Unsupported semantic component status: {self.status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("SemanticComponent confidence must be between 0 and 1")
        if self.inference_note is not None and not self.inference_note.strip():
            raise ValueError("SemanticComponent inference_note must not be blank when provided")

        validate_json_metadata(self.properties, owner="SemanticComponent")
        _validate_component_provenance(self)

    def to_dict(self) -> dict[str, object]:
        """Serialize to deterministic JSON-friendly dictionary output."""
        payload: dict[str, object] = {
            "component_type": self.component_type,
            "entity_id": self.entity_id.to_dict(),
            "properties": dict(sorted(self.properties.items())),
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
            "status": self.status,
        }
        if self.inference_note is not None:
            payload["inference_note"] = self.inference_note
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SemanticComponent:
        """Deserialize from dictionary payload."""
        component_type = str(payload.get("component_type"))
        if component_type not in SEMANTIC_COMPONENT_TYPES:
            raise ValueError(f"Unsupported semantic component type: {component_type}")
        status = str(payload.get("status"))
        if status not in SEMANTIC_COMPONENT_STATUSES:
            raise ValueError(f"Unsupported semantic component status: {status}")

        entity_id = payload.get("entity_id")
        if not isinstance(entity_id, str):
            raise ValueError("SemanticComponent entity_id must be a string")
        properties_payload = payload.get("properties", {})
        if not isinstance(properties_payload, dict):
            raise ValueError("SemanticComponent properties must be a dictionary")
        evidence_payload = payload.get("evidence", [])
        if not isinstance(evidence_payload, list):
            raise ValueError("SemanticComponent evidence must be a list")

        evidence: list[Evidence] = []
        for item in evidence_payload:
            if not isinstance(item, dict):
                raise ValueError("SemanticComponent evidence items must be dictionaries")
            evidence.append(Evidence.from_dict(item))

        inference_note_payload = payload.get("inference_note")
        inference_note = str(inference_note_payload) if inference_note_payload is not None else None
        confidence_payload = payload.get("confidence", 0.0)
        confidence = float(confidence_payload)

        return cls(
            component_type=cast(SemanticComponentType, component_type),
            entity_id=StableId.from_dict(entity_id),
            properties=dict(sorted(cast(dict[str, JsonValue], properties_payload).items())),
            evidence=tuple(evidence),
            confidence=confidence,
            status=cast(SemanticComponentStatus, status),
            inference_note=inference_note,
        )


def _validate_component_provenance(component: SemanticComponent) -> None:
    has_evidence = len(component.evidence) > 0
    has_note = component.inference_note is not None

    if not has_evidence and component.status != "needs_review":
        raise ValueError(
            "SemanticComponent requires evidence unless status is needs_review"
        )
    if component.status == "confirmed" and not has_evidence:
        raise ValueError("Confirmed SemanticComponent requires evidence")
    if component.status == "inferred" and not (has_evidence or has_note):
        raise ValueError(
            "Inferred SemanticComponent requires evidence or inference_note"
        )
