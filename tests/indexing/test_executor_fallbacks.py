"""CLI integration and fallback discipline scenarios for `rsm index --incremental`.

Covers --incremental flag behaviour (fall-back to full rebuild, mode suffix in
output) and last_index_mode metadata consistency across full and incremental runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.indexing.incremental import IncrementalPlan
from repo_semantic_memory.store import SQLiteStore

from .executor_helpers import _PY_SRC

# ---------------------------------------------------------------------------
# CLI integration – --incremental flag
# ---------------------------------------------------------------------------


def test_cli_incremental_flag_falls_back_when_no_git(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--incremental with a non-git directory falls back to full rebuild silently."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    exit_code = main(["index", str(repo), "--db", str(db_path)])
    assert exit_code == 0
    capsys.readouterr()

    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    out = capsys.readouterr()
    assert "entities=" in out.out


def test_cli_incremental_flag_without_existing_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--incremental with no prior DB falls through to a full rebuild with a stable reason."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "new.sqlite"
    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    assert db_path.exists()
    out = capsys.readouterr()
    assert "entities=" in out.out
    assert "info: incremental index fallback: incremental_index_missing" in out.err


def test_cli_incremental_mode_suffix_in_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful incremental run includes 'mode=incremental' in stdout."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    main(["index", str(repo), "--db", str(db_path)])
    capsys.readouterr()

    good_plan = IncrementalPlan(
        can_incremental=True,
        fallback_reason=None,
        indexed_head="abc123",
        current_head="def456",
        changed_paths=(),
        deleted_paths=(),
        renamed_paths=(),
        untracked_paths=(),
        dirty_paths=(),
    )
    import repo_semantic_memory.indexing as _idx_pkg

    monkeypatch.setattr(_idx_pkg, "plan_incremental_update", lambda *_a, **_kw: good_plan)

    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "mode=incremental" in out


# ---------------------------------------------------------------------------
# last_index_mode consistency
# ---------------------------------------------------------------------------


def test_full_rebuild_writes_last_index_mode_full(tmp_path: Path) -> None:
    """A full rebuild (no --incremental) writes last_index_mode=full."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    exit_code = main(["index", str(repo), "--db", str(db_path)])
    assert exit_code == 0

    store = SQLiteStore(db_path)
    store.initialize()
    meta = store.get_metadata()
    store.close()

    assert meta.get("last_index_mode") == "full"


def test_incremental_fallback_full_rebuild_writes_last_index_mode_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When --incremental falls back to a full rebuild, last_index_mode=full is written."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    main(["index", str(repo), "--db", str(db_path)])
    capsys.readouterr()

    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    capsys.readouterr()

    store = SQLiteStore(db_path)
    store.initialize()
    meta = store.get_metadata()
    store.close()

    assert meta.get("last_index_mode") == "full"
