"""Minimal MCP runtime adapters wrapping existing pure handlers.

This module is the only place that maps between JSON-shaped tool arguments and
the typed request/response dataclasses defined in :mod:`repo_semantic_memory.mcp.tools`.
It deliberately contains no transport logic and no business logic; it composes
existing pure handlers.

The exposed surface is read-only and intentionally narrow. Write and indexing
tools are not registered. See ``docs/usage/mcp.md`` and ``docs/design/mcp_runtime.md``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any

from repo_semantic_memory.mcp import handlers as _handlers
from repo_semantic_memory.mcp.tools import (
    BuildContextPackRequest,
    ExplainEntityRequest,
    GetGitSummaryRequest,
    QueryGraphRequest,
    SearchSymbolsRequest,
    ValidatePatchContextRequest,
)
from repo_semantic_memory.store import SQLiteStore
from repo_semantic_memory.version import get_version_info

# Phase 1 tool names. Kept in a tuple so the registry order and any test that
# asserts the exposed surface remains stable and easy to audit.
PHASE1_TOOL_NAMES: tuple[str, ...] = (
    "rsm_status",
    "rsm_search_symbols",
    "rsm_explain_entity",
    "rsm_build_context_pack",
    "rsm_query_graph",
    "rsm_validate_patch_context",
    "rsm_get_git_summary",
)

# Tools explicitly deferred in phase 1. Listed only so safety tests can assert
# they are NOT registered.
DEFERRED_TOOL_NAMES: tuple[str, ...] = (
    "rsm_index",
    "rsm_export_ai",
    "rsm_export_jsonl",
    "rsm_import_jsonl",
    "rsm_invariants_import",
    "rsm_invariants_export",
    "rsm_run_command",
    "rsm_run_tests",
    "rsm_apply_patch",
)


@dataclass(frozen=True)
class SessionConfig:
    """Validated repo/db configuration for one MCP server session."""

    repo_root: Path
    db_path: Path


@dataclass(frozen=True)
class ToolDescriptor:
    """Static description of an exposed MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any], SessionConfig], dict[str, Any]]


class ToolInvocationError(ValueError):
    """Raised when a tool invocation fails for a known, user-facing reason."""


def validate_session(repo: str | Path, db: str | Path) -> SessionConfig:
    """Validate ``--repo`` and ``--db`` paths and return a session config.

    Phase 1 rules:
    - ``repo`` must exist and be a directory.
    - ``db`` must exist and be a regular file (no auto-creation).
    - ``db`` must live inside ``repo`` after resolving symlinks.
    """

    repo_path = Path(repo).expanduser()
    db_path_input = Path(db).expanduser()
    if not repo_path.exists():
        raise ValueError(f"--repo path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise ValueError(f"--repo path is not a directory: {repo_path}")
    resolved_repo = repo_path.resolve(strict=True)

    if not db_path_input.exists():
        raise ValueError(
            f"--db path does not exist: {db_path_input}. "
            f"Build it first with: rsm index {resolved_repo} --db {db_path_input}"
        )
    if not db_path_input.is_file():
        raise ValueError(f"--db path is not a file: {db_path_input}")
    resolved_db = db_path_input.resolve(strict=True)
    try:
        resolved_db.relative_to(resolved_repo)
    except ValueError as exc:
        raise ValueError(
            f"--db path must be inside --repo (got db={resolved_db}, repo={resolved_repo})"
        ) from exc
    return SessionConfig(repo_root=resolved_repo, db_path=resolved_db)


def to_jsonable(value: Any) -> Any:
    """Convert dataclass instances and nested containers to JSON-safe values.

    Dataclasses become dicts, tuples become lists, and ``Path`` is rendered as
    its POSIX string. All other primitives pass through.
    """

    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _require_str(args: Mapping[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolInvocationError(f"argument '{key}' must be a non-empty string")
    return value


def _optional_int(args: Mapping[str, Any], key: str, default: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInvocationError(f"argument '{key}' must be an integer")
    return value


def _optional_bool(args: Mapping[str, Any], key: str, default: bool) -> bool:
    value = args.get(key, default)
    if not isinstance(value, bool):
        raise ToolInvocationError(f"argument '{key}' must be a boolean")
    return value


def _str_tuple(args: Mapping[str, Any], key: str) -> tuple[str, ...]:
    raw = args.get(key, [])
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ToolInvocationError(f"argument '{key}' must be a list of strings")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ToolInvocationError(f"argument '{key}' must be a list of strings")
        out.append(item)
    return tuple(out)


def _tool_status(args: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    """Lightweight local status wrapper using repo/db/index metadata."""

    del args  # status takes no inputs
    version = get_version_info()
    payload: dict[str, Any] = {
        "repo_root": session.repo_root.as_posix(),
        "db_path": session.db_path.as_posix(),
        "db_exists": session.db_path.is_file(),
        "package_version": version.package_version,
        "schema_version": version.schema_version,
        "context_pack_version": version.context_pack_version,
        "read_only": True,
        "auto_index": False,
        "tools": list(PHASE1_TOOL_NAMES),
    }
    store = SQLiteStore(session.db_path)
    try:
        store.initialize()
        metadata = store.get_metadata()
        entity_count = len(store.list_entities())
        relation_count = len(store.list_relations())
    finally:
        store.close()
    payload["index_metadata"] = dict(sorted(metadata.items()))
    payload["entity_count"] = entity_count
    payload["relation_count"] = relation_count
    return payload


def _serialize_response(response: Any) -> dict[str, Any]:
    """Convert a typed handler response (dataclass) to a JSON-safe dict.

    Handler responses are frozen dataclasses, so ``to_jsonable`` always yields
    a dict here. We still defensively raise ``TypeError`` rather than using
    ``assert``, because ``assert`` is stripped under ``python -O``.
    """

    payload = to_jsonable(response)
    if not isinstance(payload, dict):
        raise TypeError(
            f"expected dataclass response, got {type(response).__name__} -> "
            f"{type(payload).__name__}"
        )
    return payload


def _tool_search_symbols(args: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    request = SearchSymbolsRequest(
        query=_require_str(args, "query"),
        db_path=str(session.db_path),
        limit=_optional_int(args, "limit", 10),
        entity_kinds=_str_tuple(args, "entity_kinds"),
        path_roles=_str_tuple(args, "path_roles"),
        include_relations=_optional_bool(args, "include_relations", False),
    )
    response = _handlers.handle_search_symbols(request, repo_root=session.repo_root)
    return _serialize_response(response)


def _tool_explain_entity(args: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    request = ExplainEntityRequest(
        entity_id=_require_str(args, "entity_id"),
        db_path=str(session.db_path),
        include_incoming_relations=_optional_bool(args, "include_incoming_relations", True),
        include_outgoing_relations=_optional_bool(args, "include_outgoing_relations", True),
        include_components=_optional_bool(args, "include_components", True),
        include_claims=_optional_bool(args, "include_claims", True),
    )
    response = _handlers.handle_explain_entity(request, repo_root=session.repo_root)
    return _serialize_response(response)


def _tool_build_context_pack(args: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    fmt = args.get("format", "markdown")
    if fmt not in ("markdown", "yaml"):
        raise ToolInvocationError("argument 'format' must be 'markdown' or 'yaml'")
    request = BuildContextPackRequest(
        task=_require_str(args, "task"),
        db_path=str(session.db_path),
        budget_chars=_optional_int(args, "budget_chars", 4000),
        format=fmt,
        profile=str(args.get("profile", "agent_standard")),
        explain_ranking=_optional_bool(args, "explain_ranking", False),
        include_semantic_components=_optional_bool(args, "include_semantic_components", True),
        include_rendered=_optional_bool(args, "include_rendered", False),
        include_payload=_optional_bool(args, "include_payload", False),
        include_ranking_breakdowns=_optional_bool(args, "include_ranking_breakdowns", False),
        max_entities=_optional_int(args, "max_entities", 15),
        max_relations=_optional_int(args, "max_relations", 10),
        max_citations=_optional_int(args, "max_citations", 12),
    )
    response = _handlers.handle_build_context_pack(request, repo_root=session.repo_root)
    return _serialize_response(response)


def _tool_query_graph(args: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    direction = args.get("direction", "both")
    if direction not in ("outgoing", "incoming", "both"):
        raise ToolInvocationError(
            "argument 'direction' must be one of 'outgoing', 'incoming', 'both'"
        )
    entity_ids = _str_tuple(args, "entity_ids")
    if not entity_ids:
        raise ToolInvocationError("argument 'entity_ids' must be a non-empty list of strings")
    request = QueryGraphRequest(
        entity_ids=entity_ids,
        db_path=str(session.db_path),
        relation_kinds=_str_tuple(args, "relation_kinds"),
        direction=direction,
        max_hops=_optional_int(args, "max_hops", 1),
        limit=_optional_int(args, "limit", 25),
    )
    response = _handlers.handle_query_graph(request, repo_root=session.repo_root)
    return _serialize_response(response)


def _tool_validate_patch_context(args: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    changed_paths = _str_tuple(args, "changed_paths")
    if not changed_paths:
        raise ToolInvocationError("argument 'changed_paths' must be a non-empty list of strings")
    budget_value: int | None
    if "budget_chars" in args and args["budget_chars"] is not None:
        budget_value = _optional_int(args, "budget_chars", 0)
    else:
        budget_value = None
    request = ValidatePatchContextRequest(
        task=_require_str(args, "task"),
        changed_paths=changed_paths,
        db_path=str(session.db_path),
        referenced_entity_ids=_str_tuple(args, "referenced_entity_ids"),
        budget_chars=budget_value,
    )
    response = _handlers.handle_validate_patch_context(request, repo_root=session.repo_root)
    return _serialize_response(response)


def _tool_get_git_summary(args: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    path_value = args.get("path", session.repo_root.as_posix())
    if not isinstance(path_value, str) or not path_value.strip():
        raise ToolInvocationError("argument 'path' must be a non-empty string")
    request = GetGitSummaryRequest(path=path_value)
    response = _handlers.handle_get_git_summary(request, repo_root=session.repo_root)
    return _serialize_response(response)


def _input_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def build_tool_registry() -> dict[str, ToolDescriptor]:
    """Return the read-only MCP tool registry for phase 1.

    The registry never includes indexing, export, import, mutation, or arbitrary
    shell/test execution tools. See ``DEFERRED_TOOL_NAMES`` for the explicit
    deferral list used by safety regression tests.
    """

    descriptors: list[ToolDescriptor] = [
        ToolDescriptor(
            name="rsm_status",
            description=(
                "Return read-only session status: configured --repo and --db, package/schema "
                "versions, and indexed entity/relation counts."
            ),
            input_schema=_input_schema({}, []),
            handler=_tool_status,
        ),
        ToolDescriptor(
            name="rsm_search_symbols",
            description=(
                "Search indexed entities by lexical query using the bundled BM25 index. Read-only."
            ),
            input_schema=_input_schema(
                {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "entity_kinds": {"type": "array", "items": {"type": "string"}},
                    "path_roles": {"type": "array", "items": {"type": "string"}},
                    "include_relations": {"type": "boolean"},
                },
                ["query"],
            ),
            handler=_tool_search_symbols,
        ),
        ToolDescriptor(
            name="rsm_explain_entity",
            description=(
                "Resolve one entity with structural context, semantic components, and "
                "citations. Read-only."
            ),
            input_schema=_input_schema(
                {
                    "entity_id": {"type": "string"},
                    "include_incoming_relations": {"type": "boolean"},
                    "include_outgoing_relations": {"type": "boolean"},
                    "include_components": {"type": "boolean"},
                    "include_claims": {"type": "boolean"},
                },
                ["entity_id"],
            ),
            handler=_tool_explain_entity,
        ),
        ToolDescriptor(
            name="rsm_build_context_pack",
            description=(
                "Build a deterministic, source-cited, budget-bounded context pack for a task. "
                "Returns a compact summary by default; opt in to full output with "
                "include_rendered, include_payload, or include_ranking_breakdowns. Read-only."
            ),
            input_schema=_input_schema(
                {
                    "task": {"type": "string"},
                    "budget_chars": {"type": "integer", "minimum": 1},
                    "format": {"type": "string", "enum": ["markdown", "yaml"]},
                    "profile": {"type": "string"},
                    "explain_ranking": {"type": "boolean"},
                    "include_semantic_components": {"type": "boolean"},
                    "include_rendered": {"type": "boolean"},
                    "include_payload": {"type": "boolean"},
                    "include_ranking_breakdowns": {"type": "boolean"},
                    "max_entities": {"type": "integer", "minimum": 0},
                    "max_relations": {"type": "integer", "minimum": 0},
                    "max_citations": {"type": "integer", "minimum": 0},
                },
                ["task"],
            ),
            handler=_tool_build_context_pack,
        ),
        ToolDescriptor(
            name="rsm_query_graph",
            description=(
                "Bounded traversal of the structural relation graph from seed entity IDs. "
                "Read-only."
            ),
            input_schema=_input_schema(
                {
                    "entity_ids": {"type": "array", "items": {"type": "string"}},
                    "relation_kinds": {"type": "array", "items": {"type": "string"}},
                    "direction": {
                        "type": "string",
                        "enum": ["outgoing", "incoming", "both"],
                    },
                    "max_hops": {"type": "integer", "minimum": 1},
                    "limit": {"type": "integer", "minimum": 1},
                },
                ["entity_ids"],
            ),
            handler=_tool_query_graph,
        ),
        ToolDescriptor(
            name="rsm_validate_patch_context",
            description=(
                "Check whether a candidate patch's touched paths and referenced entities are "
                "covered by the local index. Read-only."
            ),
            input_schema=_input_schema(
                {
                    "task": {"type": "string"},
                    "changed_paths": {"type": "array", "items": {"type": "string"}},
                    "referenced_entity_ids": {"type": "array", "items": {"type": "string"}},
                    "budget_chars": {"type": "integer", "minimum": 1},
                },
                ["task", "changed_paths"],
            ),
            handler=_tool_validate_patch_context,
        ),
        ToolDescriptor(
            name="rsm_get_git_summary",
            description="Return minimal local Git repository summary for a bounded path.",
            input_schema=_input_schema(
                {"path": {"type": "string"}},
                [],
            ),
            handler=_tool_get_git_summary,
        ),
    ]
    registry = {descriptor.name: descriptor for descriptor in descriptors}
    # Defensive assertion: registry surface must match the phase 1 contract.
    if tuple(registry.keys()) != PHASE1_TOOL_NAMES:
        raise RuntimeError(
            "MCP tool registry order does not match PHASE1_TOOL_NAMES; "
            "this is an internal invariant violation."
        )
    return registry


def invoke_tool(name: str, arguments: Mapping[str, Any], session: SessionConfig) -> dict[str, Any]:
    """Dispatch a tool call by name with already-validated session config.

    Raises :class:`ToolInvocationError` for unknown tool names or invalid args.
    Other exceptions bubble up and are surfaced as MCP tool errors by the
    transport layer in :mod:`repo_semantic_memory.mcp.server`.
    """

    registry = build_tool_registry()
    descriptor = registry.get(name)
    if descriptor is None:
        raise ToolInvocationError(f"unknown tool: {name}")
    return descriptor.handler(arguments, session)
