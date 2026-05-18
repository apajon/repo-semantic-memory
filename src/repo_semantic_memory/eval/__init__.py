"""Retrieval benchmark harness exports."""

from repo_semantic_memory.eval.baselines import BaselineTaskResult, TaskBaselineComparison
from repo_semantic_memory.eval.datasets import GoldTargets, RetrievalDataset, RetrievalTask
from repo_semantic_memory.eval.metrics import (
    AggregateMetrics,
    BenchmarkMetrics,
    RetrievalOutcome,
    TaskMetrics,
)
from repo_semantic_memory.eval.reports import (
    render_compact_table,
    render_compare_compact_table,
    render_compare_markdown_report,
    render_markdown_report,
    to_compare_json_payload,
    to_json_payload,
    write_compare_markdown_report,
    write_markdown_report,
)
from repo_semantic_memory.eval.runner import (
    BaselineComparisonResult,
    CompareAggregate,
    RetrievalBenchmarkResult,
    run_baseline_comparison,
    run_retrieval_benchmark,
)

__all__ = [
    "AggregateMetrics",
    "BaselineComparisonResult",
    "BaselineTaskResult",
    "BenchmarkMetrics",
    "CompareAggregate",
    "GoldTargets",
    "RetrievalBenchmarkResult",
    "RetrievalDataset",
    "RetrievalOutcome",
    "RetrievalTask",
    "TaskBaselineComparison",
    "TaskMetrics",
    "render_compact_table",
    "render_compare_compact_table",
    "render_compare_markdown_report",
    "render_markdown_report",
    "run_baseline_comparison",
    "run_retrieval_benchmark",
    "to_compare_json_payload",
    "to_json_payload",
    "write_compare_markdown_report",
    "write_markdown_report",
]
