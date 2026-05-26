"""Filesystem extractor for deterministic file-level entities.

MVP choice: Python files are emitted as ``module`` entities keyed by repository-relative
file paths. A future schema may separate physical file entities from logical modules.
"""

from __future__ import annotations

import os
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


def extract_filesystem_entities(repo_root: Path | str) -> list[Entity]:
    """Extract deterministic file-level entities from a repository root."""
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")

    discovered: list[tuple[str, Path, EntityKind]] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not _should_ignore_directory_name(name)
            and not _should_ignore_directory_path(current_dir / name, root)
        )
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            relative_path = path.relative_to(root).as_posix()
            if not should_index_repo_path(root, relative_path):
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
