"""Tests for the incremental change-detection planner (Prompt 50.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.indexing.incremental import (
    IncrementalFallbackReason,
    _normalize_path,
    _parse_diff_name_status,
    _parse_status_porcelain,
    plan_incremental_update,
)
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_INDEXED_HEAD = "abc123def456"
_FAKE_CURRENT_HEAD = "deadbeef1234"
_REPO_ROOT = Path("/fake/repo")


def _git_responses(responses: dict[tuple, tuple[str | None, str | None]]):
    """Return a _run_git replacement that maps (args_tuple) -> (stdout, error)."""

    def _fake_run_git(*, cwd: Path, args: tuple) -> tuple[str | None, str | None]:
        del cwd
        return responses.get(args, (None, "unexpected git call"))

    return _fake_run_git


def _make_good_git(
    indexed_head: str = _FAKE_INDEXED_HEAD,
    current_head: str = _FAKE_CURRENT_HEAD,
    diff_out: str = "",
    status_out: str = "",
) -> dict[tuple, tuple[str | None, str | None]]:
    """Build the standard git response dict for a successful plan."""
    return {
        ("rev-parse", "HEAD"): (current_head + "\n", None),
        ("merge-base", "--is-ancestor", indexed_head, current_head): ("", None),
        ("diff", "--name-status", indexed_head, current_head): (diff_out, None),
        ("status", "--porcelain=v1"): (status_out, None),
    }


# ---------------------------------------------------------------------------
# Fallback: no indexed head
# ---------------------------------------------------------------------------


def test_fallback_none_indexed_head(tmp_path: Path) -> None:
    plan = plan_incremental_update(tmp_path, None)
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.NO_INDEXED_HEAD
    assert plan.indexed_head is None
    assert plan.current_head is None


def test_fallback_empty_indexed_head(tmp_path: Path) -> None:
    plan = plan_incremental_update(tmp_path, "")
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.NO_INDEXED_HEAD


# ---------------------------------------------------------------------------
# Fallback: schema / context-pack version mismatch
# ---------------------------------------------------------------------------


def test_fallback_schema_version_mismatch(tmp_path: Path) -> None:
    plan = plan_incremental_update(
        tmp_path,
        _FAKE_INDEXED_HEAD,
        indexed_schema_version="0.0.99",
    )
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.SCHEMA_MISMATCH


def test_no_fallback_schema_version_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git()),
    )
    plan = plan_incremental_update(
        tmp_path,
        _FAKE_INDEXED_HEAD,
        indexed_schema_version=SCHEMA_VERSION,
    )
    assert plan.can_incremental is True
    assert plan.fallback_reason is None


def test_fallback_context_pack_version_mismatch(tmp_path: Path) -> None:
    plan = plan_incremental_update(
        tmp_path,
        _FAKE_INDEXED_HEAD,
        indexed_context_pack_version="0.0.1",
    )
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.CONTEXT_PACK_MISMATCH


def test_no_fallback_context_pack_version_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git()),
    )
    plan = plan_incremental_update(
        tmp_path,
        _FAKE_INDEXED_HEAD,
        indexed_context_pack_version=CONTEXT_PACK_VERSION,
    )
    assert plan.can_incremental is True


# ---------------------------------------------------------------------------
# Fallback: previous index was built dirty
# ---------------------------------------------------------------------------


def test_fallback_previous_dirty(tmp_path: Path) -> None:
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD, indexed_git_dirty="true")
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.PREVIOUS_DIRTY


def test_no_fallback_previous_dirty_false(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git()),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD, indexed_git_dirty="false")
    assert plan.can_incremental is True


def test_no_fallback_previous_dirty_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git()),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD, indexed_git_dirty="")
    assert plan.can_incremental is True


# ---------------------------------------------------------------------------
# Fallback: git unavailable
# ---------------------------------------------------------------------------


def test_fallback_git_unavailable_rev_parse_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses({("rev-parse", "HEAD"): (None, "git executable is not available")}),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.GIT_UNAVAILABLE
    assert plan.current_head is None


def test_fallback_git_unavailable_diff_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = {
        ("rev-parse", "HEAD"): (_FAKE_CURRENT_HEAD + "\n", None),
        ("merge-base", "--is-ancestor", _FAKE_INDEXED_HEAD, _FAKE_CURRENT_HEAD): ("", None),
        ("diff", "--name-status", _FAKE_INDEXED_HEAD, _FAKE_CURRENT_HEAD): (
            None,
            "git diff failed",
        ),
    }
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(responses),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.GIT_UNAVAILABLE


def test_fallback_git_unavailable_status_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = {
        ("rev-parse", "HEAD"): (_FAKE_CURRENT_HEAD + "\n", None),
        ("merge-base", "--is-ancestor", _FAKE_INDEXED_HEAD, _FAKE_CURRENT_HEAD): ("", None),
        ("diff", "--name-status", _FAKE_INDEXED_HEAD, _FAKE_CURRENT_HEAD): ("", None),
        ("status", "--porcelain=v1"): (None, "git status failed"),
    }
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(responses),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.GIT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Fallback: history unreachable
# ---------------------------------------------------------------------------


def test_fallback_history_unreachable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    responses = {
        ("rev-parse", "HEAD"): (_FAKE_CURRENT_HEAD + "\n", None),
        ("merge-base", "--is-ancestor", _FAKE_INDEXED_HEAD, _FAKE_CURRENT_HEAD): (
            None,
            "fatal: Not a valid commit name",
        ),
    }
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(responses),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.HISTORY_UNREACHABLE
    assert plan.current_head == _FAKE_CURRENT_HEAD


# ---------------------------------------------------------------------------
# Fallback: changeset too large
# ---------------------------------------------------------------------------


def test_fallback_changeset_too_large(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Build a diff with 6 added files.
    diff_lines = "\n".join(f"A\tsrc/file{i}.py" for i in range(6))
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_lines)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD, max_changed_paths=5)
    assert plan.can_incremental is False
    assert plan.fallback_reason == IncrementalFallbackReason.CHANGESET_TOO_LARGE


def test_no_fallback_exactly_at_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    diff_lines = "\n".join(f"A\tsrc/file{i}.py" for i in range(5))
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_lines)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD, max_changed_paths=5)
    assert plan.can_incremental is True


# ---------------------------------------------------------------------------
# Successful plan: no changes
# ---------------------------------------------------------------------------


def test_plan_no_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git()),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert plan.fallback_reason is None
    assert plan.indexed_head == _FAKE_INDEXED_HEAD
    assert plan.current_head == _FAKE_CURRENT_HEAD
    assert plan.changed_paths == ()
    assert plan.deleted_paths == ()
    assert plan.renamed_paths == ()
    assert plan.untracked_paths == ()
    assert plan.dirty_paths == ()


# ---------------------------------------------------------------------------
# Successful plan: committed changes via diff
# ---------------------------------------------------------------------------


def test_plan_added_and_modified_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    diff_out = "A\tsrc/new_module.py\nM\tsrc/existing.py\nD\tsrc/old.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert plan.changed_paths == ("src/existing.py", "src/new_module.py")
    assert plan.deleted_paths == ("src/old.py",)
    assert plan.renamed_paths == ()


def test_plan_renamed_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    diff_out = "R090\tsrc/old_name.py\tsrc/new_name.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert plan.changed_paths == ("src/new_name.py",)
    assert plan.deleted_paths == ("src/old_name.py",)
    assert plan.renamed_paths == (("src/old_name.py", "src/new_name.py"),)


def test_plan_copied_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    diff_out = "C090\tsrc/original.py\tsrc/copy.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    # Copied: new path in changed, old path in deleted, NOT in renamed_paths.
    assert plan.changed_paths == ("src/copy.py",)
    assert plan.deleted_paths == ("src/original.py",)
    assert plan.renamed_paths == ()


def test_plan_type_changed_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    diff_out = "T\tsrc/symlink.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert plan.changed_paths == ("src/symlink.py",)


# ---------------------------------------------------------------------------
# Successful plan: working-tree changes
# ---------------------------------------------------------------------------


def test_plan_working_tree_modified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    status_out = " M src/dirty.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(status_out=status_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert "src/dirty.py" in plan.changed_paths
    assert "src/dirty.py" in plan.dirty_paths


def test_plan_working_tree_deleted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    status_out = " D src/gone.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(status_out=status_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert "src/gone.py" in plan.deleted_paths
    assert "src/gone.py" not in plan.changed_paths
    assert "src/gone.py" in plan.dirty_paths


def test_plan_untracked_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    status_out = "?? src/untracked.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(status_out=status_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert "src/untracked.py" in plan.untracked_paths
    assert "src/untracked.py" in plan.changed_paths
    assert "src/untracked.py" not in plan.dirty_paths


# ---------------------------------------------------------------------------
# Deletion takes precedence over change
# ---------------------------------------------------------------------------


def test_wt_deleted_overrides_diff_added(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A file committed as added but deleted in the working tree → deleted."""
    diff_out = "A\tsrc/added_then_deleted.py\n"
    status_out = " D src/added_then_deleted.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_out, status_out=status_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.can_incremental is True
    assert "src/added_then_deleted.py" in plan.deleted_paths
    assert "src/added_then_deleted.py" not in plan.changed_paths


# ---------------------------------------------------------------------------
# Output determinism: sorted tuples
# ---------------------------------------------------------------------------


def test_plan_paths_are_sorted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    diff_out = "A\tsrc/z_last.py\nA\tsrc/a_first.py\nD\tsrc/z_del.py\nD\tsrc/a_del.py\n"
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git(diff_out=diff_out)),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    assert plan.changed_paths == tuple(sorted(plan.changed_paths))
    assert plan.deleted_paths == tuple(sorted(plan.deleted_paths))


# ---------------------------------------------------------------------------
# Plan is frozen / immutable
# ---------------------------------------------------------------------------


def test_plan_is_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "repo_semantic_memory.indexing.incremental._run_git",
        _git_responses(_make_good_git()),
    )
    plan = plan_incremental_update(tmp_path, _FAKE_INDEXED_HEAD)
    with pytest.raises((AttributeError, TypeError)):
        plan.can_incremental = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _parse_diff_name_status unit tests
# ---------------------------------------------------------------------------


def test_parse_diff_added() -> None:
    changed, deleted, renamed = _parse_diff_name_status("A\tsrc/new.py\n")
    assert "src/new.py" in changed
    assert not deleted
    assert not renamed


def test_parse_diff_deleted() -> None:
    changed, deleted, renamed = _parse_diff_name_status("D\tsrc/old.py\n")
    assert "src/old.py" in deleted
    assert not changed


def test_parse_diff_modified() -> None:
    changed, deleted, renamed = _parse_diff_name_status("M\tsrc/mod.py\n")
    assert "src/mod.py" in changed


def test_parse_diff_renamed() -> None:
    changed, deleted, renamed = _parse_diff_name_status("R100\tsrc/old.py\tsrc/new.py\n")
    assert "src/old.py" in deleted
    assert "src/new.py" in changed
    assert renamed == [("src/old.py", "src/new.py")]


def test_parse_diff_copied() -> None:
    changed, deleted, renamed = _parse_diff_name_status("C100\tsrc/orig.py\tsrc/copy.py\n")
    assert "src/orig.py" in deleted
    assert "src/copy.py" in changed
    assert not renamed  # C does not produce renamed entries


def test_parse_diff_type_changed() -> None:
    changed, deleted, renamed = _parse_diff_name_status("T\tsrc/link.py\n")
    assert "src/link.py" in changed


def test_parse_diff_multiple_entries() -> None:
    output = "A\tsrc/a.py\nM\tsrc/b.py\nD\tsrc/c.py\nR090\tsrc/d_old.py\tsrc/d_new.py\n"
    changed, deleted, renamed = _parse_diff_name_status(output)
    assert "src/a.py" in changed
    assert "src/b.py" in changed
    assert "src/d_new.py" in changed
    assert "src/c.py" in deleted
    assert "src/d_old.py" in deleted
    assert renamed == [("src/d_old.py", "src/d_new.py")]


def test_parse_diff_empty() -> None:
    changed, deleted, renamed = _parse_diff_name_status("")
    assert not changed
    assert not deleted
    assert not renamed


def test_parse_diff_normalizes_backslashes() -> None:
    changed, deleted, _ = _parse_diff_name_status("A\tsrc\\new.py\n")
    assert "src/new.py" in changed


# ---------------------------------------------------------------------------
# _parse_status_porcelain unit tests
# ---------------------------------------------------------------------------


def test_parse_status_untracked() -> None:
    wt_mod, wt_del, untracked = _parse_status_porcelain("?? src/untracked.py\n")
    assert "src/untracked.py" in untracked
    assert not wt_mod
    assert not wt_del


def test_parse_status_modified_unstaged() -> None:
    wt_mod, wt_del, untracked = _parse_status_porcelain(" M src/mod.py\n")
    assert "src/mod.py" in wt_mod
    assert not wt_del


def test_parse_status_modified_staged() -> None:
    wt_mod, wt_del, untracked = _parse_status_porcelain("M  src/staged.py\n")
    assert "src/staged.py" in wt_mod


def test_parse_status_deleted_unstaged() -> None:
    wt_mod, wt_del, untracked = _parse_status_porcelain(" D src/deleted.py\n")
    assert "src/deleted.py" in wt_del
    assert not wt_mod


def test_parse_status_deleted_staged() -> None:
    wt_mod, wt_del, untracked = _parse_status_porcelain("D  src/staged_del.py\n")
    assert "src/staged_del.py" in wt_del


def test_parse_status_rename_format() -> None:
    # Porcelain v1 rename: "R  old -> new"
    wt_mod, wt_del, untracked = _parse_status_porcelain("R  src/old.py -> src/new.py\n")
    assert "src/old.py" in wt_del
    assert "src/new.py" in wt_mod


def test_parse_status_ignored_skipped() -> None:
    wt_mod, wt_del, untracked = _parse_status_porcelain("!! dist/output.py\n")
    assert not wt_mod
    assert not wt_del
    assert not untracked


def test_parse_status_mixed() -> None:
    output = "?? docs/untracked.md\n M src/dirty.py\n D src/gone.py\nM  src/staged.py\n"
    wt_mod, wt_del, untracked = _parse_status_porcelain(output)
    assert "docs/untracked.md" in untracked
    assert "src/dirty.py" in wt_mod
    assert "src/staged.py" in wt_mod
    assert "src/gone.py" in wt_del


def test_parse_status_empty() -> None:
    wt_mod, wt_del, untracked = _parse_status_porcelain("")
    assert not wt_mod
    assert not wt_del
    assert not untracked


# ---------------------------------------------------------------------------
# _normalize_path
# ---------------------------------------------------------------------------


def test_normalize_path_forward_slashes() -> None:
    assert _normalize_path("src/foo.py") == "src/foo.py"


def test_normalize_path_backslashes() -> None:
    assert _normalize_path("src\\foo.py") == "src/foo.py"


def test_normalize_path_strips_whitespace() -> None:
    assert _normalize_path("  src/foo.py  ") == "src/foo.py"


# ---------------------------------------------------------------------------
# IncrementalFallbackReason constants are stable strings
# ---------------------------------------------------------------------------


def test_fallback_reason_constants_are_stable() -> None:
    assert IncrementalFallbackReason.NO_INDEXED_HEAD == "incremental_no_indexed_head"
    assert IncrementalFallbackReason.GIT_UNAVAILABLE == "incremental_git_unavailable"
    assert IncrementalFallbackReason.SCHEMA_MISMATCH == "incremental_schema_mismatch"
    assert IncrementalFallbackReason.CONTEXT_PACK_MISMATCH == "incremental_context_pack_mismatch"
    assert IncrementalFallbackReason.HISTORY_UNREACHABLE == "incremental_history_unreachable"
    assert IncrementalFallbackReason.PREVIOUS_DIRTY == "incremental_previous_dirty"
    assert IncrementalFallbackReason.CHANGESET_TOO_LARGE == "incremental_changeset_too_large"
    assert IncrementalFallbackReason.INTERNAL_ERROR == "incremental_internal_error"
