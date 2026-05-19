"""Report rendering tests for retrieval benchmark evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from repo_semantic_memory.eval.baselines import BaselineTaskResult, TaskBaselineComparison
from repo_semantic_memory.eval.metrics import (
    RetrievalOutcome,
    compute_benchmark_metrics,
    compute_token_savings_metrics,
)
from repo_semantic_memory.eval.reports import (
    render_compact_table,
    render_compare_markdown_report,
    render_markdown_report,
    to_compare_json_payload,
    write_compare_markdown_report,
)
from repo_semantic_memory.eval.runner import (
    BaselineComparisonResult,
    CompareAggregate,
    RetrievalBenchmarkResult,
)


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
    assert "context_character_estimate" in markdown
    assert "Gold invariants are dataset metadata only" in markdown


def test_compare_reports_are_deterministic_and_markdown_is_written(tmp_path: Path) -> None:
    repo_map = BaselineTaskResult(
        baseline="repo_map",
        context_character_count=100,
        selected_files=("src/a.py",),
        selected_symbols=("pkg.a",),
        gold_file_coverage=1.0,
        gold_symbol_coverage=0.5,
        useful_context_ratio=0.75,
        missing_gold_files=(),
        missing_gold_symbols=("pkg.missing",),
        extra_selected_files=(),
        extra_selected_symbols=("pkg.extra",),
    )
    lexical = BaselineTaskResult(
        baseline="lexical_context_pack",
        context_character_count=80,
        selected_files=("src/a.py",),
        selected_symbols=("pkg.a",),
        gold_file_coverage=1.0,
        gold_symbol_coverage=1.0,
        useful_context_ratio=1.0,
        missing_gold_files=(),
        missing_gold_symbols=(),
        extra_selected_files=(),
        extra_selected_symbols=(),
    )
    result = BaselineComparisonResult(
        dataset_path="benchmarks/tasks.yaml",
        db_path=".rsm/index.sqlite",
        budget=4000,
        outcomes=(
            TaskBaselineComparison(
                task_id="compare_001",
                category="code_localization",
                prompt="where is a",
                gold_files=("src/a.py",),
                gold_symbols=("pkg.a", "pkg.missing"),
                repo_map=repo_map,
                lexical_context_pack=lexical,
                token_savings_metrics=compute_token_savings_metrics(
                    raw_baseline_chars=100,
                    selected_context_chars=80,
                    raw_gold_file_coverage=1.0,
                    raw_gold_symbol_coverage=0.5,
                    selected_gold_file_coverage=1.0,
                    selected_gold_symbol_coverage=1.0,
                ),
                winner="lexical_context_pack",
            ),
        ),
        aggregate=CompareAggregate(
            average_context_character_count={"repo_map": 100.0, "lexical_context_pack": 80.0},
            average_gold_file_coverage={"repo_map": 1.0, "lexical_context_pack": 1.0},
            average_gold_symbol_coverage={"repo_map": 0.5, "lexical_context_pack": 1.0},
            average_useful_context_ratio={"repo_map": 0.75, "lexical_context_pack": 1.0},
            wins={"repo_map": 0, "lexical_context_pack": 1, "tie": 0, "inconclusive": 0},
            major_misses=("symbol:pkg.missing",),
        ),
    )

    payload_one = to_compare_json_payload(result)
    payload_two = to_compare_json_payload(result)
    assert payload_one == payload_two
    assert json.dumps(payload_one, sort_keys=True) == json.dumps(payload_two, sort_keys=True)
    assert "average_approx_useful_item_ratio" in payload_one["aggregate"]
    assert "savings" in payload_one["aggregate"]
    assert payload_one["aggregate"]["savings"]["average_estimated_tokens_saved"] == 5.0
    repo_payload = payload_one["tasks"][0]["repo_map"]
    assert repo_payload["approx_useful_item_ratio"] == 0.75
    assert repo_payload["selected_files"] == ["src/a.py"]
    assert repo_payload["selected_symbols"] == ["pkg.a"]
    savings_payload = payload_one["tasks"][0]["savings_metrics"]
    assert savings_payload["raw_baseline_chars"] == 100
    assert savings_payload["selected_context_chars"] == 80
    assert savings_payload["estimated_raw_tokens"] == 25.0
    assert savings_payload["estimated_selected_tokens"] == 20.0
    assert savings_payload["estimated_tokens_saved"] == 5.0
    assert savings_payload["compression_ratio"] == 0.8
    assert savings_payload["gold_file_coverage_preserved"] is True
    assert savings_payload["gold_symbol_coverage_preserved"] is True
    assert savings_payload["improvement_claim_allowed"] is True

    markdown_one = render_compare_markdown_report(result)
    markdown_two = render_compare_markdown_report(result)
    assert markdown_one == markdown_two
    assert "# Baseline comparison report" in markdown_one
    assert "## Estimated token savings (approximate)" in markdown_one
    assert "### Savings table" in markdown_one
    assert "estimated_tokens = chars / 4" in markdown_one
    assert "## Limitations" in markdown_one
    assert "does not claim superiority" in markdown_one
    assert "No superiority claim is made when" in markdown_one
    assert "not guaranteed irrelevant noise" in markdown_one
    assert "Small repositories can make generic repo-map retrieval" in markdown_one

    output_path = tmp_path / "compare.md"
    write_compare_markdown_report(output_path, result)
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == markdown_one
