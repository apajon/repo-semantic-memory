"""Metric correctness tests for retrieval evaluation."""

from __future__ import annotations

from repo_semantic_memory.eval.metrics import RetrievalOutcome, compute_benchmark_metrics


def test_compute_benchmark_metrics_on_synthetic_data() -> None:
    outcomes = (
        RetrievalOutcome(
            task_id="t1",
            category="code_localization",
            prompt="find alpha",
            ranked_files=("src/a.py", "src/b.py"),
            ranked_symbols=("pkg.alpha", "pkg.beta"),
            gold_files=("src/a.py", "src/missing.py"),
            gold_symbols=("pkg.alpha", "pkg.missing"),
            gold_invariants=(),
            missing_gold_files=("src/missing.py",),
            missing_gold_symbols=("pkg.missing",),
            context_character_estimate=42,
        ),
    )

    metrics = compute_benchmark_metrics(outcomes, k_values=(1, 2))

    task = metrics.per_task[0]
    assert task.recall_at_k_files == {1: 0.5, 2: 0.5}
    assert task.recall_at_k_symbols == {1: 0.5, 2: 0.5}
    assert task.mrr_files == 1.0
    assert task.mrr_symbols == 1.0
    assert task.gold_file_coverage == 0.5
    assert task.gold_symbol_coverage == 0.5
    assert task.context_character_estimate == 42

    aggregate = metrics.aggregate
    assert aggregate.mrr_files == 1.0
    assert aggregate.mrr_symbols == 1.0
    assert aggregate.gold_file_coverage == 0.5
    assert aggregate.gold_symbol_coverage == 0.5


def test_mrr_uses_first_ranked_gold_match() -> None:
    outcomes = (
        RetrievalOutcome(
            task_id="t2",
            category="code_localization",
            prompt="find target",
            ranked_files=("src/nope.py", "src/also_nope.py", "src/hit.py", "src/hit2.py"),
            ranked_symbols=("pkg.none",),
            gold_files=("src/hit2.py", "src/hit.py"),
            gold_symbols=(),
            gold_invariants=(),
            missing_gold_files=(),
            missing_gold_symbols=(),
            context_character_estimate=12,
        ),
    )

    metrics = compute_benchmark_metrics(outcomes, k_values=(1, 3))

    assert metrics.per_task[0].mrr_files == 1 / 3
