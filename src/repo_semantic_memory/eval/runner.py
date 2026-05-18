"""Deterministic lexical retrieval benchmark runner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from repo_semantic_memory.eval.datasets import RetrievalTask, load_retrieval_dataset
from repo_semantic_memory.eval.metrics import (
    BenchmarkMetrics,
    RetrievalOutcome,
    compute_benchmark_metrics,
)
from repo_semantic_memory.model import Entity
from repo_semantic_memory.store import SQLiteStore

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_SYMBOL_KINDS = frozenset(
    {"repository", "package", "module", "class", "function", "method", "field", "test"}
)


@dataclass(frozen=True)
class RetrievalBenchmarkResult:
    """Full retrieval benchmark result payload."""

    dataset_path: str
    db_path: str
    k_values: tuple[int, ...]
    outcomes: tuple[RetrievalOutcome, ...]
    metrics: BenchmarkMetrics


def run_retrieval_benchmark(
    *,
    db_path: Path | str,
    dataset_path: Path | str,
    k_values: tuple[int, ...] = (1, 3, 5, 10),
    max_ranked_results: int = 20,
) -> RetrievalBenchmarkResult:
    """Run the retrieval baseline benchmark from SQLite entities and a YAML dataset."""
    dataset = load_retrieval_dataset(dataset_path)
    entities = _load_entities(db_path)
    outcomes = tuple(
        _run_task(
            entities=entities,
            task=task,
            max_ranked_results=max_ranked_results,
        )
        for task in dataset.tasks
    )
    metrics = compute_benchmark_metrics(outcomes, k_values=k_values)
    return RetrievalBenchmarkResult(
        dataset_path=str(Path(dataset_path)),
        db_path=str(Path(db_path)),
        k_values=k_values,
        outcomes=outcomes,
        metrics=metrics,
    )


def _load_entities(db_path: Path | str) -> tuple[Entity, ...]:
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        entities = store.list_entities()
    finally:
        store.close()
    return tuple(entities)


def _run_task(
    *,
    entities: tuple[Entity, ...],
    task: RetrievalTask,
    max_ranked_results: int,
) -> RetrievalOutcome:
    prompt_tokens = _tokenize(task.prompt)
    file_scores: dict[str, tuple[int, str]] = {}
    symbol_scores: dict[str, tuple[int, str]] = {}

    available_files = {entity.source_range.path for entity in entities}
    available_symbols = {
        entity.qualified_name
        for entity in entities
        if entity.kind in _SYMBOL_KINDS and entity.qualified_name
    }

    for entity in entities:
        score = _score_entity(entity, prompt_tokens)
        file_path = entity.source_range.path
        prior_file = file_scores.get(file_path)
        sort_key = entity.id.value
        if (
            prior_file is None
            or score > prior_file[0]
            or (score == prior_file[0] and sort_key < prior_file[1])
        ):
            file_scores[file_path] = (score, sort_key)

        if entity.kind not in _SYMBOL_KINDS:
            continue
        symbol = entity.qualified_name
        prior_symbol = symbol_scores.get(symbol)
        if (
            prior_symbol is None
            or score > prior_symbol[0]
            or (score == prior_symbol[0] and sort_key < prior_symbol[1])
        ):
            symbol_scores[symbol] = (score, sort_key)

    ranked_files = tuple(
        path
        for path, _ in sorted(
            file_scores.items(),
            key=lambda item: (-item[1][0], item[0], item[1][1]),
        )[:max_ranked_results]
    )
    ranked_symbols = tuple(
        symbol
        for symbol, _ in sorted(
            symbol_scores.items(),
            key=lambda item: (-item[1][0], item[0], item[1][1]),
        )[:max_ranked_results]
    )

    missing_gold_files = tuple(sorted(set(task.gold.files) - available_files))
    missing_gold_symbols = tuple(sorted(set(task.gold.symbols) - available_symbols))

    context_character_estimate = _estimate_context_characters(ranked_files, ranked_symbols)
    return RetrievalOutcome(
        task_id=task.id,
        category=task.category,
        prompt=task.prompt,
        ranked_files=ranked_files,
        ranked_symbols=ranked_symbols,
        gold_files=task.gold.files,
        gold_symbols=task.gold.symbols,
        gold_invariants=task.gold.invariants,
        missing_gold_files=missing_gold_files,
        missing_gold_symbols=missing_gold_symbols,
        context_character_estimate=context_character_estimate,
    )


def _score_entity(entity: Entity, prompt_tokens: tuple[str, ...]) -> int:
    haystacks = [
        entity.name,
        entity.qualified_name,
        entity.source_range.path,
        *_metadata_strings(entity.metadata),
    ]
    text = " ".join(value.lower() for value in haystacks if value)
    if not text:
        return 0

    text_tokens = set(_tokenize(text))
    exact_token_hits = sum(1 for token in prompt_tokens if token in text_tokens)
    substring_hits = sum(1 for token in prompt_tokens if token and token in text)
    return exact_token_hits * 10 + substring_hits


def _metadata_strings(value: object) -> list[str]:
    strings: list[str] = []
    _collect_metadata_strings(value, strings)
    return strings


def _collect_metadata_strings(value: object, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_metadata_strings(item, out)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_metadata_strings(item, out)


def _tokenize(text: str) -> tuple[str, ...]:
    tokens = sorted({token.lower() for token in _TOKEN_PATTERN.findall(text)})
    return tuple(tokens)


def _estimate_context_characters(
    ranked_files: tuple[str, ...], ranked_symbols: tuple[str, ...]
) -> int:
    """Return a simple newline-joined character estimate for baseline context size."""
    return len("\n".join([*ranked_files, *ranked_symbols]))
