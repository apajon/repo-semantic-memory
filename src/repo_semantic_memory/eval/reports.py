"""Report rendering for retrieval benchmark results."""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.eval.runner import RetrievalBenchmarkResult


def to_json_payload(result: RetrievalBenchmarkResult) -> dict[str, object]:
    """Convert benchmark result to deterministic JSON payload."""
    return {
        "dataset_path": result.dataset_path,
        "db_path": result.db_path,
        "k_values": list(result.k_values),
        "aggregate": _aggregate_payload(result),
        "tasks": [_task_payload(result, index) for index in range(len(result.outcomes))],
    }


def render_compact_table(result: RetrievalBenchmarkResult) -> str:
    """Render compact plain-text benchmark table."""
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
    aggregate_files = aggregate["recall_at_k_files"]
    aggregate_symbols = aggregate["recall_at_k_symbols"]
    if not isinstance(aggregate_files, dict) or not isinstance(aggregate_symbols, dict):
        raise ValueError("Aggregate recall payload has unexpected type")
    rows.append(
        (
            "AVG",
            f"{float(aggregate_files[primary_k]):.3f}",
            f"{float(aggregate_symbols[primary_k]):.3f}",
            f"{float(aggregate['mrr_files']):.3f}",
            f"{float(aggregate['mrr_symbols']):.3f}",
            f"{float(aggregate['gold_file_coverage']):.3f}",
            f"{float(aggregate['gold_symbol_coverage']):.3f}",
            f"{float(aggregate['context_character_estimate']):.1f}",
            "-",
        )
    )
    return _render_rows(rows)


def render_markdown_report(result: RetrievalBenchmarkResult) -> str:
    """Render markdown benchmark report."""
    payload = to_json_payload(result)
    aggregate = payload["aggregate"]
    if not isinstance(aggregate, dict):
        raise ValueError("Unexpected aggregate payload shape")
    lines = [
        "# Retrieval benchmark report",
        "",
        f"- dataset: `{result.dataset_path}`",
        f"- db: `{result.db_path}`",
        f"- tasks: `{len(result.outcomes)}`",
        "",
        "## Aggregate metrics",
        "",
        f"- mrr_files: `{aggregate['mrr_files']:.6f}`",
        f"- mrr_symbols: `{aggregate['mrr_symbols']:.6f}`",
        f"- gold_file_coverage: `{aggregate['gold_file_coverage']:.6f}`",
        f"- gold_symbol_coverage: `{aggregate['gold_symbol_coverage']:.6f}`",
        f"- context_character_estimate: `{aggregate['context_character_estimate']:.6f}`",
        "",
        "## Task details",
        "",
        "| task_id | category | missing_gold_files | missing_gold_symbols |",
        "|---|---|---|---|",
    ]
    for task in payload["tasks"]:
        if not isinstance(task, dict):
            continue
        lines.append(
            "| {task_id} | {category} | {missing_gold_files} | {missing_gold_symbols} |".format(
                task_id=task["task_id"],
                category=task["category"],
                missing_gold_files=", ".join(task["missing_gold_files"]) or "-",
                missing_gold_symbols=", ".join(task["missing_gold_symbols"]) or "-",
            )
        )
    return "\n".join(lines)


def write_markdown_report(path: Path | str, result: RetrievalBenchmarkResult) -> None:
    """Write markdown report to disk."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown_report(result), encoding="utf-8")


def _aggregate_payload(result: RetrievalBenchmarkResult) -> dict[str, object]:
    aggregate = result.metrics.aggregate
    files_recall = aggregate["recall_at_k_files"]
    symbols_recall = aggregate["recall_at_k_symbols"]
    if not isinstance(files_recall, dict) or not isinstance(symbols_recall, dict):
        raise ValueError("Aggregate recall payload has unexpected type")
    return {
        "recall_at_k_files": {str(k): float(files_recall[k]) for k in result.k_values},
        "recall_at_k_symbols": {str(k): float(symbols_recall[k]) for k in result.k_values},
        "mrr_files": float(aggregate["mrr_files"]),
        "mrr_symbols": float(aggregate["mrr_symbols"]),
        "context_character_estimate": float(aggregate["context_character_estimate"]),
        "gold_file_coverage": float(aggregate["gold_file_coverage"]),
        "gold_symbol_coverage": float(aggregate["gold_symbol_coverage"]),
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


def _render_rows(rows: list[tuple[str, ...]]) -> str:
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
