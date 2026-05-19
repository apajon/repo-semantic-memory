"""Version constants for package and semantic artifacts.

``PACKAGE_VERSION`` is resolved from installed package metadata.
``SCHEMA_VERSION`` and ``CONTEXT_PACK_VERSION`` remain independently managed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

_PACKAGE_DISTRIBUTION_NAME = "repo-semantic-memory"


def _resolve_package_version() -> str:
    """Resolve installed distribution version with a development-safe fallback."""
    try:
        return version(_PACKAGE_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0.0.0.dev0"


PACKAGE_VERSION = _resolve_package_version()
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
