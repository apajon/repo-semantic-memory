"""Incremental change-detection and planning for ``rsm index --incremental``.

Pure read-only analysis layer: does not modify the SQLite index, does not
change CLI or MCP behavior, and has no side-effects beyond bounded local Git
subprocess calls.  The :class:`IncrementalPlan` it produces will be consumed by
the executor.

The executor lives in :mod:`repo_semantic_memory.indexing.executor` and applies
safe plans transactionally.

All Git calls delegate to the existing
:func:`~repo_semantic_memory.extractors.git_history._run_git` helper
(local-only, bounded, no network).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repo_semantic_memory.extractors.git_history import _run_git
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, SCHEMA_VERSION


class IncrementalFallbackReason:
    """Stable string constants for :attr:`IncrementalPlan.fallback_reason`.

    These strings are emitted in fallback diagnostics on stderr and in any future
    JSON status output that wraps incremental runs.  They are distinct from
    :class:`~repo_semantic_memory.index_status.IndexStatusReason` constants
    (which describe staleness, not incremental planning) and **must not be
    renamed after release**.
    """

    INDEX_MISSING: str = "incremental_index_missing"
    NO_INDEXED_HEAD: str = "incremental_no_indexed_head"
    GIT_UNAVAILABLE: str = "incremental_git_unavailable"
    SCHEMA_MISMATCH: str = "incremental_schema_mismatch"
    CONTEXT_PACK_MISMATCH: str = "incremental_context_pack_mismatch"
    HISTORY_UNREACHABLE: str = "incremental_history_unreachable"
    PREVIOUS_DIRTY: str = "incremental_previous_dirty"
    CHANGESET_TOO_LARGE: str = "incremental_changeset_too_large"
    INTERNAL_ERROR: str = "incremental_internal_error"
    SCOPE_MISMATCH: str = "incremental_scope_mismatch"


@dataclass(frozen=True)
class IncrementalPlan:
    """Result of the incremental change-detection pass.

    When ``can_incremental`` is ``False``, ``fallback_reason`` contains one of
    the stable strings from :class:`IncrementalFallbackReason`.  The executor
    must perform a full rebuild in that case.

    All path fields contain repo-relative paths normalised to forward slashes
    and are stored in sorted tuples for deterministic output.

    Attributes:
        can_incremental: Whether a safe incremental update is possible.
        fallback_reason: Stable reason string when ``can_incremental`` is
            ``False``; ``None`` when ``can_incremental`` is ``True``.
        indexed_head: The ``git_head`` stored in the index at the time of
            planning (may be ``None`` or empty when the index has no HEAD).
        current_head: The current ``HEAD`` SHA; ``None`` when git is
            unavailable or the fallback fires before the HEAD query.
        changed_paths: Repo-relative paths of files that exist on disk and
            need re-extraction.  Includes committed changes (``git diff``
            output) plus working-tree modifications and untracked files.
        deleted_paths: Repo-relative paths of files that no longer exist and
            whose index entries must be purged.
        renamed_paths: ``(old_path, new_path)`` pairs for ``R``-status entries
            in ``git diff --name-status``.  The old path is also in
            ``deleted_paths``; the new path is also in ``changed_paths``.
        untracked_paths: Repo-relative paths of untracked files that fall
            within indexed roles (``??`` entries in ``git status``).
        dirty_paths: Repo-relative paths with any working-tree modification
            (modified, added, or deleted in the working tree, excluding
            untracked).  Informational; the executor uses ``changed_paths`` and
            ``deleted_paths`` for its purge/re-extract logic.
    """

    can_incremental: bool
    fallback_reason: str | None
    indexed_head: str | None
    current_head: str | None
    changed_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]
    renamed_paths: tuple[tuple[str, str], ...]
    untracked_paths: tuple[str, ...]
    dirty_paths: tuple[str, ...]


def plan_incremental_update(
    repo_root: Path,
    indexed_head: str | None,
    *,
    indexed_git_dirty: str | None = None,
    indexed_schema_version: str | None = None,
    indexed_context_pack_version: str | None = None,
    max_changed_paths: int = 500,
) -> IncrementalPlan:
    """Compute a pure change-detection plan for incremental indexing.

    All Git calls are local-only and bounded; no network access.  Returns an
    :class:`IncrementalPlan` with ``can_incremental=False`` and a stable
    :class:`IncrementalFallbackReason` whenever a safe incremental update
    cannot be guaranteed.  **Never modifies the index.**

    Args:
        repo_root: Absolute path to the repository working tree.
        indexed_head: The ``git_head`` value stored when the index was last
            built (from ``metadata.git_head``).  ``None`` or empty triggers
            the :attr:`~IncrementalFallbackReason.NO_INDEXED_HEAD` fallback.
        indexed_git_dirty: The ``git_dirty`` string stored in the index
            metadata (``"true"``, ``"false"``, or ``""``).  ``"true"``
            triggers the :attr:`~IncrementalFallbackReason.PREVIOUS_DIRTY`
            fallback because the prior index may not reflect a clean commit.
        indexed_schema_version: The ``schema_version`` string stored in the
            index metadata.  A mismatch against the runtime constant triggers
            :attr:`~IncrementalFallbackReason.SCHEMA_MISMATCH`.
        indexed_context_pack_version: The ``context_pack_version`` stored in
            the index metadata.  A mismatch triggers
            :attr:`~IncrementalFallbackReason.CONTEXT_PACK_MISMATCH`.
        max_changed_paths: Maximum total number of changed + deleted paths
            before the :attr:`~IncrementalFallbackReason.CHANGESET_TOO_LARGE`
            fallback fires.  Defaults to 500.

    Returns:
        An :class:`IncrementalPlan` with ``can_incremental`` indicating
        whether a safe incremental update is possible.
    """
    # 1. Validate indexed_head before any subprocess call.
    if not indexed_head:
        return _make_fallback(IncrementalFallbackReason.NO_INDEXED_HEAD, indexed_head=indexed_head)

    # 2. Schema / context-pack version checks (skipped when not provided by caller).
    if indexed_schema_version is not None and indexed_schema_version != SCHEMA_VERSION:
        return _make_fallback(IncrementalFallbackReason.SCHEMA_MISMATCH, indexed_head=indexed_head)
    if (
        indexed_context_pack_version is not None
        and indexed_context_pack_version != CONTEXT_PACK_VERSION
    ):
        return _make_fallback(
            IncrementalFallbackReason.CONTEXT_PACK_MISMATCH, indexed_head=indexed_head
        )

    # 3. Previous index was built against a dirty working tree.
    if indexed_git_dirty == "true":
        return _make_fallback(IncrementalFallbackReason.PREVIOUS_DIRTY, indexed_head=indexed_head)

    # 4. Get current HEAD.
    current_head_raw, head_err = _run_git(cwd=repo_root, args=("rev-parse", "HEAD"))
    if current_head_raw is None or head_err is not None:
        return _make_fallback(IncrementalFallbackReason.GIT_UNAVAILABLE, indexed_head=indexed_head)
    current_head = current_head_raw.strip()

    # 5. Verify indexed HEAD is an ancestor of current HEAD.
    #    git merge-base --is-ancestor exits 0 when true, non-zero otherwise.
    _, ancestor_err = _run_git(
        cwd=repo_root,
        args=("merge-base", "--is-ancestor", indexed_head, current_head),
    )
    if ancestor_err is not None:
        return _make_fallback(
            IncrementalFallbackReason.HISTORY_UNREACHABLE,
            indexed_head=indexed_head,
            current_head=current_head,
        )

    # 6. Collect committed changes since indexed_head via git diff.
    diff_out, diff_err = _run_git(
        cwd=repo_root,
        args=("diff", "--name-status", indexed_head, current_head),
    )
    if diff_out is None or diff_err is not None:
        return _make_fallback(
            IncrementalFallbackReason.GIT_UNAVAILABLE,
            indexed_head=indexed_head,
            current_head=current_head,
        )

    # 7. Collect working-tree changes (uncommitted modifications and untracked files).
    status_out, status_err = _run_git(
        cwd=repo_root,
        args=("status", "--porcelain=v1"),
    )
    if status_out is None or status_err is not None:
        return _make_fallback(
            IncrementalFallbackReason.GIT_UNAVAILABLE,
            indexed_head=indexed_head,
            current_head=current_head,
        )

    # 8. Parse change sets.
    diff_changed, diff_deleted, renamed = _parse_diff_name_status(diff_out)
    wt_modified, wt_deleted, untracked = _parse_status_porcelain(status_out)

    # Merge: deletions take precedence (a file deleted in the working tree is
    # not re-extracted regardless of what diff shows).
    all_deleted = diff_deleted | wt_deleted
    all_changed = (diff_changed | wt_modified | untracked) - all_deleted
    # dirty_paths = all working-tree changes (modified + deleted, not untracked).
    dirty = wt_modified | wt_deleted

    # 9. Changeset size guard.
    if len(all_changed) + len(all_deleted) > max_changed_paths:
        return _make_fallback(
            IncrementalFallbackReason.CHANGESET_TOO_LARGE,
            indexed_head=indexed_head,
            current_head=current_head,
        )

    return IncrementalPlan(
        can_incremental=True,
        fallback_reason=None,
        indexed_head=indexed_head,
        current_head=current_head,
        changed_paths=tuple(sorted(all_changed)),
        deleted_paths=tuple(sorted(all_deleted)),
        renamed_paths=tuple(sorted(renamed)),
        untracked_paths=tuple(sorted(untracked)),
        dirty_paths=tuple(sorted(dirty)),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_fallback(
    reason: str,
    *,
    indexed_head: str | None = None,
    current_head: str | None = None,
) -> IncrementalPlan:
    """Return a no-op :class:`IncrementalPlan` with ``can_incremental=False``."""
    return IncrementalPlan(
        can_incremental=False,
        fallback_reason=reason,
        indexed_head=indexed_head,
        current_head=current_head,
        changed_paths=(),
        deleted_paths=(),
        renamed_paths=(),
        untracked_paths=(),
        dirty_paths=(),
    )


def _normalize_path(path: str) -> str:
    """Normalise a repo-relative path to forward slashes and strip whitespace."""
    return path.strip().replace("\\", "/")


def _parse_diff_name_status(
    output: str,
) -> tuple[set[str], set[str], list[tuple[str, str]]]:
    """Parse ``git diff --name-status`` output.

    Returns ``(changed, deleted, renamed)`` where:

    - *changed* — paths that need re-extraction (statuses ``A``, ``M``, ``T``,
      the new-path side of ``R`` entries, and the new-path side of ``C`` entries).
    - *deleted* — paths that need purging (status ``D`` and the old-path side
      of ``R`` entries only; the source of a ``C`` copy is **not** deleted).
    - *renamed* — ``(old_path, new_path)`` pairs for ``R``-status entries only.

    ``Cxxx old new`` (file copy): only the *new* destination is added to
    *changed*.  The *old* source is **not** added to *deleted* because the
    original file still exists in the tree.

    All paths are normalised to forward slashes.
    """
    changed: set[str] = set()
    deleted: set[str] = set()
    renamed: list[tuple[str, str]] = []

    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0].upper()

        if status == "D":
            deleted.add(_normalize_path(parts[1]))
        elif status.startswith("R"):
            if len(parts) >= 3:
                old = _normalize_path(parts[1])
                new = _normalize_path(parts[2])
                deleted.add(old)
                changed.add(new)
                renamed.append((old, new))
        elif status.startswith("C"):
            # Copy: destination is new content to index; source is unchanged.
            if len(parts) >= 3:
                new = _normalize_path(parts[2])
                changed.add(new)
        elif status in ("A", "M", "T"):
            changed.add(_normalize_path(parts[1]))
        else:
            # Unknown status: treat conservatively as changed.
            if len(parts) >= 2 and parts[1]:
                changed.add(_normalize_path(parts[1]))

    return changed, deleted, renamed


def _parse_status_porcelain(
    output: str,
) -> tuple[set[str], set[str], set[str]]:
    """Parse ``git status --porcelain=v1`` output.

    Returns ``(wt_modified, wt_deleted, untracked)`` as sets of repo-relative
    paths normalised to forward slashes:

    - *wt_modified* — paths with any working-tree modification that are not
      classified as deleted or untracked.
    - *wt_deleted* — paths deleted in the working tree (``Y == 'D'``) or
      staged for deletion (``X == 'D'``).
    - *untracked* — untracked paths (``XY == "??"``).

    Porcelain v1 rename entries (``R  old -> new``) produce entries for both
    the old path (*wt_deleted*) and the new path (*wt_modified*).
    """
    wt_modified: set[str] = set()
    wt_deleted: set[str] = set()
    untracked: set[str] = set()

    for line in output.splitlines():
        if len(line) < 3:
            continue
        xy = line[:2]
        remainder = line[3:]

        if xy == "??":
            untracked.add(_normalize_path(remainder))
            continue
        if xy == "!!":
            # Ignored file — skip.
            continue

        # Handle porcelain v1 rename format: "R  old -> new" or "RM old -> new".
        if " -> " in remainder:
            old, _, new = remainder.partition(" -> ")
            wt_deleted.add(_normalize_path(old))
            wt_modified.add(_normalize_path(new))
            continue

        path = _normalize_path(remainder)
        index_status = xy[0]
        wt_status = xy[1]

        if wt_status == "D" or index_status == "D":
            wt_deleted.add(path)
        else:
            wt_modified.add(path)

    return wt_modified, wt_deleted, untracked
