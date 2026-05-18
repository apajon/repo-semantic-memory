"""SQLite persistence for deterministic semantic entities and relations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.version import PACKAGE_VERSION, SCHEMA_VERSION


@dataclass(frozen=True)
class ExtractionMetadata:
    """Metadata captured for a single repository extraction run."""

    repository_root: str
    schema_version: str
    package_version: str
    extractor_names: tuple[str, ...]
    timestamp: str

    def to_kv(self) -> dict[str, str]:
        """Return deterministic key/value rows for metadata persistence."""
        extractor_names = tuple(sorted(self.extractor_names))
        return {
            "repository_root": self.repository_root,
            "schema_version": self.schema_version,
            "package_version": self.package_version,
            "extractor_names": _json_dumps(list(extractor_names)),
            "timestamp": self.timestamp,
        }


class SQLiteStore:
    """SQLite-backed store for semantic extraction outputs."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")

    @property
    def db_path(self) -> Path:
        """Return the configured SQLite database path."""
        return self._db_path

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def initialize(self) -> None:
        """Create schema and validate stored schema version."""
        with self._transaction():
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    qualified_name TEXT NOT NULL,
                    source_range_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS relations (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    evidence_json TEXT,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, kind)
                )
                """
            )
            self._assert_schema_version_unlocked()

    def persist_index(
        self,
        *,
        entities: Sequence[Entity],
        relations: Sequence[Relation],
        metadata: ExtractionMetadata,
    ) -> None:
        """Persist extraction metadata, entities, and relations atomically."""
        if metadata.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Extraction schema_version mismatch: expected {SCHEMA_VERSION}, got {metadata.schema_version}"
            )

        with self._transaction():
            self._assert_schema_version_unlocked()
            self._upsert_metadata(metadata.to_kv())
            self._upsert_entities(entities)
            self._upsert_relations(relations)

    def get_metadata(self) -> dict[str, str]:
        """Return metadata rows ordered by key."""
        rows = self._conn.execute(
            "SELECT key, value FROM metadata ORDER BY key ASC"
        ).fetchall()
        return {key: value for key, value in rows}

    def list_entities(self) -> list[Entity]:
        """Return entities in deterministic ordering."""
        rows = self._conn.execute(
            """
            SELECT id, kind, name, qualified_name, source_range_json, metadata_json
            FROM entities
            ORDER BY id ASC
            """
        ).fetchall()
        entities: list[Entity] = []
        for row in rows:
            entities.append(
                Entity.from_dict(
                    {
                        "id": row[0],
                        "kind": row[1],
                        "name": row[2],
                        "qualified_name": row[3],
                        "source_range": json.loads(row[4]),
                        "metadata": json.loads(row[5]),
                    }
                )
            )
        return entities

    def list_relations(self) -> list[Relation]:
        """Return relations in deterministic ordering."""
        rows = self._conn.execute(
            """
            SELECT source_id, target_id, kind, evidence_json, metadata_json
            FROM relations
            ORDER BY kind ASC, source_id ASC, target_id ASC
            """
        ).fetchall()
        relations: list[Relation] = []
        for row in rows:
            evidence = json.loads(row[3]) if row[3] is not None else None
            relations.append(
                Relation.from_dict(
                    {
                        "source_entity_id": row[0],
                        "target_entity_id": row[1],
                        "kind": row[2],
                        "evidence": evidence,
                        "metadata": json.loads(row[4]),
                    }
                )
            )
        return relations

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._conn.execute("BEGIN")
        try:
            yield
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def _assert_schema_version_unlocked(self) -> None:
        stored = self._metadata_value("schema_version")
        if stored is None:
            self._upsert_metadata({"schema_version": SCHEMA_VERSION})
            return
        if stored != SCHEMA_VERSION:
            raise ValueError(
                "SQLite schema version mismatch: "
                f"database has {stored}, expected {SCHEMA_VERSION}. "
                "Migrations are not implemented."
            )

    def _metadata_value(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return str(row[0])

    def _upsert_metadata(self, values: dict[str, str]) -> None:
        rows = sorted(values.items(), key=lambda item: item[0])
        self._conn.executemany(
            """
            INSERT INTO metadata(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            rows,
        )

    def _upsert_entities(self, entities: Sequence[Entity]) -> None:
        ordered = sorted(entities, key=lambda entity: entity.id.value)
        self._conn.executemany(
            """
            INSERT INTO entities(id, kind, name, qualified_name, source_range_json, metadata_json)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                kind = excluded.kind,
                name = excluded.name,
                qualified_name = excluded.qualified_name,
                source_range_json = excluded.source_range_json,
                metadata_json = excluded.metadata_json
            """,
            [
                (
                    entity.id.value,
                    entity.kind,
                    entity.name,
                    entity.qualified_name,
                    _json_dumps(entity.source_range.to_dict()),
                    _json_dumps(entity.metadata),
                )
                for entity in ordered
            ],
        )

    def _upsert_relations(self, relations: Sequence[Relation]) -> None:
        ordered = sorted(
            relations,
            key=lambda relation: (
                relation.kind,
                relation.source_entity_id.value,
                relation.target_entity_id.value,
            ),
        )
        self._conn.executemany(
            """
            INSERT INTO relations(source_id, target_id, kind, evidence_json, metadata_json)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, kind) DO UPDATE SET
                evidence_json = excluded.evidence_json,
                metadata_json = excluded.metadata_json
            """,
            [
                (
                    relation.source_entity_id.value,
                    relation.target_entity_id.value,
                    relation.kind,
                    _json_dumps(relation.evidence.to_dict()) if relation.evidence is not None else None,
                    _json_dumps(relation.metadata),
                )
                for relation in ordered
            ],
        )


def build_default_extraction_metadata(
    *,
    repository_root: Path | str,
    extractor_names: Sequence[str],
    timestamp: str,
) -> ExtractionMetadata:
    """Build extraction metadata using package and schema versions."""
    return ExtractionMetadata(
        repository_root=str(Path(repository_root).resolve()),
        schema_version=SCHEMA_VERSION,
        package_version=PACKAGE_VERSION,
        extractor_names=tuple(sorted(extractor_names)),
        timestamp=timestamp,
    )


def _json_dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
