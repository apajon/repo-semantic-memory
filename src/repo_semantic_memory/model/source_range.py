"""Source range model with deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, order=True)
class SourceRange:
    """Location range for source-backed artifacts."""

    path: str
    start_line: int
    end_line: int
    start_col: int | None = None
    end_col: int | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("SourceRange path must not be empty")
        if self.start_line < 1:
            raise ValueError("SourceRange start_line must be >= 1")
        if self.end_line < self.start_line:
            raise ValueError("SourceRange end_line must be >= start_line")
        if self.start_col is not None and self.start_col < 1:
            raise ValueError("SourceRange start_col must be >= 1 when provided")
        if self.end_col is not None and self.end_col < 1:
            raise ValueError("SourceRange end_col must be >= 1 when provided")
        if (
            self.start_col is not None
            and self.end_col is not None
            and self.start_line == self.end_line
            and self.end_col < self.start_col
        ):
            raise ValueError("SourceRange end_col must be >= start_col on same line")

    def to_dict(self) -> dict[str, int | str | None]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_col": self.start_col,
            "end_col": self.end_col,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SourceRange:
        """Deserialize from a dictionary payload."""
        start_col = payload.get("start_col")
        end_col = payload.get("end_col")
        return cls(
            path=str(payload["path"]),
            start_line=int(str(payload["start_line"])),
            end_line=int(str(payload["end_line"])),
            start_col=int(str(start_col)) if start_col is not None else None,
            end_col=int(str(end_col)) if end_col is not None else None,
        )
