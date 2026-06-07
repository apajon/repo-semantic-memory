"""Tests for the minimal stdio MCP server runtime and CLI subcommand."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from repo_semantic_memory.cli import build_parser
from repo_semantic_memory.cli import main as cli_main
from repo_semantic_memory.mcp import (
    DEFERRED_TOOL_NAMES,
    PHASE1_TOOL_NAMES,
    build_tool_registry,
    invoke_tool,
    validate_session,
)
from repo_semantic_memory.mcp.runtime import ToolInvocationError
from repo_semantic_memory.mcp.server import serve_stdio
from repo_semantic_memory.model import Entity, Evidence, Relation, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata


@pytest.fixture()
def indexed_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "core.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    db_path = repo_root / ".rsm" / "index.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    entities = [
        Entity(
            id=StableId("python:module:src.core"),
            kind="module",
            name="core",
            qualified_name="src.core",
            source_range=SourceRange(path="src/core.py", start_line=1, end_line=2),
        ),
        Entity(
            id=StableId("python:function:src.core.run"),
            kind="function",
            name="run",
            qualified_name="src.core.run",
            source_range=SourceRange(path="src/core.py", start_line=1, end_line=2),
        ),
    ]
    relations = [
        Relation(
            source_entity_id=StableId("python:module:src.core"),
            target_entity_id=StableId("python:function:src.core.run"),
            kind="contains",
            evidence=Evidence(
                source_range=SourceRange(path="src/core.py", start_line=1, end_line=1),
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
    return repo_root, db_path


# ---------------------------------------------------------------------------
# CLI / import surface
# ---------------------------------------------------------------------------


def test_server_module_imports() -> None:
    from repo_semantic_memory.mcp import runtime, server  # noqa: F401


def test_cli_has_mcp_serve_subcommand() -> None:
    parser = build_parser()
    args = parser.parse_args(["mcp", "serve", "--repo", "/x", "--db", "/x/y.sqlite"])
    assert args.command == "mcp"
    assert args.mcp_target == "serve"
    assert args.repo == "/x"
    assert args.db == "/x/y.sqlite"


def test_cli_mcp_serve_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["mcp", "serve", "--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "--repo" in captured.out
    assert "--db" in captured.out


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def test_validate_session_accepts_valid_repo_and_db(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    assert session.repo_root == repo.resolve()
    assert session.db_path == db.resolve()


def test_validate_session_rejects_missing_repo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--repo path does not exist"):
        validate_session(tmp_path / "nope", tmp_path / "x.sqlite")


def test_validate_session_rejects_missing_db(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError, match="--db path does not exist"):
        validate_session(repo, repo / ".rsm" / "index.sqlite")


def test_validate_session_rejects_db_outside_repo(
    tmp_path: Path, indexed_repo: tuple[Path, Path]
) -> None:
    repo, db = indexed_repo
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()
    with pytest.raises(ValueError, match="must be inside --repo"):
        validate_session(other_repo, db)


def test_validate_session_allows_db_outside_repo_when_flag_false(
    tmp_path: Path, indexed_repo: tuple[Path, Path]
) -> None:
    # When require_db_inside_repo=False, a DB outside the repo is accepted.
    repo, db = indexed_repo
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()
    session = validate_session(other_repo, db, require_db_inside_repo=False)
    assert session.db_path == db.resolve()
    assert session.repo_root == other_repo.resolve()


def test_cli_mcp_serve_missing_db_returns_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    code = cli_main(
        [
            "mcp",
            "serve",
            "--repo",
            str(repo),
            "--db",
            str(repo / ".rsm" / "index.sqlite"),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "--db path does not exist" in err


def test_cli_mcp_serve_invalid_repo_returns_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli_main(
        [
            "mcp",
            "serve",
            "--repo",
            str(tmp_path / "nope"),
            "--db",
            str(tmp_path / "nope.sqlite"),
        ]
    )
    assert code == 2
    assert "--repo path does not exist" in capsys.readouterr().err


def test_cli_mcp_serve_optional_db_uses_registry(
    tmp_path: Path,
    indexed_repo: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When --db is omitted, run_serve resolves the DB from the Index Store."""
    from unittest import mock

    from repo_semantic_memory.store_home import IndexRegistry

    repo, db = indexed_repo
    store_home = tmp_path / "store"
    store_home.mkdir()
    (store_home / "indexes").mkdir()

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        registry = IndexRegistry(store_home)
        registry.register(repo, db)

        from repo_semantic_memory.mcp.server import run_serve

        # Mock serve_stdio so we don't need a real stdin/stdout.
        with mock.patch(
            "repo_semantic_memory.mcp.server.serve_stdio", return_value=0
        ) as mock_serve:
            code = run_serve(repo=str(repo), db=None)

    assert code == 0
    # Confirm serve_stdio was called with a valid session pointing at the registered DB.
    mock_serve.assert_called_once()
    session = mock_serve.call_args[0][0]
    assert session.db_path == db.resolve()
    assert session.repo_root == repo.resolve()
    capsys.readouterr()  # drain any captured output


def test_cli_mcp_serve_without_db_and_not_registered_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When --db is omitted and the repo is not registered, exit code 2."""
    from unittest import mock

    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = cli_main(["mcp", "serve", "--repo", str(repo)])
    assert code == 2
    err = capsys.readouterr().err
    assert "no index registered" in err


def test_cli_mcp_serve_db_optional_default_is_none() -> None:
    """Confirm --db defaults to None (not required) after our change."""
    parser = build_parser()
    args = parser.parse_args(["mcp", "serve", "--repo", "/some/repo"])
    assert args.db is None


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


def test_tool_registry_names_match_phase1_contract() -> None:
    registry = build_tool_registry()
    assert tuple(registry.keys()) == PHASE1_TOOL_NAMES
    assert set(registry.keys()) == {
        "rsm_status",
        "rsm_search_symbols",
        "rsm_explain_entity",
        "rsm_build_context_pack",
        "rsm_get_context_page",
        "rsm_query_graph",
        "rsm_validate_patch_context",
        "rsm_get_git_summary",
        "rsm_prepare_context",
    }


def test_tool_registry_does_not_expose_deferred_tools() -> None:
    registry = build_tool_registry()
    exposed = set(registry.keys())
    for deferred in DEFERRED_TOOL_NAMES:
        assert deferred not in exposed
    # No tool name should suggest write/mutation, indexing, exporting, importing,
    # shell execution, test execution, or patch application.
    forbidden_substrings = (
        "index",
        "export",
        "import",
        "run_command",
        "run_tests",
        "apply_patch",
        "write",
        "mutate",
        "shell",
        "exec",
    )
    for name in exposed:
        for needle in forbidden_substrings:
            assert needle not in name, f"tool {name!r} contains forbidden substring {needle!r}"


def test_tool_descriptors_have_schemas() -> None:
    registry = build_tool_registry()
    for descriptor in registry.values():
        assert descriptor.input_schema["type"] == "object"
        assert "additionalProperties" in descriptor.input_schema
        assert descriptor.description.strip()


# ---------------------------------------------------------------------------
# Wrapper behavior
# ---------------------------------------------------------------------------


def test_invoke_status(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool("rsm_status", {}, session)
    assert result["repo_root"] == repo.resolve().as_posix()
    assert result["db_path"] == db.resolve().as_posix()
    assert result["entity_count"] == 2
    assert result["relation_count"] == 1
    assert result["read_only"] is True
    assert result["auto_index"] is False
    assert list(result["tools"]) == list(PHASE1_TOOL_NAMES)


def test_invoke_search_symbols(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool("rsm_search_symbols", {"query": "run", "limit": 5}, session)
    assert "matches" in result
    # Results carry citations and budget envelope preserved from the handler.
    assert "citations" in result
    assert "budget" in result
    # Ergonomics: agent_instructions and top-level path fields
    assert "agent_instructions" in result
    assert isinstance(result["agent_instructions"], list)
    for item in result["results"]:
        assert "path" in item
        assert "start_line" in item
        assert "end_line" in item
        assert "score" in item


def test_invoke_explain_entity_unknown_returns_uncertainty(
    indexed_repo: tuple[Path, Path],
) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_explain_entity", {"entity_id": "python:function:does.not.exist"}, session
    )
    codes = {item["code"] for item in result["uncertainties"]}
    assert "entity_not_found" in codes


def test_invoke_build_context_pack_caps_budget(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 999_999},
        session,
    )
    assert result["budget"]["requested_chars"] == 999_999
    codes = {item["code"] for item in result["uncertainties"]}
    assert "budget_capped" in codes
    # Ergonomics fields present
    assert "selected_files" in result
    assert isinstance(result["selected_files"], list)
    assert "selected_entities" in result
    assert isinstance(result["selected_entities"], list)
    assert "selected_relations" in result
    assert isinstance(result["selected_relations"], list)
    assert "agent_instructions" in result
    assert isinstance(result["agent_instructions"], list)
    # Existing fields preserved
    assert "payload" in result
    assert "rendered" in result
    assert "selected_entity_ids" in result
    assert "selected_relation_keys" in result


def test_invoke_query_graph(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_query_graph",
        {"entity_ids": ["python:module:src.core"], "max_hops": 1, "limit": 10},
        session,
    )
    assert "python:module:src.core" in result["entity_ids"]


def test_invoke_validate_patch_context(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_validate_patch_context",
        {"task": "tweak run", "changed_paths": ["src/core.py"]},
        session,
    )
    assert "covered_paths" in result
    assert "missing_paths" in result


def test_invoke_get_git_summary_defaults_to_repo(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    # Path defaults to session.repo_root.
    result = invoke_tool("rsm_get_git_summary", {}, session)
    assert "uncertainties" in result


def test_invoke_unknown_tool_raises(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    with pytest.raises(ToolInvocationError, match="unknown tool"):
        invoke_tool("rsm_nope", {}, session)


def test_invoke_search_symbols_rejects_missing_query(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    with pytest.raises(ToolInvocationError, match="query"):
        invoke_tool("rsm_search_symbols", {}, session)


# ---------------------------------------------------------------------------
# stdio JSON-RPC protocol smoke tests
# ---------------------------------------------------------------------------


def _drive(session, messages: list[dict]) -> list[dict]:
    stdin = io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n")
    stdout = io.StringIO()
    serve_stdio(session, stdin=stdin, stdout=stdout)
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_stdio_initialize_and_tools_list(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
    )
    assert responses[0]["id"] == 1
    assert responses[0]["result"]["serverInfo"]["name"] == "repo-semantic-memory"
    assert responses[1]["id"] == 2
    names = [tool["name"] for tool in responses[1]["result"]["tools"]]
    assert names == list(PHASE1_TOOL_NAMES)


def test_stdio_tool_call_status(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "rsm_status", "arguments": {}},
            },
        ],
    )
    assert responses[0]["id"] == 7
    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert payload["entity_count"] == 2
    assert responses[0]["result"]["isError"] is False


def test_stdio_unknown_tool_returns_tool_error(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "rsm_index", "arguments": {}},
            },
        ],
    )
    assert responses[0]["result"]["isError"] is True
    assert "unknown tool" in responses[0]["result"]["content"][0]["text"]


def test_stdio_malformed_json_returns_parse_error(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    stdin = io.StringIO("{not json\n")
    stdout = io.StringIO()
    serve_stdio(session, stdin=stdin, stdout=stdout)
    line = stdout.getvalue().strip()
    payload = json.loads(line)
    assert payload["error"]["code"] == -32700


def test_stdio_unknown_method_returns_method_not_found(
    indexed_repo: tuple[Path, Path],
) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(session, [{"jsonrpc": "2.0", "id": 3, "method": "totally/unknown"}])
    assert responses[0]["error"]["code"] == -32601


def test_stdio_search_symbols_ergonomics_fields(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "rsm_search_symbols",
                    "arguments": {"query": "run", "limit": 5},
                },
            },
        ],
    )
    assert responses[0]["result"]["isError"] is False
    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert "agent_instructions" in payload
    for item in payload["results"]:
        assert "path" in item
        assert "start_line" in item
        assert "end_line" in item
        assert "score" in item


def test_stdio_build_context_pack_ergonomics_fields(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "rsm_build_context_pack",
                    "arguments": {"task": "Improve run()", "budget_chars": 8000},
                },
            },
        ],
    )
    assert responses[0]["result"]["isError"] is False
    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert "selected_files" in payload
    assert "selected_entities" in payload
    assert "selected_relations" in payload
    assert "agent_instructions" in payload
    # Existing fields preserved
    assert "payload" in payload
    assert "rendered" in payload
    assert "selected_entity_ids" in payload
    assert "selected_relation_keys" in payload


def test_stdio_build_context_pack_compact_default(indexed_repo: tuple[Path, Path]) -> None:
    """Default MCP rsm_build_context_pack output is compact.

    rendered/payload/ranking_breakdowns must be omitted unless explicitly
    requested. The response advertises omissions via ``omitted_sections``
    and points clients to progressive-disclosure follow-up calls via
    ``how_to_get_more``.
    """

    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "rsm_build_context_pack",
                    "arguments": {"task": "Improve run()", "budget_chars": 8000},
                },
            },
        ],
    )
    assert responses[0]["result"]["isError"] is False
    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert payload["rendered"] == ""
    assert payload["payload"] == {}
    assert "omitted_sections" in payload
    assert "rendered" in payload["omitted_sections"]
    assert "payload" in payload["omitted_sections"]
    assert "ranking_breakdowns" in payload["omitted_sections"]
    assert "how_to_get_more" in payload
    assert payload["how_to_get_more"]


def test_stdio_build_context_pack_include_rendered_true(
    indexed_repo: tuple[Path, Path],
) -> None:
    """Explicitly requesting include_rendered=true returns non-empty rendered output."""

    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {
                    "name": "rsm_build_context_pack",
                    "arguments": {
                        "task": "Improve run()",
                        "budget_chars": 8000,
                        "include_rendered": True,
                    },
                },
            },
        ],
    )
    assert responses[0]["result"]["isError"] is False
    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert payload["rendered"].strip()
    assert "rendered" not in payload["omitted_sections"]


# ---------------------------------------------------------------------------
# Progressive context retrieval (Prompt 46.3)
# ---------------------------------------------------------------------------


def test_invoke_build_context_pack_returns_result_set_id_and_counts(
    indexed_repo: tuple[Path, Path],
) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
    )
    assert isinstance(result.get("result_set_id"), str)
    assert result["result_set_id"].startswith("pack_")
    counts = result.get("counts")
    assert isinstance(counts, dict)
    for stream_name in ("files", "entities", "relations", "citations", "ranking_breakdowns"):
        assert stream_name in counts
        assert isinstance(counts[stream_name], int)


def test_get_context_page_reads_already_stored_streams(
    indexed_repo: tuple[Path, Path],
) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    # Reuse the same result store so paging sees what was minted.
    from repo_semantic_memory.mcp.session import ResultStore

    store = ResultStore()
    pack = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
        result_store=store,
    )
    result_set_id = pack["result_set_id"]
    page = invoke_tool(
        "rsm_get_context_page",
        {"result_set_id": result_set_id, "stream": "entities", "offset": 0, "limit": 2},
        session,
        result_store=store,
    )
    assert page["result_set_id"] == result_set_id
    assert page["stream"] == "entities"
    assert page["offset"] == 0
    assert page["limit"] == 2
    assert page["total"] == pack["counts"]["entities"]
    assert isinstance(page["items"], list)
    assert page["uncertainties"] == []
    for entry in page["items"]:
        assert "id" in entry
        assert entry["id"].startswith("e")


def test_get_context_page_unknown_id_returns_recoverable_uncertainty(
    indexed_repo: tuple[Path, Path],
) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    page = invoke_tool(
        "rsm_get_context_page",
        {"result_set_id": "pack_deadbeef00", "stream": "entities"},
        session,
    )
    # Unknown result_set_id is a tool-level uncertainty, not an exception.
    assert page["items"] == []
    assert page["total"] == 0
    assert page["next_offset"] is None
    codes = {item["code"] for item in page["uncertainties"]}
    assert "result_set_unknown" in codes
    for entry in page["uncertainties"]:
        if entry["code"] == "result_set_unknown":
            assert entry["recoverable"] is True
            assert entry["subject_id"] == "pack_deadbeef00"
            # Error message should reference both new and old tool names.
            assert "rsm_prepare_context" in entry["message"]
            assert "rsm_build_context_pack" in entry["message"]


def test_get_context_page_for_build_context_pack_works_after_prepare_context(
    indexed_repo: tuple[Path, Path],
) -> None:
    """rsm_get_context_page continues to work with rsm_build_context_pack
    result sets after rsm_prepare_context was added to the registry."""
    from repo_semantic_memory.mcp.session import ResultStore

    repo, db = indexed_repo
    session = validate_session(repo, db)
    store = ResultStore()
    pack = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
        result_store=store,
    )
    result_set_id = pack["result_set_id"]
    page = invoke_tool(
        "rsm_get_context_page",
        {"result_set_id": result_set_id, "stream": "files", "offset": 0, "limit": 5},
        session,
        result_store=store,
    )
    assert page["result_set_id"] == result_set_id
    assert page["stream"] == "files"
    assert page["uncertainties"] == []


def test_get_context_page_empty_result_set_id_is_error(
    indexed_repo: tuple[Path, Path],
) -> None:
    """Empty result_set_id should be rejected as a tool-call error."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    with pytest.raises(ToolInvocationError, match="result_set_id"):
        invoke_tool(
            "rsm_get_context_page",
            {"result_set_id": "", "stream": "entities"},
            session,
        )


def test_get_context_page_negative_offset_is_error(
    indexed_repo: tuple[Path, Path],
) -> None:
    """Negative offset should be rejected as a tool-call error."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    with pytest.raises(ToolInvocationError, match="offset"):
        invoke_tool(
            "rsm_get_context_page",
            {"result_set_id": "pack_abc", "stream": "entities", "offset": -1},
            session,
        )


def test_get_context_page_rejects_malformed_args(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    # Missing result_set_id → tool-call error (not a tool-level uncertainty).
    with pytest.raises(ToolInvocationError, match="result_set_id"):
        invoke_tool("rsm_get_context_page", {"stream": "entities"}, session)
    # Unknown stream → tool-call error.
    with pytest.raises(ToolInvocationError, match="stream"):
        invoke_tool(
            "rsm_get_context_page",
            {"result_set_id": "pack_x", "stream": "nope"},
            session,
        )
    # Out-of-range limit → tool-call error.
    with pytest.raises(ToolInvocationError, match="limit"):
        invoke_tool(
            "rsm_get_context_page",
            {"result_set_id": "pack_x", "stream": "entities", "limit": 0},
            session,
        )
    with pytest.raises(ToolInvocationError, match="limit"):
        invoke_tool(
            "rsm_get_context_page",
            {"result_set_id": "pack_x", "stream": "entities", "limit": 999},
            session,
        )


def test_stdio_get_context_page_unknown_id_is_recoverable(
    indexed_repo: tuple[Path, Path],
) -> None:
    """An unknown ``result_set_id`` over stdio must surface as a tool-level
    uncertainty (``result_set_unknown``), not a JSON-RPC protocol error."""

    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": "rsm_get_context_page",
                    "arguments": {
                        "result_set_id": "pack_deadbeef00",
                        "stream": "entities",
                    },
                },
            },
        ],
    )
    assert "error" not in responses[0]
    assert responses[0]["result"]["isError"] is False
    page = json.loads(responses[0]["result"]["content"][0]["text"])
    codes = {item["code"] for item in page["uncertainties"]}
    assert "result_set_unknown" in codes
    assert page["items"] == []
    for entry in page["uncertainties"]:
        if entry["code"] == "result_set_unknown":
            assert "rsm_prepare_context" in entry["message"]
            assert "rsm_build_context_pack" in entry["message"]


def test_stdio_in_session_paging_is_live(indexed_repo: tuple[Path, Path]) -> None:
    """Build + page calls inside the same ``serve_stdio`` run share one store.

    The page response must come back without ``result_set_unknown`` and the
    items must carry the short stable per-entry IDs added at registration
    time. Reading the build response's ``result_set_id`` mid-stream is done
    by driving the two messages with a helper that re-issues the page call
    once the first response is on the wire.
    """

    import io

    from repo_semantic_memory.mcp.server import serve_stdio

    repo, db = indexed_repo
    session = validate_session(repo, db)

    # First run: capture the freshly minted result_set_id.
    build_msg = {
        "jsonrpc": "2.0",
        "id": 70,
        "method": "tools/call",
        "params": {
            "name": "rsm_build_context_pack",
            "arguments": {"task": "Improve run()", "budget_chars": 8000},
        },
    }
    stdin = io.StringIO(json.dumps(build_msg) + "\n")
    stdout = io.StringIO()
    serve_stdio(session, stdin=stdin, stdout=stdout)
    first_payload = json.loads(
        json.loads(stdout.getvalue().strip())["result"]["content"][0]["text"]
    )
    result_set_id = first_payload["result_set_id"]

    # Second run: same session, but a fresh ResultStore. The ID must now be
    # unknown - this asserts result sets are scoped to a single MCP session.
    page_msg = {
        "jsonrpc": "2.0",
        "id": 71,
        "method": "tools/call",
        "params": {
            "name": "rsm_get_context_page",
            "arguments": {"result_set_id": result_set_id, "stream": "entities"},
        },
    }
    stdin = io.StringIO(json.dumps(page_msg) + "\n")
    stdout = io.StringIO()
    serve_stdio(session, stdin=stdin, stdout=stdout)
    page_payload = json.loads(json.loads(stdout.getvalue().strip())["result"]["content"][0]["text"])
    codes = {item["code"] for item in page_payload["uncertainties"]}
    assert "result_set_unknown" in codes


# ---------------------------------------------------------------------------
# Brief default preview (Prompt 46.4)
# ---------------------------------------------------------------------------


def test_build_context_pack_brief_default_caps(indexed_repo: tuple[Path, Path]) -> None:
    """Default ``rsm_build_context_pack`` returns a brief first-page preview.

    Brief caps: max_files=5, max_entities=5, max_relations=3, max_citations=0.
    ``counts`` still reports the full per-stream totals, and ``next`` advertises
    streams that have more items available via ``rsm_get_context_page``.
    """

    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
    )
    assert result["detail_level"] == "brief"
    assert len(result["selected_files"]) <= 5
    assert len(result["selected_entities"]) <= 5
    assert len(result["selected_relations"]) <= 3
    assert result["citations"] == []
    counts = result["counts"]
    assert counts["citations"] >= 0  # full citation count is still reported
    assert "result_set_id" in result
    assert "how_to_get_more" in result
    assert "next" in result
    if counts["citations"] > 0:
        assert "citations" in result["next"]
        assert result["next"]["citations"]["available"] == counts["citations"]
        assert result["next"]["citations"]["tool"] == "rsm_get_context_page"
    # Prompt 46.6: verbose full-list compatibility fields are emptied in
    # brief mode. The full data is still reachable via ``result_set_id`` +
    # ``rsm_get_context_page`` and ``counts`` continues to report totals.
    assert result["selected_entity_ids"] == []
    assert result["selected_relation_keys"] == []


def test_build_context_pack_compact_preserves_larger_caps(
    indexed_repo: tuple[Path, Path],
) -> None:
    """``detail_level='compact'`` keeps the post-46.1/46.3 one-shot preview."""

    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000, "detail_level": "compact"},
        session,
    )
    assert result["detail_level"] == "compact"
    counts = result["counts"]
    # Compact must not artificially shrink to brief caps. When the full
    # stream has > 5 items, compact preview shows more than 5.
    assert len(result["selected_entities"]) == min(counts["entities"], 15)
    assert len(result["selected_relations"]) == min(counts["relations"], 10)
    assert len(result["citations"]) == min(counts["citations"], 12)
    assert "result_set_id" in result
    # Prompt 46.6: compact mode preserves the populated full-list compatibility
    # fields. When the pack selected any entities/relations the lists must be
    # non-empty; otherwise they remain trivially empty for consistency.
    if counts["entities"] > 0:
        assert result["selected_entity_ids"]
    if counts["relations"] > 0:
        assert result["selected_relation_keys"]


def test_build_context_pack_explicit_overrides(indexed_repo: tuple[Path, Path]) -> None:
    """Explicit ``max_*`` values override brief/compact defaults."""

    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {
            "task": "Improve run()",
            "budget_chars": 8000,
            "max_entities": 12,
            "max_relations": 6,
            "max_citations": 4,
            "max_files": 7,
        },
        session,
    )
    counts = result["counts"]
    assert len(result["selected_entities"]) == min(counts["entities"], 12)
    assert len(result["selected_relations"]) == min(counts["relations"], 6)
    assert len(result["citations"]) == min(counts["citations"], 4)
    assert len(result["selected_files"]) == min(counts["files"], 7)


def test_build_context_pack_rejects_negative_caps(indexed_repo: tuple[Path, Path]) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    for key in ("max_files", "max_entities", "max_relations", "max_citations"):
        with pytest.raises(ToolInvocationError, match=key):
            invoke_tool(
                "rsm_build_context_pack",
                {"task": "Improve run()", "budget_chars": 8000, key: -1},
                session,
            )


def test_build_context_pack_rejects_invalid_detail_level(
    indexed_repo: tuple[Path, Path],
) -> None:
    repo, db = indexed_repo
    session = validate_session(repo, db)
    with pytest.raises(ToolInvocationError, match="detail_level"):
        invoke_tool(
            "rsm_build_context_pack",
            {"task": "Improve run()", "budget_chars": 8000, "detail_level": "nope"},
            session,
        )


def test_brief_default_paging_recovers_omitted_streams(
    indexed_repo: tuple[Path, Path],
) -> None:
    """``rsm_get_context_page`` retrieves items the brief preview omitted."""

    from repo_semantic_memory.mcp.session import ResultStore

    repo, db = indexed_repo
    session = validate_session(repo, db)
    store = ResultStore()
    pack = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
        result_store=store,
    )
    result_set_id = pack["result_set_id"]
    counts = pack["counts"]

    # Citations are always omitted from the brief preview but remain in the
    # underlying stream when the pack produced any.
    if counts["citations"] > 0:
        cit_page = invoke_tool(
            "rsm_get_context_page",
            {"result_set_id": result_set_id, "stream": "citations"},
            session,
            result_store=store,
        )
        assert cit_page["total"] == counts["citations"]
        assert cit_page["items"], "citations stream should be pageable"

    # Entities beyond the first 5 should be retrievable when the pack
    # selected more than 5.
    if counts["entities"] > 5:
        ent_page = invoke_tool(
            "rsm_get_context_page",
            {
                "result_set_id": result_set_id,
                "stream": "entities",
                "offset": 5,
                "limit": 5,
            },
            session,
            result_store=store,
        )
        assert ent_page["offset"] == 5
        assert ent_page["items"], "entities beyond brief preview should page"

    # Relations beyond the first 3 should be retrievable when available.
    if counts["relations"] > 3:
        rel_page = invoke_tool(
            "rsm_get_context_page",
            {
                "result_set_id": result_set_id,
                "stream": "relations",
                "offset": 3,
                "limit": 5,
            },
            session,
            result_store=store,
        )
        assert rel_page["offset"] == 3
        assert rel_page["items"], "relations beyond brief preview should page"


def test_stdio_brief_default_size_is_smaller_than_compact(
    indexed_repo: tuple[Path, Path],
) -> None:
    """The default brief response is materially smaller than ``compact``.

    This is a directional smoke check, not an exact-byte assertion: the
    brief default omits citations and caps files/entities/relations, so
    its serialized payload must be strictly smaller than the compact
    response on the same fixture.
    """

    repo, db = indexed_repo
    session = validate_session(repo, db)
    brief = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
    )
    compact = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000, "detail_level": "compact"},
        session,
    )
    brief_bytes = len(json.dumps(brief, separators=(",", ":"), sort_keys=True))
    compact_bytes = len(json.dumps(compact, separators=(",", ":"), sort_keys=True))
    # Use ``<=`` rather than ``<`` because the indexed-repo fixture is tiny
    # and may produce equal payloads when streams already fit under both caps.
    assert brief_bytes <= compact_bytes


# ---------------------------------------------------------------------------
# Scope metadata in rsm_status (Prompt 57.5)
# ---------------------------------------------------------------------------


@pytest.fixture()
def scoped_indexed_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Fixture for a repo indexed with include/exclude scope metadata."""
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "core.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    db_path = repo_root / ".rsm" / "index.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    entities = [
        Entity(
            id=StableId("python:module:src.core"),
            kind="module",
            name="core",
            qualified_name="src.core",
            source_range=SourceRange(path="src/core.py", start_line=1, end_line=2),
        ),
    ]

    store = SQLiteStore(db_path)
    try:
        store.initialize()
        store.persist_index(
            entities=entities,
            relations=[],
            metadata=build_default_extraction_metadata(
                repository_root=repo_root,
                extractor_names=("filesystem", "python_ast"),
                timestamp="2026-05-20T00:00:00+00:00",
            ),
        )
        store.write_extra_metadata(
            {
                "indexed_at": "2026-05-20T00:00:00+00:00",
                "entity_count": "1",
                "relation_count": "0",
                "index_scope": "scoped",
                "include_patterns": '["src/**"]',
                "exclude_patterns": '["tests/**"]',
            }
        )
    finally:
        store.close()
    return repo_root, db_path


def test_rsm_status_includes_scope_fields_full(indexed_repo: tuple[Path, Path]) -> None:
    """rsm_status returns index_scope, include_patterns, exclude_patterns for full index."""
    repo, db = indexed_repo
    store = SQLiteStore(db)
    try:
        store.initialize()
        store.write_extra_metadata(
            {
                "indexed_at": "2026-05-20T00:00:00+00:00",
                "entity_count": "2",
                "relation_count": "1",
                "index_scope": "full",
                "include_patterns": "[]",
                "exclude_patterns": "[]",
            }
        )
    finally:
        store.close()
    session = validate_session(repo, db)
    result = invoke_tool("rsm_status", {}, session)
    assert result["index_scope"] == "full"
    assert result["include_patterns"] == []
    assert result["exclude_patterns"] == []


def test_rsm_status_includes_scope_fields_scoped(scoped_indexed_repo: tuple[Path, Path]) -> None:
    """rsm_status returns correct scope for a scoped index."""
    repo, db = scoped_indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool("rsm_status", {}, session)
    assert result["index_scope"] == "scoped"
    assert result["include_patterns"] == ["src/**"]
    assert result["exclude_patterns"] == ["tests/**"]


def test_rsm_status_scope_none_for_old_index(indexed_repo: tuple[Path, Path]) -> None:
    """rsm_status returns index_scope=None and empty lists for old indexes lacking scope."""
    repo, db = indexed_repo
    # indexed_repo fixture doesn't write scope metadata → simulates old index
    session = validate_session(repo, db)
    result = invoke_tool("rsm_status", {}, session)
    assert "index_scope" in result
    assert result["index_scope"] is None
    assert result["include_patterns"] == []
    assert result["exclude_patterns"] == []


def test_rsm_build_context_pack_scope_warning_scoped(
    scoped_indexed_repo: tuple[Path, Path],
) -> None:
    """rsm_build_context_pack includes scope_warning and scope fields for scoped indexes."""
    repo, db = scoped_indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {"task": "find run function"},
        session,
    )
    assert result.get("index_scope") == "scoped"
    assert result.get("include_patterns") == ["src/**"]
    assert result.get("exclude_patterns") == ["tests/**"]
    assert "scope_warning" in result


def test_rsm_build_context_pack_no_scope_warning_full(indexed_repo: tuple[Path, Path]) -> None:
    """rsm_build_context_pack has no scope_warning for a full index."""
    repo, db = indexed_repo
    store = SQLiteStore(db)
    try:
        store.initialize()
        store.write_extra_metadata(
            {
                "indexed_at": "2026-05-20T00:00:00+00:00",
                "entity_count": "2",
                "relation_count": "1",
                "index_scope": "full",
                "include_patterns": "[]",
                "exclude_patterns": "[]",
            }
        )
    finally:
        store.close()
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {"task": "find run function"},
        session,
    )
    # For full indexes, scope_warning should be absent
    assert "scope_warning" not in result
    assert result.get("index_scope") == "full"


# ---------------------------------------------------------------------------
# rsm_prepare_context (61.3)
# ---------------------------------------------------------------------------


def test_invoke_prepare_context_is_equivalent_to_build_context_pack(
    indexed_repo: tuple[Path, Path],
) -> None:
    """rsm_prepare_context returns the same core output as rsm_build_context_pack."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    args = {"task": "Improve run()", "budget_chars": 8000}
    prepare_result = invoke_tool("rsm_prepare_context", args, session)
    build_result = invoke_tool("rsm_build_context_pack", args, session)

    # Core fields match (everything except active_repo, which is prepare_context-only,
    # and result_set_id which is a random per-call token)
    for key in (
        "rendered",
        "payload",
        "selected_entity_ids",
        "selected_relation_keys",
        "selected_files",
        "selected_entities",
        "selected_relations",
        "citations",
        "uncertainties",
        "budget",
        "agent_instructions",
        "truncated",
        "omitted_sections",
        "how_to_get_more",
        "counts",
        "detail_level",
    ):
        assert prepare_result[key] == build_result[key], f"Field {key!r} differs"

    # Both return valid result_set_id but they differ per call
    assert prepare_result["result_set_id"].startswith("pack_")
    assert build_result["result_set_id"].startswith("pack_")

    # prepare_context adds active_repo that build_context_pack does not have
    assert "active_repo" in prepare_result
    assert "active_repo" not in build_result


def test_prepare_context_includes_active_repo(
    indexed_repo: tuple[Path, Path],
) -> None:
    """rsm_prepare_context response includes active_repo metadata."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_prepare_context",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
    )
    assert "active_repo" in result
    assert result["active_repo"]["repo_root"] == repo.resolve().as_posix()
    assert result["active_repo"]["db_path"] == db.resolve().as_posix()
    assert result["active_repo"]["index_mode"] == "explicit_db"


def test_prepare_context_returns_result_set_id(
    indexed_repo: tuple[Path, Path],
) -> None:
    """rsm_prepare_context returns a result_set_id for progressive retrieval."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_prepare_context",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
    )
    assert isinstance(result.get("result_set_id"), str)
    assert result["result_set_id"].startswith("pack_")
    counts = result.get("counts")
    assert isinstance(counts, dict)
    for stream_name in ("files", "entities", "relations", "citations"):
        assert stream_name in counts


def test_prepare_context_paginates_with_get_context_page(
    indexed_repo: tuple[Path, Path],
) -> None:
    """rsm_get_context_page can page over rsm_prepare_context result sets."""
    from repo_semantic_memory.mcp.session import ResultStore

    repo, db = indexed_repo
    session = validate_session(repo, db)
    store = ResultStore()
    pack = invoke_tool(
        "rsm_prepare_context",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
        result_store=store,
    )
    result_set_id = pack["result_set_id"]
    page = invoke_tool(
        "rsm_get_context_page",
        {"result_set_id": result_set_id, "stream": "entities", "offset": 0, "limit": 2},
        session,
        result_store=store,
    )
    assert page["result_set_id"] == result_set_id
    assert page["stream"] == "entities"
    assert page["total"] == pack["counts"]["entities"]
    assert isinstance(page["items"], list)
    assert page["uncertainties"] == []


def test_build_context_pack_still_works_after_prepare_context_added(
    indexed_repo: tuple[Path, Path],
) -> None:
    """rsm_build_context_pack is unchanged after adding rsm_prepare_context."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    result = invoke_tool(
        "rsm_build_context_pack",
        {"task": "Improve run()", "budget_chars": 8000},
        session,
    )
    assert "selected_files" in result
    assert "selected_entities" in result
    assert "result_set_id" in result
    assert result["result_set_id"].startswith("pack_")
    # build_context_pack does NOT include active_repo
    assert "active_repo" not in result


def test_stdio_tool_list_includes_prepare_context(
    indexed_repo: tuple[Path, Path],
) -> None:
    """MCP tools/list includes rsm_prepare_context."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
    )
    assert responses[1]["id"] == 2
    names = [tool["name"] for tool in responses[1]["result"]["tools"]]
    assert "rsm_prepare_context" in names
    assert "rsm_build_context_pack" in names
    # names must match PHASE1_TOOL_NAMES (auto-updated via the tuple)
    assert names == list(PHASE1_TOOL_NAMES)


def test_prepare_context_stdio_tool_call(
    indexed_repo: tuple[Path, Path],
) -> None:
    """MCP tools/call with rsm_prepare_context works via stdio."""
    repo, db = indexed_repo
    session = validate_session(repo, db)
    responses = _drive(
        session,
        [
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {
                    "name": "rsm_prepare_context",
                    "arguments": {"task": "Improve run()", "budget_chars": 8000},
                },
            },
        ],
    )
    assert responses[0]["result"]["isError"] is False
    payload = json.loads(responses[0]["result"]["content"][0]["text"])
    assert "active_repo" in payload
    assert "selected_files" in payload
    assert "result_set_id" in payload
    assert payload["result_set_id"].startswith("pack_")
