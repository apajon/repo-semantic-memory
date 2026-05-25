"""Incremental indexing layer (planning and execution)."""

from repo_semantic_memory.indexing.executor import IncrementalResult, run_incremental_index
from repo_semantic_memory.indexing.incremental import (
    IncrementalFallbackReason,
    IncrementalPlan,
    plan_incremental_update,
)

__all__ = [
    "IncrementalFallbackReason",
    "IncrementalPlan",
    "IncrementalResult",
    "plan_incremental_update",
    "run_incremental_index",
]
