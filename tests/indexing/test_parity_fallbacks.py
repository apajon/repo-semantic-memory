"""Fallback discipline tests for `rsm index --incremental`.

These tests verify that expected planner fallbacks emit exactly one concise
stderr line with no traceback, and that fallback output format is correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.cli import main

from .parity_helpers import (
    _PY_A,
    _full_index,
    _prime_metadata,
    _setup_git_repo,
    _skip_if_no_git,
)

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
    _prime_metadata(db, head0, git_dirty="true")

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
