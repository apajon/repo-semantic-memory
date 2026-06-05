"""Regression fixtures for path-role classification.

Tests assert deterministic role assignment for all path categories described in
the source-root classifier design: source roots (src/, top-level package with
marker, ROS 2 package.xml, pyproject.toml, setup.py, setup.cfg, __init__.py),
test, example, doc, ci, tool, config, generated artifacts, and safe false-positive
paths that must NOT be classified as generated.

Also covers Ranking v2 (Prompt 58.2): is_runtime_test_named_path, is_public_api_file,
and path_prior_multiplier.
"""

from __future__ import annotations

import pytest

from repo_semantic_memory.context.pack_builder import (
    _build_bm25_index,
    _score_entity,
    _task_hints,
    _tokenize,
)
from repo_semantic_memory.context.path_roles import (
    CI_ROLE,
    CONFIG_ROLE,
    DOC_ROLE,
    EXAMPLE_ROLE,
    GENERATED_ROLE,
    OTHER_ROLE,
    SOURCE_ROLE,
    TEST_ROLE,
    TOOL_ROLE,
    classify_path_role,
    infer_source_roots,
    is_generated_artifact_path,
    is_public_api_file,
    is_runtime_test_named_path,
    path_prior_multiplier,
)
from repo_semantic_memory.context.query_intent import parse_query_intent
from repo_semantic_memory.model import Entity, SourceRange, StableId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(path: str) -> Entity:
    return Entity(
        id=StableId.from_parts(["file", path]),
        kind="module",
        name=path.rsplit("/", 1)[-1],
        qualified_name=path.replace("/", "."),
        source_range=SourceRange(path=path, start_line=1, end_line=1),
    )


def _classify(path: str, *, source_roots: tuple[str, ...] = ()) -> str:
    return classify_path_role(path=path, source_roots=source_roots)


# ---------------------------------------------------------------------------
# infer_source_roots
# ---------------------------------------------------------------------------


class TestInferSourceRoots:
    def test_src_layout(self) -> None:
        entities = [_entity("src/pkg_a/module.py")]
        roots = infer_source_roots(entities)
        assert "src" in roots

    def test_package_xml_marker(self) -> None:
        entities = [_entity("lifecore_state/package.xml"), _entity("lifecore_state/module.py")]
        roots = infer_source_roots(entities)
        assert "lifecore_state" in roots

    def test_pyproject_toml_marker(self) -> None:
        entities = [_entity("pkg_pyproject/pyproject.toml"), _entity("pkg_pyproject/mod.py")]
        roots = infer_source_roots(entities)
        assert "pkg_pyproject" in roots

    def test_setup_py_marker(self) -> None:
        entities = [_entity("pkg_setup/setup.py"), _entity("pkg_setup/mod.py")]
        roots = infer_source_roots(entities)
        assert "pkg_setup" in roots

    def test_setup_cfg_marker(self) -> None:
        entities = [_entity("pkg_setupcfg/setup.cfg"), _entity("pkg_setupcfg/mod.py")]
        roots = infer_source_roots(entities)
        assert "pkg_setupcfg" in roots

    def test_init_py_package_root(self) -> None:
        entities = [_entity("pkg_b/__init__.py"), _entity("pkg_b/core.py")]
        roots = infer_source_roots(entities)
        assert "pkg_b" in roots

    def test_nested_test_init_not_promoted(self) -> None:
        entities = [_entity("pkg_core/tests/__init__.py")]
        roots = infer_source_roots(entities)
        assert "pkg_core/tests" not in roots

    def test_common_source_root_names(self) -> None:
        for root in ("packages", "libs", "modules"):
            entities = [_entity(f"{root}/foo/module.py")]
            roots = infer_source_roots(entities)
            assert root in roots

    def test_output_is_sorted_and_deterministic(self) -> None:
        entities = [
            _entity("pkg_b/__init__.py"),
            _entity("src/mod.py"),
            _entity("lifecore_state/package.xml"),
        ]
        first = infer_source_roots(entities)
        second = infer_source_roots(list(reversed(entities)))
        assert first == second
        assert list(first) == sorted(first)


# ---------------------------------------------------------------------------
# classify_path_role — source variants
# ---------------------------------------------------------------------------


class TestClassifySourceRole:
    def test_src_layout_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("src/pkg_a/module.py")])
        assert _classify("src/pkg_a/module.py", source_roots=roots) == SOURCE_ROLE

    def test_top_level_package_root_with_init_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_b/__init__.py")])
        assert _classify("pkg_b/core.py", source_roots=roots) == SOURCE_ROLE

    def test_ros_package_xml_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("lifecore_state/package.xml")])
        assert _classify("lifecore_state/state_component.py", source_roots=roots) == SOURCE_ROLE

    def test_pyproject_toml_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_pyproject/pyproject.toml")])
        assert _classify("pkg_pyproject/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_setup_py_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_setup/setup.py")])
        assert _classify("pkg_setup/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_setup_cfg_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("pkg_setupcfg/setup.cfg")])
        assert _classify("pkg_setupcfg/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_packages_common_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("packages/foo/mod.py")])
        assert _classify("packages/foo/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_libs_common_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("libs/bar/mod.py")])
        assert _classify("libs/bar/mod.py", source_roots=roots) == SOURCE_ROLE

    def test_modules_common_root_classified_as_source(self) -> None:
        roots = infer_source_roots([_entity("modules/baz/mod.py")])
        assert _classify("modules/baz/mod.py", source_roots=roots) == SOURCE_ROLE


# ---------------------------------------------------------------------------
# classify_path_role — non-source roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # tests
        ("tests/test_core.py", TEST_ROLE),
        ("test/unit/test_utils.py", TEST_ROLE),
        # examples
        ("examples/example_usage.py", EXAMPLE_ROLE),
        ("example/demo.py", EXAMPLE_ROLE),
        # docs — extended prefixes (58.7C)
        ("docs_src/commands/callback/tutorial001.py", DOC_ROLE),
        ("docs_src/overview.md", DOC_ROLE),
        ("tutorials/getting_started.py", DOC_ROLE),
        ("tutorial/quickstart.md", DOC_ROLE),
        # docs — existing
        ("docs/guide.md", DOC_ROLE),
        ("doc/api.rst", DOC_ROLE),
        # ci
        (".github/workflows/ci.yml", CI_ROLE),
        (".gitlab/ci.yml", CI_ROLE),
        (".circleci/config.yml", CI_ROLE),
        ("ci/pipeline.yaml", CI_ROLE),
        # tools
        ("tools/codegen.py", TOOL_ROLE),
        ("scripts/release.sh", TOOL_ROLE),
        # config
        ("config/settings.yaml", CONFIG_ROLE),
        # other
        ("misc/last.py", OTHER_ROLE),
        ("README.md", OTHER_ROLE),
    ],
)
def test_path_roles_non_source(path: str, expected: str) -> None:
    assert _classify(path, source_roots=()) == expected


# ---------------------------------------------------------------------------
# classify_path_role — generated artifacts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "docs/_build/api.html",
        "_build/output.py",
        "dist/package-0.1.tar.gz",
        "build/lib/module.py",
        "htmlcov/index.html",
        ".pytest_cache/v/cache/nodeids",
        ".mypy_cache/3.12/module.json",
        ".ruff_cache/content",
        "mypackage.egg-info/PKG-INFO",
    ],
)
def test_generated_artifact_paths_classified_as_generated(path: str) -> None:
    assert _classify(path, source_roots=()) == GENERATED_ROLE


# ---------------------------------------------------------------------------
# is_generated_artifact_path — segment safety (false-positive guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/build_tools.py",
        "src/package/distances.py",
        "src/project/rebuilder.py",
        "tools/build_helper.py",
        "scripts/dist_check.sh",
    ],
)
def test_legitimate_paths_not_classified_as_generated(path: str) -> None:
    """Paths that merely contain build-related words must not be flagged as generated."""
    assert not is_generated_artifact_path(path)
    assert _classify(path, source_roots=("src",)) != GENERATED_ROLE


# ---------------------------------------------------------------------------
# PathRole literal coverage
# ---------------------------------------------------------------------------


def test_all_defined_roles_are_reachable() -> None:
    """Smoke test: every PathRole constant is reachable via classify_path_role."""
    roots = ("pkg_b",)
    role_samples = [
        ("pkg_b/core.py", SOURCE_ROLE),
        ("tests/test_x.py", TEST_ROLE),
        ("examples/demo.py", EXAMPLE_ROLE),
        ("docs/guide.md", DOC_ROLE),
        (".github/ci.yml", CI_ROLE),
        ("tools/gen.py", TOOL_ROLE),
        ("config/app.yaml", CONFIG_ROLE),
        ("dist/wheel.whl", GENERATED_ROLE),
        ("misc/other.py", OTHER_ROLE),
    ]
    for path, expected_role in role_samples:
        assert _classify(path, source_roots=roots) == expected_role, (
            f"{path!r} expected {expected_role!r}"
        )


# ---------------------------------------------------------------------------
# Ranking v2 (Prompt 58.2) — is_runtime_test_named_path
# ---------------------------------------------------------------------------


class TestIsRuntimeTestNamedPath:
    def test_real_tests_root_is_not_runtime(self) -> None:
        assert not is_runtime_test_named_path("tests/test_core.py")

    def test_real_test_singular_root_is_not_runtime(self) -> None:
        assert not is_runtime_test_named_path("test/units/plugins/test_plugins.py")

    def test_ansible_plugins_test_is_runtime(self) -> None:
        """lib/ansible/plugins/test/ is a runtime directory, not a unit-test root."""
        assert is_runtime_test_named_path("lib/ansible/plugins/test/core.py")

    def test_embedded_tests_segment_is_runtime(self) -> None:
        assert is_runtime_test_named_path("lib/mylib/tests/helpers.py")

    def test_source_file_without_test_segment_is_not_runtime(self) -> None:
        assert not is_runtime_test_named_path("src/mypackage/utils.py")

    def test_django_urls_resolver_is_not_runtime(self) -> None:
        assert not is_runtime_test_named_path("django/urls/resolvers.py")

    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_core.py",
            "test/units/plugins/test_x.py",
        ],
    )
    def test_real_test_root_paths_are_never_runtime(self, path: str) -> None:
        assert not is_runtime_test_named_path(path)


# ---------------------------------------------------------------------------
# Ranking v2 (Prompt 58.2) — is_public_api_file
# ---------------------------------------------------------------------------


class TestIsPublicApiFile:
    def test_init_py_in_package(self) -> None:
        assert is_public_api_file("httpx/__init__.py")

    def test_init_py_in_nested_package(self) -> None:
        assert is_public_api_file("django/urls/__init__.py")

    def test_top_level_init_py(self) -> None:
        assert is_public_api_file("__init__.py")

    def test_regular_module_is_not_public_api(self) -> None:
        assert not is_public_api_file("django/urls/resolvers.py")

    def test_init_py_only_matches_exact_filename(self) -> None:
        # A file named "__init__something.py" is NOT an __init__.py
        assert not is_public_api_file("django/urls/__init__something.py")


# ---------------------------------------------------------------------------
# Ranking v2 (Prompt 58.2) — path_prior_multiplier
# ---------------------------------------------------------------------------


def _intent(task: str):  # type: ignore[return]
    return parse_query_intent(task)


class TestPathPriorMultiplier:
    # --- tests intent ---

    def test_real_test_root_gets_positive_prior_with_tests_intent(self) -> None:
        intent = _intent("Find tests for URL resolver")
        delta = path_prior_multiplier("tests/test_resolver.py", intent)
        assert delta > 0

    def test_test_singular_root_gets_positive_prior_with_tests_intent(self) -> None:
        intent = _intent("Find tests for plugin loading")
        delta = path_prior_multiplier("test/units/plugins/test_plugins.py", intent)
        assert delta > 0

    def test_runtime_test_path_gets_negative_prior_with_tests_intent(self) -> None:
        intent = _intent("Find tests for plugin loading")
        delta = path_prior_multiplier("lib/ansible/plugins/test/core.py", intent)
        assert delta < 0

    def test_test_root_prior_stronger_than_runtime_test_prior(self) -> None:
        """Real test root must rank above a runtime-named test path when tests intent fires."""
        intent = _intent("Find tests for plugin loading")
        real_test = path_prior_multiplier("test/units/plugins/test_plugins.py", intent)
        runtime_test = path_prior_multiplier("lib/ansible/plugins/test/core.py", intent)
        assert real_test > runtime_test

    def test_source_file_neutral_with_tests_intent(self) -> None:
        intent = _intent("Find tests for URL resolver")
        delta = path_prior_multiplier("src/mypackage/resolver.py", intent)
        assert delta == 0.0

    def test_no_tests_intent_returns_zero_for_test_paths(self) -> None:
        intent = _intent("URL resolver architecture")
        delta_real = path_prior_multiplier("tests/test_resolver.py", intent)
        delta_runtime = path_prior_multiplier("lib/ansible/plugins/test/core.py", intent)
        assert delta_real == 0.0
        assert delta_runtime == 0.0

    # --- public_api intent ---

    def test_init_py_gets_positive_prior_with_public_api_intent(self) -> None:
        intent = _intent("Show public API exports")
        delta = path_prior_multiplier("httpx/__init__.py", intent)
        assert delta > 0

    def test_django_urls_init_py_gets_positive_prior(self) -> None:
        intent = _intent("Show public API exports")
        delta = path_prior_multiplier("django/urls/__init__.py", intent)
        assert delta > 0

    def test_regular_module_neutral_with_public_api_intent(self) -> None:
        intent = _intent("Show public API exports")
        delta = path_prior_multiplier("django/urls/resolvers.py", intent)
        assert delta == 0.0

    # --- implementation intent ---

    def test_docs_gets_mild_penalty_with_implementation_only_intent(self) -> None:
        intent = _intent("Where is the resolver implemented")
        # "implementation" intent fires from "implemented"; "tests" is not present
        assert "implementation" in intent.intents
        assert "tests" not in intent.intents
        delta = path_prior_multiplier("docs/guide.md", intent)
        assert delta < 0

    def test_examples_gets_mild_penalty_with_implementation_only_intent(self) -> None:
        intent = _intent("Where is the resolver implemented")
        delta = path_prior_multiplier("examples/demo.py", intent)
        assert delta < 0

    def test_tests_not_penalized_when_combined_impl_and_tests_intent(self) -> None:
        """When both implementation and tests intents fire, test files should not be penalized."""
        intent = _intent("Find tests for how resolver is implemented")
        assert "implementation" in intent.intents
        assert "tests" in intent.intents
        delta = path_prior_multiplier("tests/test_resolver.py", intent)
        # docs penalty suppressed; test root boost applies instead
        assert delta >= 0

    # --- config_build_release intent ---

    def test_pyproject_toml_gets_positive_prior_with_config_intent(self) -> None:
        intent = _intent("Find the pyproject build configuration")
        delta = path_prior_multiplier("mypackage/pyproject.toml", intent)
        assert delta > 0

    def test_setup_py_gets_positive_prior_with_config_intent(self) -> None:
        intent = _intent("Find the pyproject build configuration")
        delta = path_prior_multiplier("mypackage/setup.py", intent)
        assert delta > 0

    def test_config_dir_file_gets_positive_prior_with_config_intent(self) -> None:
        intent = _intent("Find the build configuration")
        delta = path_prior_multiplier("config/settings.yaml", intent)
        assert delta > 0

    # --- neutral / unknown intents ---

    def test_unknown_intent_returns_zero(self) -> None:
        intent = _intent("timeout configuration")
        delta = path_prior_multiplier("src/mypackage/utils.py", intent)
        assert delta == 0.0

    def test_determinism(self) -> None:
        intent = _intent("Find tests for URL resolver")
        path = "test/units/plugins/test_plugins.py"
        assert path_prior_multiplier(path, intent) == path_prior_multiplier(path, intent)

    # --- docs_examples intent guard (58.7C) ---

    def test_docs_src_tutorial_penalized_for_neutral_query(self) -> None:
        """docs_src/ tutorial files are penalized without an explicit 'implementation' token."""
        intent = _intent("Find how Typer callback command processing works")
        assert "docs_examples" not in intent.intents
        delta = path_prior_multiplier("docs_src/commands/callback/tutorial001.py", intent)
        assert delta < 0

    def test_tutorials_path_penalized_for_neutral_query(self) -> None:
        """tutorials/ paths must be penalized for code-search queries."""
        intent = _intent("Find how URL resolver works")
        assert "docs_examples" not in intent.intents
        assert "architecture_flow" not in intent.intents
        assert "public_api" not in intent.intents
        delta = path_prior_multiplier("tutorials/getting_started.py", intent)
        assert delta < 0

    def test_docs_not_penalized_when_docs_examples_intent_fires(self) -> None:
        """docs/ paths must NOT be penalized when the query explicitly asks for docs."""
        intent = _intent("Show me the documentation for URL routing")
        assert "docs_examples" in intent.intents
        delta = path_prior_multiplier("docs/guide.md", intent)
        assert delta == 0.0

    def test_tutorial_not_penalized_when_tutorial_intent_fires(self) -> None:
        """docs_src/ paths must NOT be penalized when the query asks for a tutorial."""
        intent = _intent("Find the tutorial for callback commands")
        assert "docs_examples" in intent.intents
        delta = path_prior_multiplier("docs_src/commands/callback/tutorial001.py", intent)
        assert delta == 0.0

    def test_examples_not_penalized_when_examples_intent_fires(self) -> None:
        """examples/ paths must NOT be penalized when the query asks for examples."""
        intent = _intent("Find examples of callback usage")
        assert "docs_examples" in intent.intents
        delta = path_prior_multiplier("examples/demo.py", intent)
        assert delta == 0.0

    def test_docs_src_penalized_for_implementation_query(self) -> None:
        """docs_src/ is penalized for queries with explicit implementation intent."""
        intent = _intent("Where is callback parsing implemented")
        assert "implementation" in intent.intents
        assert "docs_examples" not in intent.intents
        delta = path_prior_multiplier("docs_src/commands/callback/tutorial001.py", intent)
        assert delta < 0

    # --- architecture_flow intent exempts docs (58.7C side-effects) ---

    def test_docs_not_penalized_for_architecture_flow_query(self) -> None:
        """docs/ files must NOT be penalized when architecture_flow intent fires.

        Architecture queries legitimately reference architecture docs, and
        architecture_flow is one of the three exemptions in the docs penalty rule.
        """
        intent = _intent("How does the lifecycle dispatch flow work")
        assert "architecture_flow" in intent.intents
        assert "docs_examples" not in intent.intents
        delta = path_prior_multiplier("docs/architecture.rst", intent)
        assert delta == 0.0

    def test_docs_src_not_penalized_for_architecture_flow_query(self) -> None:
        """docs_src/ tutorial files must NOT be penalized for architecture queries."""
        intent = _intent("Explain the request response pipeline architecture")
        assert "architecture_flow" in intent.intents
        delta = path_prior_multiplier("docs_src/advanced/tutorial001.py", intent)
        assert delta == 0.0

    # --- README exempted via docs_examples (58.7C) ---

    def test_docs_not_penalized_for_readme_query(self) -> None:
        """Explicit README/usage queries fire docs_examples and must not penalize docs/."""
        intent = _intent("Show the README for this package")
        assert "docs_examples" in intent.intents
        delta = path_prior_multiplier("docs/getting_started.md", intent)
        assert delta == 0.0

    # --- design-intent: neutral queries penalize docs by default ---

    def test_neutral_query_penalizes_docs_by_design(self) -> None:
        """Neutral code-search queries (no intent tokens) penalize docs/ by design.

        When a query has no explicit docs/api/arch markers (e.g. "Find how Typer
        callback command processing works"), the default assumption is code-search.
        Tutorial and example files are penalized to prevent them from outranking
        real implementation files on shared domain tokens like 'callback'.
        The penalty is additive (–4.0), not exclusion.
        """
        intent = _intent("Find how Typer callback command processing works")
        # Confirm truly neutral: no exempting intents
        assert not (intent.intents & {"docs_examples", "public_api", "architecture_flow"})
        delta_docs_src = path_prior_multiplier("docs_src/commands/callback/tutorial001.py", intent)
        delta_impl = path_prior_multiplier("typer/core.py", intent)
        assert delta_docs_src < 0, "docs_src tutorial must be downranked for neutral query"
        assert delta_impl == 0.0, "implementation file must not be penalized"

    def test_tests_only_intent_penalizes_docs(self) -> None:
        """Tests-only queries penalize docs/ — test queries want test code, not tutorial files."""
        intent = _intent("Find tests for callback behavior")
        assert "tests" in intent.intents
        assert not (intent.intents & {"docs_examples", "public_api", "architecture_flow"})
        delta = path_prior_multiplier("docs_src/commands/callback/tutorial001.py", intent)
        assert delta < 0

    def test_config_build_intent_penalizes_docs(self) -> None:
        """Config/build queries penalize docs/ — they target packaging files, not tutorials."""
        intent = _intent("Where is the pyproject setup configuration")
        assert "config_build_release" in intent.intents
        assert not (intent.intents & {"docs_examples", "public_api", "architecture_flow"})
        delta = path_prior_multiplier("docs/configuration.md", intent)
        assert delta < 0


# ---------------------------------------------------------------------------
# Ranking v2 (Prompt 58.2) — integration: scoring tests
# ---------------------------------------------------------------------------


def _make_entity(entity_id: str, name: str, qualified_name: str, path: str) -> Entity:
    return Entity(
        id=StableId(entity_id),
        kind="module",
        name=name,
        qualified_name=qualified_name,
        source_range=SourceRange(path=path, start_line=1, end_line=1),
    )


def _score(entity: Entity, task: str, entities: list[Entity] | None = None) -> float:
    """Score a single entity against *task* using lexical + path prior scoring."""
    all_entities = entities if entities is not None else [entity]
    intent = parse_query_intent(task)
    bm25_index = _build_bm25_index(
        entities=all_entities,
        component_labels_by_entity={},
        relation_labels_by_entity={},
    )
    task_tokens = _tokenize(task)
    breakdown = _score_entity(
        entity,
        intent.lexical_tokens,
        bm25_index=bm25_index,
        is_code_task=False,
        task_hints=_task_hints(task_tokens),
        query_intent=intent,
        public_api_entity_ids=set(),
        export_source_entity_ids=set(),
        export_target_entity_ids=set(),
        source_roots=[],
    )
    return breakdown.total


class TestPathPriorIntegration:
    def test_real_test_root_scores_higher_than_runtime_test_path_with_tests_intent(self) -> None:
        """test/units/... must score above lib/.../plugins/test/... when tests intent fires."""
        real_test = _make_entity(
            "python:module:test.units.plugins.test_plugins",
            "test_plugins",
            "test.units.plugins.test_plugins",
            "test/units/plugins/test_plugins.py",
        )
        runtime_test = _make_entity(
            "python:module:ansible.plugins.test.core",
            "core",
            "ansible.plugins.test.core",
            "lib/ansible/plugins/test/core.py",
        )
        entities = [real_test, runtime_test]
        task = "Find tests for plugin loading"
        real_score = _score(real_test, task, entities)
        runtime_score = _score(runtime_test, task, entities)
        assert real_score > runtime_score, (
            f"Real test score {real_score} should exceed runtime test score {runtime_score}"
        )

    def test_tests_root_scores_higher_than_runtime_test_path_with_tests_intent(self) -> None:
        """tests/test_x.py must score above lib/.../test/... when tests intent fires."""
        real_test = _make_entity(
            "python:module:tests.test_resolver",
            "test_resolver",
            "tests.test_resolver",
            "tests/test_resolver.py",
        )
        runtime_test = _make_entity(
            "python:module:ansible.plugins.test.core",
            "core",
            "ansible.plugins.test.core",
            "lib/ansible/plugins/test/core.py",
        )
        entities = [real_test, runtime_test]
        task = "Find tests for URL resolver"
        real_score = _score(real_test, task, entities)
        runtime_score = _score(runtime_test, task, entities)
        assert real_score > runtime_score

    def test_init_py_gets_extra_boost_for_public_api_intent(self) -> None:
        """__init__.py should score higher than a plain module for public_api intent."""
        init_module = _make_entity(
            "python:module:httpx.__init__",
            "__init__",
            "httpx",
            "httpx/__init__.py",
        )
        plain_module = _make_entity(
            "python:module:httpx._client",
            "_client",
            "httpx._client",
            "httpx/_client.py",
        )
        entities = [init_module, plain_module]
        task = "Show public API exports for httpx"
        init_score = _score(init_module, task, entities)
        plain_score = _score(plain_module, task, entities)
        assert init_score > plain_score

    def test_source_file_not_demoted_for_implementation_intent(self) -> None:
        """Source files should not get the doc/example penalty for implementation intent."""
        task = "Where is the resolver implemented"
        intent = parse_query_intent(task)
        delta = path_prior_multiplier("django/urls/resolvers.py", intent)
        assert delta >= 0.0, "Source file must not be penalized for implementation intent"

    def test_impl_plus_tests_combined_intent_does_not_suppress_test_files(self) -> None:
        """Combined implementation+tests intent must not penalize test-root files."""
        intent = parse_query_intent("Find tests for how resolver is implemented")
        assert "implementation" in intent.intents
        assert "tests" in intent.intents
        doc_delta = path_prior_multiplier("docs/guide.md", intent)
        test_delta = path_prior_multiplier("tests/test_resolver.py", intent)
        # docs are penalized — neither docs_examples, public_api nor architecture_flow fire
        assert doc_delta < 0
        # test boost still fires
        assert test_delta > 0
