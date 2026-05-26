"""Core executor scenarios for `rsm index --incremental`.

Covers SQLiteStore.apply_incremental_update() unit tests and Python-focused
run_incremental_index() scenarios (empty changeset, changed/deleted/renamed
Python files, exports, metadata, entity/relation counts, dangling-relation sweep).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.indexing.executor import run_incremental_index
from repo_semantic_memory.store import SQLiteStore
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, SCHEMA_VERSION

from .executor_helpers import (
    _PY_SRC,
    _PY_SRC_UPDATED,
    _bootstrap_full_index,
    _entity_qualified_names,
    _make_plan,
    _relation_kinds,
)

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
# run_incremental_index – Python-focused executor tests
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

    store = SQLiteStore(db_path)
    store.initialize()
    qnames_before = _entity_qualified_names(store)
    store.close()
    assert any("hello" in q for q in qnames_before)

    (repo / "mod.py").write_text(_PY_SRC_UPDATED, encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("mod.py",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True
    assert result.changed_paths == ("mod.py",)

    store = SQLiteStore(db_path)
    store.initialize()
    qnames_after = _entity_qualified_names(store)
    store.close()

    assert any("goodbye" in q for q in qnames_after)


def test_executor_deleted_python_file_purges_entities(tmp_path: Path) -> None:
    """Deleted .py file: all its entities are removed from the index."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")
    (repo / "other.py").write_text("def other(): pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

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


def test_executor_with_init_py_exports_upserted(tmp_path: Path) -> None:
    """exports relations from __init__.py are upserted on change."""
    repo = tmp_path / "repo"
    pkg = repo / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("from .mod import Foo\n", encoding="utf-8")
    (pkg / "mod.py").write_text("class Foo: pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    (pkg / "__init__.py").write_text("from .mod import Foo, Bar\n", encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("mypkg/__init__.py",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True
    store = SQLiteStore(db_path)
    store.initialize()
    kinds = _relation_kinds(store)
    store.close()
    assert "exports" in kinds


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
