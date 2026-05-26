"""Reader DB path resolution for RSM commands.

Use :func:`resolve_reader_db` to determine which SQLite index file to open
for read-only commands such as ``pack``, ``repo-map``, ``inspect``, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DbResolutionSource = Literal["explicit", "index_store", "repo_local"]
"""Source that determined the resolved DB path."""


@dataclass(frozen=True)
class ResolvedDb:
    """Result of reader DB resolution.

    Attributes:
        path: Resolved Path to the SQLite file (may be relative for the
            repo-local fallback; use ``str(result.path)`` where a string
            is required).
        source: Which resolution step produced the path.
    """

    path: Path
    source: DbResolutionSource


def resolve_reader_db(db: str | None, *, cwd: Path | None = None) -> ResolvedDb:
    """Resolve the SQLite DB path for read-only commands.

    Resolution order:

    1. Explicit ``--db`` value when *db* is not ``None``.
    2. RSM Index Store entry for *cwd* (or ``Path.cwd()`` when *cwd* is
       ``None``).
    3. Repo-local fallback ``Path(".rsm/index.sqlite")`` (relative, may not
       exist).  The relative form is preserved for compatibility with callers
       that rely on the conventional relative path string.

    Errors from the Index Store lookup (``ImportError``, ``OSError``) are
    caught and silently treated as a cache miss, matching existing CLI
    behaviour.
    """
    if db is not None:
        return ResolvedDb(Path(db), "explicit")

    effective_cwd = cwd if cwd is not None else Path.cwd()
    try:
        from repo_semantic_memory.store_home.home import resolve_store_home
        from repo_semantic_memory.store_home.registry import IndexRegistry

        registry = IndexRegistry(resolve_store_home())
        looked_up = registry.lookup(effective_cwd)
        if looked_up is not None:
            return ResolvedDb(looked_up, "index_store")
    except (ImportError, OSError):
        pass

    return ResolvedDb(Path(".rsm/index.sqlite"), "repo_local")


__all__ = ["DbResolutionSource", "ResolvedDb", "resolve_reader_db"]
