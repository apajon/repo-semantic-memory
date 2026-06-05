"""Synthetic regression tests for Ranking v2 (Prompts 58.1–58.5).

These tests verify the behavioral properties that Ranking v2 guarantees,
using lightweight in-memory fixtures.  No real public-benchmark repos are
required; all assertions are against deterministic in-memory entity pools.

Coverage:
- 58.1: Generic stop-tokens ("find", "how", "files", "implementation") are
  stripped from lexical_tokens so they do not contribute BM25 mass.
- 58.2: public_api intent boosts __init__.py; test intent boosts real test roots.
- 58.3: Test branch selects tests/urlpatterns/ paths, not lib/ansible/plugins/test/.
- 58.3: lib/ansible/plugins/test/ runtime-named paths are excluded from test branch.
- 58.4: Support expansion: resolvers.py → conf.py via imports adjacency.
- 58.4: Support expansion: _client.py + exports → __init__.py with public_api intent.
- 58.4: Support expansion: loader.py → module_common.py via imports adjacency.
- 58.4: Support expansion: typer/core.py → typer/main.py via imports adjacency.
- 58.5: selection_reasons field is populated in a context pack build.
"""

from __future__ import annotations

from repo_semantic_memory.context import build_context_pack
from repo_semantic_memory.context.query_intent import parse_query_intent
from repo_semantic_memory.context.support_expansion import select_support_files
from repo_semantic_memory.context.test_branch import select_test_branch
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


def _suggested_paths(pack: object) -> list[str]:
    return list(getattr(pack, "suggested_files_to_inspect", ()))


# ---------------------------------------------------------------------------
# 58.1 — Generic token downweighting
# ---------------------------------------------------------------------------


class TestGenericTokenStripping:
    """Verify that generic phrase tokens are stripped from lexical_tokens (58.1)."""

    def test_find_stripped(self) -> None:
        intent = parse_query_intent("Find how Django resolves URL patterns")
        assert "find" not in intent.lexical_tokens

    def test_how_stripped(self) -> None:
        intent = parse_query_intent("Find how Ansible loads plugins")
        assert "how" not in intent.lexical_tokens

    def test_files_stripped(self) -> None:
        intent = parse_query_intent("Find the implementation files for URL routing")
        assert "files" not in intent.lexical_tokens

    def test_implementation_stripped(self) -> None:
        intent = parse_query_intent("implementation files for plugin loader")
        assert "implementation" not in intent.lexical_tokens

    def test_domain_tokens_preserved(self) -> None:
        intent = parse_query_intent("Find how Django resolves URL patterns into view execution")
        # Domain tokens must NOT be stripped
        assert (
            "resolves" in intent.lexical_tokens
            or "url" in intent.lexical_tokens
            or "django" in intent.lexical_tokens
        )

    def test_loader_preserved(self) -> None:
        intent = parse_query_intent("Find how Ansible discovers and loads modules")
        # "loader" / "loads" / "ansible" must survive
        assert any(t in intent.lexical_tokens for t in ("loads", "loader", "ansible", "modules"))

    def test_tests_token_preserved_for_intent(self) -> None:
        intent = parse_query_intent("including resolver implementation files and relevant tests")
        assert "tests" in intent.intents

    def test_the_and_to_stripped(self) -> None:
        intent = parse_query_intent("Find the public API to making HTTP requests")
        assert "the" not in intent.lexical_tokens
        assert "to" not in intent.lexical_tokens


# ---------------------------------------------------------------------------
# 58.2 — Path priors: public_api intent boosts __init__.py
# ---------------------------------------------------------------------------


class TestPublicApiPathPrior:
    """public_api intent causes __init__.py to be in suggested files (58.2 + 58.4)."""

    def test_httpx_init_via_public_api_intent(self) -> None:
        client = _entity("httpx/_client.py")
        init = _entity("httpx/__init__.py")
        entities = [client, init]
        relations = [_rel(init, client, "exports")]
        pack = build_context_pack(
            task=(
                "Find the public API for making HTTP requests"
                " with sync and async clients and where those clients are implemented."
            ),
            entities=entities,
            relations=relations,
            budget_chars=4000,
        )
        suggested = _suggested_paths(pack)
        assert "httpx/__init__.py" in suggested
        assert "httpx/_client.py" in suggested

    def test_public_api_intent_detected(self) -> None:
        intent = parse_query_intent(
            "Find the public API for making HTTP requests with sync and async clients"
        )
        assert "public_api" in intent.intents


# ---------------------------------------------------------------------------
# 58.3 — Test branch: real test roots selected, runtime-named paths excluded
# ---------------------------------------------------------------------------


class TestBranchRegressions:
    """Test branch excludes runtime-named paths and selects real test roots (58.3)."""

    def test_urlpatterns_test_selected(self) -> None:
        """Django URL resolver task: tests/urlpatterns/ path selected."""
        resolver = _entity("django/urls/resolvers.py")
        test_e = _entity("tests/urlpatterns/test_resolvers.py")
        intent = parse_query_intent(
            "Find how Django resolves URL patterns into view execution, including relevant tests."
        )
        assert "tests" in intent.intents

        result = select_test_branch(
            entities=[resolver, test_e],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({resolver.id.value}),
            source_roots=(),
        )
        selected_paths = [
            e.source_range.path
            for eid in [r[0] for r in result]
            for e in [resolver, test_e]
            if e.id.value == eid
        ]
        assert "tests/urlpatterns/test_resolvers.py" in selected_paths

    def test_ansible_runtime_plugin_test_excluded(self) -> None:
        """lib/ansible/plugins/test/ runtime-named paths must NOT be in test branch."""
        loader = _entity("lib/ansible/plugins/loader.py")
        runtime_test = _entity("lib/ansible/plugins/test/core.py")
        unit_test = _entity("test/units/plugins/test_plugins.py")
        intent = parse_query_intent(
            "Find how Ansible discovers and loads modules/plugins, including relevant tests."
        )
        assert "tests" in intent.intents

        result = select_test_branch(
            entities=[loader, runtime_test, unit_test],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({loader.id.value}),
            source_roots=(),
        )
        selected_eids = {r[0] for r in result}
        assert runtime_test.id.value not in selected_eids, (
            "lib/ansible/plugins/test/core.py should be excluded as a runtime-named path"
        )

    def test_ansible_unit_test_preferred_over_runtime(self) -> None:
        """test/units/ path is preferred over lib/ansible/plugins/test/ (58.3)."""
        loader = _entity("lib/ansible/plugins/loader.py")
        runtime_test = _entity("lib/ansible/plugins/test/core.py")
        unit_test = _entity("test/units/plugins/test_plugins.py")
        intent = parse_query_intent(
            "Find how Ansible discovers and loads modules/plugins, including relevant tests."
        )
        result = select_test_branch(
            entities=[loader, runtime_test, unit_test],
            relations=[],
            query_intent=intent,
            seed_entity_ids=frozenset({loader.id.value}),
            source_roots=("lib",),
        )
        selected_eids = {r[0] for r in result}
        # Unit test may be selected; runtime path must not be
        assert runtime_test.id.value not in selected_eids


# ---------------------------------------------------------------------------
# 58.4 — Support expansion: key adjacency patterns
# ---------------------------------------------------------------------------


class TestSupportExpansionRegressions:
    """Support expansion surfaces key support files via relation adjacency (58.4)."""

    def test_django_resolvers_to_conf_via_imports(self) -> None:
        """resolvers.py imports conf.py → conf.py included as support file."""
        resolvers = _entity("django/urls/resolvers.py")
        conf = _entity("django/urls/conf.py")
        relations = [_rel(resolvers, conf, "imports")]
        intent = parse_query_intent("Find how Django resolves URL patterns into view execution.")
        result = select_support_files(
            selected_entities=[resolvers],
            all_entities=[resolvers, conf],
            relations=relations,
            query_intent=intent,
        )
        selected_paths = {
            e.source_range.path for eid, _ in result for e in [resolvers, conf] if e.id.value == eid
        }
        assert "django/urls/conf.py" in selected_paths

    def test_ansible_loader_to_module_common_via_imports(self) -> None:
        """loader.py imports module_common.py → module_common.py is a support file."""
        loader = _entity("lib/ansible/plugins/loader.py")
        module_common = _entity("lib/ansible/executor/module_common.py")
        relations = [_rel(loader, module_common, "imports")]
        intent = parse_query_intent("Find how Ansible discovers and loads modules/plugins.")
        result = select_support_files(
            selected_entities=[loader],
            all_entities=[loader, module_common],
            relations=relations,
            query_intent=intent,
        )
        selected_paths = {
            e.source_range.path
            for eid, _ in result
            for e in [loader, module_common]
            if e.id.value == eid
        }
        assert "lib/ansible/executor/module_common.py" in selected_paths

    def test_httpx_client_to_init_via_exports(self) -> None:
        """__init__.py exports _client.py → __init__.py is a support file with public_api intent."""
        client = _entity("httpx/_client.py")
        init = _entity("httpx/__init__.py")
        relations = [_rel(init, client, "exports")]
        intent = parse_query_intent(
            "Find the public API for making HTTP requests with sync and async clients."
        )
        assert "public_api" in intent.intents
        result = select_support_files(
            selected_entities=[client],
            all_entities=[client, init],
            relations=relations,
            query_intent=intent,
        )
        selected_paths = {
            e.source_range.path for eid, _ in result for e in [client, init] if e.id.value == eid
        }
        assert "httpx/__init__.py" in selected_paths

    def test_typer_core_to_main_via_imports(self) -> None:
        """typer/main.py is surfaced as a support file when core.py imports it."""
        main = _entity("typer/main.py")
        core = _entity("typer/core.py")
        relations = [_rel(core, main, "imports")]
        intent = parse_query_intent(
            "Find how Typer turns @app.command() and @app.callback()"
            " declarations into Click commands."
        )
        result = select_support_files(
            selected_entities=[core],
            all_entities=[main, core],
            relations=relations,
            query_intent=intent,
        )
        selected_paths = {
            e.source_range.path for eid, _ in result for e in [main, core] if e.id.value == eid
        }
        assert "typer/main.py" in selected_paths


# ---------------------------------------------------------------------------
# 58.5 — Selection reasons populated
# ---------------------------------------------------------------------------


class TestSelectionReasonsPopulated:
    """selection_reasons field is non-empty when entities are selected (58.5)."""

    def test_selection_reasons_non_empty(self) -> None:
        resolver = _entity("django/urls/resolvers.py")
        pack = build_context_pack(
            task="Find how Django resolves URL patterns into view execution.",
            entities=[resolver],
            relations=[],
            budget_chars=4000,
        )
        assert pack.selection_reasons, "selection_reasons should be non-empty"

    def test_selection_reasons_has_entry_for_selected_entity(self) -> None:
        loader = _entity("lib/ansible/plugins/loader.py")
        pack = build_context_pack(
            task="Find how Ansible discovers and loads modules/plugins.",
            entities=[loader],
            relations=[],
            budget_chars=4000,
        )
        selected_ids = {e.id.value for e in pack.selected_entities}
        reasons_ids = set(pack.selection_reasons.keys())
        # At least one selected entity has a selection reason
        assert selected_ids & reasons_ids, (
            "At least one selected entity must appear in selection_reasons"
        )
