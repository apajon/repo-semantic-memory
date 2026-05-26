"""Tests for the incremental index executor (Prompt 50.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.cli import main
from repo_semantic_memory.indexing.executor import run_incremental_index
from repo_semantic_memory.indexing.incremental import IncrementalPlan
from repo_semantic_memory.store import SQLiteStore
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_PY_SRC = """\
def hello() -> str:
    return "hello"
"""

_PY_SRC_UPDATED = """\
def hello() -> str:
    return "world"

def goodbye() -> str:
    return "goodbye"
"""

_MD_SRC = """\
# Guide

## Section One

Content here.
"""

_MD_SRC_UPDATED = """\
# Guide

## Section One

Updated content.

## Section Two

New section.
"""

_FAKE_HEAD_A = "aaaaaaaaaaaa"
_FAKE_HEAD_B = "bbbbbbbbbbbb"


def _bootstrap_full_index(repo_root: Path, db_path: Path) -> None:
    """Run a full ``rsm index`` on *repo_root* and store result in *db_path*."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    exit_code = main(["index", str(repo_root), "--db", str(db_path)])
    assert exit_code == 0


def _make_plan(
    *,
    repo_root: Path,
    indexed_head: str = _FAKE_HEAD_A,
    changed_paths: tuple[str, ...] = (),
    deleted_paths: tuple[str, ...] = (),
    renamed_paths: tuple[tuple[str, str], ...] = (),
) -> IncrementalPlan:
    """Build a can_incremental=True plan with explicit path sets."""
    return IncrementalPlan(
        can_incremental=True,
        fallback_reason=None,
        indexed_head=indexed_head,
        current_head=_FAKE_HEAD_B,
        changed_paths=changed_paths,
        deleted_paths=deleted_paths,
        renamed_paths=renamed_paths,
        untracked_paths=(),
        dirty_paths=(),
    )


def _entity_qualified_names(store: SQLiteStore) -> set[str]:
    return {e.qualified_name for e in store.list_entities()}


def _relation_kinds(store: SQLiteStore) -> set[str]:
    return {r.kind for r in store.list_relations()}


# ---------------------------------------------------------------------------
# apply_incremental_update – unit tests on the store helper
# ---------------------------------------------------------------------------


def test_store_apply_incremental_update_empty_changeset(tmp_path: Path) -> None:
    """Empty purge + empty new content leaves existing entities/relations intact."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    store = SQLiteStore(db_path)
    store.initialize()
    before_entities = store.list_entities()
    before_relations = store.list_relations()

    entity_count, relation_count = store.apply_incremental_update(
        purge_paths=frozenset(),
        new_entities=[],
        new_relations=[],
        global_recompute_kinds=frozenset(),
        compute_global_relations=lambda e, r: [],
    )
    store.close()

    assert entity_count == len(before_entities)
    assert relation_count == len(before_relations)


def test_store_apply_incremental_update_purges_entities_by_path(tmp_path: Path) -> None:
    """Entities whose source_range.path is in purge_paths are removed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
    (repo / "b.py").write_text("def bar(): pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    store = SQLiteStore(db_path)
    store.initialize()
    entity_count, _ = store.apply_incremental_update(
        purge_paths=frozenset({"a.py"}),
        new_entities=[],
        new_relations=[],
        global_recompute_kinds=frozenset(),
        compute_global_relations=lambda e, r: [],
    )
    remaining_paths = {e.source_range.path for e in store.list_entities()}
    store.close()

    assert "a.py" not in remaining_paths
    assert "b.py" in remaining_paths


def test_store_apply_incremental_update_purges_source_relations(tmp_path: Path) -> None:
    """Relations whose source_id is in a purged entity are removed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("class A: pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    store = SQLiteStore(db_path)
    store.initialize()
    # contains relation(module → class) should exist
    before = [r for r in store.list_relations() if r.kind == "contains"]
    assert before, "expected contains relations before purge"

    store.apply_incremental_update(
        purge_paths=frozenset({"a.py"}),
        new_entities=[],
        new_relations=[],
        global_recompute_kinds=frozenset(),
        compute_global_relations=lambda e, r: [],
    )
    after = [r for r in store.list_relations() if r.kind == "contains"]
    store.close()

    # All contains relations from a.py should be gone (nothing else in the repo).
    assert after == []


def test_store_apply_incremental_update_global_recompute_kinds_purged(tmp_path: Path) -> None:
    """Global-recompute kinds are purged before the callback runs."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Manually insert a dummy "tests" relation so we can confirm it disappears.
    store = SQLiteStore(db_path)
    store.initialize()
    conn = store._conn
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO relations(source_id, target_id, kind, evidence_json, metadata_json) "
        "VALUES('fake_src', 'fake_tgt', 'tests', NULL, '{}')"
    )
    conn.execute("COMMIT")

    call_count = 0

    def _global(_entities: list, _relations: list) -> list:
        nonlocal call_count
        call_count += 1
        return []

    store.apply_incremental_update(
        purge_paths=frozenset(),
        new_entities=[],
        new_relations=[],
        global_recompute_kinds=frozenset({"tests"}),
        compute_global_relations=_global,
    )
    tests_after = [r for r in store.list_relations() if r.kind == "tests"]
    store.close()

    assert tests_after == [], "dummy tests relation should have been purged"
    assert call_count == 1, "compute_global_relations should be called once"


def test_store_apply_incremental_update_rolls_back_on_error(tmp_path: Path) -> None:
    """A failure inside the callback rolls back the transaction."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("def foo(): pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    store = SQLiteStore(db_path)
    store.initialize()
    before = store.list_entities()

    def _bad_callback(_entities: list, _relations: list) -> list:
        raise RuntimeError("deliberate failure")

    with pytest.raises(RuntimeError, match="deliberate failure"):
        store.apply_incremental_update(
            purge_paths=frozenset({"a.py"}),
            new_entities=[],
            new_relations=[],
            global_recompute_kinds=frozenset(),
            compute_global_relations=_bad_callback,
        )

    after = store.list_entities()
    store.close()
    # Transaction should have been rolled back; index is unchanged.
    assert {e.id.value for e in before} == {e.id.value for e in after}


# ---------------------------------------------------------------------------
# run_incremental_index – end-to-end executor tests
# ---------------------------------------------------------------------------


def test_executor_empty_changeset_leaves_index_intact(tmp_path: Path) -> None:
    """An incremental run with no changed/deleted paths produces an equivalent index."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    store = SQLiteStore(db_path)
    store.initialize()
    before_qnames = _entity_qualified_names(store)
    before_kinds = _relation_kinds(store)
    store.close()

    plan = _make_plan(repo_root=repo)
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True
    assert result.fallback_reason is None
    assert result.changed_paths == ()
    assert result.deleted_paths == ()

    store = SQLiteStore(db_path)
    store.initialize()
    after_qnames = _entity_qualified_names(store)
    after_kinds = _relation_kinds(store)
    store.close()

    assert before_qnames == after_qnames
    assert before_kinds == after_kinds


def test_executor_changed_python_file_updates_entities(tmp_path: Path) -> None:
    """Changed .py file: old entities purged, new entities upserted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Verify original state has "hello" function
    store = SQLiteStore(db_path)
    store.initialize()
    qnames_before = _entity_qualified_names(store)
    store.close()
    assert any("hello" in q for q in qnames_before)

    # Update the file on disk.
    (repo / "mod.py").write_text(_PY_SRC_UPDATED, encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("mod.py",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True
    assert result.changed_paths == ("mod.py",)

    store = SQLiteStore(db_path)
    store.initialize()
    qnames_after = _entity_qualified_names(store)
    store.close()

    # "goodbye" function should be present; all qnames from mod.py should be fresh.
    assert any("goodbye" in q for q in qnames_after)


def test_executor_deleted_python_file_purges_entities(tmp_path: Path) -> None:
    """Deleted .py file: all its entities are removed from the index."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")
    (repo / "other.py").write_text("def other(): pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Delete the file from disk.
    (repo / "mod.py").unlink()

    plan = _make_plan(repo_root=repo, deleted_paths=("mod.py",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True
    assert result.deleted_paths == ("mod.py",)

    store = SQLiteStore(db_path)
    store.initialize()
    remaining_paths = {e.source_range.path for e in store.list_entities()}
    store.close()

    assert "mod.py" not in remaining_paths
    assert "other.py" in remaining_paths


def test_executor_renamed_python_file_purges_old_upserts_new(tmp_path: Path) -> None:
    """Renamed .py file: old path purged, new path extracted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "old.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Simulate rename by removing old and creating new.
    (repo / "old.py").unlink()
    (repo / "new.py").write_text(_PY_SRC, encoding="utf-8")

    plan = _make_plan(
        repo_root=repo,
        changed_paths=("new.py",),
        deleted_paths=("old.py",),
        renamed_paths=(("old.py", "new.py"),),
    )
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True

    store = SQLiteStore(db_path)
    store.initialize()
    paths = {e.source_range.path for e in store.list_entities()}
    store.close()

    assert "old.py" not in paths
    assert "new.py" in paths


def test_executor_changed_markdown_file_updates_entities(tmp_path: Path) -> None:
    """Changed .md file: old doc entities purged, new ones extracted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(_MD_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Update on disk.
    (repo / "guide.md").write_text(_MD_SRC_UPDATED, encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("guide.md",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True

    store = SQLiteStore(db_path)
    store.initialize()
    qnames = _entity_qualified_names(store)
    store.close()

    # New section "Section Two" heading should appear.
    assert any("section-two" in q.lower() or "section two" in q.lower() for q in qnames)


def test_executor_changed_non_py_non_md_file(tmp_path: Path) -> None:
    """Changed .yaml file: filesystem entity is refreshed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config.yaml").write_text("key: value\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    (repo / "config.yaml").write_text("key: new_value\nextra: yes\n", encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("config.yaml",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True
    store = SQLiteStore(db_path)
    store.initialize()
    paths = {e.source_range.path for e in store.list_entities()}
    store.close()
    assert "config.yaml" in paths


def test_executor_metadata_written_with_last_index_mode(tmp_path: Path) -> None:
    """After a successful incremental run, last_index_mode=incremental is persisted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    plan = _make_plan(repo_root=repo)
    run_incremental_index(repo, db_path, plan)

    store = SQLiteStore(db_path)
    store.initialize()
    meta = store.get_metadata()
    store.close()

    assert meta.get("last_index_mode") == "incremental"
    assert meta.get("entity_count") is not None
    assert meta.get("relation_count") is not None
    assert meta.get("schema_version") == SCHEMA_VERSION
    assert meta.get("context_pack_version") == CONTEXT_PACK_VERSION


def test_executor_entity_and_relation_counts_accurate(tmp_path: Path) -> None:
    """IncrementalResult.entity_count and relation_count match the actual DB state."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("class A: pass\n", encoding="utf-8")
    (repo / "b.py").write_text("class B: pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    plan = _make_plan(repo_root=repo)
    result = run_incremental_index(repo, db_path, plan)

    store = SQLiteStore(db_path)
    store.initialize()
    actual_entities = len(store.list_entities())
    actual_relations = len(store.list_relations())
    store.close()

    assert result.entity_count == actual_entities
    assert result.relation_count == actual_relations


def test_executor_extraction_error_propagates(tmp_path: Path) -> None:
    """A SyntaxError in a changed .py file propagates, and the DB stays intact."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Record the entity IDs before the failure.
    store = SQLiteStore(db_path)
    store.initialize()
    before_ids = {e.id.value for e in store.list_entities()}
    store.close()

    # Write invalid Python.
    (repo / "mod.py").write_text("def broken(:\n", encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("mod.py",))
    with pytest.raises((SyntaxError, ValueError)):
        run_incremental_index(repo, db_path, plan)

    # Extraction runs before the transaction opens, so the DB must be unchanged.
    store = SQLiteStore(db_path)
    store.initialize()
    after_ids = {e.id.value for e in store.list_entities()}
    store.close()
    assert before_ids == after_ids, "DB must be unchanged when extraction raises"


def test_executor_nonexistent_path_skipped_gracefully(tmp_path: Path) -> None:
    """A path listed as changed but not on disk is silently skipped."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # "ghost.py" does not exist on disk.
    plan = _make_plan(repo_root=repo, changed_paths=("ghost.py",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True


def test_executor_with_init_py_exports_upserted(tmp_path: Path) -> None:
    """exports relations from __init__.py are upserted on change."""
    repo = tmp_path / "repo"
    pkg = repo / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from .mod import Foo\n", encoding="utf-8")
    (pkg / "mod.py").write_text("class Foo: pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Update __init__.py
    (pkg / "__init__.py").write_text("from .mod import Foo, Bar\n", encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("mypkg/__init__.py",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True
    store = SQLiteStore(db_path)
    store.initialize()
    kinds = _relation_kinds(store)
    store.close()
    assert "exports" in kinds


def test_executor_result_is_frozen_dataclass(tmp_path: Path) -> None:
    """IncrementalResult is a frozen dataclass (immutable)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    plan = _make_plan(repo_root=repo)
    result = run_incremental_index(repo, db_path, plan)

    with pytest.raises((TypeError, AttributeError)):
        result.used_incremental = False  # type: ignore[misc]


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
    # First, bootstrap a full index (no --incremental).
    exit_code = main(["index", str(repo), "--db", str(db_path)])
    assert exit_code == 0
    capsys.readouterr()  # discard

    # Second run: --incremental on a non-git dir → should fall back to full rebuild.
    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    out = capsys.readouterr()
    # Fallback message goes to stderr; index still succeeds.
    assert "entities=" in out.out


def test_cli_incremental_flag_without_existing_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--incremental with no prior DB falls through to a full rebuild."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "new.sqlite"
    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    assert db_path.exists()
    out = capsys.readouterr()
    assert "entities=" in out.out


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

    # Inject a valid incremental plan via monkeypatching the planner so we
    # don't need a real git repo in CI.
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
    # plan_incremental_update is imported lazily from the indexing package
    # inside _attempt_incremental_index, so we patch the package-level attribute.
    import repo_semantic_memory.indexing as _idx_pkg

    monkeypatch.setattr(_idx_pkg, "plan_incremental_update", lambda *_a, **_kw: good_plan)

    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "mode=incremental" in out


# ---------------------------------------------------------------------------
# Dangling relation sweep
# ---------------------------------------------------------------------------


def test_apply_incremental_update_sweeps_incoming_cross_file_relations(tmp_path: Path) -> None:
    """After deleting an entity, any relation pointing at it must be swept."""
    repo = tmp_path / "repo"
    repo.mkdir()
    # a.py stays; b.py will be deleted.
    (repo / "a.py").write_text("class A: pass\n", encoding="utf-8")
    (repo / "b.py").write_text("class B: pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    # Manually inject a cross-file relation A → B (simulates e.g. an imports/tests rel).
    store = SQLiteStore(db_path)
    store.initialize()
    all_entities = store.list_entities()
    non_b_entities = [e for e in all_entities if "b.py" not in (e.source_range.path or "")]
    b_entities = [e for e in all_entities if "b.py" in (e.source_range.path or "")]
    assert non_b_entities, "expected at least one entity from a.py"
    assert b_entities, "expected at least one entity from b.py"

    conn = store._conn
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO relations(source_id, target_id, kind, evidence_json, metadata_json) "
        "VALUES(?, ?, 'uses', NULL, '{}')",
        (non_b_entities[0].id.value, b_entities[0].id.value),
    )
    conn.execute("COMMIT")

    # Now delete b.py's entities via incremental update (empty re-extract set).
    store.apply_incremental_update(
        purge_paths=frozenset({"b.py"}),
        new_entities=[],
        new_relations=[],
        global_recompute_kinds=frozenset(),
        compute_global_relations=lambda e, r: [],
    )

    remaining_relations = store.list_relations()
    store.close()

    # The incoming "uses" relation targeting the deleted B entity must be swept.
    for rel in remaining_relations:
        assert rel.kind != "uses", "dangling 'uses' relation must have been removed"


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
    # First full index.
    main(["index", str(repo), "--db", str(db_path)])
    capsys.readouterr()

    # Second run with --incremental in a non-git dir (planner falls back).
    exit_code = main(["index", str(repo), "--db", str(db_path), "--incremental"])
    assert exit_code == 0
    capsys.readouterr()

    store = SQLiteStore(db_path)
    store.initialize()
    meta = store.get_metadata()
    store.close()

    assert meta.get("last_index_mode") == "full"
