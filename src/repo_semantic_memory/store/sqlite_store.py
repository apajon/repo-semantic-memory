"""SQLite persistence for deterministic semantic entities and relations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator, Sequence
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
                "Extraction schema_version mismatch: "
                f"expected {SCHEMA_VERSION}, got {metadata.schema_version}"
            )

        with self._transaction():
            self._assert_schema_version_unlocked()
            self._upsert_metadata(metadata.to_kv())
            self._upsert_entities(entities)
            self._upsert_relations(relations)

    def get_metadata(self) -> dict[str, str]:
        """Return metadata rows ordered by key."""
        rows = self._conn.execute("SELECT key, value FROM metadata ORDER BY key ASC").fetchall()
        return {key: value for key, value in rows}

    def apply_incremental_update(
        self,
        *,
        purge_paths: frozenset[str],
        new_entities: Sequence[Entity],
        new_relations: Sequence[Relation],
        global_recompute_kinds: frozenset[str],
        compute_global_relations: Callable[[list[Entity], list[Relation]], list[Relation]],
    ) -> tuple[int, int]:
        """Apply a transactional incremental index update.

        Within a single transaction:

        1. Delete all relations of *global_recompute_kinds* (will be rebuilt).
        2. Identify entity IDs whose ``source_range.path`` is in *purge_paths*.
        3. Delete their outgoing relations (where ``source_id`` matches).
        4. Delete incoming relations pointing at those same entity IDs
           (cross-file relations from unchanged files targeting deleted entities).
        5. Delete entities whose ``source_range.path`` is in *purge_paths*.
        6. Upsert *new_entities* and *new_relations*.
        7. If *global_recompute_kinds* is non-empty: load the current
           entity/relation snapshot, call *compute_global_relations*, and
           upsert the results.  Skipped when the set is empty to avoid an
           unnecessary full snapshot load.
        8. Return ``(entity_count, relation_count)`` after the update.

        Rolls back on any exception, leaving the previous index intact.

        Args:
            purge_paths: Repo-relative paths whose entities and source-side
                relations should be removed before upserting.
            new_entities: Freshly extracted entities to upsert.
            new_relations: Freshly extracted non-global relations to upsert.
            global_recompute_kinds: Relation kinds purged before upsert and
                fully recomputed via *compute_global_relations* afterward.
            compute_global_relations: Callable invoked with the post-upsert
                entity and relation snapshot; its return value is upserted.

        Returns:
            ``(entity_count, relation_count)`` — total counts after commit.
        """
        with self._transaction():
            # 1. Purge global-recompute relation kinds.
            self._delete_relation_kinds(global_recompute_kinds)

            # 2. Find entity IDs for purge_paths.
            entity_ids = self._entity_ids_for_source_paths(purge_paths)

            # 3. Delete outgoing relations (source_id in purge set).
            self._delete_relations_for_sources(entity_ids)

            # 4. Delete incoming relations (target_id in purge set) so that
            #    cross-file relations pointing at deleted entities are removed.
            self._delete_relations_for_targets(entity_ids)

            # 5. Delete entities for purge_paths.
            self._delete_entities_for_paths(purge_paths)

            # 6. Upsert freshly extracted content.
            self._upsert_entities(list(new_entities))
            self._upsert_relations(list(new_relations))

            # 7. Global recompute only when at least one global relation kind
            #    was invalidated. File-local extraction/upsert already handled
            #    changed paths; skipping this when the set is empty avoids an
            #    unnecessary full entity/relation snapshot load.
            if global_recompute_kinds:
                current_entities = self.list_entities()
                current_relations = self.list_relations()
                global_relations = compute_global_relations(current_entities, current_relations)
                self._upsert_relations(global_relations)

            # 8. Return final counts.
            entity_count: int = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            relation_count: int = self._conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            return entity_count, relation_count

    # ---------------------------------------------------------------------------
    # Private helpers for incremental updates
    # ---------------------------------------------------------------------------

    def _delete_relation_kinds(self, kinds: frozenset[str]) -> int:
        """Delete all relations whose ``kind`` is in *kinds*.

        Returns the number of rows deleted.
        """
        deleted = 0
        for kind in sorted(kinds):
            cursor = self._conn.execute("DELETE FROM relations WHERE kind = ?", (kind,))
            deleted += cursor.rowcount
        return deleted

    def _delete_relations_for_sources(self, entity_ids: frozenset[str]) -> int:
        """Delete relations whose ``source_id`` is in *entity_ids*.

        Returns the number of rows deleted.
        """
        if not entity_ids:
            return 0
        sorted_ids = sorted(entity_ids)
        placeholders = ",".join("?" * len(sorted_ids))
        cursor = self._conn.execute(
            f"DELETE FROM relations WHERE source_id IN ({placeholders})",
            sorted_ids,
        )
        return cursor.rowcount

    def _delete_relations_for_targets(self, entity_ids: frozenset[str]) -> int:
        """Delete relations whose ``target_id`` is in *entity_ids*.

        This removes incoming cross-file relations that point at entities
        about to be (or already) deleted, preventing dangling references.

        Returns the number of rows deleted.
        """
        if not entity_ids:
            return 0
        sorted_ids = sorted(entity_ids)
        placeholders = ",".join("?" * len(sorted_ids))
        cursor = self._conn.execute(
            f"DELETE FROM relations WHERE target_id IN ({placeholders})",
            sorted_ids,
        )
        return cursor.rowcount

    def _delete_entities_for_paths(self, paths: frozenset[str]) -> int:
        """Delete entities whose ``source_range.path`` is in *paths*.

        Returns the number of rows deleted.
        """
        if not paths:
            return 0
        sorted_paths = sorted(paths)
        placeholders = ",".join("?" * len(sorted_paths))
        cursor = self._conn.execute(
            "DELETE FROM entities WHERE"
            f" json_extract(source_range_json, '$.path') IN ({placeholders})",
            sorted_paths,
        )
        return cursor.rowcount

    def _entity_ids_for_source_paths(self, paths: frozenset[str]) -> frozenset[str]:
        """Return entity IDs whose ``source_range.path`` is in *paths*."""
        if not paths:
            return frozenset()
        sorted_paths = sorted(paths)
        placeholders = ",".join("?" * len(sorted_paths))
        rows = self._conn.execute(
            "SELECT id FROM entities WHERE"
            f" json_extract(source_range_json, '$.path') IN ({placeholders})",
            sorted_paths,
        ).fetchall()
        return frozenset(str(row[0]) for row in rows)

    def write_extra_metadata(self, extra: dict[str, str]) -> None:
        """Upsert additional key/value rows into the metadata table.

        Used after a successful :meth:`persist_index` call to record
        staleness-detection fields (``indexed_at``, ``git_head``,
        ``git_dirty``, ``entity_count``, ``relation_count``,
        ``context_pack_version``).  Callers must call :meth:`initialize`
        before this method.
        """
        with self._transaction():
            self._upsert_metadata(extra)

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
                    (
                        _json_dumps(relation.evidence.to_dict())
                        if relation.evidence is not None
                        else None
                    ),
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
