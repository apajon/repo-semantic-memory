"""Filesystem extractor for deterministic file-level entities."""

from __future__ import annotations

import os
from pathlib import Path

from repo_semantic_memory.model import Entity, EntityKind, SourceRange, StableId

IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
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
_BINARY_SAMPLE_BYTES = 8192


def extract_filesystem_entities(repo_root: Path | str) -> list[Entity]:
    """Extract deterministic file-level entities from a repository root."""
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")

    discovered: list[tuple[str, Path, EntityKind]] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRECTORIES)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if _is_binary_looking(path):
                continue
            kind = _classify_kind(path)
            if kind is None:
                continue
            relative_path = path.relative_to(root).as_posix()
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
    with path.open("rb") as file:
        data = file.read()
    if not data:
        return 1
    return max(1, data.count(b"\n") + (0 if data.endswith(b"\n") else 1))


def _is_binary_looking(path: Path) -> bool:
    with path.open("rb") as file:
        chunk = file.read(_BINARY_SAMPLE_BYTES)
    if b"\x00" in chunk:
        return True
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False
