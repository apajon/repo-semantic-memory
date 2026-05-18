"""Project invariant model with explicit status and provenance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from repo_semantic_memory.model.evidence import Evidence
from repo_semantic_memory.model.ids import StableId

InvariantSeverity = Literal["info", "warning", "error"]
INVARIANT_SEVERITIES: tuple[InvariantSeverity, ...] = ("info", "warning", "error")
InvariantStatus = Literal["active", "draft", "deprecated"]
INVARIANT_STATUSES: tuple[InvariantStatus, ...] = ("active", "draft", "deprecated")


@dataclass(frozen=True)
class Invariant:
    """Declarative project invariant with evidence and lifecycle status."""

    id: str | StableId
    name: str
    description: str
    scope: str
    severity: InvariantSeverity
    status: InvariantStatus
    evidence: tuple[Evidence, ...] = ()
    validation_rule: str | None = None
    related_entity_ids: tuple[str | StableId, ...] = ()
    origin_note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "id",
            _normalize_text(self.id, field_name="Invariant id"),
        )
        object.__setattr__(
            self,
            "name",
            _normalize_text(self.name, field_name="Invariant name"),
        )
        object.__setattr__(
            self,
            "description",
            _normalize_text(self.description, field_name="Invariant description"),
        )
        object.__setattr__(
            self,
            "scope",
            _normalize_text(self.scope, field_name="Invariant scope"),
        )

        if self.severity not in INVARIANT_SEVERITIES:
            raise ValueError(f"Unsupported invariant severity: {self.severity}")
        if self.status not in INVARIANT_STATUSES:
            raise ValueError(f"Unsupported invariant status: {self.status}")

        if self.validation_rule is not None and not self.validation_rule.strip():
            raise ValueError("Invariant validation_rule must not be blank when provided")
        if self.origin_note is not None and not self.origin_note.strip():
            raise ValueError("Invariant origin_note must not be blank when provided")

        related = sorted(
            {
                _normalize_text(item, field_name="Invariant related entity id")
                for item in self.related_entity_ids
            }
        )
        object.__setattr__(self, "related_entity_ids", tuple(related))
        _validate_invariant_provenance(self)

    def to_dict(self) -> dict[str, object]:
        """Serialize invariant to deterministic JSON-friendly payload."""
        payload: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "severity": self.severity,
            "status": self.status,
            "evidence": [item.to_dict() for item in self.evidence],
            "related_entity_ids": list(self.related_entity_ids),
        }
        if self.validation_rule is not None:
            payload["validation_rule"] = self.validation_rule
        if self.origin_note is not None:
            payload["origin_note"] = self.origin_note
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Invariant:
        """Deserialize invariant payload from dictionary."""
        evidence_payload = payload.get("evidence", [])
        if not isinstance(evidence_payload, list):
            raise ValueError("Invariant evidence must be a list")
        evidence = []
        for item in evidence_payload:
            if not isinstance(item, dict):
                raise ValueError("Invariant evidence items must be dictionaries")
            evidence.append(Evidence.from_dict(item))

        related_payload = payload.get("related_entity_ids", [])
        if not isinstance(related_payload, list):
            raise ValueError("Invariant related_entity_ids must be a list")
        related_entity_ids = tuple(str(item) for item in related_payload)

        return cls(
            id=payload["id"],
            name=str(payload["name"]),
            description=str(payload["description"]),
            scope=str(payload["scope"]),
            severity=str(payload["severity"]),
            status=str(payload["status"]),
            evidence=tuple(evidence),
            validation_rule=(
                str(payload["validation_rule"]) if payload.get("validation_rule") is not None else None
            ),
            related_entity_ids=related_entity_ids,
            origin_note=str(payload["origin_note"]) if payload.get("origin_note") is not None else None,
        )


def _normalize_text(value: str | StableId, *, field_name: str) -> str:
    if isinstance(value, StableId):
        text = value.value
    else:
        text = str(value)
    normalized = text.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _validate_invariant_provenance(invariant: Invariant) -> None:
    has_evidence = len(invariant.evidence) > 0
    has_origin = invariant.origin_note is not None
    if invariant.status == "active" and not (has_evidence or has_origin):
        raise ValueError("Active invariant requires evidence or origin_note")
