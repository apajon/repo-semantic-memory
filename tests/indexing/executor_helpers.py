"""Shared helpers for incremental executor unit tests.

This module contains no tests. It provides content constants, plan builders,
and index-bootstrap helpers used across the executor test suite.
"""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.cli import main
from repo_semantic_memory.indexing.incremental import IncrementalPlan
from repo_semantic_memory.store import SQLiteStore

# ---------------------------------------------------------------------------
# Content constants
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

# ---------------------------------------------------------------------------
# Index-bootstrap helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Store inspection helpers
# ---------------------------------------------------------------------------


def _entity_qualified_names(store: SQLiteStore) -> set[str]:
    return {e.qualified_name for e in store.list_entities()}


def _relation_kinds(store: SQLiteStore) -> set[str]:
    return {r.kind for r in store.list_relations()}
