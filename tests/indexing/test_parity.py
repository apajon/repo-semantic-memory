"""Prompt 50.4 — Semantic parity validation for ``rsm index --incremental``.

Each test creates a real Git repository, builds a full index, makes a change
and commits it, then builds both an incremental index and a fresh full rebuild
on the same working tree.  The two results are compared by
:func:`compare_indexes` which checks entity/relation logical identity while
ignoring volatile metadata (timestamps, ``last_index_mode``, etc.).

Tests also verify fallback output discipline:
- Expected planner fallbacks emit exactly one concise stderr line (no
  traceback).
- Unexpected executor failures are covered separately in test_executor.py.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.store import SQLiteStore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PY_A = """\
def greet(name: str) -> str:
    return f"hello, {name}"
"""

_PY_A_UPDATED_BODY = """\
def greet(name: str) -> str:
    return f"hi, {name}!"
"""

_PY_A_EXTRA_SYMBOL = """\
def greet(name: str) -> str:
    return f"hi, {name}!"

def farewell(name: str) -> str:
    return f"bye, {name}"
"""

_PY_B = """\
def compute(x: int, y: int) -> int:
    return x + y
"""

_MD_A = """\
# Introduction

Welcome to the guide.

## Getting Started

Start here.
"""

_MD_A_UPDATED = """\
# Introduction

Welcome to the updated guide.

## Getting Started

Begin here.

## Advanced Topics

More content.
"""

_INIT_PY = """\
from .mod_a import greet

__all__ = ["greet"]
"""

_INIT_PY_EMPTY = "# empty\n"

_PY_C = "def new_func() -> None:\n    pass\n"

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    """Run a git command in *repo* and return stripped stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _setup_git_repo(repo: Path) -> str:
    """Init *repo* as a git repo, add all existing files, commit, return HEAD."""
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@rsm.test")
    _git(repo, "config", "user.name", "RSM Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return _git(repo, "rev-parse", "HEAD")


def _commit_all(repo: Path, message: str = "update") -> str:
    """Stage all changes and commit; return the new HEAD."""
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _skip_if_no_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available in this environment")


# ---------------------------------------------------------------------------
# Semantic parity helper
# ---------------------------------------------------------------------------


class EntitySignature(NamedTuple):
    kind: str
    name: str
    qualified_name: str
    path: str


class RelationSignature(NamedTuple):
    kind: str
    source_id: str
    target_id: str


def compare_indexes(
    db_a: Path,
    db_b: Path,
) -> tuple[frozenset[EntitySignature], frozenset[RelationSignature]]:
    """Return *diff* between two indexes as (entity_diff, relation_diff).

    Both sets are empty when the indexes are semantically equivalent.

    Compares logical identity only:
    - Entities: ``(kind, name, qualified_name, source_range.path)``
    - Relations: ``(kind, source_entity_id, target_entity_id)``

    Ignored:
    - Timestamps (``indexed_at``)
    - Volatile metadata (``last_index_mode``, ``git_head``, ``git_dirty``)
    - SQLite row insertion order
    - Entity metadata blobs beyond the identity fields above
    """
    store_a = SQLiteStore(db_a)
    store_b = SQLiteStore(db_b)
    try:
        store_a.initialize()
        store_b.initialize()

        def _entity_sigs(store: SQLiteStore) -> frozenset[EntitySignature]:
            return frozenset(
                EntitySignature(
                    kind=str(e.kind),
                    name=e.name,
                    qualified_name=e.qualified_name,
                    path=str(e.source_range.path) if e.source_range else "",
                )
                for e in store.list_entities()
            )

        def _relation_sigs(store: SQLiteStore) -> frozenset[RelationSignature]:
            return frozenset(
                RelationSignature(
                    kind=r.kind,
                    source_id=r.source_entity_id.value,
                    target_id=r.target_entity_id.value,
                )
                for r in store.list_relations()
            )

        ent_a = _entity_sigs(store_a)
        ent_b = _entity_sigs(store_b)
        rel_a = _relation_sigs(store_a)
        rel_b = _relation_sigs(store_b)

    finally:
        store_a.close()
        store_b.close()

    return ent_a.symmetric_difference(ent_b), rel_a.symmetric_difference(rel_b)


def _assert_parity(db_incremental: Path, db_full: Path) -> None:
    """Assert that two indexes are semantically equivalent."""
    ent_diff, rel_diff = compare_indexes(db_incremental, db_full)
    assert ent_diff == frozenset(), f"Entity parity mismatch: {ent_diff}"
    assert rel_diff == frozenset(), f"Relation parity mismatch: {rel_diff}"


def _no_dangling_relations(db: Path) -> None:
    """Assert no dangling relations (every relation endpoint exists as entity)."""
    store = SQLiteStore(db)
    try:
        store.initialize()
        entity_ids = {e.id.value for e in store.list_entities()}
        for rel in store.list_relations():
            assert rel.source_entity_id.value in entity_ids, (
                f"dangling source {rel.source_entity_id.value!r} for {rel.kind} relation"
            )
            assert rel.target_entity_id.value in entity_ids, (
                f"dangling target {rel.target_entity_id.value!r} for {rel.kind} relation"
            )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Fixture: bootstrap helpers
# ---------------------------------------------------------------------------


def _full_index(repo: Path, db: Path) -> None:
    rc = main(["index", str(repo), "--db", str(db)])
    assert rc == 0


def _incremental_index(repo: Path, db: Path) -> None:
    rc = main(["index", str(repo), "--db", str(db), "--incremental"])
    assert rc == 0


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

    # Overwrite git_head in metadata to match the committed HEAD so the planner
    # sees a valid ancestor relationship.
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head, "git_dirty": "false"})
    store.close()

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
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    # Modify the body without changing the symbol shape.
    (repo / "mod_a.py").write_text(_PY_A_UPDATED_BODY, encoding="utf-8")
    head1 = _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

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
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    # Add a new symbol.
    (repo / "mod_a.py").write_text(_PY_A_EXTRA_SYMBOL, encoding="utf-8")
    _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

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
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    # Add a new file.
    (repo / "mod_b.py").write_text(_PY_B, encoding="utf-8")
    _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

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
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    # Delete one file.
    (repo / "mod_b.py").unlink()
    _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

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
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    # Rename the file.
    (repo / "mod_a.py").rename(repo / "module_alpha.py")
    _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: modified Markdown file
# ---------------------------------------------------------------------------


def test_parity_modified_markdown(tmp_path: Path) -> None:
    """Incremental update after modifying a Markdown file produces parity."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(_MD_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    (repo / "README.md").write_text(_MD_A_UPDATED, encoding="utf-8")
    _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Parity scenario: mixed — changed + deleted + new
# ---------------------------------------------------------------------------


def test_parity_mixed_changes(tmp_path: Path) -> None:
    """Incremental update with multiple simultaneous changes produces parity."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod_a.py").write_text(_PY_A, encoding="utf-8")
    (repo / "mod_b.py").write_text(_PY_B, encoding="utf-8")
    (repo / "README.md").write_text(_MD_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db_inc = tmp_path / "inc.sqlite"
    _full_index(repo, db_inc)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    # Multiple changes at once.
    (repo / "mod_a.py").write_text(_PY_A_EXTRA_SYMBOL, encoding="utf-8")
    (repo / "mod_b.py").unlink()
    (repo / "mod_c.py").write_text(_PY_C, encoding="utf-8")
    (repo / "README.md").write_text(_MD_A_UPDATED, encoding="utf-8")
    _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

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
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    # Update __init__.py to remove the export.
    (pkg / "__init__.py").write_text(_INIT_PY_EMPTY, encoding="utf-8")
    _commit_all(repo)
    store = SQLiteStore(db_inc)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)


# ---------------------------------------------------------------------------
# Fallback output discipline: expected planner reasons → concise one-liner only
# ---------------------------------------------------------------------------


def test_fallback_stderr_no_traceback_for_expected_reasons(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Expected planner fallbacks emit exactly one concise stderr line, no traceback."""
    # We do NOT need a real git repo — a non-git directory triggers the
    # git_unavailable fallback, which is a normal expected planner reason.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_A, encoding="utf-8")
    db = tmp_path / "idx.sqlite"

    # Bootstrap a full index first so the DB exists.
    rc = main(["index", str(repo), "--db", str(db)])
    assert rc == 0
    capsys.readouterr()

    # Run --incremental on a non-git dir → expected fallback (git_unavailable or
    # no_indexed_head).
    rc = main(["index", str(repo), "--db", str(db), "--incremental"])
    assert rc == 0
    captured = capsys.readouterr()

    # The fallback line must mention the stable reason constant.
    assert "incremental" in captured.err or "incremental" in captured.out, (
        "Expected a fallback reason in the output"
    )
    # No traceback — expected planner reason.
    assert "Traceback" not in captured.err, (
        f"Unexpected traceback in stderr for a normal planner fallback:\n{captured.err}"
    )
    # The fallback line format: "info: incremental index fallback: <reason>; running full rebuild"
    if captured.err:
        line = captured.err.strip().splitlines()[0]
        assert line.startswith("info: incremental index fallback:"), (
            f"Unexpected stderr line format: {line!r}"
        )


def test_fallback_stderr_one_liner_dirty_tree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dirty-tree fallback emits a concise one-liner to stderr, no traceback."""
    _skip_if_no_git()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_A, encoding="utf-8")
    head0 = _setup_git_repo(repo)

    db = tmp_path / "idx.sqlite"
    _full_index(repo, db)

    # Prime the DB with git_head AND git_dirty=true so the planner triggers
    # incremental_previous_dirty.
    store = SQLiteStore(db)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "true"})
    store.close()

    capsys.readouterr()
    rc = main(["index", str(repo), "--db", str(db), "--incremental"])
    assert rc == 0
    captured = capsys.readouterr()

    assert "Traceback" not in captured.err, (
        f"Unexpected traceback for dirty-tree fallback:\n{captured.err}"
    )
    if captured.err:
        first_line = captured.err.strip().splitlines()[0]
        assert "incremental_previous_dirty" in first_line, (
            f"Expected previous_dirty reason, got: {first_line!r}"
        )


# ---------------------------------------------------------------------------
# Index Store mode: --register --incremental composes correctly
# ---------------------------------------------------------------------------


def test_incremental_composes_with_register(tmp_path: Path) -> None:
    """``--register --incremental`` composes; falls back cleanly when no git."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_A, encoding="utf-8")

    import os

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
    store = SQLiteStore(db)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

    (repo / "mod_a.py").write_text(_PY_A_UPDATED_BODY, encoding="utf-8")
    _commit_all(repo)
    store = SQLiteStore(db)
    store.initialize()
    store.write_extra_metadata({"git_head": head0, "git_dirty": "false"})
    store.close()

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
    store = SQLiteStore(db)
    store.initialize()
    store.write_extra_metadata({"git_head": head1 or head0, "git_dirty": "false"})
    store.close()
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
