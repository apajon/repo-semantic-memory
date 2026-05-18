"""Tests for JSONL importer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.exporters import export_jsonl_directory
from repo_semantic_memory.importers import import_jsonl_directory
from repo_semantic_memory.store import SQLiteStore

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "simple_repo"


def _build_db(tmp_path: Path) -> Path:
    db_path = tmp_path / ".rsm" / "index.sqlite"
    exit_code = main(["index", str(FIXTURE_ROOT), "--db", str(db_path)])
    assert exit_code == 0
    return db_path


def _load_index(db_path: Path) -> tuple[list[object], list[object], dict[str, str]]:
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        entities = store.list_entities()
        relations = store.list_relations()
        metadata = store.get_metadata()
    finally:
        store.close()
    return entities, relations, metadata


def test_import_jsonl_reconstructs_db(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    export_dir = tmp_path / ".rsm" / "export"
    imported_db = tmp_path / ".rsm" / "imported.sqlite"
    export_jsonl_directory(
        output_dir=export_dir, entities=entities, relations=relations, metadata=metadata
    )

    result = import_jsonl_directory(input_dir=export_dir, db_path=imported_db)
    assert result.entity_count == len(entities)
    assert result.relation_count == len(relations)

    imported_entities, imported_relations, _ = _load_index(imported_db)
    assert len(imported_entities) == len(entities)
    assert len(imported_relations) == len(relations)


def test_roundtrip_export_import_preserves_entities_and_relations(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    export_dir = tmp_path / ".rsm" / "export"
    imported_db = tmp_path / ".rsm" / "imported.sqlite"
    export_jsonl_directory(
        output_dir=export_dir, entities=entities, relations=relations, metadata=metadata
    )
    import_jsonl_directory(input_dir=export_dir, db_path=imported_db)

    imported_entities, imported_relations, _ = _load_index(imported_db)
    assert [entity.to_dict() for entity in imported_entities] == [
        entity.to_dict() for entity in entities
    ]
    assert [relation.to_dict() for relation in imported_relations] == [
        relation.to_dict() for relation in relations
    ]


def test_import_jsonl_invalid_schema_version_fails_clearly(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    export_dir = tmp_path / ".rsm" / "export"
    export_jsonl_directory(
        output_dir=export_dir, entities=entities, relations=relations, metadata=metadata
    )

    metadata_path = export_dir / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "9.9.9"
    metadata_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="schema version mismatch"):
        import_jsonl_directory(input_dir=export_dir, db_path=tmp_path / "imported.sqlite")


def test_import_jsonl_invalid_export_format_fails_clearly(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    export_dir = tmp_path / ".rsm" / "export"
    export_jsonl_directory(
        output_dir=export_dir, entities=entities, relations=relations, metadata=metadata
    )

    metadata_path = export_dir / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["export_format"] = "unknown-format"
    metadata_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported export_format"):
        import_jsonl_directory(input_dir=export_dir, db_path=tmp_path / "imported.sqlite")


def test_import_jsonl_missing_extraction_metadata_does_not_invent_facts(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    export_dir = tmp_path / ".rsm" / "export"
    imported_db = tmp_path / ".rsm" / "imported.sqlite"
    export_jsonl_directory(
        output_dir=export_dir, entities=entities, relations=relations, metadata=metadata
    )

    metadata_path = export_dir / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload.pop("extraction_metadata")
    metadata_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    import_jsonl_directory(input_dir=export_dir, db_path=imported_db)
    _, _, imported_metadata = _load_index(imported_db)
    assert imported_metadata["repository_root"] == ""
    assert imported_metadata["package_version"] == ""
    assert imported_metadata["timestamp"] == ""
    assert imported_metadata["extractor_names"] == "[]"


def test_import_jsonl_malformed_line_fails_clearly(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    export_dir = tmp_path / ".rsm" / "export"
    export_jsonl_directory(
        output_dir=export_dir, entities=entities, relations=relations, metadata=metadata
    )

    entities_path = export_dir / "entities.jsonl"
    entities_path.write_text(
        entities_path.read_text(encoding="utf-8") + "{not-json}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"entities\.jsonl:\d+: malformed JSONL row"):
        import_jsonl_directory(input_dir=export_dir, db_path=tmp_path / "imported.sqlite")
