"""Report rendering for benchmark results."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from repo_semantic_memory.eval.baselines import TaskBaselineComparison
from repo_semantic_memory.eval.runner import BaselineComparisonResult, RetrievalBenchmarkResult


def to_json_payload(result: RetrievalBenchmarkResult) -> dict[str, object]:
    """Convert retrieval benchmark result to deterministic JSON payload."""
    return {
        "dataset_path": result.dataset_path,
        "db_path": result.db_path,
        "k_values": list(result.k_values),
        "aggregate": _aggregate_payload(result),
        "tasks": [_task_payload(result, index) for index in range(len(result.outcomes))],
    }


def to_compare_json_payload(result: BaselineComparisonResult) -> dict[str, object]:
    """Convert baseline comparison result to deterministic JSON payload."""
    return {
        "dataset_path": result.dataset_path,
        "db_path": result.db_path,
        "budget": result.budget,
        "aggregate": {
            "average_context_character_count": dict(
                sorted(result.aggregate.average_context_character_count.items())
            ),
            "average_gold_file_coverage": dict(
                sorted(result.aggregate.average_gold_file_coverage.items())
            ),
            "average_gold_symbol_coverage": dict(
                sorted(result.aggregate.average_gold_symbol_coverage.items())
            ),
            "average_approx_useful_item_ratio": dict(
                sorted(result.aggregate.average_approx_useful_item_ratio.items())
            ),
            "average_useful_context_ratio": dict(
                sorted(result.aggregate.average_useful_context_ratio.items())
            ),
            "wins": dict(sorted(result.aggregate.wins.items())),
            "major_misses": list(result.aggregate.major_misses),
        },
        "tasks": [_compare_task_payload(task) for task in result.outcomes],
    }


def render_compact_table(result: RetrievalBenchmarkResult) -> str:
    """Render compact plain-text retrieval benchmark table."""
    primary_k = result.k_values[-1]
    rows = [
        (
            "task_id",
            f"R@{primary_k} files",
            f"R@{primary_k} symbols",
            "MRR files",
            "MRR symbols",
            "file cov",
            "symbol cov",
            "ctx chars",
            "missing",
        )
    ]
    for outcome, metrics in zip(result.outcomes, result.metrics.per_task, strict=True):
        missing = _format_missing(outcome.missing_gold_files, outcome.missing_gold_symbols)
        rows.append(
            (
                outcome.task_id,
                f"{metrics.recall_at_k_files[primary_k]:.3f}",
                f"{metrics.recall_at_k_symbols[primary_k]:.3f}",
                f"{metrics.mrr_files:.3f}",
                f"{metrics.mrr_symbols:.3f}",
                f"{metrics.gold_file_coverage:.3f}",
                f"{metrics.gold_symbol_coverage:.3f}",
                str(metrics.context_character_estimate),
                missing,
            )
        )
    aggregate = result.metrics.aggregate
    rows.append(
        (
            "AVG",
            f"{aggregate.recall_at_k_files[primary_k]:.3f}",
            f"{aggregate.recall_at_k_symbols[primary_k]:.3f}",
            f"{aggregate.mrr_files:.3f}",
            f"{aggregate.mrr_symbols:.3f}",
            f"{aggregate.gold_file_coverage:.3f}",
            f"{aggregate.gold_symbol_coverage:.3f}",
            f"{aggregate.context_character_estimate:.1f}",
            "-",
        )
    )
    return _render_rows(rows)


def render_compare_compact_table(result: BaselineComparisonResult) -> str:
    """Render compact plain-text table for baseline comparison."""
    rows = [
        (
            "task_id",
            "repo_map approx_useful",
            "pack approx_useful",
            "repo_map gold_cov",
            "pack gold_cov",
            "repo_map chars",
            "pack chars",
            "winner",
        )
    ]
    for task in result.outcomes:
        rows.append(
            (
                task.task_id,
                f"{task.repo_map.approx_useful_item_ratio:.3f}",
                f"{task.lexical_context_pack.approx_useful_item_ratio:.3f}",
                f"{task.repo_map.gold_file_coverage:.3f}/{task.repo_map.gold_symbol_coverage:.3f}",
                (
                    f"{task.lexical_context_pack.gold_file_coverage:.3f}/"
                    f"{task.lexical_context_pack.gold_symbol_coverage:.3f}"
                ),
                str(task.repo_map.context_character_count),
                str(task.lexical_context_pack.context_character_count),
                task.winner,
            )
        )

    aggregate = result.aggregate
    rows.append(
        (
            "AVG",
            f"{aggregate.average_useful_context_ratio['repo_map']:.3f}",
            f"{aggregate.average_useful_context_ratio['lexical_context_pack']:.3f}",
            (
                f"{aggregate.average_gold_file_coverage['repo_map']:.3f}/"
                f"{aggregate.average_gold_symbol_coverage['repo_map']:.3f}"
            ),
            (
                f"{aggregate.average_gold_file_coverage['lexical_context_pack']:.3f}/"
                f"{aggregate.average_gold_symbol_coverage['lexical_context_pack']:.3f}"
            ),
            f"{aggregate.average_context_character_count['repo_map']:.1f}",
            f"{aggregate.average_context_character_count['lexical_context_pack']:.1f}",
            "-",
        )
    )
    return _render_rows(rows)


def render_markdown_report(result: RetrievalBenchmarkResult) -> str:
    """Render markdown retrieval benchmark report."""
    aggregate = result.metrics.aggregate
    lines = [
        "# Retrieval benchmark report",
        "",
        f"- dataset: `{result.dataset_path}`",
        f"- db: `{result.db_path}`",
        f"- tasks: `{len(result.outcomes)}`",
        "",
        "## Aggregate metrics",
        "",
        f"- mrr_files: `{aggregate.mrr_files:.6f}`",
        f"- mrr_symbols: `{aggregate.mrr_symbols:.6f}`",
        f"- gold_file_coverage: `{aggregate.gold_file_coverage:.6f}`",
        f"- gold_symbol_coverage: `{aggregate.gold_symbol_coverage:.6f}`",
        f"- context_character_estimate: `{aggregate.context_character_estimate:.6f}`",
        "",
        "Notes:",
        "- `context_character_estimate` is a character-based approximation, not tokenizer-based.",
        "- Gold invariants are dataset metadata only in this MVP and are not scored yet.",
        "",
        "## Task details",
        "",
        "| task_id | category | missing_gold_files | missing_gold_symbols |",
        "|---|---|---|---|",
    ]
    for outcome in result.outcomes:
        files_text = ", ".join(outcome.missing_gold_files) or "-"
        symbols_text = ", ".join(outcome.missing_gold_symbols) or "-"
        lines.append(f"| {outcome.task_id} | {outcome.category} | {files_text} | {symbols_text} |")
    return "\n".join(lines)


def render_compare_markdown_report(result: BaselineComparisonResult) -> str:
    """Render markdown report for repo-map vs lexical-context-pack comparison."""
    aggregate = result.aggregate
    lines = [
        "# Baseline comparison report",
        "",
        f"- dataset: `{result.dataset_path}`",
        f"- db: `{result.db_path}`",
        f"- budget_chars: `{result.budget}`",
        f"- tasks: `{len(result.outcomes)}`",
        "",
        "## Aggregate results",
        "",
        (
            f"- average_context_character_count: repo_map="
            f"`{aggregate.average_context_character_count['repo_map']:.6f}`, "
            f"lexical_context_pack="
            f"`{aggregate.average_context_character_count['lexical_context_pack']:.6f}`"
        ),
        (
            f"- average_gold_file_coverage: repo_map="
            f"`{aggregate.average_gold_file_coverage['repo_map']:.6f}`, "
            f"lexical_context_pack="
            f"`{aggregate.average_gold_file_coverage['lexical_context_pack']:.6f}`"
        ),
        (
            f"- average_gold_symbol_coverage: repo_map="
            f"`{aggregate.average_gold_symbol_coverage['repo_map']:.6f}`, "
            f"lexical_context_pack="
            f"`{aggregate.average_gold_symbol_coverage['lexical_context_pack']:.6f}`"
        ),
        (
            f"- average_approx_useful_item_ratio: repo_map="
            f"`{aggregate.average_approx_useful_item_ratio['repo_map']:.6f}`, "
            f"lexical_context_pack="
            f"`{aggregate.average_approx_useful_item_ratio['lexical_context_pack']:.6f}`"
        ),
        (
            f"- wins: repo_map=`{aggregate.wins['repo_map']}`, "
            f"lexical_context_pack=`{aggregate.wins['lexical_context_pack']}`, "
            f"tie=`{aggregate.wins['tie']}`, "
            f"inconclusive=`{aggregate.wins['inconclusive']}`"
        ),
        f"- major_misses: `{', '.join(aggregate.major_misses) or '-'}`",
        "",
        "## Per-task results",
        "",
        (
            "| task_id | winner | repo_map approx_useful_item_ratio | "
            "pack approx_useful_item_ratio | "
            "repo_map missing | pack missing |"
        ),
        "|---|---|---|---|---|---|",
    ]
    for task in result.outcomes:
        repo_missing = _format_missing(
            task.repo_map.missing_gold_files, task.repo_map.missing_gold_symbols
        )
        pack_missing = _format_missing(
            task.lexical_context_pack.missing_gold_files,
            task.lexical_context_pack.missing_gold_symbols,
        )
        lines.append(
            f"| {task.task_id} | {task.winner} | "
            f"{task.repo_map.approx_useful_item_ratio:.6f} | "
            f"{task.lexical_context_pack.approx_useful_item_ratio:.6f} | "
            f"{repo_missing} | {pack_missing} |"
        )

    lines.extend(
        [
            "",
            "## Limitations",
            "",
            (
                "- `useful_context_ratio` is an approximation over selected "
                "file and symbol identifiers (item-level, not token-level) "
                "and does not measure semantic correctness."
            ),
            "- Character budget is character-based and not tokenizer-based.",
            (
                "- `extra_selected_files` and `extra_selected_symbols` are "
                "non-gold selections, not guaranteed irrelevant noise."
            ),
            (
                "- Ties and all-zero useful-context outcomes are reported as "
                "`tie` or `inconclusive`; "
                "the report does not claim superiority in those cases."
            ),
            (
                "- Small repositories can make generic repo-map retrieval "
                "artificially strong relative to task-specific packs."
            ),
            (
                "- Results from toy fixtures should not be interpreted as "
                "scientific superiority claims."
            ),
        ]
    )
    return "\n".join(lines)


def write_markdown_report(path: Path | str, result: RetrievalBenchmarkResult) -> None:
    """Write retrieval markdown report to disk."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown_report(result), encoding="utf-8")


def write_compare_markdown_report(path: Path | str, result: BaselineComparisonResult) -> None:
    """Write baseline comparison markdown report to disk."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_compare_markdown_report(result), encoding="utf-8")


def _aggregate_payload(result: RetrievalBenchmarkResult) -> dict[str, object]:
    aggregate = result.metrics.aggregate
    return {
        "recall_at_k_files": {str(k): aggregate.recall_at_k_files[k] for k in result.k_values},
        "recall_at_k_symbols": {str(k): aggregate.recall_at_k_symbols[k] for k in result.k_values},
        "mrr_files": aggregate.mrr_files,
        "mrr_symbols": aggregate.mrr_symbols,
        "context_character_estimate": aggregate.context_character_estimate,
        "gold_file_coverage": aggregate.gold_file_coverage,
        "gold_symbol_coverage": aggregate.gold_symbol_coverage,
    }


def _task_payload(result: RetrievalBenchmarkResult, index: int) -> dict[str, object]:
    outcome = result.outcomes[index]
    metrics = result.metrics.per_task[index]
    return {
        "task_id": outcome.task_id,
        "category": outcome.category,
        "prompt": outcome.prompt,
        "ranked_files": list(outcome.ranked_files),
        "ranked_symbols": list(outcome.ranked_symbols),
        "gold_files": list(outcome.gold_files),
        "gold_symbols": list(outcome.gold_symbols),
        "gold_invariants": list(outcome.gold_invariants),
        "missing_gold_files": list(outcome.missing_gold_files),
        "missing_gold_symbols": list(outcome.missing_gold_symbols),
        "metrics": {
            "recall_at_k_files": {
                str(k): metrics.recall_at_k_files[k] for k in result.metrics.k_values
            },
            "recall_at_k_symbols": {
                str(k): metrics.recall_at_k_symbols[k] for k in result.metrics.k_values
            },
            "mrr_files": metrics.mrr_files,
            "mrr_symbols": metrics.mrr_symbols,
            "gold_file_coverage": metrics.gold_file_coverage,
            "gold_symbol_coverage": metrics.gold_symbol_coverage,
            "context_character_estimate": metrics.context_character_estimate,
        },
    }


def _compare_task_payload(comparison: TaskBaselineComparison) -> dict[str, object]:
    return {
        "task_id": comparison.task_id,
        "category": comparison.category,
        "prompt": comparison.prompt,
        "gold_files": list(comparison.gold_files),
        "gold_symbols": list(comparison.gold_symbols),
        "winner": comparison.winner,
        "repo_map": {
            "context_character_count": comparison.repo_map.context_character_count,
            "gold_file_coverage": comparison.repo_map.gold_file_coverage,
            "gold_symbol_coverage": comparison.repo_map.gold_symbol_coverage,
            "approx_useful_item_ratio": comparison.repo_map.approx_useful_item_ratio,
            "useful_context_ratio": comparison.repo_map.useful_context_ratio,
            "selected_files": list(comparison.repo_map.selected_files),
            "selected_symbols": list(comparison.repo_map.selected_symbols),
            "missing_gold_files": list(comparison.repo_map.missing_gold_files),
            "missing_gold_symbols": list(comparison.repo_map.missing_gold_symbols),
            "extra_selected_files": list(comparison.repo_map.extra_selected_files),
            "extra_selected_symbols": list(comparison.repo_map.extra_selected_symbols),
        },
        "lexical_context_pack": {
            "context_character_count": comparison.lexical_context_pack.context_character_count,
            "gold_file_coverage": comparison.lexical_context_pack.gold_file_coverage,
            "gold_symbol_coverage": comparison.lexical_context_pack.gold_symbol_coverage,
            "approx_useful_item_ratio": comparison.lexical_context_pack.approx_useful_item_ratio,
            "useful_context_ratio": comparison.lexical_context_pack.useful_context_ratio,
            "selected_files": list(comparison.lexical_context_pack.selected_files),
            "selected_symbols": list(comparison.lexical_context_pack.selected_symbols),
            "missing_gold_files": list(comparison.lexical_context_pack.missing_gold_files),
            "missing_gold_symbols": list(comparison.lexical_context_pack.missing_gold_symbols),
            "extra_selected_files": list(comparison.lexical_context_pack.extra_selected_files),
            "extra_selected_symbols": list(comparison.lexical_context_pack.extra_selected_symbols),
        },
    }


def _render_rows(rows: Sequence[tuple[str, ...]]) -> str:
    columns = zip(*rows, strict=True)
    widths = [max(len(value) for value in column) for column in columns]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows
    )


def _format_missing(missing_files: tuple[str, ...], missing_symbols: tuple[str, ...]) -> str:
    parts: list[str] = []
    if missing_files:
        parts.append(f"files={','.join(missing_files)}")
    if missing_symbols:
        parts.append(f"symbols={','.join(missing_symbols)}")
    return ";".join(parts) if parts else "-"
