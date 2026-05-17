"""Python AST extractor for deterministic symbols and structural relations."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Literal, cast

from repo_semantic_memory.extractors.filesystem import IGNORED_DIRECTORIES
from repo_semantic_memory.model import Entity, JsonValue, Relation, SourceRange, StableId

DefinitionNode = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def extract_python_file(
    repo_root: Path | str,
    python_file: Path | str,
) -> tuple[list[Entity], list[Relation]]:
    """Extract Python entities and relations from a single file."""
    root = Path(repo_root).resolve()
    path = Path(python_file).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")
    if not path.is_file():
        raise ValueError(f"Python file does not exist or is not a file: {path}")
    if path.suffix.lower() != ".py":
        raise ValueError(f"Expected a .py file, got: {path}")
    try:
        relative_path = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Python file is outside repository root: {path}") from exc

    source = path.read_text(encoding="utf-8")
    module_ast = ast.parse(source, filename=relative_path)

    entities: list[Entity] = []
    relations: list[Relation] = []

    module_qualified_name = relative_path
    module_id = _entity_id(relative_path, "module", module_qualified_name)
    entities.append(
        Entity(
            id=module_id,
            kind="module",
            name=path.stem,
            qualified_name=module_qualified_name,
            source_range=_source_range(relative_path, module_ast),
            metadata={"has_docstring": ast.get_docstring(module_ast) is not None},
        )
    )

    for node in module_ast.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            relations.extend(_extract_import_relations(relative_path, module_id, node))
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = _build_function_entity(
                relative_path=relative_path,
                node=node,
                module_qualified_name=module_qualified_name,
                kind="function",
            )
            entities.append(function)
            relations.append(
                Relation(
                    source_entity_id=module_id,
                    target_entity_id=function.id,
                    kind="contains",
                )
            )
            continue
        if isinstance(node, ast.ClassDef):
            class_qualified_name = f"{module_qualified_name}.{node.name}"
            class_entity = Entity(
                id=_entity_id(relative_path, "class", class_qualified_name),
                kind="class",
                name=node.name,
                qualified_name=class_qualified_name,
                source_range=_source_range(relative_path, node),
                metadata=_metadata_for_definition(node),
            )
            entities.append(class_entity)
            relations.append(
                Relation(
                    source_entity_id=module_id,
                    target_entity_id=class_entity.id,
                    kind="contains",
                )
            )
            for base in node.bases:
                base_name = _static_name(base)
                if base_name is None:
                    continue
                relations.append(
                    Relation(
                        source_entity_id=class_entity.id,
                        target_entity_id=_external_symbol_id("inherits", base_name),
                        kind="inherits",
                        metadata={"base_name": base_name},
                    )
                )
            for class_body_node in node.body:
                if not isinstance(class_body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                method = _build_function_entity(
                    relative_path=relative_path,
                    node=class_body_node,
                    module_qualified_name=class_qualified_name,
                    kind="method",
                )
                entities.append(method)
                relations.append(
                    Relation(
                        source_entity_id=class_entity.id,
                        target_entity_id=method.id,
                        kind="contains",
                    )
                )

    return _sort_entities(entities), _sort_relations(relations)


def index_python_path(path: Path | str) -> tuple[list[Entity], list[Relation]]:
    """Index Python files from a file or directory path."""
    target = Path(path).resolve()
    if not target.exists():
        raise ValueError(f"Path does not exist: {target}")

    if target.is_file():
        if target.suffix.lower() != ".py":
            return [], []
        root = _infer_repo_root_for_file(target)
        file_entities, file_relations = extract_python_file(root, target)
        return file_entities, file_relations

    root = target
    entities: list[Entity] = []
    relations: list[Relation] = []
    for python_file in _iter_python_files(root):
        file_entities, file_relations = extract_python_file(root, python_file)
        entities.extend(file_entities)
        relations.extend(file_relations)
    return _sort_entities(entities), _sort_relations(relations)


def _iter_python_files(root: Path) -> list[Path]:
    discovered: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRECTORIES)
        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            if file_path.suffix.lower() == ".py":
                discovered.append(file_path)
    return discovered


def _metadata_for_definition(node: DefinitionNode) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {"has_docstring": ast.get_docstring(node) is not None}
    decorators = _decorators_for(node)
    if decorators:
        metadata["decorators"] = cast(JsonValue, decorators)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        metadata["signature"] = ast.unparse(node.args)
        metadata["is_async"] = isinstance(node, ast.AsyncFunctionDef)
    return metadata


def _build_function_entity(
    *,
    relative_path: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_qualified_name: str,
    kind: Literal["function", "method"],
) -> Entity:
    qualified_name = f"{module_qualified_name}.{node.name}"
    return Entity(
        id=_entity_id(relative_path, kind, qualified_name),
        kind=kind,
        name=node.name,
        qualified_name=qualified_name,
        source_range=_source_range(relative_path, node),
        metadata=_metadata_for_definition(node),
    )


def _extract_import_relations(
    relative_path: str,
    module_id: StableId,
    node: ast.Import | ast.ImportFrom,
) -> list[Relation]:
    imported_names = _imported_names(node)
    return [
        Relation(
            source_entity_id=module_id,
            target_entity_id=_external_symbol_id("imports", imported_name),
            kind="imports",
            metadata={"imported_name": imported_name},
        )
        for imported_name in imported_names
    ]


def _imported_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return sorted(alias.name for alias in node.names)

    module_prefix = "." * node.level + (node.module or "")
    names: list[str] = []
    for alias in node.names:
        if alias.name == "*":
            names.append(f"{module_prefix}.*" if module_prefix else "*")
        elif module_prefix:
            names.append(f"{module_prefix}.{alias.name}")
        else:
            names.append(alias.name)
    return sorted(names)


def _decorators_for(node: ast.AST) -> list[str]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return []
    decorators: list[str] = []
    for decorator in node.decorator_list:
        static_name = _static_name(decorator)
        if static_name is not None:
            decorators.append(static_name)
    return decorators


def _static_name(node: ast.expr) -> str | None:
    """Return a static name for simple expressions (name/attribute/call), else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _static_name(node.value)
        if parent is None:
            return None
        return f"{parent}.{node.attr}"
    if isinstance(node, ast.Call):
        called = _static_name(node.func)
        if called is None:
            return None
        return f"{called}()"
    return None


def _entity_id(relative_path: str, kind: str, qualified_name: str) -> StableId:
    return StableId.from_parts(["python", relative_path, kind, qualified_name])


def _external_symbol_id(relation_kind: str, name: str) -> StableId:
    return StableId.from_parts(["python", relation_kind, name])


def _source_range(relative_path: str, node: ast.AST) -> SourceRange:
    start_line = getattr(node, "lineno", 1)
    end_line = getattr(node, "end_lineno", start_line)
    # ast column offsets are 0-based; convert start to 1-based for SourceRange.
    # end_col_offset is an exclusive boundary; we preserve its value except clamping to >= 1.
    start_col = _normalize_column(getattr(node, "col_offset", None), add_one=True)
    end_col = _normalize_column(getattr(node, "end_col_offset", None), add_one=False)
    return SourceRange(
        path=relative_path,
        start_line=start_line,
        end_line=end_line,
        start_col=start_col,
        end_col=end_col,
    )


def _normalize_column(value: int | None, *, add_one: bool) -> int | None:
    if value is None:
        return None
    column = value + 1 if add_one else value
    return max(1, column)


def _sort_entities(entities: list[Entity]) -> list[Entity]:
    return sorted(
        entities,
        key=lambda entity: (
            entity.source_range.path,
            entity.source_range.start_line,
            entity.source_range.start_col or 0,
            entity.kind,
            entity.qualified_name,
            entity.id.value,
        ),
    )


def _sort_relations(relations: list[Relation]) -> list[Relation]:
    return sorted(
        relations,
        key=lambda relation: (
            relation.kind,
            relation.source_entity_id.value,
            relation.target_entity_id.value,
            tuple(sorted(relation.metadata.items())),
        ),
    )


def _infer_repo_root_for_file(path: Path) -> Path:
    for candidate in [path.parent, *path.parents]:
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return path.parent
