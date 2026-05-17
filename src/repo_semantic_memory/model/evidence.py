"""Evidence model used to track semantic claim provenance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from repo_semantic_memory.model.source_range import SourceRange


@dataclass(frozen=True)
class Evidence:
    """Provenance envelope for extracted semantic information."""

    source_range: SourceRange
    extractor: str
    confidence: float
    commit: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.extractor:
            raise ValueError("Evidence extractor must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Evidence confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "source_range": self.source_range.to_dict(),
            "extractor": self.extractor,
            "confidence": self.confidence,
            "commit": self.commit,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Evidence:
        """Deserialize from a dictionary payload."""
        source_payload = payload.get("source_range")
        if not isinstance(source_payload, dict):
            raise ValueError("Evidence source_range must be a dictionary")
        return cls(
            source_range=SourceRange.from_dict(source_payload),
            extractor=str(payload["extractor"]),
            confidence=float(str(payload["confidence"])),
            commit=str(payload["commit"]) if payload.get("commit") is not None else None,
            note=str(payload["note"]) if payload.get("note") is not None else None,
        )
