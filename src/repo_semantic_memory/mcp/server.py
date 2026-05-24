"""Minimal stdio JSON-RPC server for the read-only RSM MCP surface.

This module is the only place that touches stdio I/O for the MCP runtime.
Business logic lives in the existing pure handlers and the thin wrappers in
:mod:`repo_semantic_memory.mcp.runtime`.

Transport model:
- newline-delimited JSON-RPC 2.0 messages on stdin/stdout, following the MCP
  stdio transport shape.
- one process per agent/client session, launched and stopped by the MCP client.
- no HTTP, no daemon, no background task framework.

This is a phase 1 prototype: it is a minimal local stdio MCP-compatible
JSON-RPC server and has not yet been validated against external MCP clients.
This implementation does not
depend on the official ``mcp`` Python SDK because RSM has a
zero-runtime-dependency policy and the phase 1 surface is a small, auditable
subset of the MCP protocol. See ``docs/usage/mcp.md`` for the dependency
rationale and the documented untested scope.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any

from repo_semantic_memory.mcp.runtime import (
    PHASE1_TOOL_NAMES,
    SessionConfig,
    ToolInvocationError,
    build_tool_registry,
    invoke_tool,
    validate_session,
)
from repo_semantic_memory.mcp.session import ResultStore
from repo_semantic_memory.version import get_version_info

# Protocol version negotiated during ``initialize``. ``2024-11-05`` is the
# widely-supported MCP stdio protocol version at the time of writing.
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "repo-semantic-memory"

# JSON-RPC standard error codes used by this implementation.
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


def _write_message(stream: IO[str], payload: Mapping[str, Any]) -> None:
    stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
    stream.flush()


def _error(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": err}


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _initialize_result() -> dict[str, Any]:
    info = get_version_info()
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": SERVER_NAME,
            "version": info.package_version,
        },
        "instructions": (
            "Read-only local RSM tools. The configured --repo and --db are fixed for "
            "this session. Call rsm_status to inspect them."
        ),
    }


def _tools_list_result() -> dict[str, Any]:
    registry = build_tool_registry()
    tools = [
        {
            "name": descriptor.name,
            "description": descriptor.description,
            "inputSchema": descriptor.input_schema,
        }
        for descriptor in registry.values()
    ]
    return {"tools": tools}


def _tool_call_result(
    name: str,
    arguments: Mapping[str, Any],
    session: SessionConfig,
    result_store: ResultStore,
) -> dict[str, Any]:
    payload = invoke_tool(name, arguments, session, result_store=result_store)
    text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _tool_error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _dispatch(
    message: Mapping[str, Any],
    session: SessionConfig,
    result_store: ResultStore,
) -> dict[str, Any] | None:
    """Dispatch a single JSON-RPC message and return an outbound payload.

    Returns ``None`` for notifications (no response). Returns a JSON-RPC error
    or result envelope for requests.
    """

    if message.get("jsonrpc") != "2.0":
        # Per JSON-RPC 2.0, missing the version field is a malformed request.
        return _error(message.get("id"), _INVALID_REQUEST, "missing jsonrpc=2.0 envelope")

    method = message.get("method")
    if not isinstance(method, str):
        return _error(message.get("id"), _INVALID_REQUEST, "missing 'method' field")

    is_notification = "id" not in message
    request_id = message.get("id")
    params_raw = message.get("params", {})
    params: Mapping[str, Any] = params_raw if isinstance(params_raw, Mapping) else {}

    if method == "initialize":
        return _result(request_id, _initialize_result())
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return _result(request_id, {})
    if method == "shutdown":
        return _result(request_id, None)
    if method == "tools/list":
        return _result(request_id, _tools_list_result())
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _error(request_id, _INVALID_PARAMS, "tools/call requires 'name'")
        arguments_raw = params.get("arguments", {})
        if not isinstance(arguments_raw, Mapping):
            return _error(request_id, _INVALID_PARAMS, "tools/call 'arguments' must be an object")
        if name not in PHASE1_TOOL_NAMES:
            return _result(request_id, _tool_error_result(f"unknown tool: {name}"))
        try:
            return _result(
                request_id, _tool_call_result(name, arguments_raw, session, result_store)
            )
        except ToolInvocationError as exc:
            return _result(request_id, _tool_error_result(str(exc)))
        except (ValueError, FileNotFoundError) as exc:
            # Handler-level validation/path errors surface as tool errors so the
            # client can recover; protocol-level errors are reserved for malformed
            # MCP messages.
            return _result(request_id, _tool_error_result(f"{type(exc).__name__}: {exc}"))

    if is_notification:
        # Unknown notifications are silently ignored per JSON-RPC 2.0.
        return None
    return _error(request_id, _METHOD_NOT_FOUND, f"method not found: {method}")


def serve_stdio(
    session: SessionConfig,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> int:
    """Serve MCP stdio for ``session`` until EOF on stdin.

    ``stdin``/``stdout`` are injected for tests; in production they default to
    ``sys.stdin``/``sys.stdout``.
    """

    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout

    # One ResultStore per MCP session. The store lives only for this
    # ``serve_stdio`` call and is discarded with the process when the client
    # closes stdin. No disk state.
    result_store = ResultStore()

    for raw_line in in_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _write_message(
                out_stream,
                _error(None, _PARSE_ERROR, f"invalid JSON: {exc.msg}"),
            )
            continue
        if not isinstance(message, Mapping):
            _write_message(
                out_stream,
                _error(None, _INVALID_REQUEST, "request must be a JSON object"),
            )
            continue
        try:
            response = _dispatch(message, session, result_store)
        except Exception as exc:  # noqa: BLE001 - top-level safety net
            _write_message(
                out_stream,
                _error(message.get("id"), _INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"),
            )
            continue
        if response is not None:
            _write_message(out_stream, response)
    return 0


def run_serve(repo: str, db: str | None) -> int:
    """CLI entry point for ``rsm mcp serve``.

    Validates the repo/db pair and starts the stdio loop. Returns a non-zero
    exit code with a clean stderr message for invalid configuration.

    When ``db`` is ``None``, the RSM Index Store registry is consulted for a
    registered index for the given ``repo``.  If no entry is found the command
    exits with code 2 and a clear ``error:`` line on stderr.
    """
    resolved_db = db
    db_from_registry = False
    if resolved_db is None:
        from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

        registry = IndexRegistry(resolve_store_home())
        looked_up = registry.lookup(Path(repo).expanduser())
        if looked_up is None:
            repo_display = repo
            repo_path = Path(repo).expanduser()
            if repo_path.exists():
                repo_display = str(repo_path.resolve())
            print(
                f"error: no index registered for repo {repo_display}\n"
                f"Register it first: rsm store register {repo_display} --index\n"
                f"Or provide an explicit --db path.",
                file=sys.stderr,
            )
            return 2
        resolved_db = str(looked_up)
        db_from_registry = True

    try:
        session = validate_session(repo, resolved_db, require_db_inside_repo=not db_from_registry)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return serve_stdio(session)
