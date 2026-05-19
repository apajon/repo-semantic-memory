"""Deterministic path-role classification for repo-map and context-pack ranking."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from repo_semantic_memory.model import Entity

PathRole = str

SOURCE_ROLE: PathRole = "source"
TESTS_ROLE: PathRole = "tests"
EXAMPLES_ROLE: PathRole = "examples"
DOCS_ROLE: PathRole = "docs"
CI_CONFIG_ROLE: PathRole = "ci_config"
TOOLS_SCRIPTS_ROLE: PathRole = "tools_scripts"
OTHER_ROLE: PathRole = "other"

_COMMON_SOURCE_ROOT_NAMES = ("src", "packages", "libs", "modules")
_MARKER_FILENAMES = {"pyproject.toml", "package.xml", "setup.py", "setup.cfg"}
_NON_SOURCE_ROLE_PREFIXES = (
    "tests/",
    "test/",
    "examples/",
    "example/",
    "docs/",
    "doc/",
    ".github/",
    "ci/",
    "tools/",
    "scripts/",
)


def classify_path_role(*, path: str, source_roots: Sequence[str]) -> PathRole:
    """Classify a repository-relative path into a deterministic role bucket."""
    normalized = _normalize(path)
    if normalized.startswith(("tests/", "test/")):
        return TESTS_ROLE
    if normalized.startswith(("examples/", "example/")):
        return EXAMPLES_ROLE
    if normalized.startswith(("docs/", "doc/")):
        return DOCS_ROLE
    if normalized.startswith(
        (".github/", ".gitlab/", ".circleci/", ".buildkite/", "ci/", "config/")
    ):
        return CI_CONFIG_ROLE
    if normalized.startswith(("tools/", "scripts/")):
        return TOOLS_SCRIPTS_ROLE
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
        if (
            filename == "__init__.py"
            and parent
            and not parent.startswith(_NON_SOURCE_ROLE_PREFIXES)
        ):
            roots.add(parent)

    return tuple(sorted(roots))


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
