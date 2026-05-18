"""Tests for deferred MCP tool contracts and placeholder types."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from repo_semantic_memory.mcp import (
    BudgetEnvelope,
    BuildContextPackRequest,
    GetGitSummaryRequest,
    QueryGraphRequest,
    SearchSymbolsRequest,
    Uncertainty,
    ValidatePatchContextRequest,
    get_mcp_tool_contracts,
)


def test_mcp_tool_contracts_are_deterministic_and_local_only() -> None:
    contracts = get_mcp_tool_contracts()
    assert tuple(contract.name for contract in contracts) == (
        "search_symbols",
        "explain_entity",
        "build_context_pack",
        "query_graph",
        "export_ai_memory",
        "validate_patch_context",
        "get_git_summary",
    )
    assert all(contract.deterministic for contract in contracts)
    assert all(not contract.requires_network for contract in contracts)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: SearchSymbolsRequest(query="   "), "query must not be empty"),
        (lambda: SearchSymbolsRequest(query="repo map", limit=0), "limit must be >= 1"),
        (lambda: BuildContextPackRequest(task="", budget_chars=10), "task must not be empty"),
        (lambda: QueryGraphRequest(entity_ids=(), max_hops=1), "entity_ids must not be empty"),
        (
            lambda: ValidatePatchContextRequest(task="audit", changed_paths=(), budget_chars=10),
            "changed_paths must not be empty",
        ),
        (lambda: GetGitSummaryRequest(path=""), "path must not be empty"),
        (lambda: Uncertainty(code="", message="missing"), "code must not be empty"),
    ],
)
def test_mcp_request_validations(factory: Callable[[], object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


@pytest.mark.parametrize(
    ("requested_chars", "used_chars", "message"),
    [
        (0, 0, "requested_chars must be >= 1"),
        (10, -1, "used_chars must be >= 0"),
        (10, 11, "used_chars must be <= requested_chars"),
    ],
)
def test_budget_envelope_validates_bounds(
    requested_chars: int, used_chars: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        BudgetEnvelope(requested_chars=requested_chars, used_chars=used_chars)


def test_budget_envelope_accepts_repeatable_valid_values() -> None:
    budget = BudgetEnvelope(requested_chars=4000, used_chars=1250, truncated=True)
    assert budget.requested_chars == 4000
    assert budget.used_chars == 1250
    assert budget.truncated is True
