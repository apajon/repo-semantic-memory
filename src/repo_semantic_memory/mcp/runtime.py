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
from repo_semantic_memory.mcp.session import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    STREAM_NAMES,
    ResultStore,
    slice_page,
)
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
    "rsm_get_context_page",
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
    """Static description of an exposed MCP tool.

    Tool handlers receive the parsed arguments, the session configuration, and
    a per-session :class:`ResultStore`. Handlers that do not use the store
    simply ignore the third argument.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any], SessionConfig, ResultStore], dict[str, Any]]


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


def _tool_status(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    """Lightweight local status wrapper using repo/db/index metadata."""

    del args, store  # status takes no inputs and does not use the result store
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
    sqlite_store = SQLiteStore(session.db_path)
    try:
        sqlite_store.initialize()
        metadata = sqlite_store.get_metadata()
        entity_count = len(sqlite_store.list_entities())
        relation_count = len(sqlite_store.list_relations())
    finally:
        sqlite_store.close()
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


def _tool_search_symbols(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    del store
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


def _tool_explain_entity(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    del store
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


def _tool_build_context_pack(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
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
    payload = _serialize_response(response)
    _register_pack_result_set(payload, store)
    return payload


def _register_pack_result_set(payload: dict[str, Any], store: ResultStore) -> None:
    """Register the compact pack streams with the session-local result store.

    The store keeps already-computed slices so a follow-up
    ``rsm_get_context_page`` call never recomputes the context pack. The
    JSON payload is extended with an opaque ``result_set_id`` and per-stream
    ``counts`` so agents can drive paging.
    """

    files = payload.get("selected_files") or []
    entities = payload.get("selected_entities") or []
    relations = payload.get("selected_relations") or []
    citations = payload.get("citations") or []
    ranking_breakdowns: list[Any] = []
    payload_section = payload.get("payload")
    if isinstance(payload_section, Mapping):
        raw_breakdowns = payload_section.get("ranking_breakdowns")
        if isinstance(raw_breakdowns, list):
            ranking_breakdowns = list(raw_breakdowns)

    streams = {
        "files": _short_id_stream("f", _file_entries(files)),
        "entities": _short_id_stream("e", entities),
        "relations": _short_id_stream("r", relations),
        "citations": _short_id_stream("c", citations),
        "ranking_breakdowns": _short_id_stream("b", ranking_breakdowns),
    }
    result_set = store.put(streams)
    payload["result_set_id"] = result_set.result_set_id
    payload["counts"] = dict(result_set.counts)


def _file_entries(files: Any) -> list[dict[str, Any]]:
    """Normalize ``selected_files`` (paths) into stream entries."""

    out: list[dict[str, Any]] = []
    if isinstance(files, (list, tuple)):
        for path in files:
            if isinstance(path, str):
                out.append({"path": path})
    return out


def _short_id_stream(prefix: str, items: Any) -> list[dict[str, Any]]:
    """Attach short stable per-result-set IDs (``e1``, ``r2``, …) to entries."""

    out: list[dict[str, Any]] = []
    if not isinstance(items, (list, tuple)):
        return out
    for index, item in enumerate(items, start=1):
        if isinstance(item, Mapping):
            entry = dict(item)
        else:
            entry = {"value": item}
        entry["id"] = f"{prefix}{index}"
        out.append(entry)
    return out


def _tool_get_context_page(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    """Page over an already-stored result set without recomputing.

    Unknown or expired ``result_set_id`` is a recoverable tool-level outcome:
    the response carries a ``result_set_unknown`` entry in ``uncertainties``
    rather than raising a JSON-RPC protocol error. Malformed arguments
    (missing/invalid types or out-of-range page bounds) remain normal
    tool-call errors via :class:`ToolInvocationError`.
    """

    del session  # paging never touches the index or filesystem
    result_set_id = _require_str(args, "result_set_id")
    stream = _require_str(args, "stream")
    if stream not in STREAM_NAMES:
        raise ToolInvocationError(f"argument 'stream' must be one of {list(STREAM_NAMES)}")
    offset = _optional_int(args, "offset", 0)
    if offset < 0:
        raise ToolInvocationError("argument 'offset' must be >= 0")
    limit = _optional_int(args, "limit", DEFAULT_PAGE_LIMIT)
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise ToolInvocationError(f"argument 'limit' must be between 1 and {MAX_PAGE_LIMIT}")

    result_set = store.get(result_set_id)
    if result_set is None:
        return {
            "result_set_id": result_set_id,
            "stream": stream,
            "offset": offset,
            "limit": limit,
            "items": [],
            "total": 0,
            "next_offset": None,
            "uncertainties": [
                {
                    "code": "result_set_unknown",
                    "message": (
                        f"result_set_id {result_set_id!r} is unknown or has expired in "
                        "this MCP session; call rsm_build_context_pack again to mint a "
                        "fresh result set."
                    ),
                    "recoverable": True,
                    "subject_id": result_set_id,
                }
            ],
        }

    items, total, next_offset = slice_page(result_set, stream=stream, offset=offset, limit=limit)
    return {
        "result_set_id": result_set.result_set_id,
        "stream": stream,
        "offset": offset,
        "limit": limit,
        "items": [dict(item) for item in items],
        "total": total,
        "next_offset": next_offset,
        "uncertainties": [],
    }


def _tool_query_graph(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    del store
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


def _tool_validate_patch_context(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    del store
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


def _tool_get_git_summary(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    del store
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
            name="rsm_get_context_page",
            description=(
                "Page over a previously-built context pack stored in this MCP session by "
                "result_set_id, without recomputing the pack. Returns a deterministic "
                "slice of the requested stream (files, entities, relations, citations, or "
                "ranking_breakdowns) with short stable per-entry IDs. Unknown or expired "
                "result_set_id surfaces as a recoverable 'result_set_unknown' uncertainty "
                "in the response. Read-only."
            ),
            input_schema=_input_schema(
                {
                    "result_set_id": {"type": "string"},
                    "stream": {
                        "type": "string",
                        "enum": list(STREAM_NAMES),
                    },
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_PAGE_LIMIT,
                    },
                },
                ["result_set_id", "stream"],
            ),
            handler=_tool_get_context_page,
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


def invoke_tool(
    name: str,
    arguments: Mapping[str, Any],
    session: SessionConfig,
    *,
    result_store: ResultStore | None = None,
) -> dict[str, Any]:
    """Dispatch a tool call by name with already-validated session config.

    Raises :class:`ToolInvocationError` for unknown tool names or invalid args.
    Other exceptions bubble up and are surfaced as MCP tool errors by the
    transport layer in :mod:`repo_semantic_memory.mcp.server`.

    ``result_store`` is the per-MCP-session in-memory store used by the
    progressive context retrieval model. A fresh, isolated store is created
    when one is not provided so that one-off ``invoke_tool`` calls (e.g. in
    unit tests) remain valid; callers that want paging across calls must
    reuse the same :class:`ResultStore`.
    """

    store = result_store if result_store is not None else ResultStore()
    registry = build_tool_registry()
    descriptor = registry.get(name)
    if descriptor is None:
        raise ToolInvocationError(f"unknown tool: {name}")
    return descriptor.handler(arguments, session, store)
