"""Tests for store_home/resolution.py — reader DB path resolution."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from repo_semantic_memory.store_home.resolution import (
    ResolvedDb,
    resolve_reader_db,
)

# ---------------------------------------------------------------------------
# Explicit --db
# ---------------------------------------------------------------------------


def test_explicit_db_wins(tmp_path: Path) -> None:
    """Explicit db argument takes priority over everything else."""
    explicit = str(tmp_path / "my.sqlite")
    result = resolve_reader_db(explicit)
    assert result.path == Path(explicit)
    assert result.source == "explicit"


def test_explicit_db_wins_over_index_store(tmp_path: Path) -> None:
    """Explicit db overrides any Index Store entry."""
    store_home = tmp_path / "rsm_home"
    store_home.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    db_in_store = store_home / "indexes" / "test" / "index.sqlite"
    db_in_store.parent.mkdir(parents=True)
    db_in_store.touch()

    from repo_semantic_memory.store_home import IndexRegistry

    IndexRegistry(store_home).register(repo_dir, db_in_store, indexed=True)

    explicit = str(tmp_path / "explicit.sqlite")
    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        result = resolve_reader_db(explicit, cwd=repo_dir)

    assert result.path == Path(explicit)
    assert result.source == "explicit"


# ---------------------------------------------------------------------------
# Index Store entry for CWD
# ---------------------------------------------------------------------------


def test_index_store_entry_wins_over_repo_local(tmp_path: Path) -> None:
    """Registered Index Store entry takes priority over repo-local fallback."""
    store_home = tmp_path / "rsm_home"
    store_home.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    db_path = store_home / "indexes" / "test" / "index.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    from repo_semantic_memory.store_home import IndexRegistry

    IndexRegistry(store_home).register(repo_dir, db_path, indexed=True)

    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        result = resolve_reader_db(None, cwd=repo_dir)

    assert result.path == db_path
    assert result.source == "index_store"


def test_index_store_uses_cwd_when_no_cwd_arg(tmp_path: Path) -> None:
    """When cwd is omitted, Path.cwd() is used for Index Store lookup."""
    store_home = tmp_path / "rsm_home"
    store_home.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    db_path = store_home / "indexes" / "test" / "index.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    from repo_semantic_memory.store_home import IndexRegistry

    IndexRegistry(store_home).register(repo_dir, db_path, indexed=True)

    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        with mock.patch("pathlib.Path.cwd", return_value=repo_dir):
            result = resolve_reader_db(None)

    assert result.path == db_path
    assert result.source == "index_store"


# ---------------------------------------------------------------------------
# Repo-local fallback
# ---------------------------------------------------------------------------


def test_repo_local_fallback_when_no_store_entry(tmp_path: Path) -> None:
    """Falls back to relative .rsm/index.sqlite when no Index Store entry."""
    store_home = tmp_path / "empty_rsm_home"
    store_home.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        result = resolve_reader_db(None, cwd=repo_dir)

    assert result.path == Path(".rsm/index.sqlite")
    assert result.source == "repo_local"


def test_repo_local_fallback_path_is_relative(tmp_path: Path) -> None:
    """The repo-local fallback path is relative for CLI compatibility."""
    store_home = tmp_path / "empty_rsm_home"
    store_home.mkdir()

    with mock.patch.dict(os.environ, {"RSM_HOME": str(store_home)}):
        result = resolve_reader_db(None, cwd=tmp_path / "repo")

    assert not result.path.is_absolute()
    assert str(result.path) == ".rsm/index.sqlite"


# ---------------------------------------------------------------------------
# Index Store lookup errors fall back to repo-local
# ---------------------------------------------------------------------------


def test_import_error_falls_back_to_repo_local(tmp_path: Path) -> None:
    """ImportError during Index Store import falls back to repo-local."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    with mock.patch(
        "repo_semantic_memory.store_home.home.resolve_store_home",
        side_effect=ImportError("no module"),
    ):
        result = resolve_reader_db(None, cwd=repo_dir)

    assert result.path == Path(".rsm/index.sqlite")
    assert result.source == "repo_local"


def test_oserror_falls_back_to_repo_local(tmp_path: Path) -> None:
    """OSError during Index Store lookup falls back to repo-local."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    with mock.patch(
        "repo_semantic_memory.store_home.home.resolve_store_home",
        side_effect=OSError("disk error"),
    ):
        result = resolve_reader_db(None, cwd=repo_dir)

    assert result.path == Path(".rsm/index.sqlite")
    assert result.source == "repo_local"


# ---------------------------------------------------------------------------
# ResolvedDb dataclass
# ---------------------------------------------------------------------------


def test_resolved_db_is_frozen() -> None:
    """ResolvedDb is immutable."""
    r = ResolvedDb(path=Path("test.sqlite"), source="explicit")
    with pytest.raises(AttributeError):
        r.path = Path("other.sqlite")  # type: ignore[misc]


def test_resolved_db_source_field() -> None:
    """ResolvedDb carries the resolution source."""
    r = ResolvedDb(path=Path("a.sqlite"), source="repo_local")
    assert r.source == "repo_local"
    assert isinstance(r.path, Path)


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_public_api_exported_from_store_home() -> None:
    """ResolvedDb and resolve_reader_db are exported from store_home package."""
    from repo_semantic_memory.store_home import ResolvedDb as _RD
    from repo_semantic_memory.store_home import resolve_reader_db as _rr

    assert _RD is ResolvedDb
    assert _rr is resolve_reader_db
