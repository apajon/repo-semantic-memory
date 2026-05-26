"""RSM Index Store home and registry utilities.

Use :func:`resolve_store_home` to locate the central local index store
directory and :class:`IndexRegistry` to look up, register, and unregister
repository index mappings.

Use :func:`resolve_reader_db` to resolve the SQLite DB path for read-only
commands, or :class:`ResolvedDb` to inspect the resolution source.
"""

from repo_semantic_memory.store_home.home import resolve_store_home
from repo_semantic_memory.store_home.registry import IndexRegistry, RegistryEntry
from repo_semantic_memory.store_home.resolution import (
    DbResolutionSource,
    ResolvedDb,
    resolve_reader_db,
)

__all__ = [
    "DbResolutionSource",
    "IndexRegistry",
    "RegistryEntry",
    "ResolvedDb",
    "resolve_reader_db",
    "resolve_store_home",
]
