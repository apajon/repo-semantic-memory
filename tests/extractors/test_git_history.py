"""Tests for minimal Git history extraction."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_semantic_memory.extractors.git_history import (
    _parse_commit_count,
    _parse_last_commit_payload,
    _run_git,
    collect_git_file_metadata,
    get_git_repository_summary,
)


def test_get_git_repository_summary_outside_repo_is_graceful(tmp_path: Path) -> None:
    summary = get_git_repository_summary(tmp_path)
    assert summary.in_git_repo is False
    assert summary.repository_root is None
    assert summary.current_commit is None
    assert summary.unavailable_reason


def test_collect_git_file_metadata_parses_mocked_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(
        command: list[str],
        *,
        cwd: str,
        check: bool,
        capture_output: bool,
        text: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, check, capture_output, text, shell
        key = tuple(command)
        if key == ("git", "log", "-n", "1", "--format=%H%n%cI", "--", "src/a.py"):
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="abc123\n2026-05-18T00:00:00+00:00\n",
                stderr="",
            )
        if key == ("git", "rev-list", "--count", "HEAD", "--", "src/a.py"):
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="7\n",
                stderr="",
            )
        raise subprocess.CalledProcessError(returncode=128, cmd=command, stderr="unknown file")

    monkeypatch.setattr("repo_semantic_memory.extractors.git_history.subprocess.run", _fake_run)
    metadata = collect_git_file_metadata(repository_root=".", relative_paths=["src/a.py", "src/missing.py"])
    assert list(metadata) == ["src/a.py"]
    assert metadata["src/a.py"].to_dict() == {
        "last_commit_hash": "abc123",
        "last_commit_date": "2026-05-18T00:00:00+00:00",
        "commit_count": 7,
    }


def test_parse_helpers_are_deterministic() -> None:
    parsed = _parse_last_commit_payload("deadbeef\n2026-05-18T00:00:00+00:00\n")
    assert parsed is not None
    assert parsed.last_commit_hash == "deadbeef"
    assert parsed.last_commit_date == "2026-05-18T00:00:00+00:00"
    assert _parse_last_commit_payload("only-one-line\n") is None
    assert _parse_commit_count("12\n") == 12
    assert _parse_commit_count("not-a-number\n") is None


def test_run_git_uses_safe_subprocess_arguments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _fake_run(
        command: list[str],
        *,
        cwd: str,
        check: bool,
        capture_output: bool,
        text: bool,
        shell: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["shell"] = shell
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("repo_semantic_memory.extractors.git_history.subprocess.run", _fake_run)
    stdout, error = _run_git(cwd=tmp_path, args=("rev-parse", "HEAD"))

    assert stdout == "ok\n"
    assert error is None
    assert captured["command"] == ["git", "rev-parse", "HEAD"]
    assert captured["shell"] is False
