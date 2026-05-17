"""Version constants for package and semantic artifacts."""

from __future__ import annotations

from dataclasses import dataclass

PACKAGE_VERSION = "0.1.0"
SCHEMA_VERSION = "0.1.0"
CONTEXT_PACK_VERSION = "0.1.0"


@dataclass(frozen=True)
class VersionInfo:
    """Container for deterministic version fields."""

    package_version: str
    schema_version: str
    context_pack_version: str


def get_version_info() -> VersionInfo:
    """Return all version constants in a typed, deterministic structure."""
    return VersionInfo(
        package_version=PACKAGE_VERSION,
        schema_version=SCHEMA_VERSION,
        context_pack_version=CONTEXT_PACK_VERSION,
    )
