"""Non-Python and filesystem executor scenarios for `rsm index --incremental`.

Covers Markdown file updates, non-Python file types, ignored/generated path
filtering, error propagation, and graceful handling of missing paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.indexing.executor import run_incremental_index
from repo_semantic_memory.store import SQLiteStore

from .executor_helpers import (
    _MD_SRC,
    _MD_SRC_UPDATED,
    _PY_SRC,
    _bootstrap_full_index,
    _entity_qualified_names,
    _make_plan,
)


def test_executor_changed_markdown_file_updates_entities(tmp_path: Path) -> None:
    """Changed .md file: old doc entities purged, new ones extracted."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(_MD_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    (repo / "guide.md").write_text(_MD_SRC_UPDATED, encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("guide.md",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True

    store = SQLiteStore(db_path)
    store.initialize()
    qnames = _entity_qualified_names(store)
    store.close()

    assert any("section-two" in q.lower() or "section two" in q.lower() for q in qnames)


def test_executor_skips_changed_paths_excluded_by_full_index_filters(tmp_path: Path) -> None:
    """Incremental extraction skips ignored/generated paths that full rebuild excludes."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "dist").mkdir(parents=True)
    (repo / "src" / "keep.py").write_text("def keep() -> None:\n    pass\n", encoding="utf-8")
    (repo / "dist" / "generated.py").write_text(
        "def generated() -> None:\n    pass\n", encoding="utf-8"
    )

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    plan = _make_plan(repo_root=repo, changed_paths=("dist/generated.py",))
    result = run_incremental_index(repo, db_path, plan)
    assert result.used_incremental is True

    store = SQLiteStore(db_path)
    store.initialize()
    paths = {e.source_range.path for e in store.list_entities()}
    store.close()

    assert "src/keep.py" in paths
    assert "dist/generated.py" not in paths


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


def test_executor_nonexistent_path_skipped_gracefully(tmp_path: Path) -> None:
    """A path listed as changed but not on disk is silently skipped."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    plan = _make_plan(repo_root=repo, changed_paths=("ghost.py",))
    result = run_incremental_index(repo, db_path, plan)

    assert result.used_incremental is True


def test_executor_extraction_error_propagates(tmp_path: Path) -> None:
    """A SyntaxError in a changed .py file propagates, and the DB stays intact."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text(_PY_SRC, encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

    store = SQLiteStore(db_path)
    store.initialize()
    before_ids = {e.id.value for e in store.list_entities()}
    store.close()

    (repo / "mod.py").write_text("def broken(:\n", encoding="utf-8")

    plan = _make_plan(repo_root=repo, changed_paths=("mod.py",))
    with pytest.raises((SyntaxError, ValueError)):
        run_incremental_index(repo, db_path, plan)

    store = SQLiteStore(db_path)
    store.initialize()
    after_ids = {e.id.value for e in store.list_entities()}
    store.close()
    assert before_ids == after_ids, "DB must be unchanged when extraction raises"


# ---------------------------------------------------------------------------
# Dangling relation sweep
# ---------------------------------------------------------------------------


def test_apply_incremental_update_sweeps_incoming_cross_file_relations(tmp_path: Path) -> None:
    """After deleting an entity, any relation pointing at it must be swept."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("class A: pass\n", encoding="utf-8")
    (repo / "b.py").write_text("class B: pass\n", encoding="utf-8")

    db_path = tmp_path / "idx.sqlite"
    _bootstrap_full_index(repo, db_path)

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

    store.apply_incremental_update(
        purge_paths=frozenset({"b.py"}),
        new_entities=[],
        new_relations=[],
        global_recompute_kinds=frozenset(),
        compute_global_relations=lambda e, r: [],
    )

    remaining_relations = store.list_relations()
    store.close()

    for rel in remaining_relations:
        assert rel.kind != "uses", "dangling 'uses' relation must have been removed"
