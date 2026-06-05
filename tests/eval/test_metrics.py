"""Metric correctness tests for retrieval evaluation."""

from __future__ import annotations

from repo_semantic_memory.eval.metrics import (
    RetrievalOutcome,
    compute_benchmark_metrics,
    compute_token_savings_metrics,
    estimate_tokens_from_chars,
    token_savings_improvement_claim_allowed,
)


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


def test_estimate_tokens_from_chars_is_deterministic() -> None:
    assert estimate_tokens_from_chars(0) == 0.0
    assert estimate_tokens_from_chars(4) == 1.0
    assert estimate_tokens_from_chars(10) == 2.5


def test_compute_token_savings_metrics_has_expected_ratio_and_coverage_per_1k() -> None:
    metrics = compute_token_savings_metrics(
        raw_baseline_chars=400,
        selected_context_chars=200,
        raw_gold_file_coverage=0.5,
        raw_gold_symbol_coverage=0.5,
        selected_gold_file_coverage=0.5,
        selected_gold_symbol_coverage=1.0,
    )

    assert metrics.estimated_raw_tokens == 100.0
    assert metrics.estimated_selected_tokens == 50.0
    assert metrics.estimated_tokens_saved == 50.0
    assert metrics.compression_ratio == 0.5
    assert metrics.coverage_per_1k_tokens == 30.0
    assert metrics.gold_file_coverage_preserved is True
    assert metrics.gold_symbol_coverage_preserved is True
    assert token_savings_improvement_claim_allowed(metrics) is True


def test_compute_token_savings_metrics_zero_division_is_safe() -> None:
    metrics = compute_token_savings_metrics(
        raw_baseline_chars=0,
        selected_context_chars=0,
        raw_gold_file_coverage=0.0,
        raw_gold_symbol_coverage=0.0,
        selected_gold_file_coverage=0.0,
        selected_gold_symbol_coverage=0.0,
    )

    assert metrics.compression_ratio == 1.0
    assert metrics.coverage_per_1k_tokens == 0.0
    assert metrics.estimated_tokens_saved == 0.0


def test_improvement_claim_is_blocked_when_coverage_drops_even_with_token_savings() -> None:
    metrics = compute_token_savings_metrics(
        raw_baseline_chars=800,
        selected_context_chars=200,
        raw_gold_file_coverage=1.0,
        raw_gold_symbol_coverage=1.0,
        selected_gold_file_coverage=0.5,
        selected_gold_symbol_coverage=1.0,
    )

    assert metrics.estimated_tokens_saved > 0.0
    assert metrics.gold_file_coverage_preserved is False
    assert token_savings_improvement_claim_allowed(metrics) is False


# ---------------------------------------------------------------------------
# 59.2 — Benchmark harness metrics tests
# ---------------------------------------------------------------------------


class TestBenchmarkCaseMetrics:
    """Tests for compute_benchmark_case_metrics (59.0 harness)."""

    def test_central_found_when_at_least_one_expected_central_selected(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/resolver.py", "src/noise.py"),
            expected_central=("src/resolver.py", "src/conf.py"),
            expected_support=(),
            expected_tests=(),
            forbidden_files=(),
        )
        assert metrics.central_file_found == 1.0

    def test_central_not_found_when_no_central_match(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/other.py",),
            expected_central=("src/resolver.py",),
            expected_support=(),
            expected_tests=(),
            forbidden_files=(),
        )
        assert metrics.central_file_found == 0.0

    def test_support_ratio_exact(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/a.py", "src/b.py", "src/c.py"),
            expected_central=("src/a.py",),
            expected_support=("src/b.py", "src/c.py", "src/d.py"),
            expected_tests=(),
            forbidden_files=(),
        )
        assert metrics.support_files_found == 2.0 / 3.0

    def test_support_ratio_none_expected_gives_1(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/a.py",),
            expected_central=("src/a.py",),
            expected_support=(),
            expected_tests=(),
            forbidden_files=(),
        )
        assert metrics.support_files_found == 1.0

    def test_tests_ratio_exact(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/a.py", "tests/test_a.py"),
            expected_central=("src/a.py",),
            expected_support=(),
            expected_tests=("tests/test_a.py", "tests/test_b.py"),
            forbidden_files=(),
        )
        assert metrics.tests_found == 0.5

    def test_tests_ratio_none_expected_gives_1(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/a.py",),
            expected_central=("src/a.py",),
            expected_support=(),
            expected_tests=(),
            forbidden_files=(),
        )
        assert metrics.tests_found == 1.0

    def test_noise_reduced_1_when_no_forbidden_files(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/a.py", "src/b.py"),
            expected_central=("src/a.py",),
            expected_support=(),
            expected_tests=(),
            forbidden_files=(),
        )
        assert metrics.noise_reduced == 1.0

    def test_noise_reduced_decreases_when_forbidden_selected(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/good.py", "src/noise.py", "src/more_noise.py"),
            expected_central=("src/good.py",),
            expected_support=(),
            expected_tests=(),
            forbidden_files=("src/noise.py", "src/more_noise.py"),
        )
        # 2 forbidden out of 3 selected → noise_ratio = 2/3 → noise_reduced = 1 - 2/3
        assert metrics.noise_reduced == 1.0 - 2 / 3

    def test_noise_reduced_0_when_only_forbidden_selected(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/noise.py",),
            expected_central=("src/central.py",),
            expected_support=(),
            expected_tests=(),
            forbidden_files=("src/noise.py",),
        )
        assert metrics.noise_reduced == 0.0

    def test_overall_weighted_aggregate(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/central.py", "src/sup.py", "tests/t.py"),
            expected_central=("src/central.py",),
            expected_support=("src/sup.py",),
            expected_tests=("tests/t.py",),
            forbidden_files=(),
        )
        # central=1.0 support=1.0 tests=1.0 noise=1.0 → overall = 0.35+0.25+0.20+0.20 = 1.0
        assert metrics.overall == 1.0

    def test_overall_with_mixed_signals(self) -> None:
        from repo_semantic_memory.eval.metrics import compute_benchmark_case_metrics

        metrics = compute_benchmark_case_metrics(
            selected_files=("src/noise.py",),
            expected_central=("src/central.py",),
            expected_support=(),
            expected_tests=(),
            forbidden_files=("src/noise.py",),
        )
        # central=0.0, support=1.0 (vacuous), tests=1.0 (vacuous), noise=0.0
        expected = 0.35 * 0.0 + 0.25 * 1.0 + 0.20 * 1.0 + 0.20 * 0.0
        assert metrics.overall == expected
