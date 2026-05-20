"""Deterministic public API export resolver for Python __init__.py files.

Extracts explicit export patterns from ``__init__.py`` files using static AST
analysis only.  No imports are executed; no dynamic resolution is performed.

Supported patterns:
- ``from module import Name``
- ``from module import Name as Alias``
- ``import module``
- ``import module as Alias``
- ``__all__ = [...]`` when statically visible at module level

Produces ``exports`` relations from the ``__init__.py`` module entity to
unresolved symbol targets.  Evidence is anchored to the export statement source
range in the ``__init__.py`` file.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

from repo_semantic_memory.extractors.filesystem import (
    _should_ignore_directory_name,
    _should_ignore_directory_path,
)
from repo_semantic_memory.model import JsonValue, Relation, SourceRange, StableId
from repo_semantic_memory.model.evidence import Evidence

_EXTRACTOR = "python_exports"
_EXPORT_CONFIDENCE = 0.9
_ALL_CONFIDENCE = 0.95


def extract_python_exports(
    repo_root: Path | str,
    python_file: Path | str,
) -> list[Relation]:
    """Extract explicit exports from a single ``__init__.py`` file.

    Returns a list of ``exports`` relations.  Non-``__init__.py`` files
    return an empty list without raising.

    Args:
        repo_root: Absolute path to the repository root directory.
        python_file: Absolute path to the Python file to inspect.

    Returns:
        Sorted list of ``exports`` Relation objects.
    """
    root = Path(repo_root).resolve()
    path = Path(python_file).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")
    if not path.is_file():
        raise ValueError(f"Python file does not exist or is not a file: {path}")
    if path.suffix.lower() != ".py":
        raise ValueError(f"Expected a .py file, got: {path}")
    if path.name != "__init__.py":
        return []
    try:
        relative_path = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Python file is outside repository root: {path}") from exc

    source = path.read_text(encoding="utf-8")
    try:
        module_ast = ast.parse(source, filename=relative_path)
    except SyntaxError:
        return []

    module_qualified_name = _module_qualified_name(relative_path)
    module_entity_id = _module_entity_id(relative_path, module_qualified_name)

    # Collect __all__ names for via_all annotation.
    all_names: set[str] = _extract_all_names(module_ast)

    relations: list[Relation] = []

    # Track exports produced from import statements to avoid duplicates.
    seen_export_names: set[str] = set()

    for node in module_ast.body:
        if isinstance(node, ast.ImportFrom):
            relations.extend(
                _export_relations_from_import_from(
                    node,
                    relative_path=relative_path,
                    module_entity_id=module_entity_id,
                    all_names=all_names,
                    seen_export_names=seen_export_names,
                )
            )
        elif isinstance(node, ast.Import):
            relations.extend(
                _export_relations_from_import(
                    node,
                    relative_path=relative_path,
                    module_entity_id=module_entity_id,
                    all_names=all_names,
                    seen_export_names=seen_export_names,
                )
            )

    # Create exports relations for __all__ entries without a matching import.
    for name in sorted(all_names):
        if name not in seen_export_names:
            source_range = _module_source_range(relative_path, module_ast)
            relations.append(
                Relation(
                    source_entity_id=module_entity_id,
                    target_entity_id=_unresolved_export_id(module_qualified_name, name),
                    kind="exports",
                    evidence=Evidence(
                        source_range=source_range,
                        extractor=_EXTRACTOR,
                        confidence=_ALL_CONFIDENCE,
                        note="__all__-only export; no corresponding import statement found",
                    ),
                    metadata={
                        "exported_name": name,
                        "resolved": False,
                        "via_all": True,
                    },
                )
            )

    return _sort_relations(relations)


def index_python_exports(path: Path | str) -> list[Relation]:
    """Index exports from all ``__init__.py`` files under a path.

    Args:
        path: Repository root directory to index recursively.

    Returns:
        Sorted list of all ``exports`` Relation objects found.
    """
    target = Path(path).resolve()
    if not target.exists():
        raise ValueError(f"Path does not exist: {target}")
    if not target.is_dir():
        # Single file case: delegate to extract_python_exports.
        root = _infer_repo_root_for_file(target)
        return extract_python_exports(root, target)

    root = target
    relations: list[Relation] = []
    for init_file in _iter_init_files(root):
        file_relations = extract_python_exports(root, init_file)
        relations.extend(file_relations)
    return _sort_relations(relations)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _export_relations_from_import_from(
    node: ast.ImportFrom,
    *,
    relative_path: str,
    module_entity_id: StableId,
    all_names: set[str],
    seen_export_names: set[str],
) -> list[Relation]:
    source_range = _node_source_range(relative_path, node)
    module_prefix = "." * node.level + (node.module or "")
    relations: list[Relation] = []
    for alias in node.names:
        if alias.name == "*":
            continue
        exported_name = alias.asname if alias.asname else alias.name
        original_name = alias.name if alias.asname else None
        via_all = exported_name in all_names
        seen_export_names.add(exported_name)
        metadata: dict[str, JsonValue] = {
            "exported_name": exported_name,
            "resolved": False,
            "source_module": module_prefix,
            "via_all": via_all,
        }
        if original_name is not None:
            metadata["original_name"] = original_name
        relations.append(
            Relation(
                source_entity_id=module_entity_id,
                target_entity_id=_unresolved_export_id(
                    _module_qualified_name(relative_path), exported_name
                ),
                kind="exports",
                evidence=Evidence(
                    source_range=source_range,
                    extractor=_EXTRACTOR,
                    confidence=_ALL_CONFIDENCE if via_all else _EXPORT_CONFIDENCE,
                    note="explicit __all__ export" if via_all else "re-export from __init__.py",
                ),
                metadata=metadata,
            )
        )
    return relations


def _export_relations_from_import(
    node: ast.Import,
    *,
    relative_path: str,
    module_entity_id: StableId,
    all_names: set[str],
    seen_export_names: set[str],
) -> list[Relation]:
    source_range = _node_source_range(relative_path, node)
    relations: list[Relation] = []
    for alias in node.names:
        exported_name = alias.asname if alias.asname else alias.name
        original_name = alias.name if alias.asname else None
        via_all = exported_name in all_names
        seen_export_names.add(exported_name)
        metadata: dict[str, JsonValue] = {
            "exported_name": exported_name,
            "resolved": False,
            "source_module": alias.name,
            "via_all": via_all,
        }
        if original_name is not None:
            metadata["original_name"] = original_name
        relations.append(
            Relation(
                source_entity_id=module_entity_id,
                target_entity_id=_unresolved_export_id(
                    _module_qualified_name(relative_path), exported_name
                ),
                kind="exports",
                evidence=Evidence(
                    source_range=source_range,
                    extractor=_EXTRACTOR,
                    confidence=_ALL_CONFIDENCE if via_all else _EXPORT_CONFIDENCE,
                    note="explicit __all__ export"
                    if via_all
                    else "module re-export from __init__.py",
                ),
                metadata=metadata,
            )
        )
    return relations


def _extract_all_names(module_ast: ast.Module) -> set[str]:
    """Return names listed in a top-level ``__all__ = [...]`` assignment, if any."""
    for node in module_ast.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "__all__"):
                continue
            if not isinstance(node.value, ast.List):
                continue
            names: set[str] = set()
            for elt in node.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    names.add(elt.value)
            return names
    return set()


def _module_qualified_name(relative_path: str) -> str:
    """Derive the logical module qualified name from a repository-relative path.

    Mirrors the logic in ``python_ast._module_qualified_name`` for ID consistency.
    """
    logical_path = relative_path.removeprefix("src/")
    module_path = logical_path.removesuffix(".py")
    parts = [part for part in module_path.split("/") if part]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return "__init__"
    return ".".join(parts)


def _module_entity_id(relative_path: str, qualified_name: str) -> StableId:
    """Compute the stable entity ID for a module, matching ``python_ast`` convention."""
    return StableId.from_parts(["python", relative_path, "module", qualified_name])


def _unresolved_export_id(module_qualified_name: str, exported_name: str) -> StableId:
    """Build a deterministic unresolved symbol target ID for an export."""
    return StableId.from_parts(["unresolved", "export", module_qualified_name, exported_name])


def _node_source_range(relative_path: str, node: ast.AST) -> SourceRange:
    start_line = getattr(node, "lineno", 1)
    end_line = getattr(node, "end_lineno", start_line)
    start_col_raw = getattr(node, "col_offset", None)
    end_col_raw = getattr(node, "end_col_offset", None)
    start_col = (max(1, start_col_raw + 1)) if start_col_raw is not None else None
    end_col = (max(1, end_col_raw)) if end_col_raw is not None else None
    return SourceRange(
        path=relative_path,
        start_line=start_line,
        end_line=end_line,
        start_col=start_col,
        end_col=end_col,
    )


def _module_source_range(relative_path: str, module_ast: ast.Module) -> SourceRange:
    """Return a minimal source range pinned to the module's first line."""
    return SourceRange(path=relative_path, start_line=1, end_line=1)


def _sort_relations(relations: list[Relation]) -> list[Relation]:
    return sorted(
        relations,
        key=lambda r: (
            r.kind,
            r.source_entity_id.value,
            r.target_entity_id.value,
            tuple(sorted((k, str(v)) for k, v in r.metadata.items())),
        ),
    )


def _iter_init_files(root: Path) -> list[Path]:
    discovered: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not _should_ignore_directory_name(name)
            and not _should_ignore_directory_path(current_dir / name, root)
        )
        for filename in sorted(filenames):
            if filename == "__init__.py":
                discovered.append(Path(dirpath) / filename)
    return discovered


def _infer_repo_root_for_file(path: Path) -> Path:
    for candidate in [path.parent, *path.parents]:
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return path.parent
