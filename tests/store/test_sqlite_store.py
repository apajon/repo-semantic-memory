"""SQLite store tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from repo_semantic_memory.model import Entity, Evidence, Relation, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata
from repo_semantic_memory.version import SCHEMA_VERSION


def _entity(*, identifier: str, name: str) -> Entity:
    return Entity(
        id=StableId(identifier),
        kind="module",
        name=name,
        qualified_name=name,
        source_range=SourceRange(path=f"{name}.py", start_line=1, end_line=1),
        metadata={"origin": "test"},
    )


def _relation(*, source: str, target: str, kind: str = "contains") -> Relation:
    return Relation(
        source_entity_id=StableId(source),
        target_entity_id=StableId(target),
        kind=kind,
        evidence=Evidence(
            source_range=SourceRange(path="src/app.py", start_line=1, end_line=1),
            extractor="test",
            confidence=1.0,
        ),
        metadata={"source": "fixture"},
    )


def test_store_and_retrieve_entities(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("filesystem", "python_ast"),
            timestamp="2026-01-01T00:00:00+00:00",
        )
        entities = [_entity(identifier="id:b", name="b"), _entity(identifier="id:a", name="a")]
        store.persist_index(entities=entities, relations=[], metadata=metadata)
        persisted = store.list_entities()
    finally:
        store.close()

    assert [entity.id.value for entity in persisted] == ["id:a", "id:b"]
    assert persisted[0].metadata == {"origin": "test"}


def test_store_and_retrieve_relations(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("filesystem", "python_ast"),
            timestamp="2026-01-01T00:00:00+00:00",
        )
        relations = [
            _relation(source="id:b", target="id:c", kind="imports"),
            _relation(source="id:a", target="id:b", kind="contains"),
        ]
        store.persist_index(entities=[], relations=relations, metadata=metadata)
        persisted = store.list_relations()
    finally:
        store.close()

    assert [(relation.kind, relation.source_entity_id.value) for relation in persisted] == [
        ("contains", "id:a"),
        ("imports", "id:b"),
    ]
    assert persisted[0].evidence is not None


def test_entity_upsert_behavior(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("filesystem",),
            timestamp="2026-01-01T00:00:00+00:00",
        )
        first = _entity(identifier="id:same", name="before")
        second = Entity(
            id=first.id,
            kind="module",
            name="after",
            qualified_name="after",
            source_range=SourceRange(path="after.py", start_line=1, end_line=3),
            metadata={"origin": "upsert"},
        )
        store.persist_index(entities=[first], relations=[], metadata=metadata)
        store.persist_index(entities=[second], relations=[], metadata=metadata)
        persisted = store.list_entities()
    finally:
        store.close()

    assert len(persisted) == 1
    assert persisted[0].name == "after"
    assert persisted[0].metadata == {"origin": "upsert"}


def test_relation_upsert_behavior(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("python_ast",),
            timestamp="2026-01-01T00:00:00+00:00",
        )
        first = Relation(
            source_entity_id=StableId("id:a"),
            target_entity_id=StableId("id:b"),
            kind="contains",
            metadata={"revision": 1},
        )
        second = Relation(
            source_entity_id=StableId("id:a"),
            target_entity_id=StableId("id:b"),
            kind="contains",
            metadata={"revision": 2},
        )
        store.persist_index(entities=[], relations=[first], metadata=metadata)
        store.persist_index(entities=[], relations=[second], metadata=metadata)
        persisted = store.list_relations()
    finally:
        store.close()

    assert len(persisted) == 1
    assert persisted[0].metadata == {"revision": 2}


def test_metadata_persistence_and_schema_version(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("filesystem", "python_ast"),
            timestamp="2026-01-01T00:00:00+00:00",
        )
        store.persist_index(entities=[], relations=[], metadata=metadata)
        persisted = store.get_metadata()
    finally:
        store.close()

    assert persisted["schema_version"] == SCHEMA_VERSION
    assert persisted["package_version"]
    assert persisted["repository_root"] == str(tmp_path.resolve())
    assert persisted["extractor_names"] == '["filesystem","python_ast"]'


def test_invalid_schema_version_fails_clearly(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata(key, value) VALUES('schema_version', '0.0.1')")
        conn.commit()
    finally:
        conn.close()

    store = SQLiteStore(db_path)
    try:
        with pytest.raises(ValueError, match="schema version mismatch"):
            store.initialize()
    finally:
        store.close()
