"""Tests for the store-scoped MCP server mode (Prompt 59)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from repo_semantic_memory.cli import build_parser
from repo_semantic_memory.cli import main as cli_main
from repo_semantic_memory.mcp import (
    PHASE1_TOOL_NAMES,
    STORE_ONLY_TOOL_NAMES,
    STORE_TOOL_NAMES,
    StoreSessionState,
    build_store_tool_registry,
    invoke_tool,
)
from repo_semantic_memory.mcp.server import serve_stdio
from repo_semantic_memory.model import Entity, Evidence, Relation, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata
from repo_semantic_memory.store_home import IndexRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_indexed_repo(
    root: Path,
    name: str,
    store_home: Path,
) -> tuple[Path, Path]:
    """Create a minimal indexed repo and register it in the store."""
    repo_root = root / name
    src = repo_root / "src"
    src.mkdir(parents=True)
    (src / "main.py").write_text(f"def run_{name}(): return 1\n", encoding="utf-8")

    registry = IndexRegistry(store_home)
    db_path = registry.default_db_path(repo_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    entities = [
        Entity(
            id=StableId(f"python:module:src.main_{name}"),
            kind="module",
            name=f"main_{name}",
            qualified_name=f"src.main_{name}",
            source_range=SourceRange(path="src/main.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId(f"python:function:src.main_{name}.run_{name}"),
            kind="function",
            name=f"run_{name}",
            qualified_name=f"src.main_{name}.run_{name}",
            source_range=SourceRange(path="src/main.py", start_line=1, end_line=1),
        ),
    ]
    relations = [
        Relation(
            source_entity_id=StableId(f"python:module:src.main_{name}"),
            target_entity_id=StableId(f"python:function:src.main_{name}.run_{name}"),
            kind="contains",
            evidence=Evidence(
                source_range=SourceRange(path="src/main.py", start_line=1, end_line=1),
                extractor="python_ast",
                confidence=1.0,
            ),
        ),
    ]

    store = SQLiteStore(db_path)
    try:
        store.initialize()
        store.persist_index(
            entities=entities,
            relations=relations,
            metadata=build_default_extraction_metadata(
                repository_root=repo_root,
                extractor_names=("filesystem", "python_ast"),
                timestamp="2026-05-20T00:00:00+00:00",
            ),
        )
    finally:
        store.close()

    registry.register(repo_root, db_path, indexed=True)
    return repo_root, db_path


def _stdio_exchange(
    session: StoreSessionState,
    messages: list[dict],
) -> list[dict]:
    """Run a list of JSON-RPC messages through serve_stdio and return responses."""
    lines = [json.dumps(m) for m in messages]
    stdin = io.StringIO("\n".join(lines) + "\n")
    stdout = io.StringIO()
    serve_stdio(session, stdin=stdin, stdout=stdout)
    responses = []
    for line in stdout.getvalue().splitlines():
        line = line.strip()
        if line:
            responses.append(json.loads(line))
    return responses


# ---------------------------------------------------------------------------
# Tool name surface
# ---------------------------------------------------------------------------


def test_store_only_tool_names_are_declared() -> None:
    assert "rsm_list_indexes" in STORE_ONLY_TOOL_NAMES
    assert "rsm_select_index" in STORE_ONLY_TOOL_NAMES
    assert "rsm_current_index" in STORE_ONLY_TOOL_NAMES


def test_store_tool_names_includes_all_phase1() -> None:
    for name in PHASE1_TOOL_NAMES:
        assert name in STORE_TOOL_NAMES


def test_store_tool_names_order_store_first() -> None:
    # Store-only tools appear before phase-1 tools.
    store_indices = [STORE_TOOL_NAMES.index(n) for n in STORE_ONLY_TOOL_NAMES]
    phase1_indices = [STORE_TOOL_NAMES.index(n) for n in PHASE1_TOOL_NAMES]
    assert max(store_indices) < min(phase1_indices)


def test_build_store_tool_registry_matches_store_tool_names() -> None:
    registry = build_store_tool_registry()
    assert tuple(registry.keys()) == STORE_TOOL_NAMES


# ---------------------------------------------------------------------------
# CLI: --store flag
# ---------------------------------------------------------------------------


def test_cli_mcp_serve_store_flag_parsed() -> None:
    parser = build_parser()
    args = parser.parse_args(["mcp", "serve", "--store"])
    assert args.mcp_target == "serve"
    assert args.store is True
    assert args.repo is None


def test_cli_mcp_serve_repo_and_store_mutually_exclusive() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["mcp", "serve", "--repo", "/x", "--store"])
    assert exc_info.value.code != 0


def test_cli_mcp_serve_requires_either_repo_or_store() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["mcp", "serve"])
    assert exc_info.value.code != 0


def test_cli_mcp_serve_help_mentions_store(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_main(["mcp", "serve", "--help"])
    captured = capsys.readouterr()
    assert "--store" in captured.out


def test_cli_mcp_serve_store_calls_run_serve_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI --store dispatches to run_serve_store, not run_serve."""
    captured_calls: list[str] = []

    def fake_run_serve_store() -> int:
        captured_calls.append("run_serve_store")
        return 0

    monkeypatch.setattr("repo_semantic_memory.mcp.server.run_serve_store", fake_run_serve_store)
    monkeypatch.setenv("RSM_HOME", str(tmp_path / "rsm"))

    code = cli_main(["mcp", "serve", "--store"])
    assert code == 0
    assert captured_calls == ["run_serve_store"]


# ---------------------------------------------------------------------------
# rsm_list_indexes
# ---------------------------------------------------------------------------


def test_list_indexes_empty_store(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    state = StoreSessionState(store_home=store_home)
    result = invoke_tool("rsm_list_indexes", {}, state)
    assert result["indexes"] == []
    assert result["count"] == 0
    assert "agent_instructions" in result


def test_list_indexes_returns_registered_repos(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "alpha", store_home)
    repo_b, db_b = _make_indexed_repo(tmp_path / "repos", "beta", store_home)

    state = StoreSessionState(store_home=store_home)
    result = invoke_tool("rsm_list_indexes", {}, state)

    assert result["count"] == 2
    indexes = result["indexes"]
    names = [i["name"] for i in indexes]
    assert "alpha" in names
    assert "beta" in names


def test_list_indexes_includes_required_fields(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "myrepo", store_home)

    state = StoreSessionState(store_home=store_home)
    result = invoke_tool("rsm_list_indexes", {}, state)

    entry = result["indexes"][0]
    assert "repo_id" in entry
    assert "name" in entry
    assert "repo_root" in entry
    assert "db_path" in entry
    assert entry["name"] == "myrepo"
    assert entry["repo_root"] == str(repo_a)
    assert entry["db_path"] == str(db_a)


def test_list_indexes_stable_ordering(tmp_path: Path) -> None:
    """Listing is deterministic: sorted by name then repo_root."""
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    _make_indexed_repo(tmp_path / "repos", "zebra", store_home)
    _make_indexed_repo(tmp_path / "repos", "alpha", store_home)
    _make_indexed_repo(tmp_path / "repos", "mango", store_home)

    state = StoreSessionState(store_home=store_home)
    result = invoke_tool("rsm_list_indexes", {}, state)

    names = [i["name"] for i in result["indexes"]]
    assert names == sorted(names)


def test_list_indexes_repo_id_is_stable(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, _ = _make_indexed_repo(tmp_path / "repos", "stable_id_test", store_home)

    state = StoreSessionState(store_home=store_home)
    r1 = invoke_tool("rsm_list_indexes", {}, state)
    r2 = invoke_tool("rsm_list_indexes", {}, state)

    assert r1["indexes"][0]["repo_id"] == r2["indexes"][0]["repo_id"]
    # The repo_id must match what IndexRegistry computes directly.
    expected_id = IndexRegistry.repo_id(repo_a)
    assert r1["indexes"][0]["repo_id"] == expected_id


# ---------------------------------------------------------------------------
# rsm_select_index
# ---------------------------------------------------------------------------


def test_select_index_by_repo_id(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "typer", store_home)
    repo_id = IndexRegistry.repo_id(repo_a)

    state = StoreSessionState(store_home=store_home)
    result = invoke_tool("rsm_select_index", {"repo_id": repo_id}, state)

    assert result["selected"]["repo_id"] == repo_id
    assert result["selected"]["name"] == "typer"
    assert "active_repo" in result
    assert state.active_index is not None
    assert state.active_index.repo_id == repo_id


def test_select_index_by_repo_root(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "richlib", store_home)

    state = StoreSessionState(store_home=store_home)
    result = invoke_tool("rsm_select_index", {"repo_root": str(repo_a)}, state)

    assert result["selected"]["repo_root"] == str(repo_a)
    assert state.active_index is not None
    assert state.active_index.repo_root == repo_a


def test_select_index_by_name_unambiguous(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, _ = _make_indexed_repo(tmp_path / "repos", "uniquename", store_home)

    state = StoreSessionState(store_home=store_home)
    result = invoke_tool("rsm_select_index", {"name": "uniquename"}, state)

    assert result["selected"]["name"] == "uniquename"
    assert state.active_index is not None


def test_select_index_by_name_ambiguous_fails(tmp_path: Path) -> None:
    """Two repos with the same basename → ambiguous name selection must fail."""
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    # Create two repos in different parent directories but with the same name.
    _make_indexed_repo(tmp_path / "workspace_a", "mylib", store_home)
    _make_indexed_repo(tmp_path / "workspace_b", "mylib", store_home)

    state = StoreSessionState(store_home=store_home)
    with pytest.raises(Exception, match="ambiguous"):
        invoke_tool("rsm_select_index", {"name": "mylib"}, state)


def test_select_index_missing_repo_id_fails(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()

    state = StoreSessionState(store_home=store_home)
    with pytest.raises(Exception, match="no registered index"):
        invoke_tool("rsm_select_index", {"repo_id": "deadbeefdeadbeef"}, state)


def test_select_index_missing_repo_root_fails(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()

    state = StoreSessionState(store_home=store_home)
    with pytest.raises(Exception, match="no registered index"):
        invoke_tool("rsm_select_index", {"repo_root": str(tmp_path / "nonexistent")}, state)


def test_select_index_no_selector_fails(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()

    state = StoreSessionState(store_home=store_home)
    with pytest.raises(ValueError):
        invoke_tool("rsm_select_index", {}, state)


# ---------------------------------------------------------------------------
# rsm_current_index
# ---------------------------------------------------------------------------


def test_current_index_no_selection_returns_null_active_repo(tmp_path: Path) -> None:
    state = StoreSessionState(store_home=tmp_path / "rsm")
    result = invoke_tool("rsm_current_index", {}, state)

    assert result["active_repo"] is None
    assert any(u["code"] == "no_active_index" for u in result["uncertainties"])
    assert result["uncertainties"][0]["recoverable"] is True


def test_current_index_after_selection_returns_active_repo(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "selected_repo", store_home)
    repo_id = IndexRegistry.repo_id(repo_a)

    state = StoreSessionState(store_home=store_home)
    invoke_tool("rsm_select_index", {"repo_id": repo_id}, state)

    result = invoke_tool("rsm_current_index", {}, state)
    assert result["active_repo"] is not None
    assert result["active_repo"]["repo_id"] == repo_id
    assert result["active_repo"]["name"] == "selected_repo"
    assert result["uncertainties"] == []


# ---------------------------------------------------------------------------
# Repository tools without selection → no_active_index
# ---------------------------------------------------------------------------


def test_repo_tool_without_selection_returns_recoverable_uncertainty(tmp_path: Path) -> None:
    """rsm_status (and any repo tool) in store mode with no active index."""
    state = StoreSessionState(store_home=tmp_path / "rsm")
    result = invoke_tool("rsm_status", {}, state)

    assert result["active_repo"] is None
    uncertainties = result.get("uncertainties", [])
    assert any(u["code"] == "no_active_index" for u in uncertainties)
    assert uncertainties[0]["recoverable"] is True


def test_build_context_pack_without_selection_returns_recoverable_uncertainty(
    tmp_path: Path,
) -> None:
    state = StoreSessionState(store_home=tmp_path / "rsm")
    result = invoke_tool("rsm_build_context_pack", {"task": "test task"}, state)

    assert result["active_repo"] is None
    assert any(u["code"] == "no_active_index" for u in result.get("uncertainties", []))


# ---------------------------------------------------------------------------
# Repository tools after selection → active_repo in every response
# ---------------------------------------------------------------------------


def test_repo_tool_after_selection_returns_active_repo(tmp_path: Path) -> None:
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "myapp", store_home)
    repo_id = IndexRegistry.repo_id(repo_a)

    state = StoreSessionState(store_home=store_home)
    invoke_tool("rsm_select_index", {"repo_id": repo_id}, state)

    result = invoke_tool("rsm_status", {}, state)
    assert "active_repo" in result
    assert result["active_repo"]["repo_id"] == repo_id
    assert result["active_repo"]["name"] == "myapp"


def test_switching_repos_updates_active_repo_in_responses(tmp_path: Path) -> None:
    """Select repo A, call rsm_status → refers to A. Select B → refers to B."""
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "alpha", store_home)
    repo_b, db_b = _make_indexed_repo(tmp_path / "repos", "beta", store_home)

    state = StoreSessionState(store_home=store_home)

    # Select alpha
    invoke_tool("rsm_select_index", {"repo_id": IndexRegistry.repo_id(repo_a)}, state)
    status_a = invoke_tool("rsm_status", {}, state)
    assert status_a["active_repo"]["name"] == "alpha"
    assert status_a["repo_root"] == str(repo_a)

    # Switch to beta
    invoke_tool("rsm_select_index", {"repo_id": IndexRegistry.repo_id(repo_b)}, state)
    status_b = invoke_tool("rsm_status", {}, state)
    assert status_b["active_repo"]["name"] == "beta"
    assert status_b["repo_root"] == str(repo_b)

    # No cross-repo stale state
    assert status_a["active_repo"]["name"] != status_b["active_repo"]["name"]


def test_no_cross_repo_stale_state(tmp_path: Path) -> None:
    """Verifies that selecting a second repo replaces the first, not accumulates."""
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, _ = _make_indexed_repo(tmp_path / "repos", "repoA", store_home)
    repo_b, _ = _make_indexed_repo(tmp_path / "repos", "repoB", store_home)

    state = StoreSessionState(store_home=store_home)

    invoke_tool("rsm_select_index", {"repo_id": IndexRegistry.repo_id(repo_a)}, state)
    assert state.active_index is not None
    assert state.active_index.name == "repoA"

    invoke_tool("rsm_select_index", {"repo_id": IndexRegistry.repo_id(repo_b)}, state)
    assert state.active_index is not None
    assert state.active_index.name == "repoB"

    # The db_path must point to repoB, not repoA.
    result = invoke_tool("rsm_status", {}, state)
    assert result["repo_root"] == str(repo_b)


# ---------------------------------------------------------------------------
# --repo mode unchanged
# ---------------------------------------------------------------------------


def test_repo_mode_tools_unchanged(tmp_path: Path) -> None:
    """--repo mode still exposes only PHASE1_TOOL_NAMES, not store tools."""
    from repo_semantic_memory.mcp import build_tool_registry

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    db_path = repo_root / ".rsm" / "index.sqlite"
    db_path.parent.mkdir(parents=True)
    # Store needs to be initialized for SessionConfig to work.
    store = SQLiteStore(db_path)
    try:
        store.initialize()
    finally:
        store.close()

    registry = build_tool_registry()
    assert tuple(registry.keys()) == PHASE1_TOOL_NAMES
    for name in STORE_ONLY_TOOL_NAMES:
        assert name not in registry


def test_store_tools_unavailable_in_repo_mode(tmp_path: Path) -> None:
    """Calling store tools with a SessionConfig raises ToolInvocationError."""
    from repo_semantic_memory.mcp import SessionConfig
    from repo_semantic_memory.mcp.runtime import ToolInvocationError

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    db_path = repo_root / ".rsm" / "index.sqlite"
    db_path.parent.mkdir()
    store = SQLiteStore(db_path)
    try:
        store.initialize()
    finally:
        store.close()

    session = SessionConfig(repo_root=repo_root.resolve(), db_path=db_path.resolve())
    with pytest.raises(ToolInvocationError, match="unknown tool"):
        invoke_tool("rsm_list_indexes", {}, session)


# ---------------------------------------------------------------------------
# serve_stdio tool-list shows store tools in store mode
# ---------------------------------------------------------------------------


def test_serve_stdio_store_mode_tools_list(tmp_path: Path) -> None:
    state = StoreSessionState(store_home=tmp_path / "rsm")
    responses = _stdio_exchange(
        state,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ],
    )
    tools_response = next(r for r in responses if r.get("id") == 2)
    tool_names = {t["name"] for t in tools_response["result"]["tools"]}

    for name in STORE_ONLY_TOOL_NAMES:
        assert name in tool_names
    for name in PHASE1_TOOL_NAMES:
        assert name in tool_names


def test_serve_stdio_store_mode_initialize_instructions(tmp_path: Path) -> None:
    """Initialize in store mode includes store-specific instructions."""
    state = StoreSessionState(store_home=tmp_path / "rsm")
    responses = _stdio_exchange(
        state,
        [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}],
    )
    init_response = responses[0]
    instructions = init_response["result"]["instructions"]
    assert "rsm_list_indexes" in instructions or "rsm_select_index" in instructions


# ---------------------------------------------------------------------------
# Stdio smoke test: full workflow
# ---------------------------------------------------------------------------


def test_stdio_smoke_store_workflow(tmp_path: Path) -> None:
    """Smoke test: initialize → list tools → list indexes → select → status."""
    store_home = tmp_path / "rsm"
    store_home.mkdir()
    repo_a, db_a = _make_indexed_repo(tmp_path / "repos", "smoketest_repo", store_home)
    repo_id = IndexRegistry.repo_id(repo_a)

    state = StoreSessionState(store_home=store_home)
    responses = _stdio_exchange(
        state,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "rsm_list_indexes", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "rsm_select_index",
                    "arguments": {"repo_id": repo_id},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "rsm_status", "arguments": {}},
            },
        ],
    )

    by_id = {r["id"]: r for r in responses}

    # initialize OK
    assert "result" in by_id[1]
    assert "protocolVersion" in by_id[1]["result"]

    # tools/list includes store tools
    tool_names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert "rsm_list_indexes" in tool_names
    assert "rsm_select_index" in tool_names
    assert "rsm_current_index" in tool_names

    # rsm_list_indexes returns our repo
    list_payload = json.loads(by_id[3]["result"]["content"][0]["text"])
    assert list_payload["count"] == 1
    assert list_payload["indexes"][0]["repo_id"] == repo_id

    # rsm_select_index succeeded
    select_payload = json.loads(by_id[4]["result"]["content"][0]["text"])
    assert select_payload["selected"]["repo_id"] == repo_id

    # rsm_status refers to the selected repo
    status_payload = json.loads(by_id[5]["result"]["content"][0]["text"])
    assert status_payload["active_repo"]["repo_id"] == repo_id
    assert status_payload["repo_root"] == str(repo_a)
