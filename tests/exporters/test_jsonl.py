"""Tests for JSONL exporter."""

from __future__ import annotations

import json
from pathlib import Path

from repo_semantic_memory.cli import main
from repo_semantic_memory.exporters import export_jsonl_directory
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


def test_export_jsonl_creates_expected_files(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    out_dir = tmp_path / ".rsm" / "export"

    result = export_jsonl_directory(
        output_dir=out_dir, entities=entities, relations=relations, metadata=metadata
    )

    assert (out_dir / "entities.jsonl").exists()
    assert (out_dir / "relations.jsonl").exists()
    assert (out_dir / "metadata.json").exists()
    assert "entities.jsonl" in result.files_written
    assert "relations.jsonl" in result.files_written
    assert "metadata.json" in result.files_written


def test_export_jsonl_lines_parse(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    out_dir = tmp_path / ".rsm" / "export"
    export_jsonl_directory(
        output_dir=out_dir, entities=entities, relations=relations, metadata=metadata
    )

    entity_lines = (out_dir / "entities.jsonl").read_text(encoding="utf-8").splitlines()
    relation_lines = (out_dir / "relations.jsonl").read_text(encoding="utf-8").splitlines()
    metadata_payload = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))

    assert entity_lines
    assert relation_lines
    for line in entity_lines:
        payload = json.loads(line)
        assert isinstance(payload, dict)
        assert "id" in payload
    for line in relation_lines:
        payload = json.loads(line)
        assert isinstance(payload, dict)
        assert "source_entity_id" in payload
        assert "target_entity_id" in payload
    assert metadata_payload["schema_version"] == "0.1.0"


def test_export_jsonl_is_deterministic(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path)
    entities, relations, metadata = _load_index(db_path)
    out_1 = tmp_path / "out_1"
    out_2 = tmp_path / "out_2"

    export_jsonl_directory(
        output_dir=out_1, entities=entities, relations=relations, metadata=metadata
    )
    export_jsonl_directory(
        output_dir=out_2, entities=entities, relations=relations, metadata=metadata
    )

    assert (out_1 / "entities.jsonl").read_text(encoding="utf-8") == (
        out_2 / "entities.jsonl"
    ).read_text(encoding="utf-8")
    assert (out_1 / "relations.jsonl").read_text(encoding="utf-8") == (
        out_2 / "relations.jsonl"
    ).read_text(encoding="utf-8")
