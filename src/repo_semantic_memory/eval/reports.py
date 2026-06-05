"""Report rendering for benchmark results."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from repo_semantic_memory.eval.baselines import TaskBaselineComparison
from repo_semantic_memory.eval.metrics import (
    APPROX_CHARS_PER_TOKEN,
    token_savings_improvement_claim_allowed,
)
from repo_semantic_memory.eval.report_data import (
    build_compare_category_payload,
    build_generated_artifact_false_positive_payload,
    build_retrieval_category_payload,
    build_savings_aggregate_payload,
)
from repo_semantic_memory.eval.runner import (
    BaselineComparisonResult,
    BenchmarkRunResult,
    RetrievalBenchmarkResult,
)


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
            "savings": build_savings_aggregate_payload(result.outcomes),
            "generated_artifact_false_positives": build_generated_artifact_false_positive_payload(
                result.outcomes
            ),
            "by_category": build_compare_category_payload(result.outcomes),
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
            "repo_map chars",
            "pack chars",
            "saved tok~",
            "compr",
            "file_cov_ok",
            "symbol_cov_ok",
            "winner",
        )
    ]
    for task in result.outcomes:
        savings = task.token_savings_metrics
        rows.append(
            (
                task.task_id,
                str(task.repo_map.context_character_count),
                str(task.lexical_context_pack.context_character_count),
                f"{savings.estimated_tokens_saved:.3f}",
                f"{savings.compression_ratio:.3f}",
                str(savings.gold_file_coverage_preserved),
                str(savings.gold_symbol_coverage_preserved),
                task.winner,
            )
        )

    aggregate = result.aggregate
    savings_aggregate = build_savings_aggregate_payload(result.outcomes)
    rows.append(
        (
            "AVG",
            f"{aggregate.average_context_character_count['repo_map']:.1f}",
            f"{aggregate.average_context_character_count['lexical_context_pack']:.1f}",
            f"{savings_aggregate['average_estimated_tokens_saved']:.3f}",
            f"{savings_aggregate['average_compression_ratio']:.3f}",
            str(int(savings_aggregate["gold_file_coverage_preserved_tasks"])),
            str(int(savings_aggregate["gold_symbol_coverage_preserved_tasks"])),
            "-",
        )
    )
    return _render_rows(rows)


def render_markdown_report(result: RetrievalBenchmarkResult) -> str:
    """Render markdown retrieval benchmark report."""
    aggregate = result.metrics.aggregate
    primary_k = result.k_values[-1]
    category_payload = build_retrieval_category_payload(result.outcomes, k_values=result.k_values)
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
        (
            "- Category-level metrics are directional only; this remains a small internal "
            "dataset and some categories still have very few tasks."
        ),
        "",
        "## Per-category metrics",
        "",
        (
            f"| category | tasks | R@{primary_k} files | R@{primary_k} symbols | "
            "| MRR files | MRR symbols | file cov | symbol cov |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for category, payload in category_payload.items():
        recall_at_k_files = payload["recall_at_k_files"]
        recall_at_k_symbols = payload["recall_at_k_symbols"]
        assert isinstance(recall_at_k_files, dict)
        assert isinstance(recall_at_k_symbols, dict)
        lines.append(
            f"| {category} | {payload['task_count']} | "
            f"{recall_at_k_files[str(primary_k)]:.6f} | "
            f"{recall_at_k_symbols[str(primary_k)]:.6f} | "
            f"{payload['mrr_files']:.6f} | {payload['mrr_symbols']:.6f} | "
            f"{payload['gold_file_coverage']:.6f} | {payload['gold_symbol_coverage']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Task details",
            "",
            "| task_id | category | missing_gold_files | missing_gold_symbols |",
            "|---|---|---|---|",
        ]
    )
    for outcome in result.outcomes:
        files_text = ", ".join(outcome.missing_gold_files) or "-"
        symbols_text = ", ".join(outcome.missing_gold_symbols) or "-"
        lines.append(f"| {outcome.task_id} | {outcome.category} | {files_text} | {symbols_text} |")
    return "\n".join(lines)


def render_compare_markdown_report(result: BaselineComparisonResult) -> str:
    """Render markdown report for repo-map vs lexical-context-pack comparison."""
    aggregate = result.aggregate
    savings = build_savings_aggregate_payload(result.outcomes)
    generated_false_positives = build_generated_artifact_false_positive_payload(result.outcomes)
    category_payload = build_compare_category_payload(result.outcomes)
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
        "## Estimated token savings (approximate)",
        "",
        (
            "- Token estimates are approximate and deterministic: "
            f"`estimated_tokens = chars / {APPROX_CHARS_PER_TOKEN:g}`."
        ),
        "- Savings are not tokenizer-accurate and must be interpreted directionally.",
        (f"- average_estimated_tokens_saved: `{savings['average_estimated_tokens_saved']:.6f}`"),
        (f"- average_compression_ratio: `{savings['average_compression_ratio']:.6f}`"),
        (
            f"- coverage_preserved_tasks: file="
            f"`{int(savings['gold_file_coverage_preserved_tasks'])}`"
            f", symbol="
            f"`{int(savings['gold_symbol_coverage_preserved_tasks'])}`"
        ),
        (
            f"- improvement_claim_allowed_tasks: "
            f"`{int(savings['improvement_claim_allowed_tasks'])}`/"
            f"`{len(result.outcomes)}`"
        ),
        "",
        "## Generated artifact false positives",
        "",
        (
            f"- repo_map: selections=`{generated_false_positives['repo_map']['selection_count']}`, "
            f"tasks=`{generated_false_positives['repo_map']['task_count']}`"
        ),
        (
            f"- lexical_context_pack: selections="
            f"`{generated_false_positives['lexical_context_pack']['selection_count']}`, "
            f"tasks=`{generated_false_positives['lexical_context_pack']['task_count']}`"
        ),
        (
            f"- repo_map_files: "
            f"`{_format_string_list_or_dash(generated_false_positives['repo_map']['files'])}`"
        ),
        (
            f"- lexical_context_pack_files: "
            f"`{_format_string_list_or_dash(generated_false_positives['lexical_context_pack']['files'])}`"
        ),
        "",
        "## Per-category results",
        "",
        (
            "- Category-level compare results are directional only; some categories still "
            "have very few tasks."
        ),
        "",
        (
            "| category | tasks | repo_map wins | pack wins | tie | inconclusive | "
            "avg saved tok~ | repo_map generated fp | pack generated fp |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for category, payload in category_payload.items():
        wins = payload["wins"]
        savings_payload = payload["savings"]
        false_positives_payload = payload["generated_artifact_false_positives"]
        assert isinstance(wins, dict)
        assert isinstance(savings_payload, dict)
        assert isinstance(false_positives_payload, dict)
        lines.append(
            f"| {category} | {payload['task_count']} | "
            f"{wins['repo_map']} | {wins['lexical_context_pack']} | "
            f"{wins['tie']} | {wins['inconclusive']} | "
            f"{savings_payload['average_estimated_tokens_saved']:.6f} | "
            f"{false_positives_payload['repo_map']['selection_count']} | "
            f"{false_positives_payload['lexical_context_pack']['selection_count']} |"
        )
    lines.extend(
        [
            "",
            "### Savings table",
            "",
            (
                "| task_id | raw_baseline_chars | selected_context_chars | "
                "estimated_raw_tokens | estimated_selected_tokens | "
                "estimated_tokens_saved | compression_ratio | "
                "gold_file_coverage_preserved | gold_symbol_coverage_preserved | "
                "coverage_per_1k_tokens | improvement_claim_allowed |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for task in result.outcomes:
        metrics = task.token_savings_metrics
        lines.append(
            f"| {task.task_id} | {metrics.raw_baseline_chars} | {metrics.selected_context_chars} | "
            f"{metrics.estimated_raw_tokens:.6f} | {metrics.estimated_selected_tokens:.6f} | "
            f"{metrics.estimated_tokens_saved:.6f} | {metrics.compression_ratio:.6f} | "
            f"{metrics.gold_file_coverage_preserved} | {metrics.gold_symbol_coverage_preserved} | "
            f"{metrics.coverage_per_1k_tokens:.6f} | "
            f"{token_savings_improvement_claim_allowed(metrics)} |"
        )

    lines.extend(
        [
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
    )
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
                "- `approx_useful_item_ratio` (`useful_context_ratio` internal "
                "name) is an approximation over selected file and symbol "
                "identifiers (item-level, not token-level) and does not "
                "measure semantic correctness."
            ),
            (
                "- Token estimates are approximate "
                f"(`chars / {APPROX_CHARS_PER_TOKEN:g}`) and are not tokenizer-accurate."
            ),
            (
                "- No superiority claim is made when "
                "`gold_file_coverage_preserved` or "
                "`gold_symbol_coverage_preserved` is false, even if "
                "`estimated_tokens_saved` is positive."
            ),
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
        "by_category": build_retrieval_category_payload(result.outcomes, k_values=result.k_values),
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
    savings_metrics = _token_savings_payload(comparison)
    return {
        "task_id": comparison.task_id,
        "category": comparison.category,
        "prompt": comparison.prompt,
        "gold_files": list(comparison.gold_files),
        "gold_symbols": list(comparison.gold_symbols),
        "winner": comparison.winner,
        "savings_metrics": savings_metrics,
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


def _token_savings_payload(comparison: TaskBaselineComparison) -> dict[str, object]:
    metrics = comparison.token_savings_metrics
    payload: dict[str, object] = {
        "raw_baseline_chars": metrics.raw_baseline_chars,
        "selected_context_chars": metrics.selected_context_chars,
        "estimated_raw_tokens": metrics.estimated_raw_tokens,
        "estimated_selected_tokens": metrics.estimated_selected_tokens,
        "estimated_tokens_saved": metrics.estimated_tokens_saved,
        "compression_ratio": metrics.compression_ratio,
        "gold_file_coverage_preserved": metrics.gold_file_coverage_preserved,
        "gold_symbol_coverage_preserved": metrics.gold_symbol_coverage_preserved,
        "coverage_per_1k_tokens": metrics.coverage_per_1k_tokens,
        "improvement_claim_allowed": token_savings_improvement_claim_allowed(metrics),
    }
    if metrics.context_noise_ratio is not None:
        payload["context_noise_ratio"] = metrics.context_noise_ratio
    return payload


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


def _format_string_list_or_dash(value: object) -> str:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return "-"
    return ", ".join(value) or "-"


# ---------------------------------------------------------------------------
# 59.5 — Benchmark harness markdown report
# ---------------------------------------------------------------------------


def render_benchmark_markdown_report(
    result: BenchmarkRunResult,
    *,
    dataset: str,
    mode: str,
) -> str:
    """Render a deterministic Markdown benchmark report for the 59.0 harness."""
    agg = result.aggregate
    lines: list[str] = [
        "# RSM Benchmark Report",
        "",
        f"- Dataset: `{dataset}`",
        f"- Mode: `{mode}`",
        f"- Cases run: `{len(result.outcomes)}`",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| central_file_found | {agg.central_file_found:.3f} |",
        f"| support_files_found | {agg.support_files_found:.3f} |",
        f"| tests_found | {agg.tests_found:.3f} |",
        f"| noise_reduced | {agg.noise_reduced:.3f} |",
        f"| overall | {agg.overall:.3f} |",
        "",
        "## Cases",
        "",
        "| Case ID | Overall | Central | Support | Tests | Noise |",
        "|---|---|---|---|---|---|",
    ]
    for o in result.outcomes:
        m = o.metrics
        lines.append(
            f"| {o.case.id} | {m.overall:.3f} | {m.central_file_found:.3f} | "
            f"{m.support_files_found:.3f} | {m.tests_found:.3f} | "
            f"{m.noise_reduced:.3f} |"
        )
    lines.append("")

    # Per-case details
    for o in result.outcomes:
        lines.append(f"## {o.case.id}")
        lines.append("")
        lines.append(f"- fixture: `{o.case.fixture}`")
        lines.append(f"- overall: `{o.metrics.overall:.3f}`")
        lines.append("")

        lines.append("### Selected files")
        if o.selected_files:
            for f in o.selected_files:
                lines.append(f"- `{f}`")
        else:
            lines.append("- *(none)*")
        lines.append("")

        if o.missing_central_files:
            lines.append("### Missing central files")
            for f in o.missing_central_files:
                lines.append(f"- `{f}`")
            lines.append("")

        if o.missing_support_files:
            lines.append("### Missing support files")
            for f in o.missing_support_files:
                lines.append(f"- `{f}`")
            lines.append("")

        if o.missing_test_files:
            lines.append("### Missing test files")
            for f in o.missing_test_files:
                lines.append(f"- `{f}`")
            lines.append("")

        if o.forbidden_files_found:
            lines.append("### Forbidden files found")
            for f in o.forbidden_files_found:
                lines.append(f"- `{f}`")
            lines.append("")

    return "\n".join(lines)


def write_benchmark_markdown_report(
    path: Path | str,
    result: BenchmarkRunResult,
    *,
    dataset: str,
    mode: str,
) -> None:
    """Write benchmark harness markdown report to disk."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_benchmark_markdown_report(result, dataset=dataset, mode=mode),
        encoding="utf-8",
    )
