"""JSONL export for machine-facing semantic index portability."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from repo_semantic_memory.memory import infer_semantic_components
from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.version import PACKAGE_VERSION, SCHEMA_VERSION

EXPORT_FORMAT = "rsm-jsonl"
EXPORT_FORMAT_VERSION = "1.0"


@dataclass(frozen=True)
class JsonlExportResult:
    """Summary of JSONL export output."""

    output_dir: Path
    entity_count: int
    relation_count: int
    component_count: int
    files_written: tuple[str, ...]


@dataclass
class JsonlExporter:
    """Exports indexed entities/relations to deterministic JSONL files."""

    output_dir: Path
    entities: list[Entity]
    relations: list[Relation]
    metadata: dict[str, str]
    generated_at: str

    def export(self) -> JsonlExportResult:
        """Write JSONL export files under output_dir."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []
        self._write_entities()
        files_written.append("entities.jsonl")
        self._write_relations()
        files_written.append("relations.jsonl")
        self._write_metadata()
        files_written.append("metadata.json")

        components = infer_semantic_components(entities=self.entities, relations=self.relations)
        if components:
            self._write_components()
            files_written.append("components.jsonl")

        return JsonlExportResult(
            output_dir=self.output_dir,
            entity_count=len(self.entities),
            relation_count=len(self.relations),
            component_count=len(components),
            files_written=tuple(files_written),
        )

    def _write_entities(self) -> None:
        ordered = sorted(self.entities, key=lambda entity: entity.id.value)
        rows = [self._json_dumps(entity.to_dict()) for entity in ordered]
        self._write_jsonl_file(path=self.output_dir / "entities.jsonl", rows=rows)

    def _write_relations(self) -> None:
        ordered = sorted(
            self.relations,
            key=lambda relation: (
                relation.kind,
                relation.source_entity_id.value,
                relation.target_entity_id.value,
            ),
        )
        rows = [self._json_dumps(relation.to_dict()) for relation in ordered]
        self._write_jsonl_file(path=self.output_dir / "relations.jsonl", rows=rows)

    def _write_components(self) -> None:
        components = infer_semantic_components(entities=self.entities, relations=self.relations)
        ordered = sorted(
            components,
            key=lambda component: (component.component_type, component.entity_id.value),
        )
        rows = [self._json_dumps(component.to_dict()) for component in ordered]
        self._write_jsonl_file(path=self.output_dir / "components.jsonl", rows=rows)

    def _write_metadata(self) -> None:
        payload = {
            "export_format": EXPORT_FORMAT,
            "export_format_version": EXPORT_FORMAT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "package_version": PACKAGE_VERSION,
            "generated_at": self.generated_at,
            "entity_count": len(self.entities),
            "relation_count": len(self.relations),
            "extraction_metadata": dict(sorted(self.metadata.items())),
        }
        (self.output_dir / "metadata.json").write_text(
            self._json_dumps(payload, pretty=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_jsonl_file(*, path: Path, rows: list[str]) -> None:
        content = "\n".join(rows)
        if content:
            content = f"{content}\n"
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _json_dumps(value: object, *, pretty: bool = False) -> str:
        if pretty:
            return json.dumps(value, indent=2, sort_keys=True)
        return json.dumps(value, sort_keys=True, separators=(",", ":"))


def export_jsonl_directory(
    *,
    output_dir: Path | str,
    entities: list[Entity],
    relations: list[Relation],
    metadata: dict[str, str],
) -> JsonlExportResult:
    """Export deterministic JSONL payloads into output_dir."""
    exporter = JsonlExporter(
        output_dir=Path(output_dir),
        entities=entities,
        relations=relations,
        metadata=metadata,
        generated_at=datetime.now(tz=UTC).isoformat(),
    )
    return exporter.export()
