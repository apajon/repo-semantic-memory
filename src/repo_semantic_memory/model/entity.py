"""Entity model definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from repo_semantic_memory.model.ids import StableId
from repo_semantic_memory.model.source_range import SourceRange

EntityKind = Literal[
    "repository",
    "package",
    "module",
    "class",
    "function",
    "method",
    "field",
    "test",
    "doc",
    "concept",
    "invariant",
]

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
ENTITY_KINDS: tuple[EntityKind, ...] = (
    "repository",
    "package",
    "module",
    "class",
    "function",
    "method",
    "field",
    "test",
    "doc",
    "concept",
    "invariant",
)


@dataclass(frozen=True)
class Entity:
    """Typed semantic entity extracted from repository artifacts."""

    id: StableId
    kind: EntityKind
    name: str
    qualified_name: str
    source_range: SourceRange
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Entity name must not be empty")
        if not self.qualified_name:
            raise ValueError("Entity qualified_name must not be empty")

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "id": self.id.to_dict(),
            "kind": self.kind,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "source_range": self.source_range.to_dict(),
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Entity:
        """Deserialize from a dictionary payload."""
        id_value = payload.get("id")
        if not isinstance(id_value, str):
            raise ValueError("Entity id must be a string")
        source_payload = payload.get("source_range")
        if not isinstance(source_payload, dict):
            raise ValueError("Entity source_range must be a dictionary")
        metadata_payload = payload.get("metadata", {})
        if not isinstance(metadata_payload, dict):
            raise ValueError("Entity metadata must be a dictionary")
        kind = str(payload["kind"])
        if kind not in ENTITY_KINDS:
            raise ValueError(f"Unsupported entity kind: {kind}")
        return cls(
            id=StableId.from_dict(id_value),
            kind=kind,
            name=str(payload["name"]),
            qualified_name=str(payload["qualified_name"]),
            source_range=SourceRange.from_dict(source_payload),
            metadata=dict(sorted(cast(dict[str, JsonValue], metadata_payload).items())),
        )
