"""Deterministic path-role classification for repo-map and context-pack ranking."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Literal

from repo_semantic_memory.model import Entity

if TYPE_CHECKING:
    from repo_semantic_memory.context.query_intent import QueryIntent

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
_DOC_PREFIXES = ("docs/", "doc/", "docs_src/", "tutorials/", "tutorial/")
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

# ---------------------------------------------------------------------------
# Path-prior scoring constants (Ranking v2 — Prompt 58.2)
# ---------------------------------------------------------------------------
# All deltas are conservative (≤ 8 absolute) so they adjust rank without
# overwhelming strong lexical or semantic matches.

# Extra boost applied by path_prior_multiplier for real test-root paths (tests/ or
# test/) when the tests intent fires.  This is *additive* to the existing
# _TEST_PATH_ROLE_BONUS in pack_builder so it should be kept small.
_PATH_PRIOR_TEST_ROOT_BOOST: float = 4.0
# Penalty applied to runtime paths that contain a ``test`` directory segment in
# a non-root position (e.g. lib/ansible/plugins/test/core.py) when the tests
# intent fires.
_PATH_PRIOR_RUNTIME_TEST_PENALTY: float = -6.0
# Boost for __init__.py files when the public_api intent fires (additive to the
# existing _PUBLIC_API_PATH_ROLE_BONUS in pack_builder).
_PATH_PRIOR_PUBLIC_API_INIT_BOOST: float = 3.0
# Downrank for docs/tutorial/example paths when the query does not explicitly ask
# for documentation or examples (i.e. the ``docs_examples`` intent is absent).
_PATH_PRIOR_DOC_EXAMPLE_PENALTY: float = -4.0
# Boost for config/build files when config_build_release intent fires.
_PATH_PRIOR_CONFIG_BOOST: float = 3.0


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


def is_runtime_test_named_path(path: str) -> bool:
    """Return True if *path* contains a ``test`` directory segment that is NOT a test root.

    Paths like ``lib/ansible/plugins/test/core.py`` have ``test`` as a library-internal
    directory, not a unit-test root.  Real test roots begin at the repository root with
    ``tests/`` or ``test/`` and are detected by :func:`classify_path_role`.

    This helper lets path priors differentiate real unit-test trees from runtime
    directories that happen to be named ``test``.

    Examples::

        is_runtime_test_named_path("lib/ansible/plugins/test/core.py")  # True
        is_runtime_test_named_path("test/units/plugins/test_x.py")      # False (real root)
        is_runtime_test_named_path("tests/test_core.py")                 # False (real root)
        is_runtime_test_named_path("src/mypackage/utils.py")             # False (no test seg)
    """
    normalized = _normalize(path)
    # A real test root starts with tests/ or test/ at the repository root.
    if normalized.startswith(_TEST_PREFIXES):
        return False
    # Detect an embedded /test/ or /tests/ directory segment that is not leading.
    bracketed = f"/{normalized}/"
    return "/test/" in bracketed or "/tests/" in bracketed


def is_public_api_file(path: str) -> bool:
    """Return True if *path* is an ``__init__.py`` package API surface file.

    Examples::

        is_public_api_file("httpx/__init__.py")           # True
        is_public_api_file("django/urls/__init__.py")     # True
        is_public_api_file("__init__.py")                 # True
        is_public_api_file("django/urls/resolvers.py")    # False
    """
    normalized = _normalize(path)
    return normalized == "__init__.py" or normalized.endswith("/__init__.py")


def path_prior_multiplier(path: str, intent: QueryIntent) -> float:
    """Return an additive score delta based on path role conditioned on *intent*.

    Applies deterministic, intent-conditioned path priors to the ranking score.
    All deltas are conservative (≤ 8 absolute) to avoid overwhelming strong
    lexical or semantic matches.

    Rules applied:

    - **tests intent** — boost real test-root paths (``tests/`` or ``test/`` prefix);
      penalize runtime paths where ``test`` is an embedded non-root directory segment
      (e.g. ``lib/ansible/plugins/test/core.py``).
    - **public_api intent** — modestly boost ``__init__.py`` package surfaces.
    - **no docs/api/arch intent** — downrank for docs/tutorial/example paths
      (``docs/``, ``doc/``, ``docs_src/``, ``tutorials/``, ``tutorial/``,
      ``examples/``, ``example/``) when none of ``docs_examples``,
      ``public_api``, or ``architecture_flow`` are present.

      Design rationale: neutral or implementation-oriented queries default to
      code-search mode.  Tutorial and example files have high lexical overlap
      with real implementation tokens (e.g. "callback", "routing") and
      consistently dominate rankings without a path-prior penalty.  The penalty
      is additive (``–4.0``), not exclusion: a strong lexical match in a doc
      file can still overcome it.  Architecture queries are explicitly exempt
      via the ``architecture_flow`` intent; doc/guide/README queries are exempt
      via ``docs_examples``; public-API queries are exempt via ``public_api``.
    - **config_build_release intent** — boost package marker / config files.
    - **unknown intents on non-doc paths** — return ``0.0``.

    Args:
        path: Repository-relative POSIX path.
        intent: Parsed :class:`~repo_semantic_memory.context.query_intent.QueryIntent`.

    Returns:
        Additive score delta.  Positive boosts the entity; negative downranks it.
    """
    normalized = _normalize(path)
    delta: float = 0.0

    if "tests" in intent.intents:
        if normalized.startswith(_TEST_PREFIXES):
            delta += _PATH_PRIOR_TEST_ROOT_BOOST
        elif is_runtime_test_named_path(normalized):
            delta += _PATH_PRIOR_RUNTIME_TEST_PENALTY

    if "public_api" in intent.intents:
        if is_public_api_file(normalized):
            delta += _PATH_PRIOR_PUBLIC_API_INIT_BOOST

    if not (intent.intents & {"docs_examples", "public_api", "architecture_flow"}):
        # Downrank doc/tutorial/example paths for code-search queries that do not
        # explicitly request documentation, tutorials, examples, public API, or
        # architecture/flow information.  Mirrors the support_expansion allowance logic.
        if normalized.startswith(_DOC_PREFIXES) or normalized.startswith(_EXAMPLE_PREFIXES):
            delta += _PATH_PRIOR_DOC_EXAMPLE_PENALTY

    if "config_build_release" in intent.intents:
        filename = normalized.rsplit("/", maxsplit=1)[-1]
        if filename in _MARKER_FILENAMES or normalized.startswith(_CONFIG_PREFIXES):
            delta += _PATH_PRIOR_CONFIG_BOOST

    return delta


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
