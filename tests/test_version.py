"""Tests for version metadata constants."""

from importlib.metadata import PackageNotFoundError, version

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


def test_resolve_package_version_falls_back_when_distribution_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_package_not_found(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(version_module, "version", _raise_package_not_found)
    assert version_module._resolve_package_version() == "0.0.0.dev0"
