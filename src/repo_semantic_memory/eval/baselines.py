"""Baseline evaluation utilities for context retrieval comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from repo_semantic_memory.context import (
    build_context_pack,
    build_repo_map_markdown,
    render_context_pack_markdown,
)
from repo_semantic_memory.eval.datasets import RetrievalTask
from repo_semantic_memory.model import Entity, Relation

BaselineName = Literal["repo_map", "lexical_context_pack"]
WinnerName = Literal["repo_map", "lexical_context_pack", "tie", "inconclusive"]

_HEADING_PATTERN = re.compile(r"^##\s+(.+)$")
_SYMBOL_LINE_PATTERN = re.compile(
    r"^\s*-\s+(?:module|class|function|method)\s+`([^`]+)`\s+([^:\s]+):\d"
)


@dataclass(frozen=True)
class BaselineTaskResult:
    """Per-task baseline result payload."""

    baseline: BaselineName
    context_character_count: int
    selected_files: tuple[str, ...]
    selected_symbols: tuple[str, ...]
    gold_file_coverage: float
    gold_symbol_coverage: float
    useful_context_ratio: float
    missing_gold_files: tuple[str, ...]
    missing_gold_symbols: tuple[str, ...]
    extra_selected_files: tuple[str, ...]
    extra_selected_symbols: tuple[str, ...]


@dataclass(frozen=True)
class TaskBaselineComparison:
    """Two-baseline comparison result for one benchmark task."""

    task_id: str
    category: str
    prompt: str
    gold_files: tuple[str, ...]
    gold_symbols: tuple[str, ...]
    repo_map: BaselineTaskResult
    lexical_context_pack: BaselineTaskResult
    winner: WinnerName


def evaluate_task_baselines(
    *,
    task: RetrievalTask,
    entities: tuple[Entity, ...],
    relations: tuple[Relation, ...],
    budget_chars: int,
) -> TaskBaselineComparison:
    """Evaluate both baselines for one task using the same budget."""
    repo_map_result = _evaluate_repo_map_baseline(
        task=task,
        entities=entities,
        relations=relations,
        budget_chars=budget_chars,
    )
    lexical_result = _evaluate_lexical_context_pack_baseline(
        task=task,
        entities=entities,
        relations=relations,
        budget_chars=budget_chars,
    )
    winner = decide_winner(repo_map_result, lexical_result)
    return TaskBaselineComparison(
        task_id=task.id,
        category=task.category,
        prompt=task.prompt,
        gold_files=task.gold.files,
        gold_symbols=task.gold.symbols,
        repo_map=repo_map_result,
        lexical_context_pack=lexical_result,
        winner=winner,
    )


def decide_winner(
    repo_map_result: BaselineTaskResult,
    lexical_context_pack_result: BaselineTaskResult,
) -> WinnerName:
    """Choose task-level winner from approximate useful-context ratio."""
    if (
        repo_map_result.useful_context_ratio == 0.0
        and lexical_context_pack_result.useful_context_ratio == 0.0
    ):
        return "inconclusive"
    if repo_map_result.useful_context_ratio == lexical_context_pack_result.useful_context_ratio:
        return "tie"
    if repo_map_result.useful_context_ratio > lexical_context_pack_result.useful_context_ratio:
        return "repo_map"
    return "lexical_context_pack"


def _evaluate_repo_map_baseline(
    *,
    task: RetrievalTask,
    entities: tuple[Entity, ...],
    relations: tuple[Relation, ...],
    budget_chars: int,
) -> BaselineTaskResult:
    markdown = build_repo_map_markdown(entities, relations, budget_chars=budget_chars)
    selected_files, selected_entities = _extract_repo_map_selection(markdown, entities)
    return _build_task_result(
        baseline="repo_map",
        task=task,
        selected_files=selected_files,
        selected_entities=selected_entities,
        context_character_count=len(markdown),
    )


def _evaluate_lexical_context_pack_baseline(
    *,
    task: RetrievalTask,
    entities: tuple[Entity, ...],
    relations: tuple[Relation, ...],
    budget_chars: int,
) -> BaselineTaskResult:
    context_pack = build_context_pack(
        task=task.prompt,
        entities=entities,
        relations=relations,
        budget_chars=budget_chars,
    )
    markdown = render_context_pack_markdown(context_pack)
    selected_files = tuple(context_pack.suggested_files_to_inspect)
    selected_entities = tuple(context_pack.selected_entities)
    return _build_task_result(
        baseline="lexical_context_pack",
        task=task,
        selected_files=selected_files,
        selected_entities=selected_entities,
        context_character_count=len(markdown),
    )


def _extract_repo_map_selection(
    markdown: str,
    entities: tuple[Entity, ...],
) -> tuple[tuple[str, ...], tuple[Entity, ...]]:
    selected_files: list[str] = []
    selected_file_set: set[str] = set()
    selected_entity_ids: list[str] = []
    selected_entity_set: set[str] = set()

    by_alias = _entities_by_alias(entities)
    by_id = {entity.id.value: entity for entity in entities}

    for line in markdown.splitlines():
        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            path = heading_match.group(1).replace("\\", "/")
            if path not in selected_file_set:
                selected_file_set.add(path)
                selected_files.append(path)
            continue

        symbol_match = _SYMBOL_LINE_PATTERN.match(line)
        if not symbol_match:
            continue
        label = symbol_match.group(1)
        path_hint = symbol_match.group(2).replace("\\", "/")
        entity = _select_entity_for_label(by_alias, label=label, path_hint=path_hint)
        if entity is None or entity.id.value in selected_entity_set:
            continue
        selected_entity_set.add(entity.id.value)
        selected_entity_ids.append(entity.id.value)

    selected_entities = tuple(by_id[entity_id] for entity_id in selected_entity_ids)
    return tuple(selected_files), selected_entities


def _select_entity_for_label(
    by_alias: dict[str, tuple[Entity, ...]],
    *,
    label: str,
    path_hint: str,
) -> Entity | None:
    candidates = by_alias.get(label, ())
    if not candidates:
        return None
    path_candidates = [
        entity
        for entity in candidates
        if entity.source_range.path.replace("\\", "/") == path_hint
    ]
    pool = path_candidates if path_candidates else list(candidates)
    return sorted(pool, key=lambda entity: entity.id.value)[0]


def _build_task_result(
    *,
    baseline: BaselineName,
    task: RetrievalTask,
    selected_files: tuple[str, ...],
    selected_entities: tuple[Entity, ...],
    context_character_count: int,
) -> BaselineTaskResult:
    selected_symbol_aliases: set[str] = set()
    selected_symbols: list[str] = []
    for entity in selected_entities:
        selected_symbols.append(entity.qualified_name)
        selected_symbol_aliases.update(_symbol_aliases(entity))

    missing_gold_files = tuple(sorted(set(task.gold.files) - set(selected_files)))
    missing_gold_symbols = tuple(
        sorted(
            gold_symbol
            for gold_symbol in set(task.gold.symbols)
            if gold_symbol not in selected_symbol_aliases
        )
    )

    gold_file_hits = len(set(task.gold.files) & set(selected_files))
    gold_symbol_hits = len(set(task.gold.symbols) - set(missing_gold_symbols))

    extra_selected_files = tuple(sorted(set(selected_files) - set(task.gold.files)))
    extra_selected_symbols = tuple(
        sorted(
            symbol
            for symbol, entity in zip(selected_symbols, selected_entities, strict=True)
            if not (set(task.gold.symbols) & _symbol_aliases(entity))
        )
    )

    useful_context_ratio = _approximate_useful_context_ratio(
        gold_file_hits=gold_file_hits,
        gold_symbol_hits=gold_symbol_hits,
        selected_file_count=len(selected_files),
        selected_symbol_count=len(selected_symbols),
    )

    return BaselineTaskResult(
        baseline=baseline,
        context_character_count=context_character_count,
        selected_files=selected_files,
        selected_symbols=tuple(selected_symbols),
        gold_file_coverage=_coverage(task.gold.files, missing_gold_files),
        gold_symbol_coverage=_coverage(task.gold.symbols, missing_gold_symbols),
        useful_context_ratio=useful_context_ratio,
        missing_gold_files=missing_gold_files,
        missing_gold_symbols=missing_gold_symbols,
        extra_selected_files=extra_selected_files,
        extra_selected_symbols=extra_selected_symbols,
    )


def _entities_by_alias(entities: tuple[Entity, ...]) -> dict[str, tuple[Entity, ...]]:
    grouped: dict[str, list[Entity]] = {}
    for entity in entities:
        for alias in _symbol_aliases(entity):
            grouped.setdefault(alias, []).append(entity)
    return {
        alias: tuple(sorted(group, key=lambda entity: entity.id.value))
        for alias, group in sorted(grouped.items())
    }


def _symbol_aliases(entity: Entity) -> set[str]:
    return {entity.qualified_name, entity.name, entity.id.value}


def _coverage(gold: tuple[str, ...], missing: tuple[str, ...]) -> float:
    if not gold:
        return 1.0
    return (len(gold) - len(missing)) / len(gold)


def _approximate_useful_context_ratio(
    *,
    gold_file_hits: int,
    gold_symbol_hits: int,
    selected_file_count: int,
    selected_symbol_count: int,
) -> float:
    selected_item_count = selected_file_count + selected_symbol_count
    if selected_item_count < 1:
        return 0.0
    useful_item_count = gold_file_hits + gold_symbol_hits
    return useful_item_count / selected_item_count
