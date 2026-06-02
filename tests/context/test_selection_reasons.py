"""Tests for closed-vocabulary machine-readable selection reasons (Ranking v2, Prompt 58.5)."""

from __future__ import annotations

import pytest

from repo_semantic_memory.context.selection_reasons import (
    SELECTION_REASON_CODES,
    SelectionReason,
    build_selection_reasons,
    classify_reason_string,
    dedupe_selection_reasons,
)

# ---------------------------------------------------------------------------
# SELECTION_REASON_CODES vocabulary
# ---------------------------------------------------------------------------


def test_selection_reason_codes_count() -> None:
    assert len(SELECTION_REASON_CODES) == 15


def test_selection_reason_codes_contains_expected() -> None:
    expected = {
        "lexical_match",
        "intent_match",
        "path_prior",
        "central_candidate",
        "graph_neighbor",
        "support_import",
        "support_export",
        "support_inherits",
        "support_same_package",
        "support_public_api",
        "test_relation",
        "test_path_proximity",
        "test_stem_match",
        "test_lexical_match",
        "scope_warning",
    }
    assert SELECTION_REASON_CODES == expected


# ---------------------------------------------------------------------------
# SelectionReason dataclass
# ---------------------------------------------------------------------------


def test_selection_reason_valid_code() -> None:
    r = SelectionReason("lexical_match")
    assert r.code == "lexical_match"
    assert r.detail is None


def test_selection_reason_valid_code_with_detail() -> None:
    r = SelectionReason("path_prior", "+4.0")
    assert r.code == "path_prior"
    assert r.detail == "+4.0"


def test_selection_reason_invalid_code_raises() -> None:
    with pytest.raises(ValueError, match="Unknown selection reason code"):
        SelectionReason("not_a_real_code")


def test_selection_reason_frozen() -> None:
    from dataclasses import FrozenInstanceError

    r = SelectionReason("lexical_match")
    with pytest.raises(FrozenInstanceError):
        r.code = "other"  # type: ignore[misc]


def test_selection_reason_to_dict_no_detail() -> None:
    d = SelectionReason("graph_neighbor").to_dict()
    assert d == {"code": "graph_neighbor"}


def test_selection_reason_to_dict_with_detail() -> None:
    d = SelectionReason("support_import", "django/urls/conf.py").to_dict()
    assert d == {"code": "support_import", "detail": "django/urls/conf.py"}


def test_selection_reason_equality() -> None:
    assert SelectionReason("lexical_match") == SelectionReason("lexical_match")
    assert SelectionReason("lexical_match", "foo") != SelectionReason("lexical_match", "bar")
    assert SelectionReason("lexical_match", None) != SelectionReason("path_prior", None)


def test_selection_reason_hashable() -> None:
    s = {SelectionReason("lexical_match"), SelectionReason("lexical_match")}
    assert len(s) == 1


# ---------------------------------------------------------------------------
# dedupe_selection_reasons
# ---------------------------------------------------------------------------


def test_dedupe_removes_identical_code_and_detail() -> None:
    reasons = (
        SelectionReason("lexical_match"),
        SelectionReason("lexical_match"),
    )
    result = dedupe_selection_reasons(reasons)
    assert result == (SelectionReason("lexical_match"),)


def test_dedupe_keeps_different_detail() -> None:
    reasons = (
        SelectionReason("support_import", "a/b.py"),
        SelectionReason("support_import", "c/d.py"),
    )
    result = dedupe_selection_reasons(reasons)
    assert len(result) == 2


def test_dedupe_keeps_different_code_same_detail() -> None:
    reasons = (
        SelectionReason("support_import", "a/b.py"),
        SelectionReason("support_export", "a/b.py"),
    )
    result = dedupe_selection_reasons(reasons)
    assert len(result) == 2


def test_dedupe_preserves_first_seen_order() -> None:
    reasons = (
        SelectionReason("graph_neighbor"),
        SelectionReason("lexical_match"),
        SelectionReason("graph_neighbor"),
    )
    result = dedupe_selection_reasons(reasons)
    assert result == (SelectionReason("graph_neighbor"), SelectionReason("lexical_match"))


def test_dedupe_empty() -> None:
    assert dedupe_selection_reasons(()) == ()


# ---------------------------------------------------------------------------
# classify_reason_string — test-branch reasons
# ---------------------------------------------------------------------------


def test_classify_test_branch_tests_relation() -> None:
    r = classify_reason_string("test branch: tests relation to tests/urlpatterns/test_resolvers.py")
    assert r.code == "test_relation"
    assert r.detail == "tests/urlpatterns/test_resolvers.py"


def test_classify_test_branch_tests_relation_impl() -> None:
    r = classify_reason_string("test branch: tests relation from python:module:resolvers")
    assert r.code == "test_relation"


def test_classify_test_branch_stem_proximity() -> None:
    r = classify_reason_string("test branch: filename stem proximity ('resolvers')")
    assert r.code == "test_stem_match"
    assert r.detail == "resolvers"


def test_classify_test_branch_lexical_token_overlap() -> None:
    r = classify_reason_string("test branch: lexical token overlap (url, resolvers)")
    assert r.code == "test_lexical_match"
    assert r.detail == "url, resolvers"


def test_classify_test_branch_test_root_path_proximity() -> None:
    r = classify_reason_string("test branch: test root path proximity")
    assert r.code == "test_path_proximity"


def test_classify_test_branch_case_insensitive() -> None:
    r = classify_reason_string("Test Branch: Tests Relation to tests/foo.py")
    assert r.code == "test_relation"


# ---------------------------------------------------------------------------
# classify_reason_string — support-expansion reasons
# ---------------------------------------------------------------------------


def test_classify_support_imported_by() -> None:
    r = classify_reason_string("support: imported by django/urls/conf.py")
    assert r.code == "support_import"
    assert r.detail == "django/urls/conf.py"


def test_classify_support_imports() -> None:
    r = classify_reason_string("support: imports lib/ansible/executor/module_common.py")
    assert r.code == "support_import"
    assert r.detail == "lib/ansible/executor/module_common.py"


def test_classify_support_export_surface() -> None:
    r = classify_reason_string("support: export surface for httpx/_client.py")
    assert r.code == "support_export"
    assert r.detail == "httpx/_client.py"


def test_classify_support_exported_by() -> None:
    r = classify_reason_string("support: exported by httpx/__init__.py")
    assert r.code == "support_export"
    assert r.detail == "httpx/__init__.py"


def test_classify_support_inherited_by() -> None:
    r = classify_reason_string("support: inherited by django/views/generic/base.py")
    assert r.code == "support_inherits"
    assert r.detail == "django/views/generic/base.py"


def test_classify_support_inherits() -> None:
    r = classify_reason_string("support: inherits django/views/base.py")
    assert r.code == "support_inherits"
    assert r.detail == "django/views/base.py"


def test_classify_support_same_package() -> None:
    r = classify_reason_string("support: same package (django/urls)")
    assert r.code == "support_same_package"
    assert r.detail == "django/urls"


def test_classify_support_public_api() -> None:
    r = classify_reason_string("support: public API surface (httpx/__init__.py)")
    assert r.code == "support_public_api"
    assert r.detail == "httpx/__init__.py"


def test_classify_support_structural_adjacency() -> None:
    r = classify_reason_string("support: structural adjacency")
    assert r.code == "support_same_package"


# ---------------------------------------------------------------------------
# classify_reason_string — graph-neighbor reasons
# ---------------------------------------------------------------------------


def test_classify_graph_neighbor_full() -> None:
    r = classify_reason_string(
        "graph neighbor via imports (depth=1, score=5.000) from python:module:foo"
    )
    assert r.code == "graph_neighbor"


def test_classify_graph_neighbor_fallback() -> None:
    r = classify_reason_string("graph neighbor (score=5.000)")
    assert r.code == "graph_neighbor"


# ---------------------------------------------------------------------------
# classify_reason_string — path-prior reasons
# ---------------------------------------------------------------------------


def test_classify_path_prior_positive() -> None:
    r = classify_reason_string("path prior (+4.0)")
    assert r.code == "path_prior"
    assert r.detail == "+4.0"


def test_classify_path_prior_negative() -> None:
    r = classify_reason_string("path prior (-6.0)")
    assert r.code == "path_prior"
    assert r.detail == "-6.0"


# ---------------------------------------------------------------------------
# classify_reason_string — scope warning
# ---------------------------------------------------------------------------


def test_classify_generated_artifact_downrank() -> None:
    r = classify_reason_string("generated/build artifact downrank")
    assert r.code == "scope_warning"
    assert r.detail == "generated artifact"


# ---------------------------------------------------------------------------
# classify_reason_string — intent-match reasons (task hints)
# ---------------------------------------------------------------------------


def test_classify_public_api_hint_downrank_docs() -> None:
    r = classify_reason_string("public API task hint -> downranked docs/prose context")
    assert r.code == "path_prior"


def test_classify_implementation_hint_boosted_source() -> None:
    r = classify_reason_string("implementation task hint -> boosted source/package root")
    assert r.code == "intent_match"
    assert r.detail == "implementation"


def test_classify_test_hint_boosted_test_root() -> None:
    r = classify_reason_string("test task hint -> boosted test root")
    assert r.code == "intent_match"
    assert r.detail == "tests"


def test_classify_public_api_intent_boost() -> None:
    r = classify_reason_string("public API task intent boost")
    assert r.code == "intent_match"
    assert r.detail == "public_api"


# ---------------------------------------------------------------------------
# classify_reason_string — lexical reasons
# ---------------------------------------------------------------------------


def test_classify_lexical_match_on_source_path() -> None:
    r = classify_reason_string('lexical match on source path "resolver.py"')
    assert r.code == "lexical_match"


def test_classify_lexical_baseline_relevance() -> None:
    r = classify_reason_string("lexical baseline relevance")
    assert r.code == "lexical_match"


# ---------------------------------------------------------------------------
# classify_reason_string — fallback / central-candidate
# ---------------------------------------------------------------------------


def test_classify_fallback_deterministic_seed() -> None:
    r = classify_reason_string("fallback deterministic seed")
    assert r.code == "central_candidate"


def test_classify_incident_to_selected_entity() -> None:
    r = classify_reason_string("incident to selected entity")
    assert r.code == "central_candidate"


def test_classify_unknown_string_falls_back_to_central_candidate() -> None:
    r = classify_reason_string("something completely unrecognized xyz123")
    assert r.code == "central_candidate"


# ---------------------------------------------------------------------------
# build_selection_reasons — integration
# ---------------------------------------------------------------------------


def test_build_selection_reasons_basic() -> None:
    reasons_by_key = {
        "python:module:resolvers": (
            'lexical match on source path "resolvers.py"',
            "path prior (+4.0)",
        ),
        "python:module:conf": ("support: imports django/urls/conf.py",),
    }
    result = build_selection_reasons(reasons_by_key)
    assert set(result.keys()) == {"python:module:resolvers", "python:module:conf"}

    resolvers = result["python:module:resolvers"]
    assert len(resolvers) == 2
    assert resolvers[0].code == "lexical_match"
    assert resolvers[1].code == "path_prior"
    assert resolvers[1].detail == "+4.0"

    conf = result["python:module:conf"]
    assert len(conf) == 1
    assert conf[0].code == "support_import"


def test_build_selection_reasons_deduplicates() -> None:
    reasons_by_key = {
        "python:module:foo": (
            "lexical baseline relevance",
            "lexical baseline relevance",
        ),
    }
    result = build_selection_reasons(reasons_by_key)
    assert len(result["python:module:foo"]) == 1


def test_build_selection_reasons_sorted_keys() -> None:
    reasons_by_key = {
        "z:module": ("fallback deterministic seed",),
        "a:module": ("fallback deterministic seed",),
    }
    result = build_selection_reasons(reasons_by_key)
    assert list(result.keys()) == ["a:module", "z:module"]


def test_build_selection_reasons_skips_empty_entries() -> None:
    reasons_by_key: dict[str, tuple[str, ...]] = {
        "python:module:foo": (),
        "python:module:bar": ("lexical baseline relevance",),
    }
    result = build_selection_reasons(reasons_by_key)
    assert "python:module:foo" not in result
    assert "python:module:bar" in result


def test_build_selection_reasons_empty_input() -> None:
    result = build_selection_reasons({})
    assert result == {}


def test_build_selection_reasons_all_reason_types() -> None:
    """End-to-end: all pipeline stages contribute reasons; all classify correctly."""
    reasons_by_key = {
        "seed:entity": (
            'lexical match on source path "resolvers.py"',
            "test task hint -> boosted test root",
        ),
        "graph:entity": ("graph neighbor via imports (depth=1, score=3.500) from seed:entity",),
        "support:entity": ("support: imports lib/ansible/executor/module_common.py",),
        "test:entity": ("test branch: tests relation to tests/urlpatterns/test_resolvers.py",),
    }
    result = build_selection_reasons(reasons_by_key)

    assert result["seed:entity"][0].code == "lexical_match"
    assert result["seed:entity"][1].code == "intent_match"
    assert result["graph:entity"][0].code == "graph_neighbor"
    assert result["support:entity"][0].code == "support_import"
    assert result["test:entity"][0].code == "test_relation"
