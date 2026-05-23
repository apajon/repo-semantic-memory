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
        "rsm_query_graph",
        "rsm_validate_patch_context",
        "rsm_get_git_summary",
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
