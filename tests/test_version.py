"""Tests for version metadata constants."""

from importlib.metadata import PackageNotFoundError, version
from typing import NoReturn

import pytest

import repo_semantic_memory.version as version_module
from repo_semantic_memory.version import (
    CONTEXT_PACK_VERSION,
    PACKAGE_VERSION,
    SCHEMA_VERSION,
    get_version_info,
)


def test_version_constants_are_deterministic() -> None:
    assert PACKAGE_VERSION == version("repo-semantic-memory")
    assert SCHEMA_VERSION == "0.1.0"
    assert CONTEXT_PACK_VERSION == "0.1.0"


def test_get_version_info_returns_expected_values() -> None:
    info = get_version_info()
    assert info.package_version == PACKAGE_VERSION
    assert info.schema_version == SCHEMA_VERSION
    assert info.context_pack_version == CONTEXT_PACK_VERSION


def test_resolve_package_version_from_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(version_module, "version", lambda _: "1.2.3")
    assert version_module._resolve_package_version() == "1.2.3"


def test_resolve_package_version_ignores_generated_module_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodesIfAccessed:
        def __getattr__(self, _: str) -> str:
            raise AssertionError("_version module should not be accessed")

    monkeypatch.setattr(
        version_module,
        "_version",
        _ExplodesIfAccessed(),
        raising=False,
    )
    monkeypatch.setattr(version_module, "version", lambda _: "1.2.3")
    assert version_module._resolve_package_version() == "1.2.3"


def test_package_version_fallback_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_package_not_found(_: str) -> NoReturn:
        raise PackageNotFoundError

    monkeypatch.setattr(version_module, "version", _raise_package_not_found)
    assert version_module._resolve_package_version() == "0.0.0+unknown"
