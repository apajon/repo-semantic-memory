"""Deterministic path-role classification for repo-map and context-pack ranking."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from repo_semantic_memory.model import Entity

PathRole = Literal[
    "source",
    "test",
    "example",
    "doc",
    "ci",
    "tool",
    "config",
    "generated",
    "other",
]

SOURCE_ROLE: PathRole = "source"
TEST_ROLE: PathRole = "test"
EXAMPLE_ROLE: PathRole = "example"
DOC_ROLE: PathRole = "doc"
CI_ROLE: PathRole = "ci"
TOOL_ROLE: PathRole = "tool"
CONFIG_ROLE: PathRole = "config"
GENERATED_ROLE: PathRole = "generated"
OTHER_ROLE: PathRole = "other"

_COMMON_SOURCE_ROOT_NAMES = (
    # Common monorepo code roots used across Python and mixed-language repositories.
    # Keep this small and explicit; broader root inference comes from package markers.
    "src",
    "packages",
    "libs",
    "modules",
)
# Package markers spanning Python and ROS 2 ecosystems.
_MARKER_FILENAMES = {"pyproject.toml", "package.xml", "setup.py", "setup.cfg"}
_TEST_PREFIXES = ("tests/", "test/")
_EXAMPLE_PREFIXES = ("examples/", "example/")
_DOC_PREFIXES = ("docs/", "doc/")
_CI_PREFIXES = (".github/", ".gitlab/", ".circleci/", ".buildkite/", "ci/")
_TOOL_PREFIXES = ("tools/", "scripts/")
_CONFIG_PREFIXES = ("config/",)
_NON_SOURCE_DIR_NAMES = {
    "tests",
    "test",
    "examples",
    "example",
    "docs",
    "doc",
    ".github",
    "ci",
    "tools",
    "scripts",
    "config",
}

# Generated/build/cache path segments.  Detection is segment-aware so that
# legitimate paths like "src/build_tools.py" are NOT classified as generated.
_GENERATED_ARTIFACT_PATTERNS = (
    "/docs/_build/",
    "/_build/",
    "/dist/",
    "/build/",
    "/htmlcov/",
    "/.pytest_cache/",
    "/.mypy_cache/",
    "/.ruff_cache/",
    ".egg-info/",
)


def classify_path_role(*, path: str, source_roots: Sequence[str]) -> PathRole:
    """Classify a repository-relative path into a deterministic role bucket."""
    normalized = _normalize(path)
    if is_generated_artifact_path(normalized):
        return GENERATED_ROLE
    if normalized.startswith(_TEST_PREFIXES):
        return TEST_ROLE
    if normalized.startswith(_EXAMPLE_PREFIXES):
        return EXAMPLE_ROLE
    if normalized.startswith(_DOC_PREFIXES):
        return DOC_ROLE
    if normalized.startswith(_CI_PREFIXES):
        return CI_ROLE
    if normalized.startswith(_TOOL_PREFIXES):
        return TOOL_ROLE
    if normalized.startswith(_CONFIG_PREFIXES):
        return CONFIG_ROLE
    if _is_source_path(normalized, source_roots):
        return SOURCE_ROLE
    return OTHER_ROLE


def infer_source_roots(entities: Iterable[Entity]) -> tuple[str, ...]:
    """Infer source/package roots from entity paths and package marker files."""
    roots: set[str] = set()
    for entity in entities:
        path = _normalize(entity.source_range.path)
        if not path:
            continue
        top_level = _first_segment(path)
        if top_level in _COMMON_SOURCE_ROOT_NAMES:
            roots.add(top_level)

        filename = path.rsplit("/", maxsplit=1)[-1]
        parent = path.rsplit("/", maxsplit=1)[0] if "/" in path else ""
        if filename in _MARKER_FILENAMES and parent:
            roots.add(parent)
        if filename == "__init__.py" and parent and not _contains_non_source_dir(parent):
            # Avoid promoting nested non-source trees (e.g. pkg/tests/__init__.py)
            # while still recognizing package roots such as lifecore_state/__init__.py.
            roots.add(parent)

    return tuple(sorted(roots))


def is_generated_artifact_path(path: str) -> bool:
    """Return True if *path* points into a generated/build/cache directory.

    Detection is segment-aware: a bare filename or path component that merely
    *contains* a build-related word (e.g. ``src/build_tools.py``) is not
    classified as generated.  Only paths whose segments match a known
    generated-artifact prefix are affected.
    """
    normalized = f"/{_normalize(path)}/"
    return any(pattern in normalized for pattern in _GENERATED_ARTIFACT_PATTERNS)


def _is_source_path(path: str, source_roots: Sequence[str]) -> bool:
    if any(
        path == root_name or path.startswith(f"{root_name}/")
        for root_name in _COMMON_SOURCE_ROOT_NAMES
    ):
        return True
    return any(path == root or path.startswith(f"{root}/") for root in source_roots)


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _first_segment(path: str) -> str:
    return path.split("/", maxsplit=1)[0]


def _contains_non_source_dir(path: str) -> bool:
    return any(segment in _NON_SOURCE_DIR_NAMES for segment in path.split("/"))
