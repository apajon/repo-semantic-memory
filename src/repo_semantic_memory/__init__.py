"""repo_semantic_memory package."""

from repo_semantic_memory.version import (
    CONTEXT_PACK_VERSION,
    PACKAGE_VERSION,
    SCHEMA_VERSION,
    VersionInfo,
    get_version_info,
)

__all__ = [
    "CONTEXT_PACK_VERSION",
    "PACKAGE_VERSION",
    "SCHEMA_VERSION",
    "VersionInfo",
    "get_version_info",
]

__version__ = PACKAGE_VERSION
