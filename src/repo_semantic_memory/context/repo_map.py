"""Compact markdown repository map rendering from indexed entities and relations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from repo_semantic_memory.context.budget import CharacterBudget
from repo_semantic_memory.context.compression import (
    CompressionProfile,
    resolve_profile,
    trim_import_names,
)
from repo_semantic_memory.context.path_roles import (
    CI_ROLE,
    CONFIG_ROLE,
    DOC_ROLE,
    EXAMPLE_ROLE,
    GENERATED_ROLE,
    OTHER_ROLE,
    SOURCE_ROLE,
    TEST_ROLE,
    TOOL_ROLE,
    classify_path_role,
    infer_source_roots,
)
from repo_semantic_memory.model import Entity, Relation

_REPO_MAP_ROLE_PRIORITY: Final[dict[str, int]] = {
    # Lower number means higher priority in rendered module ordering.
    # We prioritize likely implementation/package code first, then supporting contexts.
    SOURCE_ROLE: 0,
    TEST_ROLE: 1,
    EXAMPLE_ROLE: 2,
    DOC_ROLE: 3,
    CI_ROLE: 4,
    CONFIG_ROLE: 4,
    TOOL_ROLE: 5,
    OTHER_ROLE: 6,
    GENERATED_ROLE: 7,
}


@dataclass(frozen=True)
class ModuleSection:
    """Flattened module section payload for deterministic rendering."""

    module: Entity
    classes: tuple[Entity, ...]
    functions: tuple[Entity, ...]
    methods_by_class_id: dict[str, tuple[Entity, ...]]
    imports: tuple[str, ...]


@dataclass(frozen=True)
class DocOutline:
    """Flattened Markdown outline payload for deterministic rendering."""

    doc: Entity
    sections: tuple[Entity, ...]


def build_repo_map_markdown(
    entities: Sequence[Entity],
    relations: Sequence[Relation],
    *,
    budget_chars: int,
    profile: CompressionProfile | str | None = None,
) -> str:
    """Build a compact Markdown repository map constrained by an approximate character budget."""
    resolved_profile = resolve_profile(profile)
    budget = CharacterBudget(max_chars=budget_chars)
    module_sections = _build_module_sections(entities, relations, profile=resolved_profile)
    doc_outlines = _build_doc_outlines(entities, relations)

    if not budget.append_line("# Repo map"):
        return "# Repo map"[:budget_chars]
    if not budget.append_line(""):
        return budget.render()

    for index, section in enumerate(module_sections):
        if index > 0 and not budget.append_line(""):
            budget.append_truncation_notice()
            break
        if not _append_module_section(budget, section):
            budget.append_truncation_notice()
            break

    need_separator = bool(module_sections)
    for outline in doc_outlines:
        if need_separator and not budget.append_line(""):
            budget.append_truncation_notice()
            break
        if not _append_doc_outline(budget, outline):
            budget.append_truncation_notice()
            break
        need_separator = True

    return budget.render()


def _build_module_sections(
    entities: Sequence[Entity],
    relations: Sequence[Relation],
    *,
    profile: CompressionProfile,
) -> list[ModuleSection]:
    entity_by_id = {entity.id.value: entity for entity in entities}
    contains_targets: dict[str, list[Entity]] = defaultdict(list)
    import_names_by_module_id: dict[str, set[str]] = defaultdict(set)

    for relation in relations:
        if relation.kind == "contains":
            target = entity_by_id.get(relation.target_entity_id.value)
            if target is not None:
                contains_targets[relation.source_entity_id.value].append(target)
            continue
        if relation.kind == "imports":
            relation_resolved = relation.metadata.get("resolved") is True
            if not profile.include_unresolved_imports and not relation_resolved:
                continue
            imported_name = relation.metadata.get("imported_name")
            if isinstance(imported_name, str):
                import_names_by_module_id[relation.source_entity_id.value].add(imported_name)

    source_roots = infer_source_roots(entities)
    modules = _preferred_module_entities(entities)
    sections: list[ModuleSection] = []
    for module in modules:
        contained = contains_targets.get(module.id.value, [])
        classes = tuple(entity for entity in _sort_entities(contained) if entity.kind == "class")
        functions = tuple(
            entity for entity in _sort_entities(contained) if entity.kind == "function"
        )
        methods_by_class_id = {
            class_entity.id.value: tuple(
                method
                for method in _sort_entities(contains_targets.get(class_entity.id.value, []))
                if method.kind == "method"
            )
            for class_entity in classes
        }
        imports = trim_import_names(
            tuple(sorted(import_names_by_module_id.get(module.id.value, set()))),
            profile=profile,
        )
        sections.append(
            ModuleSection(
                module=module,
                classes=classes,
                functions=functions,
                methods_by_class_id=methods_by_class_id,
                imports=imports,
            )
        )

    return sorted(
        sections, key=lambda section: _module_section_sort_key(section.module, source_roots)
    )


def _build_doc_outlines(
    entities: Sequence[Entity], relations: Sequence[Relation]
) -> list[DocOutline]:
    entity_by_id = {entity.id.value: entity for entity in entities}
    sections_by_doc_id: dict[str, list[Entity]] = defaultdict(list)

    for relation in relations:
        if relation.kind != "contains":
            continue
        source = entity_by_id.get(relation.source_entity_id.value)
        target = entity_by_id.get(relation.target_entity_id.value)
        if source is None or target is None:
            continue
        if (
            source.kind == "doc"
            and not _is_doc_section(source)
            and _is_markdown_doc(source)
            and _is_doc_section(target)
        ):
            sections_by_doc_id[source.id.value].append(target)

    outlines = [
        DocOutline(doc=doc, sections=tuple(_sort_entities(sections)))
        for doc_id, sections in sections_by_doc_id.items()
        if (doc := entity_by_id.get(doc_id)) is not None
    ]
    return sorted(outlines, key=lambda outline: _entity_sort_key(outline.doc))


def _preferred_module_entities(entities: Sequence[Entity]) -> list[Entity]:
    modules = [entity for entity in entities if entity.kind == "module"]
    python_modules_by_path: dict[str, list[Entity]] = defaultdict(list)
    passthrough_modules: list[Entity] = []

    for module in modules:
        if Path(module.source_range.path).suffix == ".py":
            python_modules_by_path[module.source_range.path].append(module)
            continue
        passthrough_modules.append(module)

    preferred_python_modules: list[Entity] = []
    for path in sorted(python_modules_by_path):
        candidates = python_modules_by_path[path]
        python_ast_candidates = [
            candidate for candidate in candidates if candidate.id.value.startswith("python:")
        ]
        selected_pool = python_ast_candidates if python_ast_candidates else candidates
        preferred_python_modules.append(sorted(selected_pool, key=_entity_sort_key)[0])

    all_modules = [*passthrough_modules, *preferred_python_modules]
    return sorted(all_modules, key=_entity_sort_key)


def _append_module_section(budget: CharacterBudget, section: ModuleSection) -> bool:
    module = section.module
    if not budget.append_line(f"## {_to_posix_path(module.source_range.path)}"):
        return False
    if not budget.append_line(
        f"- module `{module.qualified_name}` {_format_source_citation(module)}"
    ):
        return False

    for class_entity in section.classes:
        if not budget.append_line(
            f"- class `{class_entity.qualified_name}` {_format_source_citation(class_entity)}"
        ):
            return False
        for method in section.methods_by_class_id.get(class_entity.id.value, ()):
            if not budget.append_line(
                f"  - method `{method.name}` {_format_source_citation(method)}"
            ):
                return False

    for function in section.functions:
        if not budget.append_line(
            f"- function `{function.qualified_name}` {_format_source_citation(function)}"
        ):
            return False

    if section.imports:
        if not budget.append_line(""):
            return False
        if not budget.append_line("Static imports (unresolved):"):
            return False
        for imported_name in section.imports:
            if not budget.append_line(f"- `{imported_name}`"):
                return False
    return True


def _append_doc_outline(budget: CharacterBudget, outline: DocOutline) -> bool:
    doc = outline.doc
    if not budget.append_line(f"## {_to_posix_path(doc.source_range.path)}"):
        return False
    if not budget.append_line(f"- doc `{doc.qualified_name}` {_format_source_citation(doc)}"):
        return False
    for section in outline.sections:
        level = section.metadata.get("section_level")
        numeric_level = level if isinstance(level, int) else 1
        indent = "  " * max(0, numeric_level - 1)
        if not budget.append_line(
            f"{indent}- h{numeric_level} `{section.name}` {_format_source_citation(section)}"
        ):
            return False
    return True


def _format_source_citation(entity: Entity) -> str:
    source = entity.source_range
    path = _to_posix_path(source.path)
    if source.start_line == source.end_line:
        return f"{path}:{source.start_line}"
    return f"{path}:{source.start_line}-{source.end_line}"


def _to_posix_path(path: str) -> str:
    return path.replace("\\", "/")


def _entity_sort_key(entity: Entity) -> tuple[str, int, int, str, str]:
    return (
        entity.source_range.path,
        entity.source_range.start_line,
        entity.source_range.start_col or 0,
        entity.kind,
        entity.id.value,
    )


def _module_section_sort_key(
    entity: Entity, source_roots: Sequence[str]
) -> tuple[int, str, int, int, str, str]:
    return (
        _repo_map_path_priority(entity.source_range.path, source_roots),
        entity.source_range.path,
        entity.source_range.start_line,
        entity.source_range.start_col or 0,
        entity.kind,
        entity.id.value,
    )


def _repo_map_path_priority(path: str, source_roots: Sequence[str]) -> int:
    role = classify_path_role(path=path, source_roots=source_roots)
    return _REPO_MAP_ROLE_PRIORITY[role]


def _sort_entities(entities: Sequence[Entity]) -> list[Entity]:
    return sorted(entities, key=_entity_sort_key)


def _is_markdown_doc(entity: Entity) -> bool:
    return Path(entity.source_range.path).suffix.lower() in {".md", ".markdown"}


def _is_doc_section(entity: Entity) -> bool:
    return entity.kind == "doc" and entity.metadata.get("entity_type") == "doc_section"
