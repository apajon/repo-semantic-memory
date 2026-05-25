"""Tests for store_home/registry.py — IndexRegistry and RegistryEntry."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.store_home.registry import IndexRegistry, RegistryEntry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store_home(tmp_path: Path) -> Path:
    home = tmp_path / "store"
    home.mkdir()
    (home / "indexes").mkdir()
    return home


@pytest.fixture()
def registry(store_home: Path) -> IndexRegistry:
    return IndexRegistry(store_home)


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    repo = tmp_path / "my_repo"
    repo.mkdir()
    return repo


# ---------------------------------------------------------------------------
# lookup / register roundtrip
# ---------------------------------------------------------------------------


def test_lookup_returns_none_for_unknown(registry: IndexRegistry, repo_root: Path) -> None:
    assert registry.lookup(repo_root) is None


def test_register_lookup_roundtrip(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "indexes" / "abc123" / "index.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    registry.register(repo_root, db_path)
    result = registry.lookup(repo_root)
    assert result == db_path


def test_register_external_db_stored_as_absolute(
    registry: IndexRegistry, repo_root: Path, tmp_path: Path
) -> None:
    # DB outside store_home should round-trip as an absolute path.
    external_db = tmp_path / "other" / "index.sqlite"
    external_db.parent.mkdir(parents=True)
    external_db.touch()

    registry.register(repo_root, external_db)
    result = registry.lookup(repo_root)
    assert result == external_db


def test_register_inside_store_stored_as_relative(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    # DB inside store_home should be stored as a relative path in registry.json.
    db_path = store_home / "indexes" / "abc" / "index.sqlite"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    registry.register(repo_root, db_path)

    import json

    raw = json.loads((store_home / "registry.json").read_text(encoding="utf-8"))
    entries = raw["entries"]
    entry = next(iter(entries.values()))
    assert not Path(entry["db"]).is_absolute()
    assert entry["db"] == "indexes/abc/index.sqlite"


# ---------------------------------------------------------------------------
# register metadata
# ---------------------------------------------------------------------------


def test_register_sets_registered_at(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path)

    entries = registry.list_entries()
    key = repo_root.resolve().as_posix()
    assert key in entries
    assert entries[key].registered_at


def test_register_preserves_registered_at_on_update(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path)

    first_ts = registry.list_entries()[repo_root.resolve().as_posix()].registered_at

    # Second register call should not change registered_at.
    registry.register(repo_root, db_path)
    second_ts = registry.list_entries()[repo_root.resolve().as_posix()].registered_at
    assert first_ts == second_ts


def test_register_without_indexed_leaves_last_indexed_at_none(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path, indexed=False)

    entries = registry.list_entries()
    key = repo_root.resolve().as_posix()
    assert entries[key].last_indexed_at is None


def test_register_with_indexed_sets_last_indexed_at(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path, indexed=True)

    entries = registry.list_entries()
    key = repo_root.resolve().as_posix()
    assert entries[key].last_indexed_at is not None


def test_register_indexed_update_advances_last_indexed_at(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    import time

    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path, indexed=True)
    first_ts = registry.list_entries()[repo_root.resolve().as_posix()].last_indexed_at

    time.sleep(0.01)  # ensure a different timestamp

    registry.register(repo_root, db_path, indexed=True)
    second_ts = registry.list_entries()[repo_root.resolve().as_posix()].last_indexed_at
    assert second_ts is not None
    assert first_ts != second_ts


# ---------------------------------------------------------------------------
# unregister
# ---------------------------------------------------------------------------


def test_unregister_returns_true_for_known(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path)
    assert registry.unregister(repo_root) is True


def test_unregister_returns_false_for_unknown(registry: IndexRegistry, repo_root: Path) -> None:
    assert registry.unregister(repo_root) is False


def test_unregister_removes_entry(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path)
    registry.unregister(repo_root)
    assert registry.lookup(repo_root) is None


def test_unregister_does_not_delete_db_file(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path)
    registry.unregister(repo_root)
    assert db_path.exists()


# ---------------------------------------------------------------------------
# list_entries
# ---------------------------------------------------------------------------


def test_list_entries_empty_when_no_registry(registry: IndexRegistry) -> None:
    assert registry.list_entries() == {}


def test_list_entries_sorted(registry: IndexRegistry, tmp_path: Path, store_home: Path) -> None:
    db = store_home / "idx.sqlite"
    db.touch()

    repo_b = (tmp_path / "b_repo").resolve()
    repo_a = (tmp_path / "a_repo").resolve()
    repo_b.mkdir(exist_ok=True)
    repo_a.mkdir(exist_ok=True)

    registry.register(repo_b, db)
    registry.register(repo_a, db)

    keys = list(registry.list_entries().keys())
    assert keys == sorted(keys)


def test_list_entries_returns_registry_entry_objects(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path, indexed=True)

    entries = registry.list_entries()
    assert len(entries) == 1
    entry = next(iter(entries.values()))
    assert isinstance(entry, RegistryEntry)
    assert entry.db_relative
    assert entry.registered_at
    assert entry.last_indexed_at is not None


# ---------------------------------------------------------------------------
# repo_id / default_db_path
# ---------------------------------------------------------------------------


def test_repo_id_is_stable(repo_root: Path) -> None:
    id1 = IndexRegistry.repo_id(repo_root)
    id2 = IndexRegistry.repo_id(repo_root)
    assert id1 == id2
    assert len(id1) == 16
    assert all(c in "0123456789abcdef" for c in id1)


def test_repo_id_differs_for_different_repos(tmp_path: Path) -> None:
    repo_a = (tmp_path / "a").resolve()
    repo_b = (tmp_path / "b").resolve()
    repo_a.mkdir()
    repo_b.mkdir()
    assert IndexRegistry.repo_id(repo_a) != IndexRegistry.repo_id(repo_b)


def test_default_db_path_inside_store_home(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    db = registry.default_db_path(repo_root)
    assert str(db).startswith(str(store_home))
    assert db.name == "index.sqlite"


def test_default_db_path_consistent_with_repo_id(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    repo_id = IndexRegistry.repo_id(repo_root)
    db = registry.default_db_path(repo_root)
    assert repo_id in str(db)


# ---------------------------------------------------------------------------
# atomic write
# ---------------------------------------------------------------------------


def test_save_uses_tmp_file_then_renames(
    registry: IndexRegistry, repo_root: Path, store_home: Path
) -> None:
    # After a successful register(), no .tmp file should remain.
    db_path = store_home / "index.sqlite"
    db_path.touch()
    registry.register(repo_root, db_path)
    tmp_file = store_home / "registry.json.tmp"
    assert not tmp_file.exists()
    assert (store_home / "registry.json").exists()


# ---------------------------------------------------------------------------
# Malformed registry resilience
# ---------------------------------------------------------------------------


def test_load_handles_missing_registry(registry: IndexRegistry) -> None:
    # No registry.json → empty dict, no error.
    entries = registry.list_entries()
    assert entries == {}


def test_load_handles_corrupt_json(store_home: Path) -> None:
    (store_home / "registry.json").write_text("not json", encoding="utf-8")
    reg = IndexRegistry(store_home)
    assert reg.list_entries() == {}


def test_load_handles_wrong_type(store_home: Path) -> None:
    (store_home / "registry.json").write_text("[1, 2, 3]", encoding="utf-8")
    reg = IndexRegistry(store_home)
    assert reg.list_entries() == {}
