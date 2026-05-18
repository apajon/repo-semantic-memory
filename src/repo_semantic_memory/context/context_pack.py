"""Context pack model for compact deterministic agent context payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass

from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.version import get_version_info


@dataclass(frozen=True)
class SourceCitation:
    """Minimal source citation used by downstream tools."""

    subject_kind: str
    subject_id: str
    path: str
    start_line: int
    end_line: int
    start_col: int | None = None
    end_col: int | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize citation to deterministic dictionary output."""
        payload: dict[str, object] = {
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }
        if self.start_col is not None:
            payload["start_col"] = self.start_col
        if self.end_col is not None:
            payload["end_col"] = self.end_col
        if self.note is not None:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True)
class ContextPack:
    """Task-specific compact context pack."""

    task: str
    budget: int
    selected_entities: tuple[Entity, ...]
    selected_relations: tuple[Relation, ...]
    source_citations: tuple[SourceCitation, ...]
    why_selected: dict[str, tuple[str, ...]]
    uncertainties: tuple[str, ...]
    suggested_files_to_inspect: tuple[str, ...]
    forbidden_assumptions: tuple[str, ...]
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.budget < 1:
            raise ValueError("ContextPack budget must be >= 1")

    def to_dict(self) -> dict[str, object]:
        """Serialize context pack to deterministic payload."""
        versions = get_version_info()
        return {
            "package_version": versions.package_version,
            "schema_version": versions.schema_version,
            "context_pack_version": versions.context_pack_version,
            "task": self.task,
            "budget": self.budget,
            "selected_entities": [_entity_payload(entity) for entity in self.selected_entities],
            "selected_relations": [
                _relation_payload(relation) for relation in self.selected_relations
            ],
            "source_citations": [citation.to_dict() for citation in self.source_citations],
            "why_selected": {
                key: list(self.why_selected[key]) for key in sorted(self.why_selected.keys())
            },
            "uncertainties": list(self.uncertainties),
            "suggested_files_to_inspect": list(self.suggested_files_to_inspect),
            "forbidden_assumptions": list(self.forbidden_assumptions),
            "truncated": self.truncated,
        }

    def to_yaml(self) -> str:
        """Render as YAML-compatible output.

        JSON is a strict subset of YAML 1.2 and keeps deterministic ordering here.
        """
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)


def relation_key(relation: Relation) -> str:
    """Build deterministic relation key for map-like fields."""
    return (
        "relation:"
        f"{relation.kind}:"
        f"{relation.source_entity_id.value}->"
        f"{relation.target_entity_id.value}"
    )


def _entity_payload(entity: Entity) -> dict[str, object]:
    source = entity.source_range
    return {
        "id": entity.id.value,
        "kind": entity.kind,
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "source_range": {
            "path": source.path.replace("\\", "/"),
            "start_line": source.start_line,
            "end_line": source.end_line,
            "start_col": source.start_col,
            "end_col": source.end_col,
        },
    }


def _relation_payload(relation: Relation) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_entity_id": relation.source_entity_id.value,
        "target_entity_id": relation.target_entity_id.value,
        "kind": relation.kind,
        "metadata": dict(sorted(relation.metadata.items())),
    }
    if relation.evidence is not None:
        payload["evidence"] = relation.evidence.to_dict()
    return payload
