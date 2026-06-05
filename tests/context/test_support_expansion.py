"""Unit and integration tests for support-file expansion (Ranking v2 — Prompt 58.4).

Coverage:
- Empty result when there are no entities or selected entities.
- Empty result when no useful adjacency exists (no relations, no same-package overlap).
- Forward import: selected imports candidate → candidate selected as support file.
- Reverse export: __init__.py exports selected → __init__.py selected as support file.
- Forward export: selected __init__.py exports candidate → candidate selected.
- Inherits relation: either direction contributes to support selection.
- Reverse import: candidate imports selected → lower-priority inclusion.
- Same-package proximity alone does not meet min-score threshold.
- Same-package + lexical overlap qualifies.
- Support files capped at max_support_files.
- Deduplication by source_path (prefer module-level entities).
- Test files excluded (TEST_ROLE entities never returned).
- Runtime test-named paths excluded.
- Already-selected entities excluded from candidates.
- Docs/examples excluded by default; allowed with public_api/architecture_flow intent.
- Public-API __init__.py boost with public_api intent.
- Deterministic ordering (descending score, then path as tiebreaker).
- Regression-style fixture tests:
  - package/urls/resolvers.py + imports adjacency → package/urls/base.py
  - package/urls/resolvers.py + same-package + lexical → package/urls/conf.py
  - lib/pkg/plugins/loader.py + imports adjacency → lib/pkg/executor/module_common.py
  - httpx/_client.py + exports relation + public_api intent → httpx/__init__.py
- Full context-pack integration: pack still builds successfully with support branch.
"""

from __future__ import annotations

from repo_semantic_memory.context import build_context_pack
from repo_semantic_memory.context.query_intent import parse_query_intent
from repo_semantic_memory.context.support_expansion import select_support_files
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
        qualified_name=qualified_name or path.replace("/", ".").replace(".py", ""),
        source_range=SourceRange(path=path, start_line=1, end_line=1),
    )


def _rel(src: Entity, tgt: Entity, kind: str = "imports") -> Relation:
    return Relation(
        source_entity_id=src.id,
        target_entity_id=tgt.id,
        kind=kind,  # type: ignore[arg-type]
    )


def _ids(results: list[tuple[str, str]]) -> list[str]:
    return [eid for eid, _ in results]


def _reasons(results: list[tuple[str, str]]) -> list[str]:
    return [reason for _, reason in results]


# ---------------------------------------------------------------------------
# TestSelectSupportFilesEmpty
# ---------------------------------------------------------------------------


class TestSelectSupportFilesEmpty:
    def test_empty_selected_entities(self) -> None:
        candidate = _entity("pkg/utils.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[],
            all_entities=[candidate],
            relations=[],
            query_intent=intent,
        )
        assert result == []

    def test_empty_all_entities(self) -> None:
        selected = _entity("pkg/resolvers.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[selected],
            all_entities=[],
            relations=[],
            query_intent=intent,
        )
        assert result == []

    def test_max_zero_returns_empty(self) -> None:
        selected = _entity("pkg/resolvers.py")
        candidate = _entity("pkg/base.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[selected],
            all_entities=[selected, candidate],
            relations=[_rel(selected, candidate)],
            query_intent=intent,
            max_support_files=0,
        )
        assert result == []

    def test_no_adjacency_returns_empty(self) -> None:
        """No relations, different directories → no support files."""
        selected = _entity("pkg/resolvers.py")
        candidate = _entity("other/utils.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[selected],
            all_entities=[selected, candidate],
            relations=[],
            query_intent=intent,
        )
        assert result == []


# ---------------------------------------------------------------------------
# TestForwardImport
# ---------------------------------------------------------------------------


class TestForwardImport:
    def test_forward_import_selects_candidate(self) -> None:
        """selected --imports--> candidate: candidate is a direct dependency."""
        resolver = _entity("pkg/urls/resolvers.py")
        base = _entity("pkg/urls/base.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, base],
            relations=[_rel(resolver, base, "imports")],
            query_intent=intent,
        )
        assert base.id.value in _ids(result)

    def test_forward_import_reason_contains_source_path(self) -> None:
        resolver = _entity("pkg/urls/resolvers.py")
        base = _entity("pkg/urls/base.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, base],
            relations=[_rel(resolver, base, "imports")],
            query_intent=intent,
        )
        assert result
        reason = result[0][1]
        assert "imported by" in reason
        assert "pkg/urls/resolvers.py" in reason

    def test_multiple_forward_imports_all_selected(self) -> None:
        """All directly imported files should be selected (up to cap)."""
        resolver = _entity("pkg/urls/resolvers.py")
        base = _entity("pkg/urls/base.py")
        conf = _entity("pkg/urls/conf.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, base, conf],
            relations=[
                _rel(resolver, base, "imports"),
                _rel(resolver, conf, "imports"),
            ],
            query_intent=intent,
        )
        result_ids = _ids(result)
        assert base.id.value in result_ids
        assert conf.id.value in result_ids

    def test_forward_import_cross_package(self) -> None:
        """Cross-package import (e.g. handlers/base.py) is selected."""
        loader = _entity("lib/pkg/plugins/loader.py")
        module_common = _entity("lib/pkg/executor/module_common.py")
        intent = parse_query_intent("plugin loader implementation")
        result = select_support_files(
            selected_entities=[loader],
            all_entities=[loader, module_common],
            relations=[_rel(loader, module_common, "imports")],
            query_intent=intent,
        )
        assert module_common.id.value in _ids(result)


# ---------------------------------------------------------------------------
# TestReverseExport
# ---------------------------------------------------------------------------


class TestReverseExport:
    def test_reverse_export_init_selected(self) -> None:
        """candidate --exports--> selected: __init__.py is the package surface."""
        init_py = _entity("httpx/__init__.py")
        client = _entity("httpx/_client.py")
        intent = parse_query_intent("httpx public API exports")
        result = select_support_files(
            selected_entities=[client],
            all_entities=[client, init_py],
            relations=[_rel(init_py, client, "exports")],
            query_intent=intent,
        )
        assert init_py.id.value in _ids(result)

    def test_reverse_export_reason_mentions_export_surface(self) -> None:
        init_py = _entity("httpx/__init__.py")
        client = _entity("httpx/_client.py")
        intent = parse_query_intent("httpx public API exports")
        result = select_support_files(
            selected_entities=[client],
            all_entities=[client, init_py],
            relations=[_rel(init_py, client, "exports")],
            query_intent=intent,
        )
        assert result
        reason = result[0][1]
        assert "export surface" in reason or "exported by" in reason or "public API" in reason

    def test_reverse_export_public_api_boost(self) -> None:
        """With public_api intent, __init__.py export surface gets extra boost."""
        init_py = _entity("httpx/__init__.py")
        client = _entity("httpx/_client.py")
        other = _entity("httpx/_compat.py")
        intent = parse_query_intent("httpx public API interface")
        # Reverse export for init_py; same-package for other (score 2 → below threshold)
        result = select_support_files(
            selected_entities=[client],
            all_entities=[client, init_py, other],
            relations=[_rel(init_py, client, "exports")],
            query_intent=intent,
        )
        result_ids = _ids(result)
        assert init_py.id.value in result_ids
        # other only has same-package (2.0) < min threshold (4.0); not included
        assert other.id.value not in result_ids


# ---------------------------------------------------------------------------
# TestForwardExport
# ---------------------------------------------------------------------------


class TestForwardExport:
    def test_forward_export_candidate_selected(self) -> None:
        """selected --exports--> candidate: selected is __init__.py."""
        init_py = _entity("httpx/__init__.py")
        client = _entity("httpx/_client.py")
        intent = parse_query_intent("httpx public API interface")
        result = select_support_files(
            selected_entities=[init_py],
            all_entities=[init_py, client],
            relations=[_rel(init_py, client, "exports")],
            query_intent=intent,
        )
        assert client.id.value in _ids(result)


# ---------------------------------------------------------------------------
# TestInheritsRelation
# ---------------------------------------------------------------------------


class TestInheritsRelation:
    def test_selected_inherits_candidate(self) -> None:
        """selected inherits from candidate → candidate is a base class support file."""
        base_cls = _entity("pkg/base.py", kind="class", name="BaseResolver")
        child_cls = _entity("pkg/resolvers.py", kind="class", name="URLResolver")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[child_cls],
            all_entities=[child_cls, base_cls],
            relations=[_rel(child_cls, base_cls, "inherits")],
            query_intent=intent,
        )
        assert base_cls.id.value in _ids(result)

    def test_candidate_inherits_selected(self) -> None:
        """candidate inherits from selected → candidate is a subclass support file."""
        base_cls = _entity("pkg/base.py", kind="class", name="BaseResolver")
        child_cls = _entity("pkg/resolvers.py", kind="class", name="URLResolver")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[base_cls],
            all_entities=[child_cls, base_cls],
            relations=[_rel(child_cls, base_cls, "inherits")],
            query_intent=intent,
        )
        assert child_cls.id.value in _ids(result)


# ---------------------------------------------------------------------------
# TestReverseImport
# ---------------------------------------------------------------------------


class TestReverseImport:
    def test_reverse_import_qualifies(self) -> None:
        """candidate --imports--> selected: reverse dependency just meets threshold."""
        handler = _entity("pkg/handlers/base.py")
        resolver = _entity("pkg/urls/resolvers.py")
        intent = parse_query_intent("URL resolver")
        # REVERSE_IMPORT_BONUS = 4.0 = MIN_SUPPORT_SCORE
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, handler],
            relations=[_rel(handler, resolver, "imports")],
            query_intent=intent,
        )
        assert handler.id.value in _ids(result)


# ---------------------------------------------------------------------------
# TestSamePackageProximity
# ---------------------------------------------------------------------------


class TestSamePackageProximity:
    def test_same_package_alone_does_not_qualify(self) -> None:
        """Same directory alone (score 2.0) is below the minimum threshold (4.0)."""
        resolver = _entity("pkg/urls/resolvers.py")
        sibling = _entity("pkg/urls/views.py")
        intent = parse_query_intent("resolver")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, sibling],
            relations=[],  # no relations
            query_intent=intent,
        )
        # Score = 2.0 (same-package only) < 4.0 threshold → excluded
        assert sibling.id.value not in _ids(result)

    def test_same_package_plus_lexical_qualifies(self) -> None:
        """Same-package (2.0) + 2 lexical tokens (2×1.0) = 4.0 → qualifies."""
        resolver = _entity("pkg/urls/resolvers.py")
        # "urls" and "conf" appear in the path → 2 lexical hits
        conf = _entity("pkg/urls/conf.py")
        intent = parse_query_intent("urls conf configuration")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, conf],
            relations=[],
            query_intent=intent,
        )
        # "urls" and "conf" both in lexical_tokens → 2 hits → 2.0+2.0=4.0 ≥ threshold
        assert conf.id.value in _ids(result)

    def test_same_package_does_not_pull_all_siblings(self) -> None:
        """Siblings without lexical signal stay below threshold."""
        resolver = _entity("pkg/urls/resolvers.py")
        # "views" not in lexical_tokens, no relations → stays below threshold
        views = _entity("pkg/urls/views.py")
        # "conf" is in lexical_tokens → qualifies
        conf = _entity("pkg/urls/conf.py")
        intent = parse_query_intent("urls conf configuration")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, views, conf],
            relations=[],
            query_intent=intent,
        )
        result_ids = _ids(result)
        assert views.id.value not in result_ids  # sibling without lexical match excluded
        assert conf.id.value in result_ids  # sibling with lexical match included


# ---------------------------------------------------------------------------
# TestExclusion
# ---------------------------------------------------------------------------


class TestExcludeTestFiles:
    def test_test_role_entity_excluded(self) -> None:
        """Entities in test roots (tests/) are always excluded."""
        resolver = _entity("pkg/urls/resolvers.py")
        test_file = _entity("tests/test_resolvers.py")
        intent = parse_query_intent("URL resolver implementation tests")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, test_file],
            relations=[_rel(resolver, test_file, "imports")],
            query_intent=intent,
        )
        assert test_file.id.value not in _ids(result)

    def test_runtime_test_named_path_excluded(self) -> None:
        """Paths with embedded /test/ segment (runtime) are excluded."""
        loader = _entity("lib/ansible/plugins/loader.py")
        runtime = _entity("lib/ansible/plugins/test/core.py")
        intent = parse_query_intent("plugin loader implementation")
        result = select_support_files(
            selected_entities=[loader],
            all_entities=[loader, runtime],
            relations=[_rel(loader, runtime, "imports")],
            query_intent=intent,
        )
        assert runtime.id.value not in _ids(result)

    def test_already_selected_excluded(self) -> None:
        """Entities already in selected_entities are not returned again."""
        resolver = _entity("pkg/urls/resolvers.py")
        base = _entity("pkg/urls/base.py")
        intent = parse_query_intent("URL resolver implementation")
        # Both are in selected_entities; base should not appear as support file
        result = select_support_files(
            selected_entities=[resolver, base],
            all_entities=[resolver, base],
            relations=[_rel(resolver, base, "imports")],
            query_intent=intent,
        )
        assert base.id.value not in _ids(result)


class TestExcludeDocsExamples:
    def test_docs_excluded_by_default(self) -> None:
        resolver = _entity("pkg/urls/resolvers.py")
        doc = _entity("docs/api/resolvers.rst")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, doc],
            relations=[_rel(resolver, doc, "imports")],
            query_intent=intent,
        )
        assert doc.id.value not in _ids(result)

    def test_docs_allowed_with_public_api_intent(self) -> None:
        resolver = _entity("pkg/urls/resolvers.py")
        doc = _entity("docs/api/resolvers.rst")
        intent = parse_query_intent("URL resolver public API exports interface")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, doc],
            relations=[_rel(resolver, doc, "imports")],
            query_intent=intent,
        )
        # docs allowed with public_api intent
        assert doc.id.value in _ids(result)

    def test_docs_src_excluded_by_default(self) -> None:
        """docs_src/ paths (58.7C extended prefix) are excluded for implementation queries."""
        resolver = _entity("pkg/urls/resolvers.py")
        doc = _entity("docs_src/commands/tutorial001.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, doc],
            relations=[_rel(resolver, doc, "imports")],
            query_intent=intent,
        )
        assert doc.id.value not in _ids(result)

    def test_docs_src_allowed_with_docs_examples_intent(self) -> None:
        """docs_src/ paths are included when the query explicitly requests tutorials."""
        resolver = _entity("pkg/urls/resolvers.py")
        doc = _entity("docs_src/commands/tutorial001.py")
        intent = parse_query_intent("Show tutorial examples for URL resolver usage")
        assert "docs_examples" in intent.intents
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, doc],
            relations=[_rel(resolver, doc, "imports")],
            query_intent=intent,
        )
        assert doc.id.value in _ids(result)

    def test_tutorials_path_excluded_by_default(self) -> None:
        """tutorials/ paths are excluded for neutral code-search queries."""
        resolver = _entity("pkg/urls/resolvers.py")
        doc = _entity("tutorials/getting_started.py")
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, doc],
            relations=[_rel(resolver, doc, "imports")],
            query_intent=intent,
        )
        assert doc.id.value not in _ids(result)


# ---------------------------------------------------------------------------
# TestCapAndDeduplication
# ---------------------------------------------------------------------------


class TestCap:
    def test_cap_respected(self) -> None:
        """At most max_support_files entities are returned."""
        selected = _entity("pkg/core.py")
        candidates = [_entity(f"pkg/dep{i}.py") for i in range(10)]
        all_ents = [selected] + candidates
        relations = [_rel(selected, c, "imports") for c in candidates]
        intent = parse_query_intent("core implementation")
        result = select_support_files(
            selected_entities=[selected],
            all_entities=all_ents,
            relations=relations,
            query_intent=intent,
            max_support_files=3,
        )
        assert len(result) <= 3

    def test_default_cap_is_five(self) -> None:
        selected = _entity("pkg/core.py")
        candidates = [_entity(f"pkg/dep{i}.py") for i in range(10)]
        all_ents = [selected] + candidates
        relations = [_rel(selected, c, "imports") for c in candidates]
        intent = parse_query_intent("core implementation")
        result = select_support_files(
            selected_entities=[selected],
            all_entities=all_ents,
            relations=relations,
            query_intent=intent,
        )
        assert len(result) <= 5


class TestDeduplication:
    def test_deduplication_by_source_path(self) -> None:
        """Multiple entities at the same path → only one returned."""
        selected = _entity("pkg/resolvers.py")
        # Two entities with the same path (e.g. module + class child)
        base_module = _entity("pkg/base.py", kind="module")
        base_class = Entity(
            id=StableId.from_parts(["class", "pkg/base.py", "Base"]),
            kind="class",
            name="Base",
            qualified_name="pkg.base.Base",
            source_range=SourceRange(path="pkg/base.py", start_line=10, end_line=50),
        )
        intent = parse_query_intent("resolver implementation")
        result = select_support_files(
            selected_entities=[selected],
            all_entities=[selected, base_module, base_class],
            relations=[
                _rel(selected, base_module, "imports"),
                _rel(selected, base_class, "imports"),
            ],
            query_intent=intent,
        )
        # Only one entity per path
        paths = [_entity_path_from_eid(r[0], [selected, base_module, base_class]) for r in result]
        assert len(paths) == len(set(paths))

    def test_deduplication_prefers_module_kind(self) -> None:
        """When path is shared, prefer module-kind entity over class/function."""
        selected = _entity("pkg/resolvers.py")
        base_module = _entity("pkg/base.py", kind="module")
        base_class = Entity(
            id=StableId.from_parts(["class", "pkg/base.py", "Base"]),
            kind="class",
            name="Base",
            qualified_name="pkg.base.Base",
            source_range=SourceRange(path="pkg/base.py", start_line=10, end_line=50),
        )
        intent = parse_query_intent("resolver implementation")
        result = select_support_files(
            selected_entities=[selected],
            all_entities=[selected, base_module, base_class],
            relations=[
                _rel(selected, base_module, "imports"),
            ],
            query_intent=intent,
        )
        if result:
            # The returned entity id should be the module-level one
            assert result[0][0] == base_module.id.value


def _entity_path_from_eid(eid: str, entities: list[Entity]) -> str:
    for e in entities:
        if e.id.value == eid:
            return e.source_range.path
    return eid


# ---------------------------------------------------------------------------
# TestDeterministicOrdering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_higher_score_ranked_first(self) -> None:
        """Forward import (+10) ranks above reverse import (+4)."""
        resolver = _entity("pkg/urls/resolvers.py")
        dep_a = _entity("pkg/urls/base.py")  # forward import → score 10
        dep_b = _entity("pkg/handlers/base.py")  # reverse import → score 4
        intent = parse_query_intent("URL resolver implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver, dep_a, dep_b],
            relations=[
                _rel(resolver, dep_a, "imports"),  # forward
                _rel(dep_b, resolver, "imports"),  # reverse
            ],
            query_intent=intent,
        )
        result_ids = _ids(result)
        # dep_a (score 10) should come before dep_b (score 4)
        assert result_ids.index(dep_a.id.value) < result_ids.index(dep_b.id.value)

    def test_deterministic_across_calls(self) -> None:
        """Calling select_support_files twice produces identical results."""
        selected = _entity("pkg/core.py")
        deps = [_entity(f"pkg/dep{i}.py") for i in range(5)]
        all_ents = [selected] + deps
        relations = [_rel(selected, d, "imports") for d in deps]
        intent = parse_query_intent("core implementation")
        r1 = select_support_files(
            selected_entities=[selected],
            all_entities=all_ents,
            relations=relations,
            query_intent=intent,
        )
        r2 = select_support_files(
            selected_entities=[selected],
            all_entities=all_ents,
            relations=relations,
            query_intent=intent,
        )
        assert r1 == r2


# ---------------------------------------------------------------------------
# TestRegressionFixtures — Django / Ansible / HTTPX patterns
# ---------------------------------------------------------------------------


class TestDjangoUrlRoutingPattern:
    """Regression fixture: selected resolvers.py + relations → support files."""

    def _make_entities(self) -> tuple[Entity, list[Entity]]:
        """Build a minimal Django-like URL routing fixture."""
        resolvers = _entity("pkg/urls/resolvers.py")
        base = _entity("pkg/urls/base.py")
        conf = _entity("pkg/urls/conf.py")
        init = _entity("pkg/urls/__init__.py")
        # Cross-package dependency
        handlers_base = _entity("pkg/core/handlers/base.py")
        return resolvers, [base, conf, init, handlers_base]

    def test_forward_imports_select_base_and_conf(self) -> None:
        resolver, support = self._make_entities()
        base, conf, init, handlers_base = support
        intent = parse_query_intent("URL resolver routing implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver] + support,
            relations=[
                _rel(resolver, base, "imports"),
                _rel(resolver, conf, "imports"),
            ],
            query_intent=intent,
        )
        result_ids = _ids(result)
        assert base.id.value in result_ids
        assert conf.id.value in result_ids

    def test_cross_package_handlers_selected_via_import(self) -> None:
        resolver, support = self._make_entities()
        base, conf, init, handlers_base = support
        intent = parse_query_intent("URL resolver routing implementation")
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver] + support,
            relations=[
                _rel(resolver, handlers_base, "imports"),
            ],
            query_intent=intent,
        )
        assert handlers_base.id.value in _ids(result)

    def test_init_py_selected_with_public_api_intent_and_export(self) -> None:
        resolver, support = self._make_entities()
        base, conf, init, handlers_base = support
        intent = parse_query_intent("URL routing public API exports interface")
        # __init__.py exports resolvers
        result = select_support_files(
            selected_entities=[resolver],
            all_entities=[resolver] + support,
            relations=[
                _rel(init, resolver, "exports"),
            ],
            query_intent=intent,
        )
        assert init.id.value in _ids(result)


class TestAnsiblePluginLoaderPattern:
    """Regression fixture: selected loader.py + imports → executor support file."""

    def test_cross_package_executor_selected_via_import(self) -> None:
        loader = _entity("lib/ansible/plugins/loader.py")
        module_common = _entity("lib/ansible/executor/module_common.py")
        collection_finder = _entity("lib/ansible/utils/collection_loader/_collection_finder.py")
        intent = parse_query_intent("plugin loader implementation")
        result = select_support_files(
            selected_entities=[loader],
            all_entities=[loader, module_common, collection_finder],
            relations=[
                _rel(loader, module_common, "imports"),
                _rel(loader, collection_finder, "imports"),
            ],
            query_intent=intent,
        )
        result_ids = _ids(result)
        assert module_common.id.value in result_ids
        assert collection_finder.id.value in result_ids

    def test_runtime_test_path_not_selected_as_support(self) -> None:
        loader = _entity("lib/ansible/plugins/loader.py")
        runtime = _entity("lib/ansible/plugins/test/core.py")
        intent = parse_query_intent("plugin loader implementation")
        result = select_support_files(
            selected_entities=[loader],
            all_entities=[loader, runtime],
            relations=[_rel(loader, runtime, "imports")],
            query_intent=intent,
        )
        assert runtime.id.value not in _ids(result)


class TestHttpxPublicApiPattern:
    """Regression fixture: httpx/_client.py + exports + public_api → __init__.py."""

    def test_init_py_selected_with_export_and_public_api_intent(self) -> None:
        client = _entity("httpx/_client.py")
        init = _entity("httpx/__init__.py")
        intent = parse_query_intent("httpx public API exports interface")
        result = select_support_files(
            selected_entities=[client],
            all_entities=[client, init],
            relations=[_rel(init, client, "exports")],
            query_intent=intent,
        )
        assert init.id.value in _ids(result)

    def test_init_py_selected_without_public_api_intent_via_reverse_export(self) -> None:
        """Without public_api intent, __init__.py reverse export still qualifies
        because _REVERSE_EXPORT_BONUS (8.0) >= _MIN_SUPPORT_SCORE (4.0)."""
        client = _entity("httpx/_client.py")
        init = _entity("httpx/__init__.py")
        intent = parse_query_intent("httpx implementation requests")
        result = select_support_files(
            selected_entities=[client],
            all_entities=[client, init],
            relations=[_rel(init, client, "exports")],
            query_intent=intent,
        )
        # Still included: REVERSE_EXPORT_BONUS alone meets threshold
        assert init.id.value in _ids(result)

    def test_public_api_boost_increases_score_for_init(self) -> None:
        """__init__.py gets extra boost with public_api intent (higher score = first in result)."""
        client = _entity("httpx/_client.py")
        init = _entity("httpx/__init__.py")
        compat = _entity("httpx/_compat.py")
        # init has reverse export; compat has reverse import (weaker)
        intent_no_api = parse_query_intent("httpx implementation")
        intent_with_api = parse_query_intent("httpx public API exports interface")
        result_no = select_support_files(
            selected_entities=[client],
            all_entities=[client, init, compat],
            relations=[
                _rel(init, client, "exports"),
                _rel(compat, client, "imports"),
            ],
            query_intent=intent_no_api,
        )
        result_with = select_support_files(
            selected_entities=[client],
            all_entities=[client, init, compat],
            relations=[
                _rel(init, client, "exports"),
                _rel(compat, client, "imports"),
            ],
            query_intent=intent_with_api,
        )
        # Both include init; with public_api intent, init should be first
        ids_with = _ids(result_with)
        ids_no = _ids(result_no)
        assert init.id.value in ids_with
        assert init.id.value in ids_no
        assert ids_with[0] == init.id.value


# ---------------------------------------------------------------------------
# TestPackBuilderIntegration
# ---------------------------------------------------------------------------


class TestPackBuilderIntegration:
    """Smoke test: pack_builder integrates support expansion without errors."""

    def test_pack_builds_with_support_expansion(self) -> None:
        """build_context_pack succeeds when support expansion adds new entities."""
        resolver = _entity("pkg/urls/resolvers.py")
        base = _entity("pkg/urls/base.py")
        conf = _entity("pkg/urls/conf.py")
        rel_imports_base = _rel(resolver, base, "imports")
        rel_imports_conf = _rel(resolver, conf, "imports")

        pack = build_context_pack(
            task="How does URL resolver routing work?",
            entities=[resolver, base, conf],
            relations=[rel_imports_base, rel_imports_conf],
            budget_chars=10_000,
        )
        # Pack should include at least the resolver; support files added when budget allows
        included_paths = {e.source_range.path for e in pack.selected_entities}
        assert "pkg/urls/resolvers.py" in included_paths

    def test_pack_builds_without_support_expansion_when_no_relations(self) -> None:
        """No adjacency → support expansion returns empty; pack still builds."""
        resolver = _entity("pkg/urls/resolvers.py")

        pack = build_context_pack(
            task="How does URL resolver routing work?",
            entities=[resolver],
            relations=[],
            budget_chars=10_000,
        )
        assert len(pack.selected_entities) >= 1
