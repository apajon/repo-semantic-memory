"""Semantic claim model with provenance and uncertainty constraints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from repo_semantic_memory.model.evidence import Evidence
from repo_semantic_memory.model.ids import StableId

ClaimStatus = Literal["confirmed", "inferred", "needs_review", "rejected"]
CLAIM_STATUSES: tuple[ClaimStatus, ...] = ("confirmed", "inferred", "needs_review", "rejected")


@dataclass(frozen=True)
class Claim:
    """Explicit semantic claim attached to repository entities or free-form subjects."""

    id: str | StableId
    subject: str | StableId
    predicate: str
    object: str | StableId
    status: ClaimStatus
    evidence: tuple[Evidence, ...] = ()
    confidence: float = 0.0
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalize_identifier(self.id, field_name="Claim id"))
        object.__setattr__(self, "subject", _normalize_identifier(self.subject, field_name="Claim subject"))
        object.__setattr__(self, "object", _normalize_identifier(self.object, field_name="Claim object"))

        predicate = self.predicate.strip()
        if not predicate:
            raise ValueError("Claim predicate must not be empty")
        object.__setattr__(self, "predicate", predicate)

        if self.status not in CLAIM_STATUSES:
            raise ValueError(f"Unsupported claim status: {self.status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Claim confidence must be between 0 and 1")
        if self.note is not None and not self.note.strip():
            raise ValueError("Claim note must not be blank when provided")

        _validate_claim_provenance(self)

    def to_dict(self) -> dict[str, object]:
        """Serialize claim into deterministic JSON-friendly payload."""
        payload: dict[str, object] = {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "status": self.status,
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
        }
        if self.note is not None:
            payload["note"] = self.note
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Claim:
        """Deserialize claim payload from dictionary."""
        evidence_payload = payload.get("evidence", [])
        if not isinstance(evidence_payload, list):
            raise ValueError("Claim evidence must be a list")

        evidence: list[Evidence] = []
        for item in evidence_payload:
            if not isinstance(item, dict):
                raise ValueError("Claim evidence items must be dictionaries")
            evidence.append(Evidence.from_dict(item))

        return cls(
            id=payload["id"],
            subject=payload["subject"],
            predicate=str(payload["predicate"]),
            object=payload["object"],
            status=str(payload["status"]),
            evidence=tuple(evidence),
            confidence=float(payload.get("confidence", 0.0)),
            note=str(payload["note"]) if payload.get("note") is not None else None,
        )


def _normalize_identifier(value: str | StableId, *, field_name: str) -> str:
    if isinstance(value, StableId):
        text = value.value
    else:
        text = str(value)
    normalized = text.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _validate_claim_provenance(claim: Claim) -> None:
    has_evidence = len(claim.evidence) > 0
    has_note = claim.note is not None

    if claim.status == "confirmed" and not has_evidence:
        raise ValueError("Confirmed claim requires evidence")
    if claim.status == "inferred" and not (has_evidence or has_note):
        raise ValueError("Inferred claim requires evidence or note")
    if claim.status == "rejected" and not has_note:
        raise ValueError("Rejected claim must preserve rejection note")
