"""Version constants for package and semantic artifacts.

``PACKAGE_VERSION`` prefers hatch-vcs generated ``_version.py`` and then installed metadata.
``SCHEMA_VERSION`` and ``CONTEXT_PACK_VERSION`` remain independently managed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

_PACKAGE_DISTRIBUTION_NAME = "repo-semantic-memory"


def _resolve_generated_package_version() -> str | None:
    """Resolve package version from hatch-vcs generated module when available."""
    try:
        from . import _version
    except ImportError:
        return None

    candidate = getattr(_version, "__version__", None) or getattr(_version, "version", None)
    if isinstance(candidate, str) and candidate:
        return candidate
    return None


def _resolve_package_version() -> str:
    """Resolve installed distribution version with a development-safe fallback."""
    generated = _resolve_generated_package_version()
    if generated is not None:
        return generated

    try:
        return version(_PACKAGE_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0.0.0+unknown"


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
