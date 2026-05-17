"""CLI behavior tests."""

from __future__ import annotations

import pytest

from repo_semantic_memory.cli import main


def test_help_flag_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "rsm" in out


def test_version_command_prints_all_versions(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["version"])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "package_version:" in out
    assert "schema_version:" in out
    assert "context_pack_version:" in out
