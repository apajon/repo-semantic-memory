"""Shared helpers for incremental indexing parity tests.

This module contains no tests. It builds real temporary Git repositories and
compares full vs incremental indexes while ignoring volatile metadata.
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
# Semantic parity helpers
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
# Index build helpers
# ---------------------------------------------------------------------------


def _full_index(repo: Path, db: Path) -> None:
    rc = main(["index", str(repo), "--db", str(db)])
    assert rc == 0


def _incremental_index(repo: Path, db: Path) -> None:
    rc = main(["index", str(repo), "--db", str(db), "--incremental"])
    assert rc == 0


def _prime_metadata(db: Path, git_head: str, git_dirty: str = "false") -> None:
    """Write git_head/git_dirty metadata into the DB so the planner can proceed."""
    store = SQLiteStore(db)
    store.initialize()
    store.write_extra_metadata({"git_head": git_head, "git_dirty": git_dirty})
    store.close()
