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
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal

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
    "rsm_prepare_context",
    "rsm_search",
)

# Store-mode-only tool names exposed exclusively in ``--store`` sessions.
STORE_ONLY_TOOL_NAMES: tuple[str, ...] = (
    "rsm_list_indexes",
    "rsm_select_index",
    "rsm_current_index",
)

# All tool names available in ``--store`` mode: store tools first, then repo tools.
STORE_TOOL_NAMES: tuple[str, ...] = STORE_ONLY_TOOL_NAMES + PHASE1_TOOL_NAMES

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
class ActiveIndex:
    """The currently selected index in a store-mode MCP session.

    Holds the resolved, validated state for the active repository.  Frozen so
    that the object returned by :func:`rsm_current_index` can be compared by
    value without copies.
    """

    repo_id: str
    """Stable 16-hex-char ID derived from the resolved repo root path."""

    name: str
    """Human-readable name: the final path component of ``repo_root``."""

    repo_root: Path
    """Resolved absolute path to the repository root."""

    db_path: Path
    """Resolved absolute path to the SQLite index database."""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict with string path values."""
        return {
            "repo_id": self.repo_id,
            "name": self.name,
            "repo_root": self.repo_root.as_posix(),
            "db_path": self.db_path.as_posix(),
        }


@dataclass
class StoreSessionState:
    """Mutable per-session state for ``--store`` mode.

    One instance lives for the lifetime of a single ``serve_stdio`` call.
    ``active_index`` starts as ``None`` and is updated by ``rsm_select_index``.
    No disk writes; no persistence across MCP restarts.
    """

    store_home: Path
    active_index: ActiveIndex | None = field(default=None)


@dataclass(frozen=True)
class SessionConfig:
    """Validated repo/db configuration for one MCP server session."""

    repo_root: Path
    db_path: Path
    index_mode: Literal["explicit_db", "store"] = "explicit_db"


@dataclass(frozen=True)
class ToolDescriptor:
    """Static description of an exposed MCP tool.

    Tool handlers receive the parsed arguments, the session configuration, and
    a per-session :class:`ResultStore`. Handlers that do not use the store
    simply ignore the third argument.

    Repo-tool handlers always receive a :class:`SessionConfig`.
    Store-only tool handlers always receive a :class:`StoreSessionState`.
    The union type annotation reflects that both appear in the combined registry.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any], Any, ResultStore], dict[str, Any]]


class ToolInvocationError(ValueError):
    """Raised when a tool invocation fails for a known, user-facing reason."""


def validate_session(
    repo: str | Path,
    db: str | Path,
    *,
    require_db_inside_repo: bool = True,
    index_mode: Literal["explicit_db", "store"] = "explicit_db",
) -> SessionConfig:
    """Validate ``--repo`` and ``--db`` paths and return a session config.

    Phase 1 rules:
    - ``repo`` must exist and be a directory.
    - ``db`` must exist and be a regular file (no auto-creation).
    - When ``require_db_inside_repo=True`` (the default), ``db`` must live
      inside ``repo`` after resolving symlinks.  Pass ``False`` when the DB
      lives in the central RSM Index Store rather than inside the repository.
    - ``index_mode`` is recorded in the returned :class:`SessionConfig` so
      tools like ``rsm_status`` can emit mode-aware suggested actions.
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
    if require_db_inside_repo:
        try:
            resolved_db.relative_to(resolved_repo)
        except ValueError as exc:
            raise ValueError(
                f"--db path must be inside --repo (got db={resolved_db}, repo={resolved_repo})"
            ) from exc
    return SessionConfig(repo_root=resolved_repo, db_path=resolved_db, index_mode=index_mode)


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

    # Extend with staleness detection fields.
    try:
        from repo_semantic_memory.index_status import detect_stale_from_metadata  # noqa: PLC0415

        report = detect_stale_from_metadata(
            repo_root=session.repo_root,
            db_path=session.db_path,
            index_mode=session.index_mode,
            metadata=metadata,
        )
        payload["index_status"] = report.index_status.value
        payload["index_status_reason"] = report.index_status_reason
        payload["indexed_at"] = report.indexed_at
        payload["indexed_git_head"] = report.indexed_git_head
        payload["current_git_head"] = report.current_git_head
        payload["working_tree_dirty"] = report.working_tree_dirty
        payload["index_mode"] = report.index_mode
        payload["suggested_action"] = report.suggested_action
        payload["index_scope"] = report.index_scope
        payload["include_patterns"] = list(report.include_patterns)
        payload["exclude_patterns"] = list(report.exclude_patterns)
    except Exception:  # noqa: BLE001 — staleness errors must not break status
        payload["index_status"] = "unknown"
        payload["index_status_reason"] = "detection_error"
        payload["index_mode"] = session.index_mode
        payload["suggested_action"] = None
        payload["index_scope"] = None
        payload["include_patterns"] = []
        payload["exclude_patterns"] = []

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
    response = _handlers.handle_search_symbols(
        request,
        repo_root=session.repo_root,
        require_db_inside_repo=(session.index_mode != "store"),
    )
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
    response = _handlers.handle_explain_entity(
        request,
        repo_root=session.repo_root,
        require_db_inside_repo=(session.index_mode != "store"),
    )
    return _serialize_response(response)


# Internal store cap used when collecting pack streams to make available via
# ``rsm_get_context_page``. The handler will not slice beyond this, so the
# session-local result store sees the full pack output (subject to the pack's
# own ranking/selection budget) while the response shows a smaller preview.
_PACK_STORE_CAP = 1000

# Hard safety cap for user-supplied per-stream preview values. Mirrors the
# handler's own non-negative check while preventing accidental enormous
# previews from MCP callers.
_PACK_PREVIEW_SAFETY_CAP = 200

# Per-``detail_level`` brief/compact preview defaults.
_DETAIL_LEVEL_DEFAULTS: dict[str, dict[str, int]] = {
    "brief": {
        "max_files": 5,
        "max_entities": 5,
        "max_relations": 3,
        "max_citations": 0,
    },
    "compact": {
        # ``compact`` preserves the post-46.1/46.3 one-shot preview shape so
        # agents that want a larger first response keep their behavior. Files
        # are intentionally not capped in compact mode.
        "max_files": _PACK_STORE_CAP,
        "max_entities": 15,
        "max_relations": 10,
        "max_citations": 12,
    },
}


def _bounded_preview_int(args: Mapping[str, Any], key: str, default: int) -> int:
    """Parse an optional preview cap; reject negatives, clamp to safety cap."""

    value = _optional_int(args, key, default)
    if value < 0:
        raise ToolInvocationError(f"argument {key!r} must be >= 0")
    return min(value, _PACK_PREVIEW_SAFETY_CAP)


def _tool_build_context_pack(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    fmt = args.get("format", "markdown")
    if fmt not in ("markdown", "yaml"):
        raise ToolInvocationError("argument 'format' must be 'markdown' or 'yaml'")
    detail_level = args.get("detail_level", "brief")
    if detail_level not in _DETAIL_LEVEL_DEFAULTS:
        raise ToolInvocationError(
            f"argument 'detail_level' must be one of {sorted(_DETAIL_LEVEL_DEFAULTS)}"
        )
    defaults = _DETAIL_LEVEL_DEFAULTS[detail_level]
    preview_caps = {
        "files": _bounded_preview_int(args, "max_files", defaults["max_files"]),
        "entities": _bounded_preview_int(args, "max_entities", defaults["max_entities"]),
        "relations": _bounded_preview_int(args, "max_relations", defaults["max_relations"]),
        "citations": _bounded_preview_int(args, "max_citations", defaults["max_citations"]),
    }

    # Always ask the handler for the full pack streams so ``rsm_get_context_page``
    # can later page over items that the preview omitted (e.g. citations under
    # the brief default). Preview-side caps are applied in this runtime layer.
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
        max_entities=_PACK_STORE_CAP,
        max_relations=_PACK_STORE_CAP,
        max_citations=_PACK_STORE_CAP,
    )
    response = _handlers.handle_build_context_pack(
        request,
        repo_root=session.repo_root,
        require_db_inside_repo=(session.index_mode != "store"),
    )
    payload = _serialize_response(response)

    # Snapshot the full streams (as returned by the handler) before applying
    # the per-stream preview caps so the result store can serve subsequent
    # ``rsm_get_context_page`` calls without recomputing the pack.
    full_files = list(payload.get("selected_files") or [])
    full_entities = list(payload.get("selected_entities") or [])
    full_relations = list(payload.get("selected_relations") or [])
    full_citations = list(payload.get("citations") or [])

    # Apply preview caps to the user-facing response. Underlying streams
    # remain in the result store (see ``_register_pack_result_set``).
    payload["selected_files"] = full_files[: preview_caps["files"]]
    payload["selected_entities"] = full_entities[: preview_caps["entities"]]
    payload["selected_relations"] = full_relations[: preview_caps["relations"]]
    payload["citations"] = full_citations[: preview_caps["citations"]]

    # In brief mode, intentionally empty the verbose full-list compatibility
    # fields. The full data remains accessible via ``result_set_id`` +
    # ``rsm_get_context_page``; ``counts`` still reports full totals. Compact
    # mode keeps the previous post-46.1/46.3 populated shape.
    if detail_level == "brief":
        payload["selected_entity_ids"] = []
        payload["selected_relation_keys"] = []

    _register_pack_result_set(
        payload,
        store,
        full_files=full_files,
        full_entities=full_entities,
        full_relations=full_relations,
        full_citations=full_citations,
        preview_caps=preview_caps,
    )
    payload["detail_level"] = detail_level

    # Append scope warning when the index was built with include/exclude filters.
    # Errors here must never break context-pack delivery.
    try:
        from repo_semantic_memory.index_status import detect_stale_from_metadata  # noqa: PLC0415

        _cp_store = SQLiteStore(session.db_path)
        try:
            _cp_store.initialize()
            _meta = _cp_store.get_metadata()
        finally:
            _cp_store.close()
        _cp_report = detect_stale_from_metadata(
            repo_root=session.repo_root,
            db_path=session.db_path,
            index_mode=session.index_mode,
            metadata=_meta,
        )
        if _cp_report.index_scope == "scoped":
            payload["index_scope"] = "scoped"
            payload["include_patterns"] = list(_cp_report.include_patterns)
            payload["exclude_patterns"] = list(_cp_report.exclude_patterns)
            payload["scope_warning"] = (
                "This index is scoped and may not cover the full repository. "
                "Results are limited to the indexed paths."
            )
        else:
            payload["index_scope"] = _cp_report.index_scope
            payload["include_patterns"] = []
            payload["exclude_patterns"] = []
    except Exception:  # noqa: BLE001 — scope warnings must never break context packs
        pass

    return payload


def _register_pack_result_set(
    payload: dict[str, Any],
    store: ResultStore,
    *,
    full_files: list[Any],
    full_entities: list[Any],
    full_relations: list[Any],
    full_citations: list[Any],
    preview_caps: Mapping[str, int],
) -> None:
    """Register full pack streams and inject result_set_id/counts/next hints.

    The store keeps the full streams (not just the preview slice) so a
    follow-up ``rsm_get_context_page`` call never recomputes the context
    pack and can return items beyond the preview cap (for example, the
    citations omitted from the brief default).
    """

    ranking_breakdowns: list[Any] = []
    payload_section = payload.get("payload")
    if isinstance(payload_section, Mapping):
        raw_breakdowns = payload_section.get("ranking_breakdowns")
        if isinstance(raw_breakdowns, list):
            ranking_breakdowns = list(raw_breakdowns)

    streams = {
        "files": _short_id_stream("f", _file_entries(full_files)),
        "entities": _short_id_stream("e", full_entities),
        "relations": _short_id_stream("r", full_relations),
        "citations": _short_id_stream("c", full_citations),
        "ranking_breakdowns": _short_id_stream("b", ranking_breakdowns),
    }
    result_set = store.put(streams)
    counts: dict[str, int] = dict(result_set.counts)
    payload["result_set_id"] = result_set.result_set_id
    payload["counts"] = counts

    # ``next`` advertises per-stream availability beyond what the preview
    # shows so agents know which streams they can page with
    # ``rsm_get_context_page``. ``ranking_breakdowns`` is included whenever
    # any are stored (the preview never embeds them).
    shown_counts: dict[str, int] = {
        "files": min(len(full_files), preview_caps["files"]),
        "entities": min(len(full_entities), preview_caps["entities"]),
        "relations": min(len(full_relations), preview_caps["relations"]),
        "citations": min(len(full_citations), preview_caps["citations"]),
        "ranking_breakdowns": 0,
    }
    next_hints: dict[str, dict[str, Any]] = {}
    for stream_name in ("files", "entities", "relations", "citations", "ranking_breakdowns"):
        available = counts.get(stream_name, 0)
        shown = shown_counts[stream_name]
        if available > shown:
            next_hints[stream_name] = {
                "stream": stream_name,
                "available": available,
                "shown": shown,
                "tool": "rsm_get_context_page",
            }
    payload["next"] = next_hints


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


def _tool_prepare_context(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    """Preferred wrapper for building a task-centered ContextPack.

    Delegates to :func:`_tool_build_context_pack` so the output is identical.
    Adds ``active_repo`` metadata to every response.
    """

    result = _tool_build_context_pack(args, session, store)
    result["active_repo"] = {
        "repo_root": session.repo_root.as_posix(),
        "db_path": session.db_path.as_posix(),
        "index_mode": session.index_mode,
    }
    return result


def _tool_search(
    args: Mapping[str, Any], session: SessionConfig, store: ResultStore
) -> dict[str, Any]:
    """Broad discovery across indexed files, symbols, docs and tests.

    Wraps :func:`_tool_search_symbols` with a cleaned output shape,
    deterministic per-result IDs, and ``active_repo`` metadata.
    """

    # Translate cleaned input names to the internal SearchSymbolsRequest shape.
    # kind -> entity_kinds, path_role -> path_roles.
    mapped_args = dict(args)
    if "kind" in mapped_args and "entity_kinds" not in mapped_args:
        mapped_args["entity_kinds"] = mapped_args.pop("kind")
    else:
        mapped_args.pop("kind", None)
    if "path_role" in mapped_args and "path_roles" not in mapped_args:
        mapped_args["path_roles"] = mapped_args.pop("path_role")
    else:
        mapped_args.pop("path_role", None)
    # Remove any keys not handled by the internal handler.
    for key in list(mapped_args.keys()):
        if key not in ("query", "limit", "entity_kinds", "path_roles", "include_relations"):
            mapped_args.pop(key, None)

    raw = _tool_search_symbols(mapped_args, session, store)

    # Build the cleaned output shape.
    raw_results: list[dict[str, Any]] = (
        raw.get("results")  # type: ignore[assignment]
        if isinstance(raw.get("results"), list)
        else []
    )
    results: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_results, start=1):
        source_range = (
            item.get("source_range") if isinstance(item.get("source_range"), dict) else {}
        )
        results.append(
            {
                "result_id": f"search_{idx:04d}",
                "entity_id": item.get("entity_id"),
                "path": item.get("path"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "qualified_name": item.get("qualified_name"),
                "source_range": {
                    "start_line": source_range.get("start_line"),
                    "end_line": source_range.get("end_line"),
                }
                if source_range
                else None,
                "path_role": item.get("path_role"),
                "score": item.get("score"),
                "reasons": item.get("ranking_reasons"),
            }
        )

    return {
        "active_repo": {
            "repo_root": session.repo_root.as_posix(),
            "db_path": session.db_path.as_posix(),
            "index_mode": session.index_mode,
        },
        "query": str(args.get("query", "")),
        "results": results,
        "count": len(results),
        "uncertainties": list(raw.get("uncertainties", ())),
        "warnings": [],
    }


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
                        "this MCP session; call rsm_prepare_context (or rsm_build_context_pack) "
                        "to mint a fresh result set."
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
    response = _handlers.handle_query_graph(
        request,
        repo_root=session.repo_root,
        require_db_inside_repo=(session.index_mode != "store"),
    )
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
    response = _handlers.handle_validate_patch_context(
        request,
        repo_root=session.repo_root,
        require_db_inside_repo=(session.index_mode != "store"),
    )
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
                "Returns a brief first-page preview by default (5 files, 5 entities, 3 relations, "
                "0 citations) plus a session-scoped result_set_id; use rsm_get_context_page to "
                "page over omitted items. Pass detail_level='compact' for the larger one-shot "
                "preview, or opt in to full output with include_rendered, include_payload, or "
                "include_ranking_breakdowns. Read-only."
            ),
            input_schema=_input_schema(
                {
                    "task": {"type": "string"},
                    "budget_chars": {"type": "integer", "minimum": 1},
                    "format": {"type": "string", "enum": ["markdown", "yaml"]},
                    "profile": {"type": "string"},
                    "detail_level": {
                        "type": "string",
                        "enum": sorted(_DETAIL_LEVEL_DEFAULTS),
                    },
                    "explain_ranking": {"type": "boolean"},
                    "include_semantic_components": {"type": "boolean"},
                    "include_rendered": {"type": "boolean"},
                    "include_payload": {"type": "boolean"},
                    "include_ranking_breakdowns": {"type": "boolean"},
                    "max_files": {"type": "integer", "minimum": 0},
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
        ToolDescriptor(
            name="rsm_prepare_context",
            description=(
                "Prepare a task-centered ContextPack for a coding agent. "
                "Preferred high-level replacement for rsm_build_context_pack. "
                "Returns a brief first-page preview by default (5 files, 5 entities, 3 relations, "
                "0 citations) plus a session-scoped result_set_id; use rsm_get_context_page to "
                "page over omitted items. Every response includes active_repo metadata. "
                "Read-only."
            ),
            input_schema=_input_schema(
                {
                    "task": {"type": "string"},
                    "budget_chars": {"type": "integer", "minimum": 1},
                    "format": {"type": "string", "enum": ["markdown", "yaml"]},
                    "profile": {"type": "string"},
                    "detail_level": {
                        "type": "string",
                        "enum": sorted(_DETAIL_LEVEL_DEFAULTS),
                    },
                    "explain_ranking": {"type": "boolean"},
                    "include_semantic_components": {"type": "boolean"},
                    "include_rendered": {"type": "boolean"},
                    "include_payload": {"type": "boolean"},
                    "include_ranking_breakdowns": {"type": "boolean"},
                    "max_files": {"type": "integer", "minimum": 0},
                    "max_entities": {"type": "integer", "minimum": 0},
                    "max_relations": {"type": "integer", "minimum": 0},
                    "max_citations": {"type": "integer", "minimum": 0},
                },
                ["task"],
            ),
            handler=_tool_prepare_context,
        ),
        ToolDescriptor(
            name="rsm_search",
            description=(
                "Broad discovery across indexed files, symbols, docs and tests. "
                "Returns compact, deterministic results with source paths, entity kinds, "
                "and scoring reasons. Preferred high-level replacement for "
                "rsm_search_symbols. Every response includes active_repo metadata. "
                "Read-only."
            ),
            input_schema=_input_schema(
                {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "kind": {"type": "array", "items": {"type": "string"}},
                    "path_role": {"type": "array", "items": {"type": "string"}},
                },
                ["query"],
            ),
            handler=_tool_search,
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


# ---------------------------------------------------------------------------
# Store-mode tools
# ---------------------------------------------------------------------------


def _no_active_index_response() -> dict[str, Any]:
    """Return the standard recoverable no_active_index uncertainty payload."""
    return {
        "active_repo": None,
        "uncertainties": [
            {
                "code": "no_active_index",
                "message": ("Call rsm_list_indexes then rsm_select_index before repository tools."),
                "recoverable": True,
            }
        ],
        "agent_instructions": [
            "Use rsm_list_indexes to see registered repositories.",
            "Call rsm_select_index before repository-specific tools.",
            "Check active_repo in each response before using paths.",
            "Do not assume paths from one repository apply to another.",
        ],
    }


def _tool_list_indexes(
    args: Mapping[str, Any], session: StoreSessionState, store: ResultStore
) -> dict[str, Any]:
    """List all registered indexes from the RSM Index Store."""

    del args, store
    from repo_semantic_memory.store_home import IndexRegistry  # noqa: PLC0415

    registry = IndexRegistry(session.store_home)
    entries = registry.list_entries()

    indexes: list[dict[str, Any]] = []
    for repo_root_str, entry in entries.items():
        repo_root = Path(repo_root_str)
        repo_id_val = IndexRegistry.repo_id(repo_root)
        name = repo_root.name
        db_path = registry._resolve_db(entry.db_relative)

        index_entry: dict[str, Any] = {
            "repo_id": repo_id_val,
            "name": name,
            "repo_root": repo_root_str,
            "db_path": db_path.as_posix(),
            "registered_at": entry.registered_at,
            "last_indexed_at": entry.last_indexed_at,
        }

        # Best-effort status detection: failure for one repo must not abort all.
        try:
            from repo_semantic_memory.index_status import detect_index_status  # noqa: PLC0415

            report = detect_index_status(
                repo_root=repo_root,
                db_path=db_path if db_path.exists() else None,
                index_mode="store",
            )
            index_entry["status"] = report.index_status.value
            index_entry["status_reason"] = report.index_status_reason
            index_entry["indexed_at"] = report.indexed_at
            index_entry["git_head"] = report.indexed_git_head
            index_entry["working_tree_dirty"] = report.working_tree_dirty
        except Exception:  # noqa: BLE001
            index_entry["status"] = "unknown"
            index_entry["status_reason"] = "detection_error"
            index_entry["indexed_at"] = None
            index_entry["git_head"] = None
            index_entry["working_tree_dirty"] = None

        indexes.append(index_entry)

    # Stable ordering: name then repo_root.
    indexes.sort(key=lambda x: (x["name"], x["repo_root"]))

    return {
        "indexes": indexes,
        "count": len(indexes),
        "agent_instructions": [
            "Use rsm_list_indexes to see registered repositories.",
            "Call rsm_select_index before repository-specific tools.",
            "Check active_repo in each response before using paths.",
            "Do not assume paths from one repository apply to another.",
        ],
    }


def _tool_select_index(
    args: Mapping[str, Any], session: StoreSessionState, store: ResultStore
) -> dict[str, Any]:
    """Select the active index for this MCP session by repo_id, repo_root, or name."""

    del store
    from repo_semantic_memory.store_home import IndexRegistry  # noqa: PLC0415

    registry = IndexRegistry(session.store_home)
    entries = registry.list_entries()

    # Build candidate tuples: (repo_root_str, repo_id, db_path, name)
    candidates: list[tuple[str, str, Path, str]] = []
    for repo_root_str, entry in entries.items():
        repo_root = Path(repo_root_str)
        repo_id_val = IndexRegistry.repo_id(repo_root)
        db_path = registry._resolve_db(entry.db_relative)
        name = repo_root.name
        candidates.append((repo_root_str, repo_id_val, db_path, name))

    selector_repo_id = args.get("repo_id")
    selector_repo_root = args.get("repo_root")
    selector_name = args.get("name")

    if not any(
        isinstance(v, str) and v.strip()
        for v in (selector_repo_id, selector_repo_root, selector_name)
    ):
        raise ToolInvocationError("provide at least one of: repo_id, repo_root, or name")

    matched: list[tuple[str, str, Path, str]]

    if isinstance(selector_repo_id, str) and selector_repo_id.strip():
        matched = [c for c in candidates if c[1] == selector_repo_id.strip()]
        if not matched:
            raise ToolInvocationError(f"no registered index with repo_id={selector_repo_id!r}")
    elif isinstance(selector_repo_root, str) and selector_repo_root.strip():
        try:
            selector_path = Path(selector_repo_root).expanduser().resolve()
        except (OSError, ValueError) as exc:
            raise ToolInvocationError(f"invalid repo_root path: {exc}") from exc
        matched = [c for c in candidates if Path(c[0]) == selector_path]
        if not matched:
            raise ToolInvocationError(f"no registered index for repo_root={selector_repo_root!r}")
    else:
        name_val = selector_name.strip() if isinstance(selector_name, str) else ""
        matched = [c for c in candidates if c[3] == name_val]
        if len(matched) > 1:
            roots = [c[0] for c in matched]
            raise ToolInvocationError(
                f"ambiguous name {name_val!r}: matches multiple repos {roots}; "
                f"use repo_id or repo_root to disambiguate"
            )
        if not matched:
            raise ToolInvocationError(f"no registered index with name={name_val!r}")

    repo_root_str, repo_id_val, db_path, name_val = matched[0]

    if not db_path.exists():
        raise ToolInvocationError(
            f"index DB does not exist: {db_path}. "
            f"Rebuild with: rsm index {repo_root_str} --register"
        )

    active = ActiveIndex(
        repo_id=repo_id_val,
        name=name_val,
        repo_root=Path(repo_root_str),
        db_path=db_path,
    )
    session.active_index = active

    return {
        "selected": active.as_dict(),
        "active_repo": active.as_dict(),
    }


def _tool_current_index(
    args: Mapping[str, Any], session: StoreSessionState, store: ResultStore
) -> dict[str, Any]:
    """Return the active index for this MCP session, or a recoverable uncertainty."""

    del args, store

    if session.active_index is None:
        return {
            "active_repo": None,
            "uncertainties": [
                {
                    "code": "no_active_index",
                    "message": (
                        "No active index selected. Call rsm_list_indexes then "
                        "rsm_select_index before repository tools."
                    ),
                    "recoverable": True,
                }
            ],
            "agent_instructions": [
                "Use rsm_list_indexes to see registered repositories.",
                "Call rsm_select_index before repository-specific tools.",
            ],
        }

    return {
        "active_repo": session.active_index.as_dict(),
        "uncertainties": [],
    }


def build_store_tool_registry() -> dict[str, ToolDescriptor]:
    """Return the full tool registry for ``--store`` mode.

    Includes the three store-management tools (``rsm_list_indexes``,
    ``rsm_select_index``, ``rsm_current_index``) followed by all
    :func:`build_tool_registry` phase-1 tools.
    """

    store_descriptors: list[ToolDescriptor] = [
        ToolDescriptor(
            name="rsm_list_indexes",
            description=(
                "List all repositories registered in the RSM Index Store. "
                "Returns repo_id, name, repo_root, db_path, and best-effort status "
                "for each registered index. Use this first to discover available "
                "repositories, then call rsm_select_index to activate one. Read-only."
            ),
            input_schema=_input_schema({}, []),
            handler=_tool_list_indexes,
        ),
        ToolDescriptor(
            name="rsm_select_index",
            description=(
                "Select the active repository index for this MCP session. "
                "Accepts repo_id (preferred), repo_root (absolute path), or name "
                "(basename of repo_root; rejected if ambiguous). Validates that the "
                "selected DB exists. Active selection is session-scoped: it is lost "
                "when the MCP server process restarts. Read-only."
            ),
            input_schema=_input_schema(
                {
                    "repo_id": {"type": "string"},
                    "repo_root": {"type": "string"},
                    "name": {"type": "string"},
                },
                [],
            ),
            handler=_tool_select_index,
        ),
        ToolDescriptor(
            name="rsm_current_index",
            description=(
                "Return the currently active repository index for this MCP session. "
                "If no index has been selected, returns active_repo: null and a "
                "recoverable no_active_index uncertainty. Read-only."
            ),
            input_schema=_input_schema({}, []),
            handler=_tool_current_index,
        ),
    ]

    repo_registry = build_tool_registry()
    combined = {d.name: d for d in store_descriptors}
    combined.update(repo_registry)

    if tuple(combined.keys()) != STORE_TOOL_NAMES:
        raise RuntimeError(
            "Store tool registry order does not match STORE_TOOL_NAMES; "
            "this is an internal invariant violation."
        )
    return combined


def invoke_tool(
    name: str,
    arguments: Mapping[str, Any],
    session: SessionConfig | StoreSessionState,
    *,
    result_store: ResultStore | None = None,
) -> dict[str, Any]:
    """Dispatch a tool call by name with already-validated session config.

    In ``--repo`` mode (``session`` is :class:`SessionConfig`): routes directly
    to the phase-1 tool registry.  Only ``PHASE1_TOOL_NAMES`` are valid.

    In ``--store`` mode (``session`` is :class:`StoreSessionState`): routes
    store-management tools (``STORE_ONLY_TOOL_NAMES``) directly to their
    handlers.  Repository-specific tools (``PHASE1_TOOL_NAMES``) require an
    active index; if none is selected the response contains a recoverable
    ``no_active_index`` uncertainty instead of raising an error.  Every
    repository-specific response in store mode includes an ``active_repo`` field
    so agents can confirm which repository was queried.

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

    if isinstance(session, StoreSessionState):
        # --store mode: store-only tools go directly to their handlers.
        if name in STORE_ONLY_TOOL_NAMES:
            registry = build_store_tool_registry()
            descriptor = registry.get(name)
            if descriptor is None:
                raise ToolInvocationError(f"unknown tool: {name}")
            return descriptor.handler(arguments, session, store)

        # Repository tools: require an active index.
        if name not in PHASE1_TOOL_NAMES:
            raise ToolInvocationError(f"unknown tool: {name}")
        if session.active_index is None:
            return _no_active_index_response()

        # Build a temporary SessionConfig from the active index and dispatch.
        repo_session = SessionConfig(
            repo_root=session.active_index.repo_root,
            db_path=session.active_index.db_path,
            index_mode="store",
        )
        repo_registry = build_tool_registry()
        descriptor = repo_registry.get(name)
        if descriptor is None:
            raise ToolInvocationError(f"unknown tool: {name}")
        result = descriptor.handler(arguments, repo_session, store)
        result["active_repo"] = session.active_index.as_dict()
        return result

    # --repo mode: route directly to the phase-1 registry.
    registry = build_tool_registry()
    descriptor = registry.get(name)
    if descriptor is None:
        raise ToolInvocationError(f"unknown tool: {name}")
    return descriptor.handler(arguments, session, store)
