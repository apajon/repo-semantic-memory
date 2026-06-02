"""Unit tests for ScopeFilter — include/exclude glob scoping."""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.extractors.filesystem import ScopeFilter

# ---------------------------------------------------------------------------
# Passthrough (no patterns)
# ---------------------------------------------------------------------------


def test_passthrough_no_patterns() -> None:
    sf = ScopeFilter()
    assert sf.is_passthrough is True


def test_passthrough_with_patterns() -> None:
    sf = ScopeFilter(includes=["src/**"])
    assert sf.is_passthrough is False


def test_passthrough_empty_lists() -> None:
    sf = ScopeFilter(includes=[], excludes=[])
    assert sf.is_passthrough is True


def test_passthrough_strips_empty_strings() -> None:
    """Blank strings should be ignored so a filter with only blanks is passthrough."""
    sf = ScopeFilter(includes=["", "  "], excludes=["", " "])
    # Strips to nothing → passthrough
    assert sf.is_passthrough is True


# ---------------------------------------------------------------------------
# should_index_file — includes only
# ---------------------------------------------------------------------------


def test_include_matches_file() -> None:
    sf = ScopeFilter(includes=["src/**"])
    assert sf.should_index_file("src/app.py") is True


def test_include_does_not_match_different_dir() -> None:
    sf = ScopeFilter(includes=["src/**"])
    assert sf.should_index_file("tests/test_app.py") is False


def test_multiple_includes_either_matches() -> None:
    sf = ScopeFilter(includes=["src/**", "tests/**"])
    assert sf.should_index_file("src/app.py") is True
    assert sf.should_index_file("tests/test_app.py") is True
    assert sf.should_index_file("docs/guide.md") is False


def test_include_exact_filename() -> None:
    sf = ScopeFilter(includes=["README.md"])
    assert sf.should_index_file("README.md") is True
    assert sf.should_index_file("docs/README.md") is False


def test_include_extension_wildcard() -> None:
    sf = ScopeFilter(includes=["**/*.py"])
    assert sf.should_index_file("src/app.py") is True
    assert sf.should_index_file("tests/test_app.py") is True
    assert sf.should_index_file("docs/guide.md") is False


# ---------------------------------------------------------------------------
# should_index_file — excludes only
# ---------------------------------------------------------------------------


def test_exclude_matches_file() -> None:
    sf = ScopeFilter(excludes=["docs/**"])
    assert sf.should_index_file("docs/guide.md") is False
    assert sf.should_index_file("src/app.py") is True


def test_exclude_takes_precedence_over_include() -> None:
    sf = ScopeFilter(includes=["**"], excludes=["docs/**"])
    assert sf.should_index_file("docs/guide.md") is False
    assert sf.should_index_file("src/app.py") is True


def test_exclude_multiple_patterns() -> None:
    sf = ScopeFilter(excludes=["docs/**", "tests/**"])
    assert sf.should_index_file("docs/guide.md") is False
    assert sf.should_index_file("tests/test_app.py") is False
    assert sf.should_index_file("src/app.py") is True


# ---------------------------------------------------------------------------
# should_index_file — combined
# ---------------------------------------------------------------------------


def test_combined_include_and_exclude() -> None:
    sf = ScopeFilter(includes=["src/**"], excludes=["src/generated/**"])
    assert sf.should_index_file("src/app.py") is True
    assert sf.should_index_file("src/generated/proto.py") is False
    assert sf.should_index_file("tests/test_app.py") is False


def test_no_patterns_allows_all_files() -> None:
    sf = ScopeFilter()
    assert sf.should_index_file("anything/at/all.py") is True


def test_leading_slash_stripped() -> None:
    sf = ScopeFilter(includes=["/src/**"])
    assert sf.should_index_file("src/app.py") is True


# ---------------------------------------------------------------------------
# should_descend_directory — includes only
# ---------------------------------------------------------------------------


def test_descend_with_matching_include() -> None:
    sf = ScopeFilter(includes=["src/**"])
    assert sf.should_descend_directory("src") is True


def test_descend_excludes_unrelated_dir_with_include() -> None:
    sf = ScopeFilter(includes=["src/**"])
    # Nothing inside "docs" can match "src/**"
    assert sf.should_descend_directory("docs") is False


def test_descend_deep_with_ancestor_prefix() -> None:
    sf = ScopeFilter(includes=["homeassistant/components/**"])
    # "homeassistant" is an ancestor of the literal prefix → must descend
    assert sf.should_descend_directory("homeassistant") is True
    # "homeassistant/components" itself matches
    assert sf.should_descend_directory("homeassistant/components") is True
    # Sibling directory
    assert sf.should_descend_directory("tests") is False


def test_descend_no_patterns_always_true() -> None:
    sf = ScopeFilter()
    assert sf.should_descend_directory("anything") is True


# ---------------------------------------------------------------------------
# should_descend_directory — excludes only
# ---------------------------------------------------------------------------


def test_descend_excluded_directory() -> None:
    sf = ScopeFilter(excludes=["docs/**"])
    assert sf.should_descend_directory("docs") is False
    assert sf.should_descend_directory("src") is True


def test_descend_exclude_bare_dir_name() -> None:
    sf = ScopeFilter(excludes=["vendor"])
    assert sf.should_descend_directory("vendor") is False
    assert sf.should_descend_directory("src") is True


def test_descend_exclude_with_trailing_slash() -> None:
    sf = ScopeFilter(excludes=["dist/"])
    assert sf.should_descend_directory("dist") is False


def test_descend_partial_dir_name_not_excluded() -> None:
    """Exclude "docs" should not prune "docs_extra"."""
    sf = ScopeFilter(excludes=["docs"])
    assert sf.should_descend_directory("docs_extra") is True


# ---------------------------------------------------------------------------
# should_descend_directory — combined
# ---------------------------------------------------------------------------


def test_exclude_overrides_include_for_directory() -> None:
    sf = ScopeFilter(includes=["**"], excludes=["node_modules/**"])
    assert sf.should_descend_directory("node_modules") is False
    assert sf.should_descend_directory("src") is True


# ---------------------------------------------------------------------------
# Integration: actual filtering reduces entity count
# ---------------------------------------------------------------------------


def test_scope_filter_with_extract_filesystem_entities(tmp_path: Path) -> None:
    """ScopeFilter passed to extract_filesystem_entities reduces discovered files."""
    from repo_semantic_memory.extractors.filesystem import extract_filesystem_entities

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide")

    all_entities = extract_filesystem_entities(tmp_path)
    src_only = extract_filesystem_entities(tmp_path, scope_filter=ScopeFilter(includes=["src/**"]))
    docs_excluded = extract_filesystem_entities(
        tmp_path, scope_filter=ScopeFilter(excludes=["docs/**"])
    )

    all_names = {e.qualified_name for e in all_entities}
    src_names = {e.qualified_name for e in src_only}
    no_docs_names = {e.qualified_name for e in docs_excluded}

    assert "src/app.py" in all_names
    assert "docs/guide.md" in all_names
    assert "src/app.py" in src_names
    assert "docs/guide.md" not in src_names
    assert "src/app.py" in no_docs_names
    assert "docs/guide.md" not in no_docs_names
