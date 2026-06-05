"""Context builders for agent-facing compact outputs."""

from repo_semantic_memory.context.budget import CharacterBudget
from repo_semantic_memory.context.compression import (
    CompressionProfile,
    available_profile_names,
    resolve_profile,
)
from repo_semantic_memory.context.context_pack import ContextPack
from repo_semantic_memory.context.pack_builder import build_context_pack
from repo_semantic_memory.context.render_markdown import render_context_pack_markdown
from repo_semantic_memory.context.repo_map import build_repo_map_markdown
from repo_semantic_memory.context.selection_reasons import (
    SELECTION_REASON_CODES,
    SelectionReason,
    build_selection_reasons,
    classify_reason_string,
    dedupe_selection_reasons,
)

__all__ = [
    "CharacterBudget",
    "CompressionProfile",
    "ContextPack",
    "SELECTION_REASON_CODES",
    "SelectionReason",
    "available_profile_names",
    "build_context_pack",
    "build_repo_map_markdown",
    "build_selection_reasons",
    "classify_reason_string",
    "dedupe_selection_reasons",
    "render_context_pack_markdown",
    "resolve_profile",
]
