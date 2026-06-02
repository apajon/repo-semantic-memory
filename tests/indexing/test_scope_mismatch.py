"""Tests for incremental scope mismatch safety (Prompt 57.5.1).

When ``--incremental`` is requested with a scope (includes/excludes) that
differs from the scope stored in the index metadata, RSM must fall back to a
full rebuild with the stable reason ``incremental_scope_mismatch``.

These tests use non-git repos so incremental runs always fall back — but we
can distinguish *which* fallback reason fires first.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.indexing.incremental import IncrementalFallbackReason
from repo_semantic_memory.store import SQLiteStore

from .executor_helpers import _PY_SRC

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_full_index(repo: Path, db_path: Path) -> None:
    """Index *repo* (full scope) and write result to *db_path*."""
    exit_code = main(["index", str(repo), "--db", str(db_path)])
    assert exit_code == 0


def _build_scoped_index(
    repo: Path,
    db_path: Path,
    *,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
) -> None:
    """Index *repo* with scope and write result to *db_path*."""
    cmd = ["index", str(repo), "--db", str(db_path)]
    for pat in includes or []:
        cmd += ["--include", pat]
    for pat in excludes or []:
        cmd += ["--exclude", pat]
    exit_code = main(cmd)
    assert exit_code == 0


def _meta(db_path: Path) -> dict[str, str]:
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        return store.get_metadata()
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Stable reason constant
# ---------------------------------------------------------------------------


def test_fallback_reason_is_stable() -> None:
    """SCOPE_MISMATCH reason string is exactly 'incremental_scope_mismatch'."""
    assert IncrementalFallbackReason.SCOPE_MISMATCH == "incremental_scope_mismatch"


# ---------------------------------------------------------------------------
# full → scoped triggers fallback
# ---------------------------------------------------------------------------


def test_full_to_scoped_incremental_triggers_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A full index followed by ``--incremental --include src/`` triggers scope mismatch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _build_full_index(repo, db_path)
    capsys.readouterr()

    exit_code = main(
        ["index", str(repo), "--db", str(db_path), "--incremental", "--include", "src/"]
    )
    assert exit_code == 0
    err = capsys.readouterr().err
    assert IncrementalFallbackReason.SCOPE_MISMATCH in err


# ---------------------------------------------------------------------------
# scoped → full triggers fallback
# ---------------------------------------------------------------------------


def test_scoped_to_full_incremental_triggers_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A scoped index followed by plain ``--incremental`` triggers scope mismatch."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _build_scoped_index(repo, db_path, includes=["src/"])
    capsys.readouterr()

    # Plain incremental (full scope) against a scoped index.
    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    err = capsys.readouterr().err
    assert IncrementalFallbackReason.SCOPE_MISMATCH in err


# ---------------------------------------------------------------------------
# scoped include changed triggers fallback
# ---------------------------------------------------------------------------


def test_scoped_include_changed_triggers_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Changing the include patterns triggers scope mismatch."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _build_scoped_index(repo, db_path, includes=["src/"])
    capsys.readouterr()

    # Incremental with different includes.
    exit_code = main(
        ["index", str(repo), "--db", str(db_path), "--incremental", "--include", "lib/"]
    )
    assert exit_code == 0
    err = capsys.readouterr().err
    assert IncrementalFallbackReason.SCOPE_MISMATCH in err


# ---------------------------------------------------------------------------
# scoped exclude changed triggers fallback
# ---------------------------------------------------------------------------


def test_scoped_exclude_changed_triggers_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Changing the exclude patterns triggers scope mismatch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _build_scoped_index(repo, db_path, excludes=["tests/"])
    capsys.readouterr()

    # Incremental with different excludes.
    exit_code = main(
        ["index", str(repo), "--db", str(db_path), "--incremental", "--exclude", "docs/"]
    )
    assert exit_code == 0
    err = capsys.readouterr().err
    assert IncrementalFallbackReason.SCOPE_MISMATCH in err


# ---------------------------------------------------------------------------
# same scope → no scope mismatch
# ---------------------------------------------------------------------------


def test_same_full_scope_no_scope_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Full → full incremental does not trigger scope mismatch (may fail for other reasons)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _build_full_index(repo, db_path)
    capsys.readouterr()

    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    err = capsys.readouterr().err
    # Scope mismatch must NOT appear — some other reason may fire (e.g. no git).
    assert IncrementalFallbackReason.SCOPE_MISMATCH not in err


def test_same_scoped_scope_no_scope_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scoped → same scoped incremental does not trigger scope mismatch."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _build_scoped_index(repo, db_path, includes=["src/"], excludes=["tests/"])
    capsys.readouterr()

    exit_code = main(
        [
            "index",
            str(repo),
            "--db",
            str(db_path),
            "--incremental",
            "--include",
            "src/",
            "--exclude",
            "tests/",
        ]
    )
    assert exit_code == 0
    err = capsys.readouterr().err
    assert IncrementalFallbackReason.SCOPE_MISMATCH not in err


# ---------------------------------------------------------------------------
# metadata after rebuild reflects requested scope
# ---------------------------------------------------------------------------


def test_metadata_after_rebuild_reflects_requested_scope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After scope-mismatch fallback to full rebuild, metadata reflects the new scope."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"

    # Start with a scoped index.
    _build_scoped_index(repo, db_path, includes=["src/"])
    capsys.readouterr()

    meta_before = _meta(db_path)
    assert meta_before.get("index_scope") == "scoped"

    # Incremental with full scope triggers mismatch → full rebuild.
    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    capsys.readouterr()

    meta_after = _meta(db_path)
    assert meta_after.get("index_scope") == "full"
    assert json.loads(meta_after.get("include_patterns", "[]")) == []
    assert json.loads(meta_after.get("exclude_patterns", "[]")) == []


def test_metadata_after_rebuild_preserves_new_scoped_patterns(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After scope-mismatch fallback, metadata stores the newly requested patterns."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"

    # Start with a full index.
    _build_full_index(repo, db_path)
    capsys.readouterr()

    # Incremental with a new scoped pattern triggers mismatch → full rebuild.
    exit_code = main(
        ["index", str(repo), "--db", str(db_path), "--incremental", "--exclude", "tests/"]
    )
    assert exit_code == 0
    capsys.readouterr()

    meta_after = _meta(db_path)
    assert meta_after.get("index_scope") == "scoped"
    assert json.loads(meta_after.get("exclude_patterns", "[]")) == ["tests/"]
