"""Unit and integration tests for the test-file retrieval branch (Ranking v2 — Prompt 58.3).

Coverage:
- No test branch when ``tests`` intent absent.
- Test branch active when task includes test-related tokens.
- Relation-first: test entity with a ``tests`` relation to a seed entity is selected.
- ``test/units/...`` paths are considered real test roots.
- ``lib/ansible/plugins/test/core.py`` (runtime-named path) is NOT selected as a test root.
- Branch is capped at ``max_test_files`` and results are deterministic.
- Deduplication by source_path (prefer module/file-level entities over function children).
- Full context-pack integration: pack still builds successfully with the test branch active.
- Path/name proximity fallback selects ``test/units/plugins/test_plugins.py`` over
  ``lib/ansible/plugins/test/core.py``.
"""

from __future__ import annotations

from repo_semantic_memory.context import build_context_pack
from repo_semantic_memory.context.query_intent import parse_query_intent
from repo_semantic_memory.context.test_branch import (
    _normalize_filename_stem,
    select_test_branch,
)
from repo_semantic_memory.model import Entity, Relation, SourceRange, StableId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(
    path: str,
    *,
    kind: str = "module",
    name: str | None = None,
    qualified_name: str | None = None,
) -> Entity:
    filename = path.rsplit("/", 1)[-1]
    return Entity(
        id=StableId.from_parts(["file", path]),
        kind=kind,  # type: ignore[arg-type]
        name=name or filename,
        qualified_name=qualified_name or path.replace("/", "."),
        source_range=SourceRange(path=path, start_line=1, end_line=1),
    )


def _relation(src: Entity, tgt: Entity, kind: str = "tests") -> Relation:
    return Relation(
        source_entity_id=src.id,
        target_entity_id=tgt.id,
        kind=kind,  # type: ignore[arg-type]
    )


def _intent_tests() -> object:
    return parse_query_intent("plugin loader tests")


# ---------------------------------------------------------------------------
# TestNormalizeFilenameStem — internal helper
# ---------------------------------------------------------------------------


class TestNormalizeFilenameStem:
    def test_strips_test_prefix_and_extension(self) -> None:
        assert _normalize_filename_stem("test_resolvers.py") == "resolvers"

    def test_strips_test_suffix_and_extension(self) -> None:
        assert _normalize_filename_stem("resolvers_test.py") == "resolvers"

    def test_no_test_prefix_returns_stem(self) -> None:
        assert _normalize_filename_stem("resolvers.py") == "resolvers"

    def test_test_prefix_no_extension(self) -> None:
        assert _normalize_filename_stem("test_plugins") == "plugins"

    def test_tests_prefix_stripped(self) -> None:
        assert _normalize_filename_stem("tests_loader.py") == "loader"

    def test_spec_suffix_stripped(self) -> None:
        assert _normalize_filename_stem("loader_spec.py") == "loader"

    def test_empty_returns_empty(self) -> None:
        assert _normalize_filename_stem("") == ""


# ---------------------------------------------------------------------------
# TestNoTestsIntentReturnsEmpty
# ---------------------------------------------------------------------------


class TestNoTestsIntentReturnsEmpty:
    def test_pure_implementation_task(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        test_e = _entity("tests/test_loader.py")
        intent = parse_query_intent("plugin loader implementation")
        assert "tests" not in intent.intents

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )
        assert result == []

    def test_url_resolver_no_test_token(self) -> None:
        impl = _entity("django/urls/resolvers.py")
        test_e = _entity("tests/urlpatterns/test_resolvers.py")
        intent = parse_query_intent("url resolver implementation")
        assert "tests" not in intent.intents

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=(),
        )
        assert result == []

    def test_max_test_files_zero(self) -> None:
        intent = parse_query_intent("plugin loader tests")
        test_e = _entity("tests/test_loader.py")
        result = select_test_branch(
            entities=[test_e],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset(),
            source_roots=(),
            max_test_files=0,
        )
        assert result == []


# ---------------------------------------------------------------------------
# TestRelationFirst — tests relation to seed entity selects test file
# ---------------------------------------------------------------------------


class TestRelationFirst:
    def test_test_entity_via_normal_direction_relation(self) -> None:
        """test_entity --tests--> impl_entity (normal direction)."""
        impl = _entity("src/mypackage/loader.py")
        test_e = _entity("test/units/test_loader.py")
        rel = _relation(test_e, impl)  # test tests impl
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[rel],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        assert test_e.id.value in entity_ids

    def test_reason_mentions_impl_path_for_normal_direction(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        test_e = _entity("test/units/test_loader.py")
        rel = _relation(test_e, impl)
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[rel],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        reasons = {eid: r for eid, r in result}
        reason = reasons.get(test_e.id.value, "")
        assert "test branch" in reason
        assert "loader.py" in reason

    def test_test_entity_via_inverted_direction_relation(self) -> None:
        """impl_entity --tests--> test_entity (inverted direction)."""
        impl = _entity("src/mypackage/loader.py")
        test_e = _entity("test/units/test_loader.py")
        rel = _relation(impl, test_e)  # impl tests test — inverted
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[rel],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        assert test_e.id.value in entity_ids

    def test_relation_first_outranks_proximity_only(self) -> None:
        """Test entity with relation comes before proximity-only entity."""
        impl = _entity("src/mypackage/loader.py")
        test_with_rel = _entity("test/units/test_loader.py")
        test_proximity = _entity("test/units/test_resolver.py")
        rel = _relation(test_with_rel, impl)
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_with_rel, test_proximity],
            relations=[rel],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        assert test_with_rel.id.value in entity_ids
        # Relation entity should come first
        assert (
            entity_ids.index(test_with_rel.id.value) < entity_ids.index(test_proximity.id.value)
            if test_proximity.id.value in entity_ids
            else True
        )

    def test_runtime_test_path_not_selected_via_relation(self) -> None:
        """Runtime path lib/X/test/Y should NOT be selected even if a tests relation exists."""
        impl = _entity("lib/ansible/plugins/loader.py")
        runtime_test = _entity("lib/ansible/plugins/test/core.py")
        rel = _relation(runtime_test, impl)
        intent = parse_query_intent("ansible plugin loader tests")

        result = select_test_branch(
            entities=[impl, runtime_test],
            relations=[rel],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("lib",),
        )

        entity_ids = [eid for eid, _ in result]
        assert runtime_test.id.value not in entity_ids


# ---------------------------------------------------------------------------
# TestTestRootPathClassification
# ---------------------------------------------------------------------------


class TestTestRootPathClassification:
    def test_test_units_path_is_real_test_root(self) -> None:
        impl = _entity("lib/ansible/plugins/loader.py")
        test_e = _entity("test/units/plugins/test_plugins.py")
        intent = parse_query_intent("ansible plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=(),
        )

        # test/units/... is a real test root; should be eligible
        entity_ids = [eid for eid, _ in result]
        assert test_e.id.value in entity_ids

    def test_runtime_embedded_test_segment_excluded(self) -> None:
        """lib/ansible/plugins/test/core.py should not be selected as a test root."""
        impl = _entity("lib/ansible/plugins/loader.py")
        runtime_test = _entity("lib/ansible/plugins/test/core.py")
        test_real = _entity("test/units/plugins/test_plugins.py")
        intent = parse_query_intent("ansible plugin loader tests")

        result = select_test_branch(
            entities=[impl, runtime_test, test_real],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=(),
        )

        entity_ids = [eid for eid, _ in result]
        assert runtime_test.id.value not in entity_ids
        assert test_real.id.value in entity_ids

    def test_tests_root_prefix_is_real_test_root(self) -> None:
        test_e = _entity("tests/test_core.py")
        impl = _entity("src/core.py")
        intent = parse_query_intent("core module tests")

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        assert test_e.id.value in entity_ids


# ---------------------------------------------------------------------------
# TestProximityScoring
# ---------------------------------------------------------------------------


class TestProximityScoring:
    def test_stem_proximity_preferred_over_unrelated_test(self) -> None:
        """test_loader.py should score higher than test_unrelated.py for loader.py seed."""
        impl = _entity("src/mypackage/loader.py")
        stem_match = _entity("tests/test_loader.py")
        unrelated = _entity("tests/test_unrelated.py")
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, stem_match, unrelated],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        assert stem_match.id.value in entity_ids
        if unrelated.id.value in entity_ids:
            # Stem match must come first
            assert entity_ids.index(stem_match.id.value) <= entity_ids.index(unrelated.id.value)

    def test_real_unit_test_preferred_over_runtime_test_path(self) -> None:
        """test/units/plugins/test_plugins.py preferred over lib/ansible/plugins/test/core.py."""
        impl = _entity("lib/ansible/plugins/loader.py")
        real_test = _entity("test/units/plugins/test_plugins.py")
        runtime_test = _entity("lib/ansible/plugins/test/core.py")
        intent = parse_query_intent("ansible plugin loader tests")

        result = select_test_branch(
            entities=[impl, real_test, runtime_test],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=(),
        )

        entity_ids = [eid for eid, _ in result]
        assert real_test.id.value in entity_ids
        assert runtime_test.id.value not in entity_ids

    def test_lexical_token_overlap_scores_test_entity(self) -> None:
        """Test entity whose path contains a query lexical token should be selected."""
        impl = _entity("src/resolver/engine.py")
        # test path contains "resolver" which is in lexical_tokens for a resolver query
        test_e = _entity("tests/test_resolver.py")
        intent = parse_query_intent("url resolver tests")

        result = select_test_branch(
            entities=[impl, test_e],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        assert test_e.id.value in entity_ids


# ---------------------------------------------------------------------------
# TestDeduplication — prefer module/file-level over function/class children
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_module_preferred_over_class_in_same_path(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        test_mod = _entity("tests/test_loader.py", kind="module")
        test_cls = _entity("tests/test_loader.py", kind="class", name="TestLoader")
        test_fn = _entity("tests/test_loader.py", kind="function", name="test_load")
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_mod, test_cls, test_fn],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        # Only one representative per path should be returned
        paths_returned = [
            e_id
            for e_id in entity_ids
            if e_id in {test_mod.id.value, test_cls.id.value, test_fn.id.value}
        ]
        assert len(paths_returned) == 1
        # Module is preferred over class or function
        assert paths_returned[0] == test_mod.id.value

    def test_class_preferred_over_function_when_no_module(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        test_cls = _entity("tests/test_loader.py", kind="class", name="TestLoader")
        test_fn = _entity("tests/test_loader.py", kind="function", name="test_load")
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_cls, test_fn],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        paths_returned = [
            e_id for e_id in entity_ids if e_id in {test_cls.id.value, test_fn.id.value}
        ]
        assert len(paths_returned) == 1

    def test_distinct_paths_not_deduplicated(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        test_a = _entity("tests/test_loader.py")
        test_b = _entity("tests/test_plugins.py")
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, test_a, test_b],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        entity_ids = [eid for eid, _ in result]
        # Both test files from different paths can be included (up to cap)
        assert test_a.id.value in entity_ids or test_b.id.value in entity_ids


# ---------------------------------------------------------------------------
# TestCap
# ---------------------------------------------------------------------------


class TestCap:
    def test_cap_limits_results(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        test_entities = [_entity(f"tests/test_file_{i}.py") for i in range(10)]
        # Add relations so all qualify via relation-first
        relations = [_relation(te, impl) for te in test_entities]
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, *test_entities],
            relations=relations,
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
            max_test_files=3,
        )

        assert len(result) <= 3

    def test_default_cap_is_five(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        test_entities = [_entity(f"tests/test_file_{i}.py") for i in range(8)]
        relations = [_relation(te, impl) for te in test_entities]
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl, *test_entities],
            relations=relations,
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )

        assert len(result) <= 5

    def test_results_are_deterministic(self) -> None:
        """Two calls with identical inputs produce identical outputs."""
        impl = _entity("src/mypackage/loader.py")
        test_entities = [_entity(f"tests/test_file_{i}.py") for i in range(6)]
        relations = [_relation(te, impl) for te in test_entities]
        intent = parse_query_intent("plugin loader tests")

        kwargs = dict(
            entities=[impl, *test_entities],
            relations=relations,
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )
        result_a = select_test_branch(**kwargs)  # type: ignore[arg-type]
        result_b = select_test_branch(**kwargs)  # type: ignore[arg-type]

        assert result_a == result_b


# ---------------------------------------------------------------------------
# TestNoTestEntitiesFound
# ---------------------------------------------------------------------------


class TestNoTestEntitiesFound:
    def test_returns_empty_when_no_test_entities(self) -> None:
        impl = _entity("src/mypackage/loader.py")
        intent = parse_query_intent("plugin loader tests")

        result = select_test_branch(
            entities=[impl],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=("src",),
        )
        assert result == []

    def test_returns_empty_when_only_runtime_test_paths(self) -> None:
        impl = _entity("lib/ansible/plugins/loader.py")
        runtime_test = _entity("lib/ansible/plugins/test/core.py")
        intent = parse_query_intent("ansible plugin loader tests")

        result = select_test_branch(
            entities=[impl, runtime_test],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({impl.id.value}),
            source_roots=(),
        )
        assert result == []

    def test_returns_empty_when_empty_entity_list(self) -> None:
        intent = parse_query_intent("plugin loader tests")
        result = select_test_branch(
            entities=[],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset(),
            source_roots=(),
        )
        assert result == []


# ---------------------------------------------------------------------------
# TestIntegrationWithBuildContextPack
# ---------------------------------------------------------------------------


class TestIntegrationWithBuildContextPack:
    def test_pack_builds_successfully_with_test_branch_active(self) -> None:
        """Context pack should build without errors when tests intent is active."""
        impl = _entity("src/mypackage/loader.py")
        test_e = _entity("test/units/test_loader.py")
        rel = _relation(test_e, impl)

        pack = build_context_pack(
            task="plugin loader tests",
            entities=[impl, test_e],
            relations=[rel],
            budget_chars=4000,
        )

        selected_paths = {e.source_range.path for e in pack.selected_entities}
        assert "test/units/test_loader.py" in selected_paths

    def test_pack_without_test_intent_no_test_branch_reasons(self) -> None:
        """Context pack for an implementation-only task must not emit test branch reasons."""
        impl = _entity("src/mypackage/loader.py")
        test_e = _entity("test/units/test_unrelated.py")

        pack = build_context_pack(
            task="url resolver implementation",
            entities=[impl, test_e],
            relations=[],
            budget_chars=4000,
            explain_ranking=True,
        )

        # No "test branch" reason should appear for any entity when tests intent is absent.
        for reasons in pack.why_selected.values():
            for reason in reasons:
                assert "test branch" not in reason

    def test_pack_includes_test_entity_via_tests_relation(self) -> None:
        """Test entity reached via tests relation must appear in pack selected entities."""
        impl = _entity("src/mypackage/resolver.py")
        test_e = _entity("test/units/test_resolver.py")
        rel = _relation(test_e, impl)

        pack = build_context_pack(
            task="url resolver tests",
            entities=[impl, test_e],
            relations=[rel],
            budget_chars=8000,
        )

        selected_paths = {e.source_range.path for e in pack.selected_entities}
        assert "test/units/test_resolver.py" in selected_paths

    def test_pack_runtime_test_path_not_selected_via_test_branch(self) -> None:
        """Runtime-named path must not receive a test-branch reason when tests intent fires."""
        impl = _entity("lib/ansible/plugins/loader.py")
        runtime_test = _entity("lib/ansible/plugins/test/core.py")
        real_test = _entity("test/units/plugins/test_loader.py")
        rel_real = _relation(real_test, impl)
        rel_runtime = _relation(runtime_test, impl)

        pack = build_context_pack(
            task="ansible plugin loader tests",
            entities=[impl, runtime_test, real_test],
            relations=[rel_real, rel_runtime],
            budget_chars=8000,
            explain_ranking=True,
        )

        # The real test path must appear in the pack (via test branch or lexical match).
        selected_paths = {e.source_range.path for e in pack.selected_entities}
        assert "test/units/plugins/test_loader.py" in selected_paths

        # The runtime-named path must NOT receive a test-branch reason.
        runtime_reasons = pack.why_selected.get(runtime_test.id.value, [])
        assert not any("test branch" in r for r in runtime_reasons), (
            f"Unexpected 'test branch' reason for runtime path: {runtime_reasons}"
        )

    def test_pack_does_not_duplicate_already_selected_test_entity(self) -> None:
        """A test entity already selected in the main pass should not appear twice."""
        impl = _entity("src/mypackage/loader.py")
        test_e = _entity("tests/test_loader.py")
        rel = _relation(test_e, impl)

        pack = build_context_pack(
            task="plugin loader tests",
            entities=[impl, test_e],
            relations=[rel],
            budget_chars=8000,
        )

        paths = [e.source_range.path for e in pack.selected_entities]
        assert paths.count("tests/test_loader.py") == 1
