"""Tests for index staleness detection (index_status.py)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from repo_semantic_memory.index_status import (
    IndexStatus,
    IndexStatusReason,
    detect_index_status,
    detect_stale_from_metadata,
)
from repo_semantic_memory.model import Entity, SourceRange, StableId
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata
from repo_semantic_memory.version import CONTEXT_PACK_VERSION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(
    db_path: Path,
    repo_root: Path,
    *,
    extra_metadata: dict[str, str] | None = None,
) -> None:
    """Create a minimal valid SQLite index at *db_path*."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    entities = [
        Entity(
            id=StableId("python:module:src.core"),
            kind="module",
            name="core",
            qualified_name="src.core",
            source_range=SourceRange(path="src/core.py", start_line=1, end_line=1),
        )
    ]
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        store.persist_index(
            entities=entities,
            relations=[],
            metadata=build_default_extraction_metadata(
                repository_root=repo_root,
                extractor_names=("filesystem",),
                timestamp="2026-05-24T00:00:00+00:00",
            ),
        )
        if extra_metadata:
            store.write_extra_metadata(extra_metadata)
    finally:
        store.close()


def _staleness_meta(
    *,
    indexed_at: str = "2026-05-24T00:00:00+00:00",
    git_head: str = "abc123",
    git_dirty: str = "false",
    entity_count: str = "1",
    relation_count: str = "0",
    context_pack_version: str | None = None,
) -> dict[str, str]:
    return {
        "indexed_at": indexed_at,
        "git_head": git_head,
        "git_dirty": git_dirty,
        "entity_count": entity_count,
        "relation_count": relation_count,
        "context_pack_version": context_pack_version or CONTEXT_PACK_VERSION,
    }


# ---------------------------------------------------------------------------
# Missing DB
# ---------------------------------------------------------------------------


def test_detect_missing_unregistered(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report = detect_index_status(repo_root=repo, db_path=None, index_mode="store")
    assert report.index_status == IndexStatus.MISSING
    assert report.index_status_reason == IndexStatusReason.UNREGISTERED
    assert report.suggested_action is not None
    assert "--index" in (report.suggested_action or "")
    assert "register" in (report.suggested_action or "")


def test_detect_missing_registered_db_gone(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "store" / "index.sqlite"  # does not exist
    report = detect_index_status(repo_root=repo, db_path=db, index_mode="store")
    assert report.index_status == IndexStatus.MISSING
    assert report.index_status_reason == IndexStatusReason.REGISTERED_DB_MISSING
    assert report.suggested_action is not None
    assert "--register" in (report.suggested_action or "")


def test_detect_missing_explicit_db(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "explicit.sqlite"  # does not exist
    report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")
    assert report.index_status == IndexStatus.MISSING
    assert report.index_status_reason == IndexStatusReason.EXPLICIT_DB_MISSING
    assert report.suggested_action is not None
    assert "--db" in (report.suggested_action or "")
    # explicit_db mode must never suggest --register
    assert "--register" not in (report.suggested_action or "")


# ---------------------------------------------------------------------------
# Schema mismatch
# ---------------------------------------------------------------------------


def test_detect_schema_mismatch_hard_error(tmp_path: Path) -> None:
    """A DB with a different schema_version returns SCHEMA_MISMATCH."""
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo)

    # Patch SCHEMA_VERSION in the SQLiteStore module so initialize() detects a
    # mismatch when the runtime "upgrades" to a newer schema.
    with mock.patch(
        "repo_semantic_memory.store.sqlite_store.SCHEMA_VERSION",
        "99.0.0",
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.SCHEMA_MISMATCH
    assert report.index_status_reason == IndexStatusReason.SCHEMA_VERSION_MISMATCH


def test_detect_context_pack_version_mismatch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(
        db,
        repo,
        extra_metadata={
            **_staleness_meta(),
            "context_pack_version": "0.0.1",  # old version
        },
    )
    with mock.patch("repo_semantic_memory.index_status.CONTEXT_PACK_VERSION", "99.0.0"):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.SCHEMA_MISMATCH
    assert report.index_status_reason == IndexStatusReason.CONTEXT_PACK_VERSION_MISMATCH


# ---------------------------------------------------------------------------
# Unknown (missing staleness metadata)
# ---------------------------------------------------------------------------


def test_detect_unknown_when_indexed_at_missing(tmp_path: Path) -> None:
    """Index built before staleness tracking → UNKNOWN/metadata_incomplete."""
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    # No extra_metadata → indexed_at is absent
    _make_db(db, repo)

    report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")
    assert report.index_status == IndexStatus.UNKNOWN
    assert report.index_status_reason == IndexStatusReason.METADATA_INCOMPLETE
    # No suggested action for unknown
    assert report.suggested_action is None


def test_detect_unknown_when_git_unavailable(tmp_path: Path) -> None:
    """When neither the index nor the runtime has git info → UNKNOWN."""
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    # indexed_at present but git_head empty → no heads to compare
    _make_db(db, repo, extra_metadata={**_staleness_meta(), "git_head": ""})

    # Also mock current git to be unavailable
    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    unavailable = GitRepositorySummary(
        path=str(repo),
        in_git_repo=False,
        repository_root=None,
        current_commit=None,
        is_dirty=None,
        tracked_file_count=None,
        unavailable_reason="not a git repo",
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=unavailable,
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.UNKNOWN
    assert report.index_status_reason == IndexStatusReason.GIT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Stale
# ---------------------------------------------------------------------------


def test_detect_stale_when_heads_differ(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="def456",  # different from indexed abc123
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.STALE
    assert report.index_status_reason == IndexStatusReason.GIT_HEAD_CHANGED
    assert report.indexed_git_head == "abc123"
    assert report.current_git_head == "def456"


def test_detect_stale_explicit_db_suggests_db_flag(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="def456",
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.STALE
    assert report.suggested_action is not None
    assert "--db" in report.suggested_action
    assert "--register" not in report.suggested_action


def test_detect_stale_store_mode_suggests_register(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="def456",
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="store")

    assert report.index_status == IndexStatus.STALE
    assert report.suggested_action is not None
    assert "--register" in report.suggested_action
    assert "--db" not in report.suggested_action


# ---------------------------------------------------------------------------
# Maybe stale
# ---------------------------------------------------------------------------


def test_detect_maybe_stale_when_dirty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="abc123",  # same HEAD
        is_dirty=True,  # but dirty working tree
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.MAYBE_STALE
    assert report.index_status_reason == IndexStatusReason.WORKING_TREE_DIRTY
    assert report.working_tree_dirty is True
    # maybe_stale has no suggested action (it's just informational)
    assert report.suggested_action is None


# ---------------------------------------------------------------------------
# Fresh
# ---------------------------------------------------------------------------


def test_detect_fresh_when_heads_match_and_clean(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123", git_dirty="false"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="abc123",
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.FRESH
    assert report.index_status_reason == IndexStatusReason.OK
    assert report.suggested_action is None


def test_fresh_report_carries_indexed_at(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    ts = "2026-05-25T00:00:00+00:00"
    _make_db(db, repo, extra_metadata=_staleness_meta(indexed_at=ts, git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="abc123",
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        report = detect_index_status(repo_root=repo, db_path=db, index_mode="explicit_db")

    assert report.index_status == IndexStatus.FRESH
    assert report.indexed_at == ts


# ---------------------------------------------------------------------------
# detect_stale_from_metadata (pre-loaded metadata path)
# ---------------------------------------------------------------------------


def test_detect_stale_from_metadata_stale(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    db.touch()

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="new_head",
        is_dirty=False,
        tracked_file_count=5,
    )
    meta = {
        **_staleness_meta(git_head="old_head"),
        "repository_root": str(repo),
    }
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        report = detect_stale_from_metadata(
            repo_root=repo,
            db_path=db,
            index_mode="explicit_db",
            metadata=meta,
        )

    assert report.index_status == IndexStatus.STALE
    assert report.index_status_reason == IndexStatusReason.GIT_HEAD_CHANGED


def test_detect_stale_from_metadata_missing_indexed_at(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    db.touch()

    report = detect_stale_from_metadata(
        repo_root=repo,
        db_path=db,
        index_mode="explicit_db",
        metadata={"repository_root": str(repo)},  # no indexed_at
    )
    assert report.index_status == IndexStatus.UNKNOWN
    assert report.index_status_reason == IndexStatusReason.METADATA_INCOMPLETE


# ---------------------------------------------------------------------------
# Suggested action discipline (never cross modes)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("index_mode", "reason", "forbidden", "required"),
    [
        ("explicit_db", IndexStatusReason.EXPLICIT_DB_MISSING, "--register", "--db"),
        ("explicit_db", IndexStatusReason.GIT_HEAD_CHANGED, "--register", "--db"),
        ("explicit_db", IndexStatusReason.SCHEMA_VERSION_MISMATCH, "--register", "--db"),
        ("store", IndexStatusReason.UNREGISTERED, "--db", "register"),
        ("store", IndexStatusReason.REGISTERED_DB_MISSING, "--db", "--register"),
        ("store", IndexStatusReason.GIT_HEAD_CHANGED, "--db", "--register"),
    ],
)
def test_suggested_action_never_crosses_modes(
    tmp_path: Path,
    index_mode: str,
    reason: str,
    forbidden: str,
    required: str,
) -> None:
    """Verify suggested actions are mode-aware."""
    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"

    from repo_semantic_memory.index_status import _suggest  # noqa: PLC2701

    action = _suggest(
        index_mode=index_mode,  # type: ignore[arg-type]
        repo_root=repo,
        db_path=db,
        status=IndexStatus.STALE,
        reason=reason,
    )
    assert action is not None
    assert forbidden not in action, (
        f"'{forbidden}' must not appear in suggested action for {index_mode}"
    )
    assert required in action, f"'{required}' must appear in suggested action for {index_mode}"


# ---------------------------------------------------------------------------
# CLI: rsm store status
# ---------------------------------------------------------------------------


def test_store_status_command_missing_unregistered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from repo_semantic_memory.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()
    store_home = tmp_path / "store"

    with mock.patch.dict("os.environ", {"RSM_HOME": str(store_home)}):
        code = main(["store", "status", str(repo)])

    assert code == 0
    out = capsys.readouterr().out
    assert "missing" in out.lower()


def test_store_status_command_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from repo_semantic_memory.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    current = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="abc123",
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=current,
    ):
        code = main(["store", "status", str(repo), "--db", str(db), "--json"])

    assert code == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["index_status"] == "fresh"
    assert payload["index_mode"] == "explicit_db"
    assert payload["index_status_reason"] == "ok"
    assert payload["suggested_action"] is None


def test_store_status_command_invalid_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from repo_semantic_memory.cli import main

    code = main(["store", "status", str(tmp_path / "nonexistent")])
    assert code == 2
    assert "does not exist" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Stale warning in rsm pack / rsm repo-map
# ---------------------------------------------------------------------------


def test_pack_emits_stale_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """rsm pack prints a stderr warning when the index is stale."""
    from repo_semantic_memory.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    stale_git = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="def456",
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=stale_git,
    ):
        code = main(["pack", "--task", "find core symbols", "--db", str(db), "--budget", "200"])

    assert code == 0  # stale warning never blocks the command
    err = capsys.readouterr().err
    assert "warning:" in err
    assert "stale" in err


def test_repo_map_emits_stale_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """rsm repo-map prints a stderr warning when the index is stale."""
    from repo_semantic_memory.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "index.sqlite"
    _make_db(db, repo, extra_metadata=_staleness_meta(git_head="abc123"))

    from repo_semantic_memory.extractors.git_history import GitRepositorySummary

    stale_git = GitRepositorySummary(
        path=str(repo),
        in_git_repo=True,
        repository_root=str(repo),
        current_commit="new_head",
        is_dirty=False,
        tracked_file_count=5,
    )
    with mock.patch(
        "repo_semantic_memory.index_status.get_git_repository_summary",
        return_value=stale_git,
    ):
        code = main(["repo-map", "--db", str(db), "--budget", "200"])

    assert code == 0
    err = capsys.readouterr().err
    assert "warning:" in err
    assert "stale" in err


# ---------------------------------------------------------------------------
# Index command writes staleness metadata
# ---------------------------------------------------------------------------


def test_index_command_writes_staleness_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """rsm index writes indexed_at, schema_version, entity_count, relation_count, context_pack_version."""  # noqa: E501
    from repo_semantic_memory.cli import main
    from repo_semantic_memory.version import SCHEMA_VERSION

    fixture_root = Path(__file__).resolve().parent / "fixtures" / "simple_repo"
    db = tmp_path / "index.sqlite"

    code = main(["index", str(fixture_root), "--db", str(db)])
    assert code == 0

    store = SQLiteStore(db)
    try:
        store.initialize()
        meta = store.get_metadata()
    finally:
        store.close()

    assert "indexed_at" in meta
    assert meta["indexed_at"]  # non-empty ISO timestamp
    assert "entity_count" in meta
    assert int(meta["entity_count"]) > 0
    assert "relation_count" in meta
    assert int(meta["relation_count"]) >= 0
    assert "schema_version" in meta
    assert meta["schema_version"] == SCHEMA_VERSION
    assert "context_pack_version" in meta
    assert meta["context_pack_version"] == CONTEXT_PACK_VERSION
    # git_head may be present or empty depending on CI environment
    assert "git_head" in meta
