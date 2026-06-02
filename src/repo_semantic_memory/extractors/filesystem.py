"""Filesystem extractor for deterministic file-level entities.

MVP choice: Python files are emitted as ``module`` entities keyed by repository-relative
file paths. A future schema may separate physical file entities from logical modules.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Sequence
from pathlib import Path

from repo_semantic_memory.context.path_roles import is_generated_artifact_path
from repo_semantic_memory.model import Entity, EntityKind, SourceRange, StableId

IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "_build",
        "htmlcov",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".idea",
        ".vscode",
    }
)

DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt", ".yaml", ".yml", ".json"})
MODULE_EXTENSIONS: frozenset[str] = frozenset({".py"})
IGNORED_FILES: frozenset[str] = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "cargo.lock",
        "pipfile.lock",
    }
)
BINARY_SAMPLE_BYTES = 8192
_IGNORED_PATH_PREFIXES: tuple[str, ...] = ("docs/_build/",)


# ---------------------------------------------------------------------------
# Scope filter — include/exclude glob patterns
# ---------------------------------------------------------------------------


class ScopeFilter:
    """Glob-pattern filter for scoped repository indexing.

    Both ``includes`` and ``excludes`` accept POSIX-style glob patterns
    relative to the repository root (e.g. ``homeassistant/components/**``).
    Python's :func:`fnmatch.fnmatch` is used: ``*`` matches any characters
    including ``/``, so ``foo/**`` and ``foo/*`` are effectively equivalent.

    Semantics:
    - Excludes take precedence over includes.
    - If no includes are given, all non-excluded files are indexed.
    - If includes are given, only files matching at least one include pattern
      are indexed (after excludes are applied).
    - With no patterns, :attr:`is_passthrough` is ``True`` and no overhead
      is added to the walk.
    """

    def __init__(self, includes: Sequence[str] = (), excludes: Sequence[str] = ()) -> None:
        self._includes = [p.strip("/ ") for p in includes if p.strip("/ ")]
        self._excludes = [p.strip("/ ") for p in excludes if p.strip("/ ")]

    @property
    def is_passthrough(self) -> bool:
        """True when no patterns are configured; filtering is skipped entirely."""
        return not self._includes and not self._excludes

    def should_index_file(self, rel_path: str) -> bool:
        """Return True if the repository-relative file path should be indexed."""
        normalized = rel_path.replace("\\", "/").strip("/")
        if not normalized:
            return False
        for pat in self._excludes:
            if fnmatch.fnmatch(normalized, pat):
                return False
        if self._includes:
            return any(fnmatch.fnmatch(normalized, pat) for pat in self._includes)
        return True

    def should_descend_directory(self, rel_dir: str) -> bool:
        """Return True if os.walk should descend into the given directory.

        Args:
            rel_dir: POSIX-style repository-relative path of the directory
                (e.g. ``"homeassistant/components"``).  Must not be empty.
        """
        normalized = rel_dir.replace("\\", "/").strip("/")
        if not normalized:
            return True
        for pat in self._excludes:
            if self._dir_excluded(normalized, pat):
                return False
        if self._includes:
            return any(self._dir_could_match(normalized, pat) for pat in self._includes)
        return True

    @staticmethod
    def _dir_excluded(rel_dir: str, pattern: str) -> bool:
        """True when the exclude pattern covers the entire directory subtree.

        Note: ``fnmatch.fnmatch`` treats ``*`` as matching any character including
        ``/``, so ``foo/*`` and ``foo/**`` are equivalent here — both match files
        at any depth inside ``foo``.  Consequently, stripping trailing ``/*`` from
        the pattern to obtain the bare directory name is intentional: if you wrote
        ``--exclude foo/*``, pruning the ``foo`` directory entirely is correct and
        optimal.
        """
        # Strip trailing wildcard separators so "foo/bar", "foo/bar/*", and
        # "foo/bar/**" all exclude the directory "foo/bar".
        bare = pattern.rstrip("/*")
        if bare and fnmatch.fnmatch(rel_dir, bare):
            return True
        # A wildcard pattern like "foo/**" where a hypothetical direct child
        # would match confirms the whole directory is excluded.
        return bool(bare) and fnmatch.fnmatch(rel_dir + "/x", pattern)

    @staticmethod
    def _dir_could_match(rel_dir: str, pattern: str) -> bool:
        """True when the include pattern could match a file under rel_dir."""
        # Hypothetical direct child matches.
        if fnmatch.fnmatch(rel_dir + "/x", pattern):
            return True
        # The directory is an ancestor of the pattern's literal (non-wildcard)
        # prefix, e.g. pattern "homeassistant/components/**", dir "homeassistant".
        lit_prefix = pattern.split("*")[0].rstrip("/")
        if lit_prefix.startswith(rel_dir + "/") or lit_prefix == rel_dir:
            return True
        # Catch-all: pattern is a leading wildcard (matches any path).
        return pattern.startswith("*")


# ---------------------------------------------------------------------------
# Filesystem extractor
# ---------------------------------------------------------------------------


def extract_filesystem_entities(
    repo_root: Path | str,
    *,
    scope_filter: ScopeFilter | None = None,
) -> list[Entity]:
    """Extract deterministic file-level entities from a repository root."""
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")

    discovered: list[tuple[str, Path, EntityKind]] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        rel_current = current_dir.relative_to(root).as_posix()
        if rel_current == ".":
            rel_current = ""
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not _should_ignore_directory_name(name)
            and not _should_ignore_directory_path(current_dir / name, root)
            and (
                scope_filter is None
                or scope_filter.should_descend_directory(
                    name if not rel_current else f"{rel_current}/{name}"
                )
            )
        )
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            relative_path = path.relative_to(root).as_posix()
            if not should_index_repo_path(root, relative_path):
                continue
            if scope_filter is not None and not scope_filter.should_index_file(relative_path):
                continue
            if _is_binary_looking(path):
                continue
            kind = _classify_kind(path)
            if kind is None:
                continue
            discovered.append((relative_path, path, kind))

    discovered.sort(key=lambda item: item[0])
    return [
        _build_entity(relative_path, path, kind=kind) for relative_path, path, kind in discovered
    ]


def _build_entity(relative_path: str, path: Path, *, kind: EntityKind) -> Entity:
    return Entity(
        id=StableId.from_parts(["file", relative_path]),
        kind=kind,
        name=path.name,
        qualified_name=relative_path,
        source_range=SourceRange(path=relative_path, start_line=1, end_line=_line_count(path)),
    )


def _classify_kind(path: Path) -> EntityKind | None:
    suffix = path.suffix.lower()
    if suffix in MODULE_EXTENSIONS:
        return "module"
    if suffix in DOC_EXTENSIONS:
        return "doc"
    return None


def _line_count(path: Path) -> int:
    try:
        with path.open("rb") as file:
            data = file.read()
    except OSError:
        return 1
    if not data:
        return 1
    return max(1, data.count(b"\n") + (0 if data.endswith(b"\n") else 1))


def _is_binary_looking(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            chunk = file.read(BINARY_SAMPLE_BYTES)
    except OSError:
        return True
    if b"\x00" in chunk:
        return True
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def should_index_repo_path(repo_root: Path | str, rel_path: str) -> bool:
    """Return whether a repo-relative file path is eligible for indexing."""
    root = Path(repo_root).resolve()
    normalized = rel_path.replace("\\", "/").strip("/")
    if not normalized:
        return False
    path = Path(normalized)
    if path.name.lower() in IGNORED_FILES:
        return False
    if is_generated_artifact_path(normalized):
        return False

    current = root
    for segment in path.parts[:-1]:
        if _should_ignore_directory_name(segment):
            return False
        current = current / segment
        if _should_ignore_directory_path(current, root):
            return False
    return True


def _should_ignore_directory_name(name: str) -> bool:
    if name in IGNORED_DIRECTORIES:
        return True
    return name.endswith(".egg-info")


def _should_ignore_directory_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(relative.startswith(prefix) for prefix in _IGNORED_PATH_PREFIXES)
