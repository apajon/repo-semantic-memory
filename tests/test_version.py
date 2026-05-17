"""Tests for version metadata constants."""

from repo_semantic_memory.version import (
    CONTEXT_PACK_VERSION,
    PACKAGE_VERSION,
    SCHEMA_VERSION,
    get_version_info,
)


def test_version_constants_are_deterministic() -> None:
    assert PACKAGE_VERSION == "0.1.0"
    assert SCHEMA_VERSION == "0.1.0"
    assert CONTEXT_PACK_VERSION == "0.1.0"


def test_get_version_info_returns_expected_values() -> None:
    info = get_version_info()
    assert info.package_version == PACKAGE_VERSION
    assert info.schema_version == SCHEMA_VERSION
    assert info.context_pack_version == CONTEXT_PACK_VERSION
