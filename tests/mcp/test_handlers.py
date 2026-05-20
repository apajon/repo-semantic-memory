"""Tests for pure MCP-style handler implementations."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from repo_semantic_memory.extractors.git_history import GitRepositorySummary
from repo_semantic_memory.mcp.handlers import (
    handle_build_context_pack,
    handle_export_ai_memory,
    handle_get_git_summary,
    handle_query_graph,
    handle_search_symbols,
    handle_validate_patch_context,
)
from repo_semantic_memory.mcp.tools import (
    BuildContextPackRequest,
    ExportAiMemoryRequest,
    GetGitSummaryRequest,
    QueryGraphRequest,
    SearchSymbolsRequest,
    ValidatePatchContextRequest,
)
from repo_semantic_memory.model import Entity, Evidence, Relation, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata


@pytest.fixture()
def indexed_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "core.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (repo_root / "tests" / "test_core.py").write_text(
        "from src.core import run\n", encoding="utf-8"
    )

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
        Entity(
            id=StableId("python:module:tests.test_core"),
            kind="module",
            name="test_core",
            qualified_name="tests.test_core",
            source_range=SourceRange(path="tests/test_core.py", start_line=1, end_line=1),
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
        Relation(
            source_entity_id=StableId("python:module:tests.test_core"),
            target_entity_id=StableId("python:function:src.core.run"),
            kind="tests",
        ),
    ]

    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = build_default_extraction_metadata(
            repository_root=repo_root,
            extractor_names=("filesystem", "python_ast", "test_relationships"),
            timestamp="2026-05-20T00:00:00+00:00",
        )
        store.persist_index(entities=entities, relations=relations, metadata=metadata)
    finally:
        store.close()

    return repo_root, db_path


def test_search_symbols_enforces_result_limit(indexed_repo: tuple[Path, Path]) -> None:
    repo_root, db_path = indexed_repo
    response = handle_search_symbols(
        SearchSymbolsRequest(query="core", db_path=str(db_path), limit=999),
        repo_root=repo_root,
    )

    assert len(response.results) <= 100
    assert any(item.code == "search_limit_capped" for item in response.uncertainties)


def test_search_symbols_is_deterministic(indexed_repo: tuple[Path, Path]) -> None:
    repo_root, db_path = indexed_repo
    request = SearchSymbolsRequest(query="run", db_path=str(db_path), limit=10)

    first = handle_search_symbols(request, repo_root=repo_root)
    second = handle_search_symbols(request, repo_root=repo_root)

    assert first == second


def test_build_context_pack_enforces_budget_cap(indexed_repo: tuple[Path, Path]) -> None:
    repo_root, db_path = indexed_repo
    response = handle_build_context_pack(
        BuildContextPackRequest(
            task="Update run behavior",
            db_path=str(db_path),
            budget_chars=999_999,
            profile="agent_standard",
        ),
        repo_root=repo_root,
    )

    assert response.budget.requested_chars == 999_999
    assert any(item.code == "budget_capped" for item in response.uncertainties)


def test_query_graph_is_bounded(indexed_repo: tuple[Path, Path]) -> None:
    repo_root, db_path = indexed_repo
    response = handle_query_graph(
        QueryGraphRequest(
            db_path=str(db_path),
            entity_ids=("python:module:src.core",),
            max_hops=99,
            limit=999,
        ),
        repo_root=repo_root,
    )

    assert len(response.entity_ids) <= 101
    codes = {item.code for item in response.uncertainties}
    assert "graph_depth_capped" in codes
    assert "graph_entity_limit_capped" in codes


def test_export_ai_requires_explicit_output_path() -> None:
    with pytest.raises(ValueError, match="output_dir must be explicitly provided"):
        ExportAiMemoryRequest()


def test_export_ai_writes_only_to_explicit_path(indexed_repo: tuple[Path, Path]) -> None:
    repo_root, db_path = indexed_repo
    output_dir = repo_root / "explicit_ai"

    response = handle_export_ai_memory(
        ExportAiMemoryRequest(db_path=str(db_path), output_dir=str(output_dir), force=True),
        repo_root=repo_root,
    )

    assert "INDEX.yaml" in response.files_written
    assert output_dir.exists()


def test_handlers_reject_paths_outside_repo_root(indexed_repo: tuple[Path, Path]) -> None:
    repo_root, _ = indexed_repo
    outside_db = repo_root.parent / "outside.sqlite"
    outside_db.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="db_path must stay within repo_root"):
        handle_search_symbols(
            SearchSymbolsRequest(query="x", db_path=str(outside_db)),
            repo_root=repo_root,
        )


def test_validate_patch_context_reports_coverage_not_correctness(
    indexed_repo: tuple[Path, Path],
) -> None:
    repo_root, db_path = indexed_repo
    response = handle_validate_patch_context(
        ValidatePatchContextRequest(
            task="Refactor run",
            db_path=str(db_path),
            changed_paths=("src/core.py", "docs/missing.md"),
            referenced_entity_ids=("python:function:src.core.run",),
        ),
        repo_root=repo_root,
    )

    assert response.covered_paths == ("src/core.py",)
    assert response.missing_paths == ("docs/missing.md",)
    assert response.suggested_context_query is not None


def test_get_git_summary_is_graceful_for_non_git_repo(indexed_repo: tuple[Path, Path]) -> None:
    repo_root, _ = indexed_repo
    response = handle_get_git_summary(
        GetGitSummaryRequest(path=str(repo_root)), repo_root=repo_root
    )

    assert response.repository_root is None
    assert any(item.code == "not_in_git_repo" for item in response.uncertainties)


def test_get_git_summary_uses_existing_core_logic(
    monkeypatch: pytest.MonkeyPatch,
    indexed_repo: tuple[Path, Path],
) -> None:
    repo_root, _ = indexed_repo
    called = {"value": False}

    def _fake_summary(path: Path | str) -> GitRepositorySummary:
        called["value"] = True
        return GitRepositorySummary(
            path=str(path),
            in_git_repo=False,
            repository_root=None,
            current_commit=None,
            is_dirty=None,
            tracked_file_count=None,
            unavailable_reason="outside",
        )

    monkeypatch.setattr(
        "repo_semantic_memory.mcp.handlers.get_git_repository_summary", _fake_summary
    )
    response = handle_get_git_summary(
        GetGitSummaryRequest(path=str(repo_root)), repo_root=repo_root
    )

    assert called["value"] is True
    assert response.uncertainties


def test_project_has_no_mcp_runtime_dependency(
    project_root: Path = Path(__file__).resolve().parents[2],
) -> None:
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject.get("project", {}).get("dependencies", [])
    assert all("mcp" not in str(item).lower() for item in dependencies)
