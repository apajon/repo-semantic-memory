"""Baseline comparison tests."""

from __future__ import annotations

from repo_semantic_memory.eval.baselines import (
    BaselineTaskResult,
    decide_winner,
    evaluate_task_baselines,
)
from repo_semantic_memory.eval.datasets import GoldTargets, RetrievalTask
from repo_semantic_memory.eval.metrics import token_savings_improvement_claim_allowed
from repo_semantic_memory.model import Entity, SourceRange, StableId


def test_evaluate_task_baselines_reports_missing_gold_items() -> None:
    entities = (
        Entity(
            id=StableId("id:alpha"),
            kind="module",
            name="alpha",
            qualified_name="pkg.alpha",
            source_range=SourceRange(path="src/alpha.py", start_line=1, end_line=5),
            metadata={},
        ),
    )
    task = RetrievalTask(
        id="compare_missing_001",
        category="code_localization",
        prompt="alpha",
        gold=GoldTargets(
            files=("src/alpha.py", "src/missing.py"),
            symbols=("pkg.alpha", "id:missing"),
            invariants=(),
        ),
    )

    result = evaluate_task_baselines(task=task, entities=entities, relations=(), budget_chars=4000)

    assert "src/missing.py" in result.repo_map.missing_gold_files
    assert "id:missing" in result.repo_map.missing_gold_symbols
    assert "src/missing.py" in result.lexical_context_pack.missing_gold_files
    assert "id:missing" in result.lexical_context_pack.missing_gold_symbols
    assert (
        result.token_savings_metrics.raw_baseline_chars == result.repo_map.context_character_count
    )
    assert (
        result.token_savings_metrics.selected_context_chars
        == result.lexical_context_pack.context_character_count
    )
    assert result.token_savings_metrics.estimated_raw_tokens == (
        result.repo_map.context_character_count / 4.0
    )
    assert result.token_savings_metrics.estimated_selected_tokens == (
        result.lexical_context_pack.context_character_count / 4.0
    )


def test_token_savings_improvement_claim_blocked_when_coverage_drops() -> None:
    entities = (
        Entity(
            id=StableId("id:alpha"),
            kind="module",
            name="alpha",
            qualified_name="pkg.alpha",
            source_range=SourceRange(path="src/alpha.py", start_line=1, end_line=5),
            metadata={},
        ),
        Entity(
            id=StableId("id:beta"),
            kind="module",
            name="beta",
            qualified_name="pkg.beta",
            source_range=SourceRange(path="src/beta.py", start_line=1, end_line=5),
            metadata={},
        ),
    )
    task = RetrievalTask(
        id="compare_coverage_drop_001",
        category="code_localization",
        prompt="alpha",
        gold=GoldTargets(
            files=("src/alpha.py", "src/beta.py"),
            symbols=("pkg.alpha", "pkg.beta"),
            invariants=(),
        ),
    )

    result = evaluate_task_baselines(task=task, entities=entities, relations=(), budget_chars=80)

    assert (
        result.token_savings_metrics.gold_file_coverage_preserved is False
        or result.token_savings_metrics.gold_symbol_coverage_preserved is False
    )
    assert token_savings_improvement_claim_allowed(result.token_savings_metrics) is False


def test_decide_winner_returns_tie_or_inconclusive() -> None:
    tie_repo_map = BaselineTaskResult(
        baseline="repo_map",
        context_character_count=100,
        selected_files=("src/a.py",),
        selected_symbols=("pkg.a",),
        gold_file_coverage=1.0,
        gold_symbol_coverage=1.0,
        useful_context_ratio=0.5,
        missing_gold_files=(),
        missing_gold_symbols=(),
        extra_selected_files=(),
        extra_selected_symbols=(),
    )
    tie_pack = BaselineTaskResult(
        baseline="lexical_context_pack",
        context_character_count=100,
        selected_files=("src/a.py",),
        selected_symbols=("pkg.a",),
        gold_file_coverage=1.0,
        gold_symbol_coverage=1.0,
        useful_context_ratio=0.5,
        missing_gold_files=(),
        missing_gold_symbols=(),
        extra_selected_files=(),
        extra_selected_symbols=(),
    )
    assert decide_winner(tie_repo_map, tie_pack) == "tie"

    inconclusive_repo_map = BaselineTaskResult(
        baseline="repo_map",
        context_character_count=0,
        selected_files=(),
        selected_symbols=(),
        gold_file_coverage=0.0,
        gold_symbol_coverage=0.0,
        useful_context_ratio=0.0,
        missing_gold_files=("src/a.py",),
        missing_gold_symbols=("pkg.a",),
        extra_selected_files=(),
        extra_selected_symbols=(),
    )
    inconclusive_pack = BaselineTaskResult(
        baseline="lexical_context_pack",
        context_character_count=0,
        selected_files=(),
        selected_symbols=(),
        gold_file_coverage=0.0,
        gold_symbol_coverage=0.0,
        useful_context_ratio=0.0,
        missing_gold_files=("src/a.py",),
        missing_gold_symbols=("pkg.a",),
        extra_selected_files=(),
        extra_selected_symbols=(),
    )
    assert decide_winner(inconclusive_repo_map, inconclusive_pack) == "inconclusive"


def test_decide_winner_prioritizes_gold_coverage_before_density() -> None:
    higher_coverage = BaselineTaskResult(
        baseline="repo_map",
        context_character_count=200,
        selected_files=("src/a.py",),
        selected_symbols=("pkg.a",),
        gold_file_coverage=1.0,
        gold_symbol_coverage=1.0,
        useful_context_ratio=0.3,
        missing_gold_files=(),
        missing_gold_symbols=(),
        extra_selected_files=(),
        extra_selected_symbols=(),
    )
    smaller_but_misses_gold = BaselineTaskResult(
        baseline="lexical_context_pack",
        context_character_count=50,
        selected_files=("src/a.py",),
        selected_symbols=("pkg.a",),
        gold_file_coverage=1.0,
        gold_symbol_coverage=0.0,
        useful_context_ratio=0.9,
        missing_gold_files=(),
        missing_gold_symbols=("pkg.missing",),
        extra_selected_files=(),
        extra_selected_symbols=(),
    )
    assert decide_winner(higher_coverage, smaller_but_misses_gold) == "repo_map"
