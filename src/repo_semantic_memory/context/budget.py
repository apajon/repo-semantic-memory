"""Budget utilities for compact deterministic text rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CharacterBudget:
    """Track a rough character budget while appending line-based content."""

    max_chars: int
    _lines: list[str] = field(default_factory=list)
    _used_chars: int = 0

    def __post_init__(self) -> None:
        if self.max_chars < 1:
            raise ValueError("Character budget must be >= 1")

    def append_line(self, line: str) -> bool:
        """Append a line if it fits the remaining budget."""
        additional_chars = len(line)
        if self._lines:
            additional_chars += 1  # newline separator
        if self._used_chars + additional_chars > self.max_chars:
            return False
        self._lines.append(line)
        self._used_chars += additional_chars
        return True

    def append_truncation_notice(self) -> None:
        """Append a deterministic truncation notice when budget is exhausted."""
        self.append_line("...")

    def render(self) -> str:
        """Render accumulated lines."""
        return "\n".join(self._lines)
