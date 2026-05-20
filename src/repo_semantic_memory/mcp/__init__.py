"""Minimal typed placeholders for the future MCP integration layer.

These exports are pre-stable design artifacts for a future read-only MCP
surface. They are not a declared stable public API yet.
"""

from repo_semantic_memory.mcp.tools import (
    BudgetEnvelope,
    BuildContextPackRequest,
    BuildContextPackResponse,
    Citation,
    ExplainEntityRequest,
    ExplainEntityResponse,
    ExportAiMemoryRequest,
    ExportAiMemoryResponse,
    GetGitSummaryRequest,
    GetGitSummaryResponse,
    McpToolName,
    QueryGraphRequest,
    QueryGraphResponse,
    SearchSymbolsRequest,
    SearchSymbolsResponse,
    ToolContract,
    Uncertainty,
    ValidatePatchContextRequest,
    ValidatePatchContextResponse,
    get_mcp_tool_contracts,
)
from repo_semantic_memory.mcp.handlers import (
    handle_build_context_pack,
    handle_explain_entity,
    handle_export_ai_memory,
    handle_get_git_summary,
    handle_query_graph,
    handle_search_symbols,
    handle_validate_patch_context,
)

__all__ = [
    "BudgetEnvelope",
    "BuildContextPackRequest",
    "BuildContextPackResponse",
    "Citation",
    "ExplainEntityRequest",
    "ExplainEntityResponse",
    "ExportAiMemoryRequest",
    "ExportAiMemoryResponse",
    "GetGitSummaryRequest",
    "GetGitSummaryResponse",
    "McpToolName",
    "QueryGraphRequest",
    "QueryGraphResponse",
    "SearchSymbolsRequest",
    "SearchSymbolsResponse",
    "ToolContract",
    "Uncertainty",
    "ValidatePatchContextRequest",
    "ValidatePatchContextResponse",
    "handle_build_context_pack",
    "handle_explain_entity",
    "handle_export_ai_memory",
    "handle_get_git_summary",
    "handle_query_graph",
    "handle_search_symbols",
    "handle_validate_patch_context",
    "get_mcp_tool_contracts",
]
