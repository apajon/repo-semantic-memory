"""Tests for store_home/home.py — RSM Index Store home directory resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from repo_semantic_memory.store_home.home import _locate_home, resolve_store_home


def test_rsm_home_env_var_takes_precedence(tmp_path: Path) -> None:
    custom = tmp_path / "custom_store"
    with mock.patch.dict("os.environ", {"RSM_HOME": str(custom)}):
        result = _locate_home()
    assert result == custom


def test_rsm_home_env_var_expands_user(tmp_path: Path) -> None:
    # Use a literal ~ to ensure expanduser is called
    with mock.patch.dict("os.environ", {"RSM_HOME": "~/rsm_test_store"}):
        result = _locate_home()
    assert not str(result).startswith("~")
    assert result == Path.home() / "rsm_test_store"


def test_linux_xdg_data_home(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg_data"
    env = {"XDG_DATA_HOME": str(xdg)}
    with mock.patch.dict("os.environ", env, clear=False), mock.patch("sys.platform", "linux"):
        # Ensure RSM_HOME is not set
        with mock.patch.dict("os.environ", {"RSM_HOME": ""}, clear=False):
            result = _locate_home()
    assert result == xdg / "repo-semantic-memory"


def test_linux_fallback_without_xdg(tmp_path: Path) -> None:
    env_patch = {"RSM_HOME": ""}
    env_remove = ["XDG_DATA_HOME"]
    with (
        mock.patch("sys.platform", "linux"),
        mock.patch.dict("os.environ", env_patch, clear=False),
    ):
        # Remove XDG_DATA_HOME if present
        import os

        saved = os.environ.pop("XDG_DATA_HOME", None)
        try:
            result = _locate_home()
        finally:
            if saved is not None:
                os.environ["XDG_DATA_HOME"] = saved
    assert result == Path.home() / ".local" / "share" / "repo-semantic-memory"
    _ = env_remove  # referenced to satisfy the linter


def test_macos_path() -> None:
    with (
        mock.patch("sys.platform", "darwin"),
        mock.patch.dict("os.environ", {"RSM_HOME": ""}, clear=False),
    ):
        result = _locate_home()
    assert result == Path.home() / "Library" / "Application Support" / "repo-semantic-memory"


def test_windows_path_with_localappdata(tmp_path: Path) -> None:
    local_app_data = tmp_path / "AppData" / "Local"
    with (
        mock.patch("sys.platform", "win32"),
        mock.patch.dict(
            "os.environ", {"LOCALAPPDATA": str(local_app_data), "RSM_HOME": ""}, clear=False
        ),
    ):
        result = _locate_home()
    assert result == local_app_data / "repo-semantic-memory"


def test_windows_fallback_without_localappdata() -> None:
    import os

    saved = os.environ.pop("LOCALAPPDATA", None)
    try:
        with (
            mock.patch("sys.platform", "win32"),
            mock.patch.dict("os.environ", {"RSM_HOME": ""}, clear=False),
        ):
            result = _locate_home()
        assert result == Path.home() / "AppData" / "Local" / "repo-semantic-memory"
    finally:
        if saved is not None:
            os.environ["LOCALAPPDATA"] = saved


def test_resolve_store_home_creates_directory_and_indexes(tmp_path: Path) -> None:
    custom = tmp_path / "my_store"
    assert not custom.exists()
    with mock.patch.dict("os.environ", {"RSM_HOME": str(custom)}):
        result = resolve_store_home()
    assert result == custom
    assert custom.is_dir()
    assert (custom / "indexes").is_dir()


def test_resolve_store_home_idempotent(tmp_path: Path) -> None:
    custom = tmp_path / "my_store"
    with mock.patch.dict("os.environ", {"RSM_HOME": str(custom)}):
        first = resolve_store_home()
        second = resolve_store_home()
    assert first == second
    assert custom.is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths only")
def test_resolve_store_home_current_platform(tmp_path: Path) -> None:
    # Smoke test: resolve_store_home() on the current platform returns a Path
    # inside tmp_path when RSM_HOME is set.
    with mock.patch.dict("os.environ", {"RSM_HOME": str(tmp_path / "smoke")}):
        result = resolve_store_home()
    assert isinstance(result, Path)
    assert result.is_dir()
