"""Metric calculations for retrieval benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class RetrievalOutcome:
    """Raw retrieval outcome for one task."""

    task_id: str
    category: str
    prompt: str
    ranked_files: tuple[str, ...]
    ranked_symbols: tuple[str, ...]
    gold_files: tuple[str, ...]
    gold_symbols: tuple[str, ...]
    gold_invariants: tuple[str, ...]
    missing_gold_files: tuple[str, ...]
    missing_gold_symbols: tuple[str, ...]
    context_character_estimate: int


@dataclass(frozen=True)
class TaskMetrics:
    """Computed metrics for one retrieval task."""

    task_id: str
    category: str
    recall_at_k_files: dict[int, float]
    recall_at_k_symbols: dict[int, float]
    mrr_files: float
    mrr_symbols: float
    gold_file_coverage: float
    gold_symbol_coverage: float
    context_character_estimate: int


@dataclass(frozen=True)
class BenchmarkMetrics:
    """Per-task and aggregate retrieval metrics."""

    k_values: tuple[int, ...]
    per_task: tuple[TaskMetrics, ...]
    aggregate: AggregateMetrics


@dataclass(frozen=True)
class AggregateMetrics:
    """Aggregate benchmark metrics."""

    recall_at_k_files: dict[int, float]
    recall_at_k_symbols: dict[int, float]
    mrr_files: float
    mrr_symbols: float
    gold_file_coverage: float
    gold_symbol_coverage: float
    context_character_estimate: float


def compute_benchmark_metrics(
    outcomes: tuple[RetrievalOutcome, ...],
    *,
    k_values: tuple[int, ...],
) -> BenchmarkMetrics:
    """Compute per-task and aggregate benchmark metrics."""
    per_task = tuple(compute_task_metrics(outcome, k_values=k_values) for outcome in outcomes)
    if not per_task:
        raise ValueError("Benchmark run produced no task outcomes")

    aggregate = AggregateMetrics(
        recall_at_k_files={
            k: mean(task.recall_at_k_files[k] for task in per_task) for k in k_values
        },
        recall_at_k_symbols={
            k: mean(task.recall_at_k_symbols[k] for task in per_task) for k in k_values
        },
        mrr_files=mean(task.mrr_files for task in per_task),
        mrr_symbols=mean(task.mrr_symbols for task in per_task),
        gold_file_coverage=mean(task.gold_file_coverage for task in per_task),
        gold_symbol_coverage=mean(task.gold_symbol_coverage for task in per_task),
        context_character_estimate=mean(task.context_character_estimate for task in per_task),
    )
    return BenchmarkMetrics(k_values=k_values, per_task=per_task, aggregate=aggregate)


def compute_task_metrics(outcome: RetrievalOutcome, *, k_values: tuple[int, ...]) -> TaskMetrics:
    """Compute metrics for a single retrieval outcome."""
    recall_at_k_files = {
        k: _recall_at_k(outcome.gold_files, outcome.ranked_files, k=k) for k in k_values
    }
    recall_at_k_symbols = {
        k: _recall_at_k(outcome.gold_symbols, outcome.ranked_symbols, k=k) for k in k_values
    }
    return TaskMetrics(
        task_id=outcome.task_id,
        category=outcome.category,
        recall_at_k_files=recall_at_k_files,
        recall_at_k_symbols=recall_at_k_symbols,
        mrr_files=_mrr(outcome.gold_files, outcome.ranked_files),
        mrr_symbols=_mrr(outcome.gold_symbols, outcome.ranked_symbols),
        gold_file_coverage=_coverage(outcome.gold_files, outcome.missing_gold_files),
        gold_symbol_coverage=_coverage(outcome.gold_symbols, outcome.missing_gold_symbols),
        context_character_estimate=outcome.context_character_estimate,
    )


def _recall_at_k(gold: tuple[str, ...], ranked: tuple[str, ...], *, k: int) -> float:
    if not gold:
        return 1.0
    top_k = set(ranked[:k])
    hits = sum(1 for item in gold if item in top_k)
    return hits / len(gold)


def _mrr(gold: tuple[str, ...], ranked: tuple[str, ...]) -> float:
    """Return reciprocal rank of the first ranked item that matches any gold target."""
    if not gold:
        return 1.0
    gold_set = set(gold)
    for index, candidate in enumerate(ranked, start=1):
        if candidate in gold_set:
            return 1.0 / index
    return 0.0


def _coverage(gold: tuple[str, ...], missing: tuple[str, ...]) -> float:
    if not gold:
        return 1.0
    found = len(gold) - len(missing)
    return found / len(gold)
