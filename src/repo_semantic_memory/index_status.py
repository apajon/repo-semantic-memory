"""Index staleness detection for RSM.

Provides a compact, deterministic status for a resolved index database:
  fresh | missing | stale | maybe_stale | schema_mismatch | unknown

Precedence (highest wins): schema_mismatch > missing > stale > maybe_stale >
unknown > fresh.

Detection is local-only: no network, no remote Git.
Policy is report-only: this module never auto-rebuilds an index.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from repo_semantic_memory.extractors.git_history import get_git_repository_summary
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, SCHEMA_VERSION


class IndexStatus(StrEnum):
    """Public status enum for a resolved index database."""

    FRESH = "fresh"
    MISSING = "missing"
    STALE = "stale"
    MAYBE_STALE = "maybe_stale"
    SCHEMA_MISMATCH = "schema_mismatch"
    UNKNOWN = "unknown"


class IndexStatusReason:
    """Stable string constants for ``IndexStatusReport.index_status_reason``.

    These strings are emitted in JSON payloads and checked by tests; they must
    not be renamed once released.
    """

    OK = "ok"
    UNREGISTERED = "unregistered"
    REGISTERED_DB_MISSING = "registered_db_missing"
    EXPLICIT_DB_MISSING = "explicit_db_missing"
    METADATA_INCOMPLETE = "metadata_incomplete"
    SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"
    CONTEXT_PACK_VERSION_MISMATCH = "context_pack_version_mismatch"
    GIT_HEAD_CHANGED = "git_head_changed"
    WORKING_TREE_DIRTY = "working_tree_dirty"
    GIT_UNAVAILABLE = "git_unavailable"


@dataclass(frozen=True)
class IndexStatusReport:
    """Immutable result of a staleness detection pass."""

    index_status: IndexStatus
    index_status_reason: str
    repo_root: Path
    db_path: Path | None
    index_mode: Literal["explicit_db", "store"]
    indexed_at: str | None
    indexed_git_head: str | None
    current_git_head: str | None
    working_tree_dirty: bool | None
    schema_version: str | None
    context_pack_version: str | None
    suggested_action: str | None


def detect_index_status(
    *,
    repo_root: Path,
    db_path: Path | None,
    index_mode: Literal["explicit_db", "store"],
) -> IndexStatusReport:
    """Return a staleness report for the given repo / db combination.

    Opens the SQLite DB when it exists to read metadata.  Returns immediately
    for missing-DB and unregistered cases without touching disk beyond the
    existence check.

    Args:
        repo_root: Absolute path to the repository root.
        db_path: Absolute path to the index SQLite file, or ``None`` when the
            Index Store has no entry for the repo (store mode, unregistered).
        index_mode: ``"explicit_db"`` when the user provided ``--db``; ``"store"``
            when the path was resolved from the Index Store registry.
    """
    # ------------------------------------------------------------------ #
    # 1. Missing DB
    # ------------------------------------------------------------------ #
    if db_path is None:
        # Only reachable in store mode when the repo is not registered.
        return _report(
            status=IndexStatus.MISSING,
            reason=IndexStatusReason.UNREGISTERED,
            repo_root=repo_root,
            db_path=None,
            index_mode=index_mode,
            metadata={},
            current_git_head=None,
            working_tree_dirty=None,
            suggested_action=_suggest(
                index_mode=index_mode,
                repo_root=repo_root,
                db_path=None,
                status=IndexStatus.MISSING,
                reason=IndexStatusReason.UNREGISTERED,
            ),
        )

    if not db_path.is_file():
        reason = (
            IndexStatusReason.REGISTERED_DB_MISSING
            if index_mode == "store"
            else IndexStatusReason.EXPLICIT_DB_MISSING
        )
        return _report(
            status=IndexStatus.MISSING,
            reason=reason,
            repo_root=repo_root,
            db_path=db_path,
            index_mode=index_mode,
            metadata={},
            current_git_head=None,
            working_tree_dirty=None,
            suggested_action=_suggest(
                index_mode=index_mode,
                repo_root=repo_root,
                db_path=db_path,
                status=IndexStatus.MISSING,
                reason=reason,
            ),
        )

    # ------------------------------------------------------------------ #
    # 2. DB exists — open and read metadata
    # ------------------------------------------------------------------ #
    schema_mismatch = False
    metadata: dict[str, str] = {}

    # Import here to avoid a circular dependency at module level: cli.py
    # imports both index_status and the store, and the store imports version.
    from repo_semantic_memory.store import SQLiteStore  # noqa: PLC0415

    store = SQLiteStore(db_path)
    try:
        try:
            store.initialize()
        except ValueError:
            schema_mismatch = True
        if not schema_mismatch:
            metadata = store.get_metadata()
    finally:
        store.close()

    if schema_mismatch:
        return _report(
            status=IndexStatus.SCHEMA_MISMATCH,
            reason=IndexStatusReason.SCHEMA_VERSION_MISMATCH,
            repo_root=repo_root,
            db_path=db_path,
            index_mode=index_mode,
            metadata=metadata,
            current_git_head=None,
            working_tree_dirty=None,
            suggested_action=_suggest(
                index_mode=index_mode,
                repo_root=repo_root,
                db_path=db_path,
                status=IndexStatus.SCHEMA_MISMATCH,
                reason=IndexStatusReason.SCHEMA_VERSION_MISMATCH,
            ),
        )

    # ------------------------------------------------------------------ #
    # 3. Check context_pack_version compatibility
    # ------------------------------------------------------------------ #
    stored_cpv = _nonempty(metadata.get("context_pack_version"))
    if stored_cpv is not None and stored_cpv != CONTEXT_PACK_VERSION:
        return _report(
            status=IndexStatus.SCHEMA_MISMATCH,
            reason=IndexStatusReason.CONTEXT_PACK_VERSION_MISMATCH,
            repo_root=repo_root,
            db_path=db_path,
            index_mode=index_mode,
            metadata=metadata,
            current_git_head=None,
            working_tree_dirty=None,
            suggested_action=_suggest(
                index_mode=index_mode,
                repo_root=repo_root,
                db_path=db_path,
                status=IndexStatus.SCHEMA_MISMATCH,
                reason=IndexStatusReason.CONTEXT_PACK_VERSION_MISMATCH,
            ),
        )

    # ------------------------------------------------------------------ #
    # 4. DB is readable; delegate to metadata-based analysis
    # ------------------------------------------------------------------ #
    return detect_stale_from_metadata(
        repo_root=repo_root,
        db_path=db_path,
        index_mode=index_mode,
        metadata=metadata,
    )


def detect_stale_from_metadata(
    *,
    repo_root: Path,
    db_path: Path,
    index_mode: Literal["explicit_db", "store"],
    metadata: dict[str, str],
) -> IndexStatusReport:
    """Detect staleness from pre-loaded metadata (DB already open/closed).

    Skips schema-version and DB-existence checks; callers are responsible for
    ensuring the DB was successfully opened.  Use this inside commands that
    already have the metadata loaded to avoid re-opening the database.

    Args:
        repo_root: Absolute path to the repository root.
        db_path: Absolute path to the index SQLite file.
        index_mode: Resolution mode (see :func:`detect_index_status`).
        metadata: Key/value rows from ``SQLiteStore.get_metadata()``.
    """
    indexed_at = _nonempty(metadata.get("indexed_at"))

    if indexed_at is None:
        # Index was built before staleness tracking was added.
        return _report(
            status=IndexStatus.UNKNOWN,
            reason=IndexStatusReason.METADATA_INCOMPLETE,
            repo_root=repo_root,
            db_path=db_path,
            index_mode=index_mode,
            metadata=metadata,
            current_git_head=None,
            working_tree_dirty=None,
            suggested_action=None,
        )

    # ------------------------------------------------------------------ #
    # 5. Collect current Git state
    # ------------------------------------------------------------------ #
    current_git_head: str | None = None
    working_tree_dirty: bool | None = None
    try:
        summary = get_git_repository_summary(repo_root)
        if summary.in_git_repo:
            current_git_head = _nonempty(summary.current_commit)
            working_tree_dirty = summary.is_dirty
    except Exception:  # noqa: BLE001 — git errors must never block status
        pass

    indexed_git_head = _nonempty(metadata.get("git_head"))

    # ------------------------------------------------------------------ #
    # 6. Compare heads
    # ------------------------------------------------------------------ #
    if indexed_git_head and current_git_head:
        if indexed_git_head != current_git_head:
            return _report(
                status=IndexStatus.STALE,
                reason=IndexStatusReason.GIT_HEAD_CHANGED,
                repo_root=repo_root,
                db_path=db_path,
                index_mode=index_mode,
                metadata=metadata,
                current_git_head=current_git_head,
                working_tree_dirty=working_tree_dirty,
                suggested_action=_suggest(
                    index_mode=index_mode,
                    repo_root=repo_root,
                    db_path=db_path,
                    status=IndexStatus.STALE,
                    reason=IndexStatusReason.GIT_HEAD_CHANGED,
                ),
            )
        # Heads match — check for dirty working tree
        if working_tree_dirty:
            return _report(
                status=IndexStatus.MAYBE_STALE,
                reason=IndexStatusReason.WORKING_TREE_DIRTY,
                repo_root=repo_root,
                db_path=db_path,
                index_mode=index_mode,
                metadata=metadata,
                current_git_head=current_git_head,
                working_tree_dirty=working_tree_dirty,
                suggested_action=None,
            )
        # Heads match and tree is clean
        return _report(
            status=IndexStatus.FRESH,
            reason=IndexStatusReason.OK,
            repo_root=repo_root,
            db_path=db_path,
            index_mode=index_mode,
            metadata=metadata,
            current_git_head=current_git_head,
            working_tree_dirty=working_tree_dirty,
            suggested_action=None,
        )

    # ------------------------------------------------------------------ #
    # 7. Git not fully available — fall back to unknown
    # ------------------------------------------------------------------ #
    return _report(
        status=IndexStatus.UNKNOWN,
        reason=IndexStatusReason.GIT_UNAVAILABLE,
        repo_root=repo_root,
        db_path=db_path,
        index_mode=index_mode,
        metadata=metadata,
        current_git_head=current_git_head,
        working_tree_dirty=working_tree_dirty,
        suggested_action=None,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _nonempty(value: str | None) -> str | None:
    """Return ``value`` if non-empty after stripping, else ``None``."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _suggest(
    *,
    index_mode: Literal["explicit_db", "store"],
    repo_root: Path,
    db_path: Path | None,
    status: IndexStatus,
    reason: str,
) -> str | None:
    """Return a mode-aware suggested CLI action, or ``None`` when not needed."""
    if status == IndexStatus.FRESH:
        return None

    repo_str = str(repo_root)

    if index_mode == "store":
        if reason == IndexStatusReason.UNREGISTERED:
            return f"rsm store register {repo_str} --index"
        # registered_db_missing, stale, schema_mismatch — re-index
        return f"rsm index {repo_str} --register"

    # explicit_db mode
    if db_path is not None:
        return f"rsm index {repo_str} --db {db_path}"
    return f"rsm index {repo_str} --db <path>"


def _report(
    *,
    status: IndexStatus,
    reason: str,
    repo_root: Path,
    db_path: Path | None,
    index_mode: Literal["explicit_db", "store"],
    metadata: dict[str, str],
    current_git_head: str | None,
    working_tree_dirty: bool | None,
    suggested_action: str | None,
) -> IndexStatusReport:
    """Construct an ``IndexStatusReport`` from common fields + metadata dict."""
    return IndexStatusReport(
        index_status=status,
        index_status_reason=reason,
        repo_root=repo_root,
        db_path=db_path,
        index_mode=index_mode,
        indexed_at=_nonempty(metadata.get("indexed_at")),
        indexed_git_head=_nonempty(metadata.get("git_head")),
        current_git_head=current_git_head,
        working_tree_dirty=working_tree_dirty,
        schema_version=_nonempty(metadata.get("schema_version")) or SCHEMA_VERSION,
        context_pack_version=(
            _nonempty(metadata.get("context_pack_version")) or CONTEXT_PACK_VERSION
        ),
        suggested_action=suggested_action,
    )


__all__ = [
    "IndexStatus",
    "IndexStatusReason",
    "IndexStatusReport",
    "detect_index_status",
    "detect_stale_from_metadata",
]
