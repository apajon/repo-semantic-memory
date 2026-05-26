"""Non-Python and filesystem parity scenarios for `rsm index --incremental`.

These tests compare an incremental update against a fresh full rebuild for
Markdown, mixed Python/Markdown, and multi-file filesystem changes.
"""

from __future__ import annotations

from pathlib import Path

from .parity_helpers import (
    _MD_A,
    _MD_A_UPDATED,
    _PY_A,
    _PY_A_EXTRA_SYMBOL,
    _PY_B,
    _PY_C,
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
    _prime_metadata(db_inc, head0)

    (repo / "README.md").write_text(_MD_A_UPDATED, encoding="utf-8")
    _commit_all(repo)
    _prime_metadata(db_inc, head0)

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
    _prime_metadata(db_inc, head0)

    # Multiple changes at once.
    (repo / "mod_a.py").write_text(_PY_A_EXTRA_SYMBOL, encoding="utf-8")
    (repo / "mod_b.py").unlink()
    (repo / "mod_c.py").write_text(_PY_C, encoding="utf-8")
    (repo / "README.md").write_text(_MD_A_UPDATED, encoding="utf-8")
    _commit_all(repo)
    _prime_metadata(db_inc, head0)

    _incremental_index(repo, db_inc)
    _no_dangling_relations(db_inc)

    db_full = tmp_path / "full.sqlite"
    _full_index(repo, db_full)
    _assert_parity(db_inc, db_full)
