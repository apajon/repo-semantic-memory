"""JSONL import for machine-facing semantic index interchange."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_semantic_memory.exporters.jsonl import EXPORT_FORMAT, EXPORT_FORMAT_VERSION
from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.store import ExtractionMetadata, SQLiteStore
from repo_semantic_memory.version import SCHEMA_VERSION


@dataclass(frozen=True)
class JsonlImportResult:
    """Summary of JSONL import operation."""

    input_dir: Path
    db_path: Path
    entity_count: int
    relation_count: int
    components_snapshot_ignored: bool


def import_jsonl_directory(*, input_dir: Path | str, db_path: Path | str) -> JsonlImportResult:
    """Import entities/relations from JSONL export files into SQLite."""
    source_dir = Path(input_dir)
    entities = _read_entities(source_dir / "entities.jsonl")
    relations = _read_relations(source_dir / "relations.jsonl")
    metadata_payload = _read_metadata(source_dir / "metadata.json")
    _validate_export_format(metadata_payload)
    _validate_schema_version(metadata_payload)
    metadata = _extract_extraction_metadata(payload=metadata_payload)
    components_snapshot_ignored = (source_dir / "components.jsonl").exists()

    db = SQLiteStore(db_path)
    try:
        db.initialize()
        db.persist_index(entities=entities, relations=relations, metadata=metadata)
    finally:
        db.close()
    return JsonlImportResult(
        input_dir=source_dir,
        db_path=Path(db_path),
        entity_count=len(entities),
        relation_count=len(relations),
        components_snapshot_ignored=components_snapshot_ignored,
    )


def _read_entities(path: Path) -> list[Entity]:
    entities: list[Entity] = []
    for line_number, row in _load_jsonl_rows(path):
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number}: expected JSON object")
        try:
            entities.append(Entity.from_dict(row))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid entity row: {exc}") from exc
    return entities


def _read_relations(path: Path) -> list[Relation]:
    relations: list[Relation] = []
    for line_number, row in _load_jsonl_rows(path):
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number}: expected JSON object")
        try:
            relations.append(Relation.from_dict(row))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path.name}:{line_number}: invalid relation row: {exc}") from exc
    return relations


def _load_jsonl_rows(path: Path) -> list[tuple[int, Any]]:
    if not path.exists():
        raise ValueError(f"Missing required file: {path}")
    rows: list[tuple[int, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: malformed JSONL row: {exc.msg}") from exc
        rows.append((line_number, value))
    return rows


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Missing required file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: malformed JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name}: expected top-level JSON object")
    return payload


def _validate_schema_version(metadata_payload: dict[str, Any]) -> None:
    schema_version = metadata_payload.get("schema_version")
    if not isinstance(schema_version, str):
        raise ValueError("metadata.json: schema_version must be a string")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            "metadata.json: schema version mismatch: "
            f"import has {schema_version}, expected {SCHEMA_VERSION}"
        )


def _validate_export_format(metadata_payload: dict[str, Any]) -> None:
    export_format = metadata_payload.get("export_format")
    if not isinstance(export_format, str):
        raise ValueError("metadata.json: export_format must be a string")
    if export_format != EXPORT_FORMAT:
        raise ValueError(
            f"metadata.json: unsupported export_format: {export_format} (expected {EXPORT_FORMAT})"
        )

    export_format_version = metadata_payload.get("export_format_version")
    if not isinstance(export_format_version, str):
        raise ValueError("metadata.json: export_format_version must be a string")
    if export_format_version != EXPORT_FORMAT_VERSION:
        raise ValueError(
            "metadata.json: unsupported export_format_version: "
            f"{export_format_version} (expected {EXPORT_FORMAT_VERSION})"
        )


def _extract_extraction_metadata(*, payload: dict[str, Any]) -> ExtractionMetadata:
    extraction_payload = payload.get("extraction_metadata", {})
    if extraction_payload is None:
        extraction_payload = {}
    if not isinstance(extraction_payload, dict):
        raise ValueError("metadata.json: extraction_metadata must be an object when provided")

    repository_root = _coerce_optional_str(
        extraction_payload.get("repository_root"),
        field_name="metadata.json: extraction_metadata.repository_root",
    )
    package_version = _coerce_optional_str(
        extraction_payload.get("package_version"),
        field_name="metadata.json: extraction_metadata.package_version",
    )
    timestamp = _coerce_optional_str(
        extraction_payload.get("timestamp"),
        field_name="metadata.json: extraction_metadata.timestamp",
    )
    extractor_names = _coerce_extractor_names(extraction_payload.get("extractor_names"))

    return ExtractionMetadata(
        repository_root=repository_root,
        schema_version=SCHEMA_VERSION,
        package_version=package_version,
        extractor_names=extractor_names,
        timestamp=timestamp,
    )


def _coerce_extractor_names(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            raise ValueError(
                "metadata.json: extraction_metadata.extractor_names string must contain JSON array"
            ) from None
        if isinstance(loaded, list) and all(isinstance(item, str) for item in loaded):
            return tuple(sorted(loaded))
        raise ValueError(
            "metadata.json: extraction_metadata.extractor_names string must contain JSON array"
        )
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(sorted(value))
    raise ValueError(
        "metadata.json: extraction_metadata.extractor_names must be list[str] or string"
    )


def _coerce_optional_str(value: Any, *, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string when provided")
    return value
