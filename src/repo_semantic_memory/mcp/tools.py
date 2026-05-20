"""Typed placeholders for a future MCP tool surface.

These contracts document the intended local query API without introducing any
runtime MCP dependency, transport implementation, or server process. They are
pre-stable design artifacts rather than a declared public compatibility surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

McpToolName = Literal[
    "search_symbols",
    "explain_entity",
    "build_context_pack",
    "query_graph",
    "export_ai_memory",
    "validate_patch_context",
    "get_git_summary",
]


@dataclass(frozen=True)
class Citation:
    """Structured citation returned with MCP tool results."""

    subject_kind: Literal["entity", "relation", "claim", "git_summary"]
    subject_id: str
    path: str
    start_line: int
    end_line: int
    start_col: int | None = None
    end_col: int | None = None
    extractor: str | None = None
    confidence: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class Uncertainty:
    """Machine-readable uncertainty envelope for incomplete or derived results."""

    code: str
    message: str
    recoverable: bool = True
    subject_id: str | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Uncertainty code must not be empty")
        if not self.message:
            raise ValueError("Uncertainty message must not be empty")


@dataclass(frozen=True)
class BudgetEnvelope:
    """Explicit character-budget accounting for bounded MCP responses."""

    requested_chars: int
    used_chars: int = 0
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.requested_chars < 1:
            raise ValueError("BudgetEnvelope requested_chars must be >= 1")
        if self.used_chars < 0:
            raise ValueError("BudgetEnvelope used_chars must be >= 0")
        if self.used_chars > self.requested_chars:
            raise ValueError("BudgetEnvelope used_chars must be <= requested_chars")


@dataclass(frozen=True)
class ToolContract:
    """Declarative description of a future MCP tool.

    This is metadata only; it does not bind an executable MCP handler.
    """

    name: McpToolName
    summary: str
    request_type: str
    response_type: str
    deterministic: bool = True
    requires_network: bool = False
    deferred_runtime_reason: str = "Runtime transport intentionally deferred."


@dataclass(frozen=True)
class SearchSymbolsRequest:
    """Placeholder request for symbol lookup over the local index."""

    query: str
    db_path: str = ".rsm/index.sqlite"
    limit: int = 10
    entity_kinds: tuple[str, ...] = ()
    path_roles: tuple[str, ...] = ()
    include_relations: bool = False

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("SearchSymbolsRequest query must not be empty")
        if self.limit < 1:
            raise ValueError("SearchSymbolsRequest limit must be >= 1")


@dataclass(frozen=True)
class SearchSymbolsResponse:
    """Placeholder response for symbol search results."""

    matches: tuple[str, ...] = ()
    results: tuple[dict[str, object], ...] = ()
    citations: tuple[Citation, ...] = ()
    uncertainties: tuple[Uncertainty, ...] = ()
    budget: BudgetEnvelope | None = None


@dataclass(frozen=True)
class ExplainEntityRequest:
    """Placeholder request for deterministic entity explanation."""

    entity_id: str
    db_path: str = ".rsm/index.sqlite"
    include_incoming_relations: bool = True
    include_outgoing_relations: bool = True
    include_components: bool = True
    include_claims: bool = True

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("ExplainEntityRequest entity_id must not be empty")


@dataclass(frozen=True)
class ExplainEntityResponse:
    """Placeholder response for a resolved entity description."""

    entity_id: str
    entity: dict[str, object] | None = None
    relations: tuple[dict[str, object], ...] = ()
    semantic_components: tuple[dict[str, object], ...] = ()
    related_entity_ids: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    uncertainties: tuple[Uncertainty, ...] = ()


@dataclass(frozen=True)
class BuildContextPackRequest:
    """Placeholder request for bounded context-pack construction."""

    task: str
    db_path: str = ".rsm/index.sqlite"
    budget_chars: int = 4000
    format: Literal["markdown", "yaml"] = "markdown"
    profile: str = "agent_standard"
    explain_ranking: bool = False
    include_semantic_components: bool = True

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("BuildContextPackRequest task must not be empty")
        if self.budget_chars < 1:
            raise ValueError("BuildContextPackRequest budget_chars must be >= 1")


@dataclass(frozen=True)
class BuildContextPackResponse:
    """Placeholder response for future context-pack MCP output."""

    rendered: str
    payload: dict[str, object] = field(default_factory=dict)
    selected_entity_ids: tuple[str, ...] = ()
    selected_relation_keys: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    uncertainties: tuple[Uncertainty, ...] = ()
    budget: BudgetEnvelope = field(default_factory=lambda: BudgetEnvelope(requested_chars=1))


@dataclass(frozen=True)
class QueryGraphRequest:
    """Placeholder request for bounded graph traversal."""

    db_path: str = ".rsm/index.sqlite"
    entity_ids: tuple[str, ...]
    relation_kinds: tuple[str, ...] = ()
    direction: Literal["outgoing", "incoming", "both"] = "both"
    max_hops: int = 1
    limit: int = 25

    def __post_init__(self) -> None:
        if not self.entity_ids:
            raise ValueError("QueryGraphRequest entity_ids must not be empty")
        if self.max_hops < 1:
            raise ValueError("QueryGraphRequest max_hops must be >= 1")
        if self.limit < 1:
            raise ValueError("QueryGraphRequest limit must be >= 1")


@dataclass(frozen=True)
class QueryGraphResponse:
    """Placeholder response for graph query results."""

    entity_ids: tuple[str, ...] = ()
    entities: tuple[dict[str, object], ...] = ()
    relations: tuple[dict[str, object], ...] = ()
    relation_keys: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    uncertainties: tuple[Uncertainty, ...] = ()
    budget: BudgetEnvelope | None = None


@dataclass(frozen=True)
class ExportAiMemoryRequest:
    """Placeholder request matching the existing local `.ai/` export flow."""

    db_path: str = ".rsm/index.sqlite"
    output_dir: str | None = None
    force: bool = False

    def __post_init__(self) -> None:
        if self.output_dir is None or not self.output_dir.strip():
            raise ValueError("ExportAiMemoryRequest output_dir must be explicitly provided")


@dataclass(frozen=True)
class ExportAiMemoryResponse:
    """Placeholder response for `.ai/` export summaries."""

    files_written: tuple[str, ...] = ()
    files_skipped: tuple[str, ...] = ()
    entity_count: int = 0
    relation_count: int = 0
    component_count: int = 0
    invariant_count: int = 0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatePatchContextRequest:
    """Placeholder request for cited patch-context coverage checks.

    This future tool is scoped to touched-file justification and context
    sufficiency, not patch correctness.
    """

    task: str
    db_path: str = ".rsm/index.sqlite"
    changed_paths: tuple[str, ...]
    referenced_entity_ids: tuple[str, ...] = ()
    budget_chars: int | None = None

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("ValidatePatchContextRequest task must not be empty")
        if not self.changed_paths:
            raise ValueError("ValidatePatchContextRequest changed_paths must not be empty")
        if self.budget_chars is not None and self.budget_chars < 1:
            raise ValueError("ValidatePatchContextRequest budget_chars must be >= 1")


@dataclass(frozen=True)
class ValidatePatchContextResponse:
    """Placeholder response for missing-context recommendations.

    The response is meant to explain what context is missing or unjustified,
    not whether a patch is correct.
    """

    covered_paths: tuple[str, ...] = ()
    missing_paths: tuple[str, ...] = ()
    covered_entity_ids: tuple[str, ...] = ()
    missing_entity_ids: tuple[str, ...] = ()
    suggested_context_query: str | None = None
    suggested_follow_up_tools: tuple[McpToolName, ...] = ()
    uncertainties: tuple[Uncertainty, ...] = ()
    budget: BudgetEnvelope | None = None


@dataclass(frozen=True)
class GetGitSummaryRequest:
    """Placeholder request mirroring the local git summary command."""

    path: str

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("GetGitSummaryRequest path must not be empty")


@dataclass(frozen=True)
class GetGitSummaryResponse:
    """Placeholder response for local Git repository summary data."""

    repository_root: str | None = None
    branch: str | None = None
    head_commit: str | None = None
    dirty: bool = False
    citations: tuple[Citation, ...] = ()
    uncertainties: tuple[Uncertainty, ...] = ()


def get_mcp_tool_contracts() -> tuple[ToolContract, ...]:
    """Return declarative contracts for the planned MCP tool surface.

    The returned values describe names and typed envelopes only. They are not
    executable handlers and do not start or configure any MCP runtime.
    """

    return (
        ToolContract(
            name="search_symbols",
            summary="Find indexed entities by lexical query.",
            request_type="SearchSymbolsRequest",
            response_type="SearchSymbolsResponse",
        ),
        ToolContract(
            name="explain_entity",
            summary="Resolve one entity with structural context and citations.",
            request_type="ExplainEntityRequest",
            response_type="ExplainEntityResponse",
        ),
        ToolContract(
            name="build_context_pack",
            summary="Build a bounded task-specific context pack.",
            request_type="BuildContextPackRequest",
            response_type="BuildContextPackResponse",
        ),
        ToolContract(
            name="query_graph",
            summary="Traverse a bounded structural subgraph.",
            request_type="QueryGraphRequest",
            response_type="QueryGraphResponse",
        ),
        ToolContract(
            name="export_ai_memory",
            summary="Regenerate local `.ai/` artifacts without network access.",
            request_type="ExportAiMemoryRequest",
            response_type="ExportAiMemoryResponse",
        ),
        ToolContract(
            name="validate_patch_context",
            summary="Check whether a patch has enough indexed context.",
            request_type="ValidatePatchContextRequest",
            response_type="ValidatePatchContextResponse",
        ),
        ToolContract(
            name="get_git_summary",
            summary="Expose local Git summary metadata when available.",
            request_type="GetGitSummaryRequest",
            response_type="GetGitSummaryResponse",
        ),
    )
