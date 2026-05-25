"""Tests for the rsm store CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.model import Entity, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata
from repo_semantic_memory.store_home import IndexRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_indexed_db(db_path: Path, repo_root: Path) -> None:
    """Create a minimal valid SQLite index at db_path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    entities = [
        Entity(
            id=StableId("file:src/core.py"),
            kind="file",
            name="core.py",
            qualified_name="src/core.py",
            source_range=SourceRange(path="src/core.py", start_line=1, end_line=1),
        )
    ]
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        store.persist_index(
            entities=entities,
            relations=[],
            metadata=build_default_extraction_metadata(
                repository_root=repo_root,
                extractor_names=("filesystem",),
                timestamp="2026-05-24T00:00:00+00:00",
            ),
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# rsm store path
# ---------------------------------------------------------------------------


def test_store_path_prints_store_home(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    custom = tmp_path / "my_store"
    with mock.patch.dict("os.environ", {"RSM_HOME": str(custom)}):
        code = main(["store", "path"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert str(custom) == out


# ---------------------------------------------------------------------------
# rsm store list
# ---------------------------------------------------------------------------


def test_store_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "list"])
    assert code == 0
    out = capsys.readouterr().out
    assert "No repositories" in out


def test_store_list_shows_registered_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        registry = IndexRegistry(store_home)
        store_home.mkdir(parents=True, exist_ok=True)
        (store_home / "indexes").mkdir(exist_ok=True)
        db_path = registry.default_db_path(repo)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch()
        registry.register(repo, db_path)

        code = main(["store", "list"])
    assert code == 0
    out = capsys.readouterr().out
    assert str(repo.resolve()) in out


def test_store_list_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        store_home.mkdir(parents=True, exist_ok=True)
        (store_home / "indexes").mkdir(exist_ok=True)
        registry = IndexRegistry(store_home)
        db_path = registry.default_db_path(repo)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch()
        registry.register(repo, db_path)

        code = main(["store", "list", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, dict)
    assert str(repo.resolve()) in payload


# ---------------------------------------------------------------------------
# rsm store register
# ---------------------------------------------------------------------------


def test_store_register_creates_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "register", str(repo)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Registered" in out

    # Verify the registry actually has the entry.
    registry = IndexRegistry(store_home)
    assert registry.lookup(repo) is not None


def test_store_register_note_when_index_not_built(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "register", str(repo)])
    assert code == 0
    out = capsys.readouterr().out
    # When DB doesn't exist yet, a note should mention building the index.
    assert "Note" in out or "index" in out.lower()


def test_store_register_index_builds_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "core.py").write_text("def run():\n    pass\n", encoding="utf-8")

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "register", str(repo), "--index"])
    assert code == 0

    # DB should now exist at the canonical store path.
    registry = IndexRegistry(store_home)
    db_path = registry.lookup(repo)
    assert db_path is not None
    assert db_path.exists()


def test_store_register_index_updates_last_indexed_at(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        main(["store", "register", str(repo), "--index"])
        registry = IndexRegistry(store_home)
        entries = registry.list_entries()
    key = repo.resolve().as_posix()
    assert key in entries
    assert entries[key].last_indexed_at is not None


def test_store_register_invalid_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "register", str(tmp_path / "nonexistent")])
    assert code == 2
    assert "does not exist" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# rsm store unregister
# ---------------------------------------------------------------------------


def test_store_unregister_removes_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        main(["store", "register", str(repo)])
        code = main(["store", "unregister", str(repo)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Unregistered" in out

    registry = IndexRegistry(store_home)
    assert registry.lookup(repo) is None


def test_store_unregister_missing_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "unregister", str(repo)])
    assert code == 2
    assert "no entry" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# rsm store db
# ---------------------------------------------------------------------------


def test_store_db_prints_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        main(["store", "register", str(repo)])
        code = main(["store", "db", str(repo)])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("index.sqlite")


def test_store_db_missing_returns_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "db", str(repo)])
    assert code == 2
    assert "no entry" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# rsm index --register
# ---------------------------------------------------------------------------


def test_index_register_flag_writes_to_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = repo / ".rsm" / "index.sqlite"

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["index", str(repo), "--db", str(db_path), "--register"])
    assert code == 0

    registry = IndexRegistry(store_home)
    result = registry.lookup(repo)
    assert result is not None
    assert result == db_path.resolve()


def test_index_register_without_db_uses_store_canonical_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """rsm index <repo> --register with no --db writes to the RSM Index Store path."""
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["index", str(repo), "--register"])
    assert code == 0

    registry = IndexRegistry(store_home)
    result = registry.lookup(repo)
    # DB must exist in the store, not in the repo's .rsm/ directory.
    assert result is not None
    assert result.exists()
    assert str(store_home) in str(result), "DB should be inside the RSM Index Store"
    assert not str(result).startswith(str(repo)), "DB must NOT be in the repo directory"
    assert result.name == "index.sqlite"


def test_index_without_register_flag_does_not_write_to_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_home = tmp_path / "store"
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = repo / ".rsm" / "index.sqlite"

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["index", str(repo), "--db", str(db_path)])
    assert code == 0

    registry = IndexRegistry(store_home)
    assert registry.lookup(repo) is None
