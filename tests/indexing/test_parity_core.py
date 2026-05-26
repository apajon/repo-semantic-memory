"""Core semantic parity scenarios for `rsm index --incremental`.

These tests compare an incremental update against a fresh full rebuild on the
same Git working tree.  Covers Python source-code scenarios, idempotency, and
Index Store --register composition.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.store import SQLiteStore

from .parity_helpers import (
    _INIT_PY,
    _INIT_PY_EMPTY,
    _PY_A,
    _PY_A_EXTRA_SYMBOL,
    _PY_A_UPDATED_BODY,
    _PY_B,
    _assert_parity,
    _commit_all,
    _full_index,
    _incremental_index,
    _no_dangling_relations,
    _prime_metadata,
    _setup_git_repo,
    _skip_if_no_git,
)

# ---------------------------------------------------------------------------
# Parity scenario: no changes since last index
# ---------------------------------------------------------------------------


def test_parity_no_changes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Incremental index with no changes is identical to the prior full index."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")

    head = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    _prime_metadata(db_inc, head)

    capsys.readouterr()
    _incremental_index(repo, db_inc)
    captured = capsys.readouterr()

    # No fallback message — incremental path was taken.
    assert "mode=incremental" in captured.out, (
        "Expected 'mode=incremental' in stdout; maybe incremental fell back: " + captured.err
    )
    assert "Traceback" not in captured.err, "No traceback expected for clean incremental"

    # Parity against a fresh full rebuild.
    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: modified Python body (same symbols)
# ---------------------------------------------------------------------------


def test_parity_modified_python_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Incremental update after a body-only Python change produces parity."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    _prime_metadata(db_inc, head0)

    # Modify the body without changing the symbol shape.
    (repo / "mod_a.py").write_text(_PY_A_UPDATED_BODY, encoding="utf-8")
    head1 = _commit_all(repo)
    _prime_metadata(db_inc, head0)

    capsys.readouterr()
    _incremental_index(repo, db_inc)
    captured = capsys.readouterr()
    assert "mode=incremental" in captured.out, "Incremental should have been taken: " + captured.err
    _ = head1  # used implicitly via git diff

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: added Python symbol in an existing file
# ---------------------------------------------------------------------------


def test_parity_added_symbol_in_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Incremental update after adding a symbol to an existing file produces parity."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    _prime_metadata(db_inc, head0)

    # Add a new symbol.
    (repo / "mod_a.py").write_text(_PY_A_EXTRA_SYMBOL, encoding="utf-8")
    _commit_all(repo)
    _prime_metadata(db_inc, head0)

    _incremental_index(repo, db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: added new Python file
# ---------------------------------------------------------------------------


def test_parity_added_python_file(tmp_path: Path) -> None:
    """Incremental update after adding a new Python file produces parity."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    _prime_metadata(db_inc, head0)

    # Add a new file.
    (repo / "mod_b.py").write_text(_PY_B, encoding="utf-8")
    _commit_all(repo)
    _prime_metadata(db_inc, head0)

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: deleted Python file (no dangling relations)
# ---------------------------------------------------------------------------


def test_parity_deleted_python_file(tmp_path: Path) -> None:
    """Incremental update after deleting a Python file leaves no dangling relations."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    (repo / "mod_b.py").write_text(_PY_B, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    _prime_metadata(db_inc, head0)

    # Delete one file.
    (repo / "mod_b.py").unlink()
    _commit_all(repo)
    _prime_metadata(db_inc, head0)

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: renamed Python file (no dangling relations)
# ---------------------------------------------------------------------------


def test_parity_renamed_python_file(tmp_path: Path) -> None:
    """Incremental update after renaming a Python file leaves no dangling relations."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    _prime_metadata(db_inc, head0)

    # Rename the file.
    (repo / "mod_a.py").rename(repo / "module_alpha.py")
    _commit_all(repo)
    _prime_metadata(db_inc, head0)

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: exports (PublicAPI) after __init__.py change
# ---------------------------------------------------------------------------


def test_parity_exports_recomputed_after_init_change(tmp_path: Path) -> None:
    """Incremental update recomputes exports/PublicAPI after __init__.py changes."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    pkg = repo / "mypkg"
    pkg.mkdir()
    (pkg / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    (pkg / "__init__.py").write_text(_INIT_PY, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    _prime_metadata(db_inc, head0)

    # Update __init__.py to remove the export.
    (pkg / "__init__.py").write_text(_INIT_PY_EMPTY, encoding="utf-8")
    _commit_all(repo)
    _prime_metadata(db_inc, head0)

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Idempotency: two incremental runs on the same committed state are identical
# ---------------------------------------------------------------------------


def test_incremental_idempotent(tmp_path: Path) -> None:
    """Two incremental runs on the same committed state produce equal indexes."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db = tmp_path / "db.sqlite"
    _full_index(repo, db)
    _prime_metadata(db, head0)

    (repo / "mod_a.py").write_text(_PY_A_UPDATED_BODY, encoding="utf-8")
    _commit_all(repo)
    _prime_metadata(db, head0)

    # First incremental run.
    _incremental_index(repo, db)
    store = SQLiteStore(db)
    store.initialize()
    meta1 = store.get_metadata()
    ents1 = {e.id.value for e in store.list_entities()}
    rels1 = {
        (r.source_entity_id.value, r.target_entity_id.value, r.kind) for r in store.list_relations()
    }
    head1 = meta1.get("git_head", "")
    store.close()

    # Second incremental run on the same state (no new changes).
    _prime_metadata(db, head1 or head0)
    _incremental_index(repo, db)

    store = SQLiteStore(db)
    store.initialize()
    ents2 = {e.id.value for e in store.list_entities()}
    rels2 = {
        (r.source_entity_id.value, r.target_entity_id.value, r.kind) for r in store.list_relations()
    }
    store.close()

    assert ents1 == ents2, "Entities must be stable across idempotent incremental runs"
    assert rels1 == rels2, "Relations must be stable across idempotent incremental runs"


# ---------------------------------------------------------------------------
# Index Store mode: --register --incremental composes correctly
# ---------------------------------------------------------------------------


def test_incremental_composes_with_register(tmp_path: Path) -> None:
    """``--register --incremental`` composes; falls back cleanly when no git."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_A, encoding="utf-8")

    env_key = "RSM_HOME"
    original = os.environ.get(env_key)
    store_home = tmp_path / "rsm_home"
    store_home.mkdir()
    os.environ[env_key] = str(store_home)
    try:
        db = tmp_path / "idx.sqlite"
        # Full index with --register to set up the registry.
        rc = main(["index", str(repo), "--db", str(db), "--register"])
        assert rc == 0

        # Incremental with --register (no git → falls back to full rebuild).
        rc = main(["index", str(repo), "--db", str(db), "--register", "--incremental"])
        assert rc == 0

        # Registry must still be valid after the fallback.
        from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

        reg = IndexRegistry(resolve_store_home())
        entry = reg.lookup(repo)
        assert entry is not None, "Registry entry must survive fallback"
    finally:
        if original is None:
            del os.environ[env_key]
        else:
            os.environ[env_key] = original
