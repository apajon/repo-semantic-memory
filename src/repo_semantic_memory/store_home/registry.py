"""RSM Index Store registry: maps repository roots to local index files.

The registry is a single ``registry.json`` file at the root of the RSM Index
Store home directory. It maps resolved absolute repository paths to their
associated SQLite index files.

File format::

    {
      "version": 1,
      "entries": {
        "/absolute/path/to/repo": {
          "db": "indexes/a1b2c3d4e5f6a7b8/index.sqlite",
          "registered_at": "2026-05-24T21:00:00+00:00",
          "last_indexed_at": "2026-05-24T21:05:00+00:00"
        }
      }
    }

Design notes:

- Keys are resolved POSIX paths (symlinks resolved).
- ``db`` is a path relative to the store home when the database lives inside
  the store; otherwise it is an absolute POSIX path string.
- Writes go to ``registry.json.tmp`` then are atomically renamed over
  ``registry.json`` (POSIX-atomic; best-effort on Windows).
- Single-writer assumption: concurrent writes from multiple processes to the
  same store are not supported.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class RegistryEntry:
    """A single entry in the RSM Index Store registry."""

    db_relative: str
    """DB path relative to the store home, or an absolute path if external."""

    registered_at: str
    """ISO 8601 timestamp of when the entry was first registered."""

    last_indexed_at: str | None
    """ISO 8601 timestamp of the last successful index run, or ``None``."""


class IndexRegistry:
    """Registry mapping resolved repository roots to index DB files.

    Instantiate with the store home directory returned by
    :func:`~repo_semantic_memory.store_home.home.resolve_store_home`.
    """

    _REGISTRY_VERSION: int = 1

    def __init__(self, store_home: Path) -> None:
        self._store_home = store_home
        self._registry_path = store_home / "registry.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, repo_root: Path) -> Path | None:
        """Return the absolute DB path for ``repo_root``, or ``None``.

        Returns ``None`` if the repository is not registered or if the
        registry file is absent or malformed.
        """
        entries = self._load()
        key = self._repo_key(repo_root)
        entry_data = entries.get(key)
        if entry_data is None:
            return None
        db_str = entry_data.get("db", "")
        if not db_str:
            return None
        return self._resolve_db(db_str)

    def register(
        self,
        repo_root: Path,
        db_path: Path,
        *,
        indexed: bool = False,
    ) -> None:
        """Add or update the registry entry for ``repo_root``.

        ``db_path`` must be an absolute path. If ``indexed=True``,
        ``last_indexed_at`` is updated to the current UTC time.
        ``registered_at`` is preserved if an entry already exists.
        """
        entries = self._load()
        key = self._repo_key(repo_root)
        now = _iso_now()
        db_str = self._db_str(db_path.resolve())
        existing = entries.get(key, {})
        entry: dict[str, str | None] = {
            "db": db_str,
            "registered_at": existing.get("registered_at") or now,
            "last_indexed_at": now if indexed else existing.get("last_indexed_at"),
        }
        entries[key] = entry
        self._save(entries)

    def unregister(self, repo_root: Path) -> bool:
        """Remove the registry entry for ``repo_root``.

        Returns ``True`` if an entry was removed, ``False`` if none existed.
        Does *not* delete the index SQLite file.
        """
        entries = self._load()
        key = self._repo_key(repo_root)
        if key not in entries:
            return False
        del entries[key]
        self._save(entries)
        return True

    def list_entries(self) -> dict[str, RegistryEntry]:
        """Return all entries keyed by resolved repo path string, sorted."""
        raw = self._load()
        result: dict[str, RegistryEntry] = {}
        for key in sorted(raw):
            data = raw[key]
            result[key] = RegistryEntry(
                db_relative=data.get("db") or "",
                registered_at=data.get("registered_at") or "",
                last_indexed_at=data.get("last_indexed_at"),
            )
        return result

    def default_db_path(self, repo_root: Path) -> Path:
        """Return the canonical store DB path for a repo (may not exist yet)."""
        return self._store_home / "indexes" / self.repo_id(repo_root) / "index.sqlite"

    @staticmethod
    def repo_id(repo_root: Path) -> str:
        """Return a stable 16-hex-char ID derived from the resolved repo path."""
        canonical = repo_root.resolve().as_posix()
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _repo_key(repo_root: Path) -> str:
        return repo_root.resolve().as_posix()

    def _db_str(self, db_abs: Path) -> str:
        """Return relative (preferred) or absolute string for ``db_abs``."""
        try:
            return db_abs.relative_to(self._store_home).as_posix()
        except ValueError:
            return db_abs.as_posix()

    def _resolve_db(self, db_str: str) -> Path:
        """Resolve a stored db string to an absolute Path."""
        db_path = Path(db_str)
        if db_path.is_absolute():
            return db_path
        return self._store_home / db_str

    def _load(self) -> dict[str, dict[str, str | None]]:
        if not self._registry_path.exists():
            return {}
        try:
            raw = json.loads(self._registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(raw, dict):
            return {}
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            return {}
        return {k: v for k, v in entries.items() if isinstance(v, dict)}

    def _save(self, entries: dict[str, dict[str, str | None]]) -> None:
        payload = json.dumps(
            {"version": self._REGISTRY_VERSION, "entries": entries},
            indent=2,
            sort_keys=True,
        )
        tmp = self._registry_path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._registry_path)


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


__all__ = ["IndexRegistry", "RegistryEntry"]
