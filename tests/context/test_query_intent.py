"""Tests for the deterministic query intent parser (Ranking v2, Prompt 58.1)."""

from __future__ import annotations

from repo_semantic_memory.context.pack_builder import _build_bm25_index, _score_entity
from repo_semantic_memory.context.query_intent import (
    _DOMAIN_TOKEN_ALLOWLIST,
    _GENERIC_STOP_TOKENS,
    _INTENT_ONLY_TOKENS,
    QueryIntent,
    parse_query_intent,
)
from repo_semantic_memory.model import Entity, SourceRange, StableId

# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


def test_detects_tests_intent_from_token_test() -> None:
    intent = parse_query_intent("Find tests for URL resolver")
    assert "tests" in intent.intents


def test_detects_tests_intent_from_token_tests() -> None:
    intent = parse_query_intent("Find tests for activation gating behavior")
    assert "tests" in intent.intents


def test_detects_tests_intent_from_coverage() -> None:
    intent = parse_query_intent("Where is the coverage for this module")
    assert "tests" in intent.intents


def test_detects_tests_intent_from_pytest() -> None:
    intent = parse_query_intent("Run pytest for the resolver module")
    assert "tests" in intent.intents


def test_detects_public_api_intent() -> None:
    intent = parse_query_intent("Show the public API exports for httpx")
    assert "public_api" in intent.intents


def test_detects_public_api_intent_from_init() -> None:
    intent = parse_query_intent("Find the __init__ exports for this package")
    assert "public_api" in intent.intents


def test_detects_implementation_intent_from_explicit_token() -> None:
    intent = parse_query_intent("Find where URL resolver is implemented")
    assert "implementation" in intent.intents


def test_detects_implementation_intent_from_core_logic() -> None:
    intent = parse_query_intent("Find the core logic of the routing pipeline")
    assert "implementation" in intent.intents


def test_detects_architecture_flow_intent_from_dispatch() -> None:
    intent = parse_query_intent("How does URL dispatch flow through the handler")
    assert "architecture_flow" in intent.intents


def test_detects_architecture_flow_intent_from_routing() -> None:
    intent = parse_query_intent("Explain the routing lifecycle")
    assert "architecture_flow" in intent.intents


def test_detects_error_handling_intent() -> None:
    intent = parse_query_intent("Find where exceptions are raised and handled")
    assert "error_handling" in intent.intents


def test_detects_config_build_intent() -> None:
    intent = parse_query_intent("Find the pyproject build configuration")
    assert "config_build_release" in intent.intents


def test_multiple_intents_can_fire() -> None:
    intent = parse_query_intent("Find tests for the public API implementation")
    assert "tests" in intent.intents
    assert "public_api" in intent.intents
    assert "implementation" in intent.intents


def test_pure_domain_query_triggers_architecture_flow() -> None:
    """Tokens like 'handler' and 'dispatch' trigger the architecture_flow intent."""
    intent = parse_query_intent("url resolver handler dispatch")
    # "handler" and "dispatch" are architecture-flow signal tokens.
    assert "architecture_flow" in intent.intents


# ---------------------------------------------------------------------------
# Generic token downweighting
# ---------------------------------------------------------------------------


def test_find_is_downweighted() -> None:
    intent = parse_query_intent("Find how plugin loading works")
    assert "find" in intent.downweighted_tokens
    assert "find" not in intent.lexical_tokens


def test_how_is_downweighted() -> None:
    intent = parse_query_intent("Find how plugin loading works")
    assert "how" in intent.downweighted_tokens
    assert "how" not in intent.lexical_tokens


def test_files_is_downweighted() -> None:
    intent = parse_query_intent("Find implementation files for URL routing")
    assert "files" in intent.downweighted_tokens
    assert "files" not in intent.lexical_tokens


def test_where_is_downweighted() -> None:
    intent = parse_query_intent("Where is the resolver implemented")
    assert "where" in intent.downweighted_tokens
    assert "where" not in intent.lexical_tokens


def test_implementation_token_is_intent_only_not_lexical() -> None:
    intent = parse_query_intent("Find implementation files for URL routing")
    assert "implementation" in intent.downweighted_tokens
    assert "implementation" not in intent.lexical_tokens


def test_test_token_is_intent_only_not_lexical() -> None:
    intent = parse_query_intent("Find tests for URL resolver")
    assert "test" not in intent.lexical_tokens
    # "tests" is also intent-only
    intent2 = parse_query_intent("Find tests for plugin loader")
    assert "tests" not in intent2.lexical_tokens


def test_behavior_is_downweighted() -> None:
    intent = parse_query_intent("Find tests for activation gating behavior")
    assert "behavior" in intent.downweighted_tokens
    assert "behavior" not in intent.lexical_tokens


def test_code_is_downweighted() -> None:
    intent = parse_query_intent("Find code for URL resolver")
    assert "code" in intent.downweighted_tokens
    assert "code" not in intent.lexical_tokens


def test_works_is_downweighted() -> None:
    # tokenize_text produces "works" (not "work") for this input
    intent = parse_query_intent("Find how plugin loading works and how it works")
    assert "works" in intent.downweighted_tokens
    assert "works" not in intent.lexical_tokens


# ---------------------------------------------------------------------------
# Domain token preservation
# ---------------------------------------------------------------------------


def test_loader_is_preserved() -> None:
    intent = parse_query_intent("Find how plugin loader works")
    assert "loader" in intent.lexical_tokens


def test_resolver_is_preserved() -> None:
    intent = parse_query_intent("Find how URL resolver works")
    assert "resolver" in intent.lexical_tokens


def test_handler_is_preserved() -> None:
    intent = parse_query_intent("Find how request handler dispatches")
    assert "handler" in intent.lexical_tokens


def test_dispatch_is_preserved() -> None:
    intent = parse_query_intent("Find dispatch flow")
    assert "dispatch" in intent.lexical_tokens


def test_url_is_preserved() -> None:
    intent = parse_query_intent("Find URL routing implementation")
    assert "url" in intent.lexical_tokens


def test_plugin_is_preserved() -> None:
    intent = parse_query_intent("Find how plugin loading works")
    assert "plugin" in intent.lexical_tokens


def test_timeout_is_preserved() -> None:
    intent = parse_query_intent("Find timeout configuration")
    assert "timeout" in intent.lexical_tokens
    assert "configuration" in intent.lexical_tokens


def test_transport_is_preserved() -> None:
    intent = parse_query_intent("Find transport architecture")
    assert "transport" in intent.lexical_tokens
    assert "architecture" in intent.lexical_tokens


def test_middleware_is_preserved() -> None:
    intent = parse_query_intent("Find middleware dispatch flow")
    assert "middleware" in intent.lexical_tokens


# ---------------------------------------------------------------------------
# Backward-compatibility: simple domain-heavy queries unchanged
# ---------------------------------------------------------------------------


def test_domain_heavy_query_timeout_configuration_unchanged() -> None:
    intent = parse_query_intent("timeout configuration")
    assert "timeout" in intent.lexical_tokens
    assert "configuration" in intent.lexical_tokens
    assert not intent.downweighted_tokens


def test_domain_heavy_query_plugin_loader_unchanged() -> None:
    intent = parse_query_intent("plugin loader")
    assert "plugin" in intent.lexical_tokens
    assert "loader" in intent.lexical_tokens
    assert not intent.downweighted_tokens


def test_domain_heavy_query_url_resolver_unchanged() -> None:
    intent = parse_query_intent("URL resolver")
    assert "url" in intent.lexical_tokens
    assert "resolver" in intent.lexical_tokens


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_parse_query_intent_is_deterministic() -> None:
    task = "Find how URL resolver implementation files work including tests"
    result1 = parse_query_intent(task)
    result2 = parse_query_intent(task)
    assert result1 == result2


def test_parse_query_intent_returns_query_intent_instance() -> None:
    result = parse_query_intent("Find where activation gating is implemented")
    assert isinstance(result, QueryIntent)
    assert isinstance(result.intents, frozenset)
    assert isinstance(result.lexical_tokens, tuple)
    assert isinstance(result.downweighted_tokens, tuple)
    assert isinstance(result.domain_tokens, tuple)


# ---------------------------------------------------------------------------
# Domain allowlist integrity
# ---------------------------------------------------------------------------


def test_domain_tokens_not_in_generic_stop_set() -> None:
    """No domain-allowlisted token should appear in the stop-set."""
    overlap = _DOMAIN_TOKEN_ALLOWLIST & _GENERIC_STOP_TOKENS
    assert not overlap, f"Domain tokens found in stop-set: {overlap}"


def test_domain_tokens_not_in_intent_only_set() -> None:
    """No domain-allowlisted token should be in the intent-only set."""
    overlap = _DOMAIN_TOKEN_ALLOWLIST & _INTENT_ONLY_TOKENS
    assert not overlap, f"Domain tokens found in intent-only set: {overlap}"


# ---------------------------------------------------------------------------
# Ranking effect: generic tokens must not boost noise paths
# ---------------------------------------------------------------------------


def _make_entity(entity_id: str, name: str, qualified_name: str, path: str) -> Entity:
    return Entity(
        id=StableId(entity_id),
        kind="module",
        name=name,
        qualified_name=qualified_name,
        source_range=SourceRange(path=path, start_line=1, end_line=1),
    )


def _lexical_scores_for_entities(entities: list[Entity], task: str) -> dict[str, float]:
    """Score multiple entities in a shared BM25 index using lexical_tokens."""
    qi = parse_query_intent(task)
    bm25_index = _build_bm25_index(
        entities=entities,
        component_labels_by_entity={},
        relation_labels_by_entity={},
    )
    scores: dict[str, float] = {}
    for entity in entities:
        breakdown = _score_entity(
            entity,
            qi.lexical_tokens,
            bm25_index=bm25_index,
            is_code_task=False,
            task_hints=set(),
            public_api_entity_ids=set(),
            export_source_entity_ids=set(),
            export_target_entity_ids=set(),
            source_roots=[],
        )
        scores[str(entity.id)] = breakdown.lexical
    return scores


def test_find_token_does_not_boost_find_py_module() -> None:
    """Token 'find' must not give a lexical advantage to a module named find.py."""
    find_module = _make_entity(
        "python:module:ansible.modules.find",
        "find",
        "ansible.modules.find",
        "lib/ansible/modules/find.py",
    )
    plugin_loader = _make_entity(
        "python:module:ansible.plugins.loader",
        "loader",
        "ansible.plugins.loader",
        "lib/ansible/plugins/loader.py",
    )
    entities = [find_module, plugin_loader]
    # "Find how plugin loading works" → 'find' is stripped; loader should match at least as well
    scores = _lexical_scores_for_entities(entities, "Find how plugin loading works")
    assert (
        scores["python:module:ansible.plugins.loader"]
        >= scores["python:module:ansible.modules.find"]
    ), "Generic 'find' token must not make find.py outscore the domain-matching loader.py"


def test_files_token_does_not_boost_files_storage_path() -> None:
    """Token 'files' must not boost django/core/files/storage.py above the resolver."""
    resolver = _make_entity(
        "python:module:django.urls.resolvers",
        "resolvers",
        "django.urls.resolvers",
        "django/urls/resolvers.py",
    )
    storage = _make_entity(
        "python:module:django.core.files.storage",
        "storage",
        "django.core.files.storage",
        "django/core/files/storage.py",
    )
    entities = [resolver, storage]
    scores = _lexical_scores_for_entities(entities, "Find URL resolvers implementation files work")
    assert (
        scores["python:module:django.urls.resolvers"]
        >= scores["python:module:django.core.files.storage"]
    ), "Generic 'files' token must not make storage.py outscore the domain-matching resolvers.py"


def test_domain_token_still_ranks_domain_path() -> None:
    """Domain token 'resolvers' must still provide a lexical advantage to the resolver module."""
    resolver = _make_entity(
        "python:module:django.urls.resolvers",
        "resolvers",
        "django.urls.resolvers",
        "django/urls/resolvers.py",
    )
    noise = _make_entity(
        "python:module:django.contrib.staticfiles.finders",
        "finders",
        "django.contrib.staticfiles.finders",
        "django/contrib/staticfiles/finders.py",
    )
    entities = [resolver, noise]
    # Use "resolvers" (plural) so the token matches the indexed path/name tokens exactly;
    # BM25 has no stemming so "resolver" ≠ "resolvers" in the index.
    task = "Find how URL resolvers implementation files work"
    scores = _lexical_scores_for_entities(entities, task)
    assert (
        scores["python:module:django.urls.resolvers"]
        > scores["python:module:django.contrib.staticfiles.finders"]
    ), (
        f"Resolver score {scores['python:module:django.urls.resolvers']} "
        f"should exceed noise score {scores['python:module:django.contrib.staticfiles.finders']}"
    )
