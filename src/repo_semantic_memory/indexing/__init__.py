"""Incremental indexing layer (planning and future execution)."""

from repo_semantic_memory.indexing.incremental import (
    IncrementalFallbackReason,
    IncrementalPlan,
    plan_incremental_update,
)

__all__ = [
    "IncrementalFallbackReason",
    "IncrementalPlan",
    "plan_incremental_update",
]
