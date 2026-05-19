"""Deterministic aggregate payload helpers for benchmark reports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from statistics import mean

from repo_semantic_memory.context.path_roles import is_generated_artifact_path
from repo_semantic_memory.eval.baselines import TaskBaselineComparison
from repo_semantic_memory.eval.metrics import (
    RetrievalOutcome,
    TokenSavingsMetrics,
    compute_benchmark_metrics,
    token_savings_improvement_claim_allowed,
)


def build_retrieval_category_payload(
    outcomes: Sequence[RetrievalOutcome], *, k_values: tuple[int, ...]
) -> dict[str, dict[str, object]]:
    """Build per-category retrieval aggregates."""
    grouped: dict[str, list[RetrievalOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.category].append(outcome)

    payload: dict[str, dict[str, object]] = {}
    for category in sorted(grouped):
        category_outcomes = tuple(grouped[category])
        metrics = compute_benchmark_metrics(category_outcomes, k_values=k_values).aggregate
        payload[category] = {
            "task_count": len(category_outcomes),
            "recall_at_k_files": {str(k): metrics.recall_at_k_files[k] for k in k_values},
            "recall_at_k_symbols": {str(k): metrics.recall_at_k_symbols[k] for k in k_values},
            "mrr_files": metrics.mrr_files,
            "mrr_symbols": metrics.mrr_symbols,
            "gold_file_coverage": metrics.gold_file_coverage,
            "gold_symbol_coverage": metrics.gold_symbol_coverage,
            "context_character_estimate": metrics.context_character_estimate,
        }
    return payload


def build_compare_category_payload(
    outcomes: Sequence[TaskBaselineComparison],
) -> dict[str, dict[str, object]]:
    """Build per-category baseline-comparison aggregates."""
    grouped: dict[str, list[TaskBaselineComparison]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.category].append(outcome)

    payload: dict[str, dict[str, object]] = {}
    for category in sorted(grouped):
        category_outcomes = tuple(grouped[category])
        payload[category] = {
            "task_count": len(category_outcomes),
            "average_context_character_count": {
                "repo_map": mean(
                    task.repo_map.context_character_count for task in category_outcomes
                ),
                "lexical_context_pack": mean(
                    task.lexical_context_pack.context_character_count for task in category_outcomes
                ),
            },
            "average_gold_file_coverage": {
                "repo_map": mean(task.repo_map.gold_file_coverage for task in category_outcomes),
                "lexical_context_pack": mean(
                    task.lexical_context_pack.gold_file_coverage for task in category_outcomes
                ),
            },
            "average_gold_symbol_coverage": {
                "repo_map": mean(task.repo_map.gold_symbol_coverage for task in category_outcomes),
                "lexical_context_pack": mean(
                    task.lexical_context_pack.gold_symbol_coverage for task in category_outcomes
                ),
            },
            "average_useful_context_ratio": {
                "repo_map": mean(task.repo_map.useful_context_ratio for task in category_outcomes),
                "lexical_context_pack": mean(
                    task.lexical_context_pack.useful_context_ratio for task in category_outcomes
                ),
            },
            "wins": {
                "repo_map": sum(1 for task in category_outcomes if task.winner == "repo_map"),
                "lexical_context_pack": sum(
                    1 for task in category_outcomes if task.winner == "lexical_context_pack"
                ),
                "tie": sum(1 for task in category_outcomes if task.winner == "tie"),
                "inconclusive": sum(
                    1 for task in category_outcomes if task.winner == "inconclusive"
                ),
            },
            "savings": build_savings_aggregate_payload(category_outcomes),
            "generated_artifact_false_positives": build_generated_artifact_false_positive_payload(
                category_outcomes
            ),
        }
    return payload


def build_savings_aggregate_payload(
    outcomes: Sequence[TaskBaselineComparison],
) -> dict[str, int | float]:
    """Build aggregate token-savings payload."""
    if not outcomes:
        return {
            "average_raw_baseline_chars": 0.0,
            "average_selected_context_chars": 0.0,
            "average_estimated_raw_tokens": 0.0,
            "average_estimated_selected_tokens": 0.0,
            "average_estimated_tokens_saved": 0.0,
            "average_compression_ratio": 0.0,
            "average_coverage_per_1k_tokens": 0.0,
            "gold_file_coverage_preserved_tasks": 0,
            "gold_symbol_coverage_preserved_tasks": 0,
            "improvement_claim_allowed_tasks": 0,
        }

    metrics = [outcome.token_savings_metrics for outcome in outcomes]
    return _build_savings_metrics_payload(metrics)


def build_generated_artifact_false_positive_payload(
    outcomes: Sequence[TaskBaselineComparison],
) -> dict[str, dict[str, object]]:
    """Build deterministic generated-artifact false-positive summary."""
    baselines = {
        "repo_map": [task.repo_map for task in outcomes],
        "lexical_context_pack": [task.lexical_context_pack for task in outcomes],
    }
    payload: dict[str, dict[str, object]] = {}
    for baseline_name, results in baselines.items():
        files = sorted(
            {
                file_path
                for result in results
                for file_path in result.extra_selected_files
                if is_generated_artifact_path(file_path)
            }
        )
        task_ids = sorted(
            {
                task.task_id
                for task in outcomes
                if any(
                    is_generated_artifact_path(file_path)
                    for file_path in (
                        task.repo_map.extra_selected_files
                        if baseline_name == "repo_map"
                        else task.lexical_context_pack.extra_selected_files
                    )
                )
            }
        )
        payload[baseline_name] = {
            "selection_count": sum(
                1
                for result in results
                for file_path in result.extra_selected_files
                if is_generated_artifact_path(file_path)
            ),
            "task_count": len(task_ids),
            "files": files,
            "task_ids": task_ids,
        }
    return payload


def _build_savings_metrics_payload(
    metrics: Sequence[TokenSavingsMetrics],
) -> dict[str, int | float]:
    if not metrics:
        return {
            "average_raw_baseline_chars": 0.0,
            "average_selected_context_chars": 0.0,
            "average_estimated_raw_tokens": 0.0,
            "average_estimated_selected_tokens": 0.0,
            "average_estimated_tokens_saved": 0.0,
            "average_compression_ratio": 0.0,
            "average_coverage_per_1k_tokens": 0.0,
            "gold_file_coverage_preserved_tasks": 0,
            "gold_symbol_coverage_preserved_tasks": 0,
            "improvement_claim_allowed_tasks": 0,
        }
    return {
        "average_raw_baseline_chars": mean(metric.raw_baseline_chars for metric in metrics),
        "average_selected_context_chars": mean(metric.selected_context_chars for metric in metrics),
        "average_estimated_raw_tokens": mean(metric.estimated_raw_tokens for metric in metrics),
        "average_estimated_selected_tokens": mean(
            metric.estimated_selected_tokens for metric in metrics
        ),
        "average_estimated_tokens_saved": mean(metric.estimated_tokens_saved for metric in metrics),
        "average_compression_ratio": mean(metric.compression_ratio for metric in metrics),
        "average_coverage_per_1k_tokens": mean(metric.coverage_per_1k_tokens for metric in metrics),
        "gold_file_coverage_preserved_tasks": sum(
            1 for metric in metrics if metric.gold_file_coverage_preserved
        ),
        "gold_symbol_coverage_preserved_tasks": sum(
            1 for metric in metrics if metric.gold_symbol_coverage_preserved
        ),
        "improvement_claim_allowed_tasks": sum(
            1 for metric in metrics if token_savings_improvement_claim_allowed(metric)
        ),
    }
