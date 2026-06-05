"""Runner behavior tests for retrieval benchmark evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.eval.baselines import BaselineTaskResult, TaskBaselineComparison
from repo_semantic_memory.eval.metrics import compute_token_savings_metrics
from repo_semantic_memory.eval.runner import run_baseline_comparison, run_retrieval_benchmark
from repo_semantic_memory.model import Entity, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata


def test_runner_is_deterministic_and_reports_missing_gold(tmp_path: Path) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: deterministic_001",
                "    category: code_localization",
                '    prompt: "Where are python symbols defined?"',
                "    gold:",
                "      files:",
                "        - src/python_symbols.py",
                "        - src/does_not_exist.py",
                "      symbols:",
                "        - python_symbols.DerivedThing",
                "        - python_symbols.Missing",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0

    first = run_retrieval_benchmark(db_path=db_path, dataset_path=dataset_path)
    second = run_retrieval_benchmark(db_path=db_path, dataset_path=dataset_path)

    assert first.outcomes == second.outcomes
    outcome = first.outcomes[0]
    assert "src/python_symbols.py" in outcome.ranked_files
    assert "python_symbols.DerivedThing" in outcome.ranked_symbols
    assert outcome.missing_gold_files == ("src/does_not_exist.py",)
    assert outcome.missing_gold_symbols == ("python_symbols.Missing",)


def test_runner_tie_breaks_rankings_by_entity_id(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: tie_break_001",
                "    category: code_localization",
                '    prompt: "alpha"',
                "    gold:",
                "      files:",
                "        - b.py",
                "      symbols:",
                "        - alpha.two",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )

    entities = [
        Entity(
            id=StableId("id:z"),
            kind="module",
            name="alpha",
            qualified_name="alpha.one",
            source_range=SourceRange(path="a.py", start_line=1, end_line=1),
            metadata={},
        ),
        Entity(
            id=StableId("id:a"),
            kind="module",
            name="alpha",
            qualified_name="alpha.two",
            source_range=SourceRange(path="b.py", start_line=1, end_line=1),
            metadata={},
        ),
    ]
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("test",),
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        store.persist_index(entities=entities, relations=[], metadata=metadata)
    finally:
        store.close()

    result = run_retrieval_benchmark(
        db_path=db_path, dataset_path=dataset_path, max_ranked_results=2
    )

    outcome = result.outcomes[0]
    assert outcome.ranked_files[:2] == ("b.py", "a.py")
    assert outcome.ranked_symbols[:2] == ("alpha.two", "alpha.one")


def test_run_baseline_comparison_on_synthetic_data(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: compare_001",
                "    category: code_localization",
                '    prompt: "alpha"',
                "    gold:",
                "      files:",
                "        - src/a.py",
                "      symbols:",
                "        - alpha.symbol",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )

    entities = [
        Entity(
            id=StableId("id:alpha"),
            kind="module",
            name="alpha",
            qualified_name="alpha.symbol",
            source_range=SourceRange(path="src/a.py", start_line=1, end_line=10),
            metadata={},
        ),
    ]
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("test",),
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        store.persist_index(entities=entities, relations=[], metadata=metadata)
    finally:
        store.close()

    result = run_baseline_comparison(db_path=db_path, dataset_path=dataset_path, budget_chars=4000)

    assert result.budget == 4000
    assert len(result.outcomes) == 1
    assert result.outcomes[0].task_id == "compare_001"
    assert result.aggregate.average_context_character_count["repo_map"] >= 0
    assert result.aggregate.average_context_character_count["lexical_context_pack"] >= 0


def test_run_baseline_comparison_passes_budget_to_both_baselines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: compare_002",
                "    category: code_localization",
                '    prompt: "alpha"',
                "    gold:",
                "      files:",
                "        - src/a.py",
                "      symbols:",
                "        - alpha.symbol",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )
    entities = [
        Entity(
            id=StableId("id:alpha"),
            kind="module",
            name="alpha",
            qualified_name="alpha.symbol",
            source_range=SourceRange(path="src/a.py", start_line=1, end_line=1),
            metadata={},
        ),
    ]
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=tmp_path,
            extractor_names=("test",),
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        store.persist_index(entities=entities, relations=[], metadata=metadata)
    finally:
        store.close()

    observed_budgets: list[int] = []

    def _fake_evaluate_task_baselines(
        *, task: object, entities: object, relations: object, budget_chars: int
    ) -> TaskBaselineComparison:
        del task, entities, relations
        observed_budgets.append(budget_chars)
        baseline = BaselineTaskResult(
            baseline="repo_map",
            context_character_count=50,
            selected_files=("src/a.py",),
            selected_symbols=("alpha.symbol",),
            gold_file_coverage=1.0,
            gold_symbol_coverage=1.0,
            useful_context_ratio=1.0,
            missing_gold_files=(),
            missing_gold_symbols=(),
            extra_selected_files=(),
            extra_selected_symbols=(),
        )
        lexical = BaselineTaskResult(
            baseline="lexical_context_pack",
            context_character_count=50,
            selected_files=("src/a.py",),
            selected_symbols=("alpha.symbol",),
            gold_file_coverage=1.0,
            gold_symbol_coverage=1.0,
            useful_context_ratio=1.0,
            missing_gold_files=(),
            missing_gold_symbols=(),
            extra_selected_files=(),
            extra_selected_symbols=(),
        )
        return TaskBaselineComparison(
            task_id="compare_002",
            category="code_localization",
            prompt="alpha",
            gold_files=("src/a.py",),
            gold_symbols=("alpha.symbol",),
            repo_map=baseline,
            lexical_context_pack=lexical,
            token_savings_metrics=compute_token_savings_metrics(
                raw_baseline_chars=50,
                selected_context_chars=50,
                raw_gold_file_coverage=1.0,
                raw_gold_symbol_coverage=1.0,
                selected_gold_file_coverage=1.0,
                selected_gold_symbol_coverage=1.0,
            ),
            winner="tie",
        )

    monkeypatch.setattr(
        "repo_semantic_memory.eval.runner.evaluate_task_baselines",
        _fake_evaluate_task_baselines,
    )

    run_baseline_comparison(db_path=db_path, dataset_path=dataset_path, budget_chars=777)

    assert observed_budgets == [777]


def test_baseline_comparison_savings_deterministic_across_budgets(
    tmp_path: Path,
) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"
    db_path = tmp_path / ".rsm" / "index.sqlite"
    dataset_path = tmp_path / "tasks.yaml"
    dataset_path.write_text(
        "\n".join(
            [
                "tasks:",
                "  - id: compare_budget_001",
                "    category: code_localization",
                '    prompt: "Where is DerivedThing defined?"',
                "    gold:",
                "      files:",
                "        - src/python_symbols.py",
                "      symbols:",
                "        - python_symbols.DerivedThing",
                "      invariants:",
                "        - none",
            ]
        ),
        encoding="utf-8",
    )
    assert main(["index", str(fixture_root), "--db", str(db_path)]) == 0

    first_4000 = run_baseline_comparison(
        db_path=db_path, dataset_path=dataset_path, budget_chars=4000
    )
    second_4000 = run_baseline_comparison(
        db_path=db_path, dataset_path=dataset_path, budget_chars=4000
    )
    first_8000 = run_baseline_comparison(
        db_path=db_path, dataset_path=dataset_path, budget_chars=8000
    )
    second_8000 = run_baseline_comparison(
        db_path=db_path, dataset_path=dataset_path, budget_chars=8000
    )

    assert first_4000.outcomes == second_4000.outcomes
    assert first_8000.outcomes == second_8000.outcomes
    assert (
        first_4000.outcomes[0].token_savings_metrics
        == second_4000.outcomes[0].token_savings_metrics
    )
    assert (
        first_8000.outcomes[0].token_savings_metrics
        == second_8000.outcomes[0].token_savings_metrics
    )


# ---------------------------------------------------------------------------
# 59.2 — Benchmark harness runner tests
# ---------------------------------------------------------------------------


from repo_semantic_memory.context.context_pack import ContextPack  # noqa: E402
from repo_semantic_memory.eval.datasets import BenchmarkCase, BenchmarkExpected  # noqa: E402
from repo_semantic_memory.eval.runner import (  # noqa: E402
    extract_selected_files,
    run_benchmark_cases,
)


def _fake_pack(
    *,
    suggested: tuple[str, ...] = (),
    entity_paths: tuple[str, ...] = (),
) -> ContextPack:
    """Build a minimal deterministic ContextPack for runner tests."""
    entities = tuple(
        Entity(
            id=StableId.from_parts(["file", path]),
            kind="module",
            name=path.rsplit("/", 1)[-1],
            qualified_name=path.replace("/", ".").replace(".py", ""),
            source_range=SourceRange(path=path, start_line=1, end_line=1),
        )
        for path in entity_paths
    )
    return ContextPack(
        task="test task",
        budget=1000,
        selected_entities=entities,
        selected_relations=(),
        source_citations=(),
        why_selected={},
        ranking_breakdowns={},
        semantic_components=(),
        uncertainties=(),
        suggested_files_to_inspect=suggested,
        forbidden_assumptions=(),
    )


class TestExtractSelectedFiles:
    """Tests for extract_selected_files."""

    def test_uses_suggested_files_to_inspect_first(self) -> None:
        pack = _fake_pack(
            suggested=("src/a.py", "src/b.py"),
            entity_paths=("src/x.py", "src/y.py"),
        )
        result = extract_selected_files(pack)
        assert result == ("src/a.py", "src/b.py")

    def test_falls_back_to_entity_paths_when_no_suggested(self) -> None:
        pack = _fake_pack(entity_paths=("src/x.py", "src/y.py"))
        result = extract_selected_files(pack)
        assert result == ("src/x.py", "src/y.py")

    def test_dedupes_deterministically_preserving_first_occurrence(self) -> None:
        pack = _fake_pack(
            suggested=("src/a.py", "src/b.py", "src/a.py", "src/c.py"),
        )
        result = extract_selected_files(pack)
        assert result == ("src/a.py", "src/b.py", "src/c.py")

    def test_empty_suggested_and_empty_entities_returns_empty(self) -> None:
        pack = _fake_pack()
        result = extract_selected_files(pack)
        assert result == ()


class TestRunBenchmarkCases:
    """Tests for run_benchmark_cases."""

    def _make_case(
        self,
        case_id: str = "case_001",
        central: tuple[str, ...] = ("src/central.py",),
        support: tuple[str, ...] = (),
        tests: tuple[str, ...] = (),
        forbidden: tuple[str, ...] = (),
    ) -> BenchmarkCase:
        return BenchmarkCase(
            id=case_id,
            fixture="test_fixture",
            query="find central",
            expected=BenchmarkExpected(
                central_files=central,
                support_files=support,
                test_files=tests,
                forbidden_files=forbidden,
            ),
            tags=(),
            notes="",
            mode="ci_fixture",
        )

    def test_evaluates_one_valid_case(self) -> None:
        case = self._make_case(central=("src/central.py",))

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=("src/central.py",))

        result = run_benchmark_cases(cases=[case], build_pack=build)
        assert len(result.outcomes) == 1
        assert result.outcomes[0].case.id == "case_001"
        assert result.outcomes[0].metrics.central_file_found == 1.0
        assert result.outcomes[0].metrics.overall == 1.0

    def test_evaluates_multiple_cases(self) -> None:
        case_a = self._make_case("a", central=("src/a.py",))
        case_b = self._make_case("b", central=("src/b.py",))

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=(c.expected.central_files[0],))

        result = run_benchmark_cases(cases=[case_a, case_b], build_pack=build)
        assert len(result.outcomes) == 2
        assert result.outcomes[0].case.id == "a"
        assert result.outcomes[1].case.id == "b"

    def test_computes_aggregate_metrics(self) -> None:
        case_a = self._make_case("a", central=("src/a.py",))

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=("src/a.py",))

        result = run_benchmark_cases(cases=[case_a, case_a], build_pack=build)
        # Both cases have identical outcomes → aggregate should match
        assert result.aggregate.central_file_found == 1.0
        assert result.aggregate.overall == 1.0

    def test_reports_missing_central_files(self) -> None:
        case = self._make_case(central=("src/central.py", "src/missing.py"))

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=("src/central.py",))

        result = run_benchmark_cases(cases=[case], build_pack=build)
        assert result.outcomes[0].missing_central_files == ("src/missing.py",)

    def test_reports_missing_support_files(self) -> None:
        case = self._make_case(
            central=("src/central.py",),
            support=("src/sup_a.py", "src/sup_b.py"),
        )

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=("src/central.py", "src/sup_a.py"))

        result = run_benchmark_cases(cases=[case], build_pack=build)
        assert result.outcomes[0].missing_support_files == ("src/sup_b.py",)

    def test_reports_missing_test_files(self) -> None:
        case = self._make_case(
            central=("src/central.py",),
            tests=("tests/test_a.py", "tests/test_b.py"),
        )

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=("src/central.py",))

        result = run_benchmark_cases(cases=[case], build_pack=build)
        assert result.outcomes[0].missing_test_files == (
            "tests/test_a.py",
            "tests/test_b.py",
        )

    def test_reports_forbidden_files_found(self) -> None:
        case = self._make_case(
            central=("src/central.py",),
            forbidden=("src/noise_a.py", "src/noise_b.py"),
        )

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=("src/central.py", "src/noise_a.py"))

        result = run_benchmark_cases(cases=[case], build_pack=build)
        assert result.outcomes[0].forbidden_files_found == ("src/noise_a.py",)

    def test_preserves_deterministic_outcome_order(self) -> None:
        cases = [
            self._make_case("a", central=("src/a.py",)),
            self._make_case("b", central=("src/b.py",)),
        ]

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=(c.expected.central_files[0],))

        r1 = run_benchmark_cases(cases=cases, build_pack=build)
        r2 = run_benchmark_cases(cases=cases, build_pack=build)
        assert r1.outcomes[0].case.id == r2.outcomes[0].case.id
        assert r1.outcomes[1].case.id == r2.outcomes[1].case.id

    def test_does_not_mutate_benchmark_case(self) -> None:
        case = self._make_case("a", central=("src/a.py",))

        def build(c: BenchmarkCase) -> ContextPack:
            return _fake_pack(suggested=("src/a.py",))

        run_benchmark_cases(cases=[case], build_pack=build)
        # Case should be unchanged after evaluation
        assert case.expected.central_files == ("src/a.py",)
        assert case.id == "a"
