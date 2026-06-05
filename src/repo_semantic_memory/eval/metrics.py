"""Metric calculations for retrieval benchmark runs."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

APPROX_CHARS_PER_TOKEN = 4.0


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


@dataclass(frozen=True)
class TokenSavingsMetrics:
    """Deterministic token-savings metrics for baseline comparison tasks.

    Token estimates are approximate and intentionally tokenizer-agnostic in MVP:
    estimated_tokens = chars / APPROX_CHARS_PER_TOKEN
    """

    raw_baseline_chars: int
    selected_context_chars: int
    estimated_raw_tokens: float
    estimated_selected_tokens: float
    estimated_tokens_saved: float
    compression_ratio: float
    gold_file_coverage_preserved: bool
    gold_symbol_coverage_preserved: bool
    coverage_per_1k_tokens: float
    context_noise_ratio: float | None = None


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


def estimate_tokens_from_chars(chars: int) -> float:
    """Return deterministic approximate token count from character count."""
    if chars < 0:
        raise ValueError("chars must be >= 0")
    return chars / APPROX_CHARS_PER_TOKEN


def compute_token_savings_metrics(
    *,
    raw_baseline_chars: int,
    selected_context_chars: int,
    raw_gold_file_coverage: float,
    raw_gold_symbol_coverage: float,
    selected_gold_file_coverage: float,
    selected_gold_symbol_coverage: float,
    context_noise_ratio: float | None = None,
) -> TokenSavingsMetrics:
    """Compute deterministic token-savings and coverage-preservation metrics."""
    if raw_baseline_chars < 0:
        raise ValueError("raw_baseline_chars must be >= 0")
    if selected_context_chars < 0:
        raise ValueError("selected_context_chars must be >= 0")

    estimated_raw_tokens = estimate_tokens_from_chars(raw_baseline_chars)
    estimated_selected_tokens = estimate_tokens_from_chars(selected_context_chars)
    estimated_tokens_saved = estimated_raw_tokens - estimated_selected_tokens
    compression_ratio = _safe_compression_ratio(
        selected_chars=selected_context_chars, raw_chars=raw_baseline_chars
    )
    gold_file_coverage_preserved = selected_gold_file_coverage >= raw_gold_file_coverage
    gold_symbol_coverage_preserved = selected_gold_symbol_coverage >= raw_gold_symbol_coverage
    coverage_per_1k_tokens = _coverage_per_1k_tokens(
        gold_file_coverage=selected_gold_file_coverage,
        gold_symbol_coverage=selected_gold_symbol_coverage,
        estimated_tokens=estimated_selected_tokens,
    )

    return TokenSavingsMetrics(
        raw_baseline_chars=raw_baseline_chars,
        selected_context_chars=selected_context_chars,
        estimated_raw_tokens=estimated_raw_tokens,
        estimated_selected_tokens=estimated_selected_tokens,
        estimated_tokens_saved=estimated_tokens_saved,
        compression_ratio=compression_ratio,
        gold_file_coverage_preserved=gold_file_coverage_preserved,
        gold_symbol_coverage_preserved=gold_symbol_coverage_preserved,
        coverage_per_1k_tokens=coverage_per_1k_tokens,
        context_noise_ratio=context_noise_ratio,
    )


def token_savings_improvement_claim_allowed(metrics: TokenSavingsMetrics) -> bool:
    """Return True only when token savings are positive and gold coverage is preserved."""
    return (
        metrics.estimated_tokens_saved > 0.0
        and metrics.gold_file_coverage_preserved
        and metrics.gold_symbol_coverage_preserved
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


def _safe_compression_ratio(*, selected_chars: int, raw_chars: int) -> float:
    if raw_chars <= 0:
        # Deterministic sentinel for undefined division-by-zero case; kept finite and JSON-safe.
        return 1.0 if selected_chars <= 0 else 0.0
    return selected_chars / raw_chars


def _coverage_per_1k_tokens(
    *,
    gold_file_coverage: float,
    gold_symbol_coverage: float,
    estimated_tokens: float,
) -> float:
    if estimated_tokens <= 0.0:
        return 0.0
    return ((gold_file_coverage + gold_symbol_coverage) / estimated_tokens) * 1000.0


# ---------------------------------------------------------------------------
# 59.2 — Benchmark harness metrics
# ---------------------------------------------------------------------------

_BENCHMARK_WEIGHTS = {
    "central": 0.35,
    "support": 0.25,
    "tests": 0.20,
    "noise": 0.20,
}


@dataclass(frozen=True)
class BenchmarkCaseMetrics:
    """Per-case metrics for the 59.0 benchmark harness.

    All scores are in [0.0, 1.0].  ``central_file_found`` is binary; the other
    three are continuous ratios.  ``overall`` is the weighted aggregate.
    """

    central_file_found: float
    support_files_found: float
    tests_found: float
    noise_reduced: float
    overall: float


def compute_benchmark_case_metrics(
    *,
    selected_files: tuple[str, ...],
    expected_central: tuple[str, ...],
    expected_support: tuple[str, ...],
    expected_tests: tuple[str, ...],
    forbidden_files: tuple[str, ...],
) -> BenchmarkCaseMetrics:
    """Compute 59.0 harness metrics for a single benchmark case."""
    selected_set = frozenset(selected_files)
    central_set = frozenset(expected_central)

    # central_file_found: binary
    central_found = 1.0 if selected_set & central_set else 0.0

    # support_files_found
    if not expected_support:
        support_found = 1.0
    else:
        support_hits = sum(1 for f in expected_support if f in selected_set)
        support_found = support_hits / len(expected_support)

    # tests_found
    if not expected_tests:
        tests_found = 1.0
    else:
        test_hits = sum(1 for f in expected_tests if f in selected_set)
        tests_found = test_hits / len(expected_tests)

    # noise_reduced
    if not forbidden_files:
        noise_reduced = 1.0
    else:
        forbidden_hits = sum(1 for f in forbidden_files if f in selected_set)
        noise_ratio = forbidden_hits / max(1, len(selected_set))
        noise_reduced = 1.0 - min(1.0, noise_ratio)

    # overall weighted aggregate
    overall = (
        _BENCHMARK_WEIGHTS["central"] * central_found
        + _BENCHMARK_WEIGHTS["support"] * support_found
        + _BENCHMARK_WEIGHTS["tests"] * tests_found
        + _BENCHMARK_WEIGHTS["noise"] * noise_reduced
    )

    return BenchmarkCaseMetrics(
        central_file_found=central_found,
        support_files_found=support_found,
        tests_found=tests_found,
        noise_reduced=noise_reduced,
        overall=overall,
    )


def compute_aggregate_benchmark_case_metrics(
    per_case: tuple[BenchmarkCaseMetrics, ...],
) -> BenchmarkCaseMetrics:
    """Compute aggregate metrics as the mean of per-case metrics."""
    if not per_case:
        return BenchmarkCaseMetrics(
            central_file_found=0.0,
            support_files_found=0.0,
            tests_found=0.0,
            noise_reduced=0.0,
            overall=0.0,
        )
    return BenchmarkCaseMetrics(
        central_file_found=mean(m.central_file_found for m in per_case),
        support_files_found=mean(m.support_files_found for m in per_case),
        tests_found=mean(m.tests_found for m in per_case),
        noise_reduced=mean(m.noise_reduced for m in per_case),
        overall=mean(m.overall for m in per_case),
    )
