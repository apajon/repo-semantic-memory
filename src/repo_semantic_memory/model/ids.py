"""Stable identifier primitives for semantic model entities."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9._/-]+")
_DUP_DASH_PATTERN = re.compile(r"-+")


@dataclass(frozen=True, order=True)
class StableId:
    """Deterministic identifier composed from normalized parts."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("StableId value must not be empty")

    @classmethod
    def from_parts(cls, parts: Iterable[str]) -> StableId:
        """Build a stable identifier from normalized, non-empty parts."""
        normalized_parts = [cls._normalize_part(part) for part in parts]
        if not normalized_parts:
            raise ValueError("StableId requires at least one part")
        return cls(":".join(normalized_parts))

    @staticmethod
    def _normalize_part(part: str) -> str:
        token = part.strip().lower().replace("\\", "/")
        token = _NORMALIZE_PATTERN.sub("-", token)
        token = _DUP_DASH_PATTERN.sub("-", token).strip("-")
        if not token:
            raise ValueError("StableId parts must contain at least one valid character")
        return token

    def to_dict(self) -> str:
        """Serialize as plain string for lightweight storage."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> StableId:
        """Deserialize from plain string value."""
        return cls(value=value)

    def __str__(self) -> str:
        return self.value
