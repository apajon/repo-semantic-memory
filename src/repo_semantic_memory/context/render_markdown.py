"""Markdown renderer for compact context packs."""

from __future__ import annotations

from repo_semantic_memory.context.budget import CharacterBudget
from repo_semantic_memory.context.context_pack import ContextPack
from repo_semantic_memory.model import Entity, Relation


def render_context_pack_markdown(context_pack: ContextPack) -> str:
    """Render a compact deterministic Markdown context pack."""
    budget = CharacterBudget(max_chars=context_pack.budget)
    entity_by_id = {entity.id.value: entity for entity in context_pack.selected_entities}

    if not _append_or_truncate(budget, "# Context pack"):
        return budget.render()
    if not _append_or_truncate(budget, ""):
        return budget.render()
    if not _append_or_truncate(budget, f"Task: {context_pack.task}"):
        return budget.render()
    if not _append_or_truncate(budget, ""):
        return budget.render()

    if not _append_selected_symbols(
        budget=budget,
        entities=context_pack.selected_entities,
        why_selected=context_pack.why_selected,
    ):
        return budget.render()
    if not _append_related_symbols(
        budget=budget,
        relations=context_pack.selected_relations,
        entity_by_id=entity_by_id,
        why_selected=context_pack.why_selected,
    ):
        return budget.render()
    if not _append_suggested_files(
        budget=budget,
        files=context_pack.suggested_files_to_inspect,
    ):
        return budget.render()
    if not _append_forbidden_assumptions(
        budget=budget,
        assumptions=context_pack.forbidden_assumptions,
    ):
        return budget.render()
    if not _append_uncertainties(
        budget=budget,
        uncertainties=context_pack.uncertainties,
    ):
        return budget.render()
    if not _append_source_citations(budget=budget, context_pack=context_pack):
        return budget.render()

    if context_pack.truncated:
        budget.append_truncation_notice()
    return budget.render()


def _append_selected_symbols(
    *,
    budget: CharacterBudget,
    entities: tuple[Entity, ...],
    why_selected: dict[str, tuple[str, ...]],
) -> bool:
    if not _append_or_truncate(budget, "## Selected symbols"):
        return False
    if not entities:
        if not _append_or_truncate(budget, "- none"):
            return False
        if not _append_or_truncate(budget, ""):
            return False
        return True
    for entity in entities:
        if not _append_or_truncate(
            budget,
            f"- `{entity.qualified_name}` {_format_source_citation(entity)}",
        ):
            return False
        reasons = why_selected.get(entity.id.value, ())
        # Keep output compact by showing only the first deterministic reason.
        if reasons and not _append_or_truncate(budget, f"  Reason: {reasons[0]}"):
            return False
    return _append_or_truncate(budget, "")


def _append_related_symbols(
    *,
    budget: CharacterBudget,
    relations: tuple[Relation, ...],
    entity_by_id: dict[str, Entity],
    why_selected: dict[str, tuple[str, ...]],
) -> bool:
    if not _append_or_truncate(budget, "## Related symbols"):
        return False
    if not relations:
        if not _append_or_truncate(budget, "- none"):
            return False
        if not _append_or_truncate(budget, ""):
            return False
        return True
    for relation in relations:
        source = _entity_label(entity_by_id, relation.source_entity_id.value)
        target = _entity_label(entity_by_id, relation.target_entity_id.value)
        resolution = relation.metadata.get("resolved")
        resolution_text = ""
        if isinstance(resolution, bool):
            resolution_text = f" (resolved: {str(resolution).lower()})"
        line = f"- `{source}` --{relation.kind}--> `{target}`{resolution_text}"
        if not _append_or_truncate(budget, line):
            return False
        key = (
            "relation:"
            f"{relation.kind}:{relation.source_entity_id.value}->{relation.target_entity_id.value}"
        )
        reasons = why_selected.get(key, ())
        # Keep output compact by showing only the first deterministic reason.
        if reasons and not _append_or_truncate(budget, f"  Reason: {reasons[0]}"):
            return False
    return _append_or_truncate(budget, "")


def _append_suggested_files(*, budget: CharacterBudget, files: tuple[str, ...]) -> bool:
    if not _append_or_truncate(budget, "## Suggested files to inspect"):
        return False
    if not files:
        if not _append_or_truncate(budget, "- none"):
            return False
    for path in files:
        if not _append_or_truncate(budget, f"- `{path}`"):
            return False
    return _append_or_truncate(budget, "")


def _append_forbidden_assumptions(*, budget: CharacterBudget, assumptions: tuple[str, ...]) -> bool:
    if not _append_or_truncate(budget, "## Forbidden assumptions"):
        return False
    for assumption in assumptions:
        if not _append_or_truncate(budget, f"- {assumption}"):
            return False
    return _append_or_truncate(budget, "")


def _append_uncertainties(*, budget: CharacterBudget, uncertainties: tuple[str, ...]) -> bool:
    if not _append_or_truncate(budget, "## Uncertainties"):
        return False
    if not uncertainties and not _append_or_truncate(budget, "- none"):
        return False
    for uncertainty in uncertainties:
        if not _append_or_truncate(budget, f"- {uncertainty}"):
            return False
    return _append_or_truncate(budget, "")


def _append_source_citations(*, budget: CharacterBudget, context_pack: ContextPack) -> bool:
    if not _append_or_truncate(budget, "## Source citations"):
        return False
    if not context_pack.source_citations and not _append_or_truncate(budget, "- none"):
        return False
    for citation in context_pack.source_citations:
        line = (
            f"- {citation.subject_kind} `{citation.subject_id}` "
            f"{citation.path}:{citation.start_line}-{citation.end_line}"
        )
        if citation.note is not None:
            line = f"{line} ({citation.note})"
        if not _append_or_truncate(budget, line):
            return False
    return True


def _append_or_truncate(budget: CharacterBudget, line: str) -> bool:
    if budget.append_line(line):
        return True
    budget.append_truncation_notice()
    return False


def _entity_label(entity_by_id: dict[str, Entity], entity_id: str) -> str:
    entity = entity_by_id.get(entity_id)
    if entity is None:
        return entity_id
    return entity.qualified_name


def _format_source_citation(entity: Entity) -> str:
    source = entity.source_range
    path = source.path.replace("\\", "/")
    if source.start_line == source.end_line:
        return f"{path}:{source.start_line}"
    return f"{path}:{source.start_line}-{source.end_line}"
