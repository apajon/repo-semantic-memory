"""Minimal Git temporal metadata extraction helpers."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_semantic_memory.model import JsonValue


@dataclass(frozen=True)
class GitRepositorySummary:
    """Minimal summary of Git repository state for a path."""

    path: str
    in_git_repo: bool
    repository_root: str | None
    current_commit: str | None
    is_dirty: bool | None
    tracked_file_count: int | None
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        """Return JSON-safe summary payload."""
        return {
            "path": self.path,
            "in_git_repo": self.in_git_repo,
            "repository_root": self.repository_root,
            "current_commit": self.current_commit,
            "is_dirty": self.is_dirty,
            "tracked_file_count": self.tracked_file_count,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class GitFileMetadata:
    """Minimal file-level temporal metadata from local Git history."""

    last_commit_hash: str
    last_commit_date: str
    commit_count: int

    def to_dict(self) -> dict[str, JsonValue]:
        """Return JSON-safe file metadata payload."""
        return {
            "last_commit_hash": self.last_commit_hash,
            "last_commit_date": self.last_commit_date,
            "commit_count": self.commit_count,
        }


def get_git_repository_summary(path: Path | str) -> GitRepositorySummary:
    """Return minimal repository-level Git metadata for a path."""
    resolved = Path(path).resolve()

    inside_worktree, inside_error = _run_git(
        cwd=resolved,
        args=("rev-parse", "--is-inside-work-tree"),
    )
    if inside_worktree is None:
        return GitRepositorySummary(
            path=str(resolved),
            in_git_repo=False,
            repository_root=None,
            current_commit=None,
            is_dirty=None,
            tracked_file_count=None,
            unavailable_reason=inside_error,
        )
    if inside_worktree.strip().lower() != "true":
        return GitRepositorySummary(
            path=str(resolved),
            in_git_repo=False,
            repository_root=None,
            current_commit=None,
            is_dirty=None,
            tracked_file_count=None,
            unavailable_reason="path is not inside a Git repository",
        )

    repository_root, root_error = _run_git(cwd=resolved, args=("rev-parse", "--show-toplevel"))
    current_commit, commit_error = _run_git(cwd=resolved, args=("rev-parse", "HEAD"))
    status_porcelain, status_error = _run_git(cwd=resolved, args=("status", "--porcelain"))
    tracked_files, tracked_error = _run_git(cwd=resolved, args=("ls-files", "-z"))

    errors = tuple(
        error
        for error in (root_error, commit_error, status_error, tracked_error)
        if error is not None
    )
    tracked_count = _count_tracked_files(tracked_files) if tracked_files is not None else None
    return GitRepositorySummary(
        path=str(resolved),
        in_git_repo=True,
        repository_root=repository_root.strip() if repository_root is not None else None,
        current_commit=current_commit.strip() if current_commit is not None else None,
        is_dirty=None if status_porcelain is None else bool(status_porcelain.strip()),
        tracked_file_count=tracked_count,
        unavailable_reason="; ".join(errors) if errors else None,
    )


def collect_git_file_metadata(
    *,
    repository_root: Path | str,
    relative_paths: Sequence[str],
) -> dict[str, GitFileMetadata]:
    """Collect file-level Git metadata for repository-relative paths."""
    root = Path(repository_root).resolve()
    metadata_by_path: dict[str, GitFileMetadata] = {}
    for relative_path in sorted(set(relative_paths)):
        normalized = Path(relative_path).as_posix()
        file_metadata = _extract_file_metadata(root=root, relative_path=normalized)
        if file_metadata is not None:
            metadata_by_path[normalized] = file_metadata
    return metadata_by_path


def _extract_file_metadata(*, root: Path, relative_path: str) -> GitFileMetadata | None:
    log_output, log_error = _run_git(
        cwd=root,
        args=("log", "-n", "1", "--format=%H%n%cI", "--", relative_path),
    )
    if log_output is None or log_error is not None:
        return None
    parsed = _parse_last_commit_payload(log_output)
    if parsed is None:
        return None

    count_output, count_error = _run_git(
        cwd=root,
        args=("rev-list", "--count", "HEAD", "--", relative_path),
    )
    if count_output is None or count_error is not None:
        return None
    commit_count = _parse_commit_count(count_output)
    if commit_count is None:
        return None

    return GitFileMetadata(
        last_commit_hash=parsed.last_commit_hash,
        last_commit_date=parsed.last_commit_date,
        commit_count=commit_count,
    )


@dataclass(frozen=True)
class _ParsedCommit:
    last_commit_hash: str
    last_commit_date: str


def _parse_last_commit_payload(payload: str) -> _ParsedCommit | None:
    lines = [line.strip() for line in payload.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    return _ParsedCommit(last_commit_hash=lines[0], last_commit_date=lines[1])


def _parse_commit_count(payload: str) -> int | None:
    stripped = payload.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _count_tracked_files(payload: str) -> int:
    if payload == "":
        return 0
    return payload.count("\x00")


def _run_git(*, cwd: Path, args: Sequence[str]) -> tuple[str | None, str | None]:
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
    except FileNotFoundError:
        return None, "git executable is not available"
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        detail = stderr or stdout or "git command failed"
        return None, detail
    return result.stdout, None
