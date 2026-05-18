"""Report rendering tests for retrieval benchmark evaluation."""

from __future__ import annotations

from repo_semantic_memory.eval.metrics import RetrievalOutcome, compute_benchmark_metrics
from repo_semantic_memory.eval.reports import render_compact_table, render_markdown_report
from repo_semantic_memory.eval.runner import RetrievalBenchmarkResult


def test_report_generation_outputs_expected_sections() -> None:
    outcomes = (
        RetrievalOutcome(
            task_id="report_001",
            category="code_localization",
            prompt="where is alpha",
            ranked_files=("src/a.py",),
            ranked_symbols=("pkg.alpha",),
            gold_files=("src/a.py",),
            gold_symbols=("pkg.alpha",),
            gold_invariants=("alpha_guard",),
            missing_gold_files=(),
            missing_gold_symbols=(),
            context_character_estimate=20,
        ),
    )
    metrics = compute_benchmark_metrics(outcomes, k_values=(1, 5))
    result = RetrievalBenchmarkResult(
        dataset_path="benchmarks/tasks.yaml",
        db_path=".rsm/index.sqlite",
        k_values=(1, 5),
        outcomes=outcomes,
        metrics=metrics,
    )

    table = render_compact_table(result)
    markdown = render_markdown_report(result)

    assert "task_id" in table
    assert "report_001" in table
    assert "# Retrieval benchmark report" in markdown
    assert "## Aggregate metrics" in markdown
    assert "## Task details" in markdown
