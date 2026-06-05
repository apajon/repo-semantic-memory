"""Context pack builder tests."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from repo_semantic_memory.context import build_context_pack, render_context_pack_markdown
from repo_semantic_memory.context.compression import (
    available_profile_names,
    filter_related_relations,
    resolve_profile,
)
from repo_semantic_memory.context.context_pack import ContextPack, relation_key
from repo_semantic_memory.context.import_scoring import build_import_scoring_context
from repo_semantic_memory.context.pack_builder import (
    _PACK_FIXED_OVERHEAD_CHARS,
    _build_bm25_index,
    _component_labels_by_entity,
    _estimate_entity_chars,
    _estimate_relation_chars,
    _is_code_task,
    _is_graph_seed_eligible,
    _is_markdown_or_tooling_relation,
    _order_relations_for_profile_cap,
    _relation_budget_priority,
    _relation_endpoint_coverage,
    _relation_labels_by_entity,
    _score_entity,
    _task_hints,
    _tokenize,
    _truncate_to_budget,
)
from repo_semantic_memory.extractors import (
    extract_filesystem_entities,
    extract_markdown_file,
    extract_markdown_outline_path,
    extract_test_relationships,
    index_python_exports,
    index_python_path,
)
from repo_semantic_memory.memory import infer_semantic_components
from repo_semantic_memory.model import Entity, Relation, SourceRange, StableId

_ACTIVATION_GATING_SOURCE = (
    "class ActivationGating:\n"
    "    def should_activate(self, watchdog_ok: bool) -> bool:\n"
    "        return watchdog_ok\n"
)
_ACTIVATION_GATING_TESTS = (
    "from lifecore_ros2.core.activation_gating import ActivationGating\n\n"
    "class TestPublisherActivationGating:\n"
    "    def test_watchdog_allows_activation(self) -> None:\n"
    "        assert ActivationGating().should_activate(True)\n\n"
    "class TestSubscriberActivationGating:\n"
    "    def test_watchdog_blocks_activation(self) -> None:\n"
    "        assert not ActivationGating().should_activate(False)\n"
)
# Relation kinds considered task-relevant in diagnostics:
# structural source-code links + behavioral links that should survive relation budgeting.
_DIAGNOSTIC_USEFUL_RELATION_KINDS = frozenset(
    {"contains", "tests", "exports", "uses", "owns", "inherits", "imports"}
)


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"


def _indexed_entities_and_relations() -> tuple[list[Entity], list[Relation]]:
    fixture_root = _fixture_root()
    filesystem_entities = [
        entity
        for entity in extract_filesystem_entities(fixture_root)
        if not (entity.kind == "module" and entity.source_range.path.endswith(".py"))
    ]
    markdown_outline = extract_markdown_outline_path(fixture_root)
    python_entities, python_relations = index_python_path(fixture_root)
    return [*filesystem_entities, *markdown_outline.entities, *python_entities], [
        *markdown_outline.relations,
        *python_relations,
    ]


def _ranking_fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "ranking_repo"


def _ranking_fixture_entities_and_relations() -> tuple[list[Entity], list[Relation]]:
    fixture_root = _ranking_fixture_root()
    filesystem_entities = [
        entity
        for entity in extract_filesystem_entities(fixture_root)
        if not (entity.kind == "module" and entity.source_range.path.endswith(".py"))
    ]
    markdown_outline = extract_markdown_outline_path(fixture_root)
    python_entities, python_relations = index_python_path(fixture_root)
    return [*filesystem_entities, *markdown_outline.entities, *python_entities], [
        *markdown_outline.relations,
        *python_relations,
    ]


def _ranking_fixture_entities_and_all_relations() -> tuple[list[Entity], list[Relation]]:
    fixture_root = _ranking_fixture_root()
    filesystem_entities = [
        entity
        for entity in extract_filesystem_entities(fixture_root)
        if not (entity.kind == "module" and entity.source_range.path.endswith(".py"))
    ]
    markdown_outline = extract_markdown_outline_path(fixture_root)
    python_entities, python_relations = index_python_path(fixture_root)
    export_relations = index_python_exports(fixture_root)
    entities = [*filesystem_entities, *markdown_outline.entities, *python_entities]
    relations = [*markdown_outline.relations, *python_relations, *export_relations]
    test_relations = extract_test_relationships(fixture_root, entities, relations)
    return entities, [*relations, *test_relations]


def test_pack_selects_symbol_by_name() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="Update DerivedThing behavior.",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )

    selected = {entity.qualified_name for entity in pack.selected_entities}
    assert "python_symbols.DerivedThing" in selected


def test_pack_selects_symbol_by_qualified_name() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="Inspect python_symbols.DerivedThing implementation.",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )

    selected = {entity.qualified_name for entity in pack.selected_entities}
    assert "python_symbols.DerivedThing" in selected


def test_pack_selects_symbol_by_source_path() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="Work on src/python_symbols.py imports.",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )

    selected_paths = {entity.source_range.path for entity in pack.selected_entities}
    assert "src/python_symbols.py" in selected_paths


def test_pack_includes_direct_neighbors() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="DerivedThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )

    selected = {entity.qualified_name for entity in pack.selected_entities}
    assert "python_symbols.DerivedThing" in selected
    assert "python_symbols" in selected


def test_pack_budget_is_approximately_respected_and_marked_when_truncated() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="python_symbols",
        entities=entities,
        relations=relations,
        budget_chars=200,
    )
    output = render_context_pack_markdown(pack)

    assert len(output) <= 200
    assert "[truncated: budget reached]" in output


def test_pack_includes_source_citations() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="top_level_function",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )

    assert pack.source_citations
    citation_paths = {citation.path for citation in pack.source_citations}
    assert "src/python_symbols.py" in citation_paths


def test_pack_output_is_deterministic() -> None:
    entities, relations = _indexed_entities_and_relations()

    first = build_context_pack(
        task="DerivedThing import BaseThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    second = build_context_pack(
        task="DerivedThing import BaseThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )

    assert first.to_dict() == second.to_dict()
    assert render_context_pack_markdown(first) == render_context_pack_markdown(second)


def test_pack_yaml_output_parses() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="DerivedThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    payload = json.loads(pack.to_yaml())

    assert payload["task"] == "DerivedThing"
    assert "context_pack_version" in payload
    assert "schema_version" in payload
    assert "package_version" in payload


def test_unresolved_imports_and_inherits_are_marked_uncertain() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="DerivedThing imports inherits",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    markdown = render_context_pack_markdown(pack)

    assert any("Relation imports" in uncertainty for uncertainty in pack.uncertainties)
    assert any("Relation inherits" in uncertainty for uncertainty in pack.uncertainties)
    assert "Do not assume inheritance targets are resolved" in markdown
    assert "Do not assume imports are resolved" in markdown


def test_pack_output_excludes_source_bodies_and_docstrings() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="DerivedThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    markdown = render_context_pack_markdown(pack)

    assert '"""A class with a docstring."""' not in markdown
    assert "return str(value)" not in markdown


def test_pack_can_select_relevant_markdown_doc_section_without_body_leakage(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "benchmark_plan.md"
    doc.write_text(
        "# Benchmark plan\n\n"
        "Do not leak this body paragraph into compact context.\n\n"
        "## Retrieval dataset\n\n"
        "Gold files and symbols for benchmark tasks live here.\n",
        encoding="utf-8",
    )
    entities, relations = extract_markdown_file(repo, doc)

    pack = build_context_pack(
        task="Find retrieval dataset benchmark documentation",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    markdown = render_context_pack_markdown(pack)

    selected_headings = {
        entity.metadata.get("heading")
        for entity in pack.selected_entities
        if entity.metadata.get("entity_type") == "doc_section"
    }
    assert "Retrieval dataset" in selected_headings
    assert "Do not leak this body paragraph" not in markdown
    assert "Gold files and symbols" not in markdown


def test_suggested_files_are_deduplicated_deterministic_and_bounded() -> None:
    entities, relations = _indexed_entities_and_relations()

    full_pack = build_context_pack(
        task="python_symbols app imports",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    tight_pack = build_context_pack(
        task="python_symbols app imports",
        entities=entities,
        relations=relations,
        budget_chars=220,
    )
    second_full_pack = build_context_pack(
        task="python_symbols app imports",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )

    full_files = full_pack.suggested_files_to_inspect
    tight_files = tight_pack.suggested_files_to_inspect
    second_full_files = second_full_pack.suggested_files_to_inspect

    assert len(full_files) == len(set(full_files))
    assert full_files == second_full_files
    assert len(tight_files) <= len(full_files)


def test_pack_includes_compact_semantic_component_labels_when_available() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="test top_level_function behavior",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    payload = pack.to_dict()
    semantic_components = payload["semantic_components"]

    assert isinstance(semantic_components, list)
    if semantic_components:
        first = semantic_components[0]
        assert set(first.keys()) == {"component_type", "entity_id", "status"}


def test_semantic_component_labels_do_not_displace_markdown_symbols_or_citations() -> None:
    entities = [
        Entity(
            id=StableId("python:module:tests.sample"),
            kind="module",
            name="sample",
            qualified_name="tests.sample",
            source_range=SourceRange(path="tests/sample.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId("python:function:tests.sample.test_behavior"),
            kind="function",
            name="test_behavior",
            qualified_name="tests.sample.test_behavior",
            source_range=SourceRange(path="tests/sample.py", start_line=3, end_line=4),
        ),
    ]
    pack = build_context_pack(
        task="test behavior",
        entities=entities,
        relations=[],
        budget_chars=4000,
    )
    markdown = render_context_pack_markdown(pack)

    assert pack.semantic_components
    assert "tests.sample.test_behavior" in markdown
    assert "## Source citations" in markdown
    assert "## Semantic components" not in markdown


def test_public_api_task_prioritizes_init_exports_over_generated_artifacts() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()

    pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=6000,
    )
    selected_paths = [entity.source_range.path for entity in pack.selected_entities]

    assert "src/lifecore_ros2/__init__.py" in selected_paths
    assert "lifecore_state/__init__.py" in selected_paths
    assert any(
        "lifecore_ros2.components.lifecycle_component.LifecycleComponent" == entity.qualified_name
        for entity in pack.selected_entities
    )
    assert "tests/public_api_checks.py" in selected_paths
    assert all(not path.startswith("docs/_build/") for path in selected_paths)
    assert all(".egg-info/" not in path for path in selected_paths)


def test_implementation_cleanup_task_excludes_test_files() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()

    pack = build_context_pack(
        task="Find lifecycle component ownership and cleanup rules",
        entities=entities,
        relations=relations,
        budget_chars=6000,
    )
    selected_paths = {entity.source_range.path for entity in pack.selected_entities}

    assert "src/lifecore_ros2/components/lifecycle_component.py" in selected_paths
    assert "lifecore_state/state_component.py" in selected_paths
    assert "tests/public_api_checks.py" not in selected_paths


def test_activation_gating_intent_ranks_source_for_implementation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "lifecore_ros2" / "core").mkdir(parents=True)
    (repo / "tests" / "core").mkdir(parents=True)

    (repo / "src" / "lifecore_ros2" / "core" / "activation_gating.py").write_text(
        _ACTIVATION_GATING_SOURCE,
        encoding="utf-8",
    )
    (repo / "tests" / "core" / "test_activation_gating.py").write_text(
        _ACTIVATION_GATING_TESTS,
        encoding="utf-8",
    )

    filesystem_entities = [
        entity
        for entity in extract_filesystem_entities(repo)
        # Keep filesystem coverage entities while avoiding duplicate python module
        # entities that are already provided by index_python_path().
        if not (entity.kind == "module" and entity.source_range.path.endswith(".py"))
    ]
    markdown_outline = extract_markdown_outline_path(repo)
    python_entities, python_relations = index_python_path(repo)
    entities = [*filesystem_entities, *markdown_outline.entities, *python_entities]
    relations = [*markdown_outline.relations, *python_relations]

    implementation_pack = build_context_pack(
        task="Find where activation gating is implemented",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        explain_ranking=True,
    )
    regression_pack = build_context_pack(
        task="Find regression tests for activation gating behavior",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        explain_ranking=True,
    )

    source_path = "src/lifecore_ros2/core/activation_gating.py"
    test_path = "tests/core/test_activation_gating.py"

    implementation_paths = [
        entity.source_range.path for entity in implementation_pack.selected_entities
    ]
    regression_paths = [entity.source_range.path for entity in regression_pack.selected_entities]
    assert source_path in implementation_paths
    assert test_path in implementation_paths
    assert source_path in regression_paths
    assert test_path in regression_paths
    assert implementation_paths.index(source_path) < implementation_paths.index(test_path)
    assert regression_paths.index(test_path) < regression_paths.index(source_path)
    assert any(
        reason.message == "implementation task hint -> boosted source/package root"
        for breakdown in implementation_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )
    assert any(
        reason.message == "implementation task hint -> boosted source entity kind"
        for breakdown in implementation_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )
    assert any(
        reason.message == "test-like task intent boost"
        for breakdown in regression_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )


def test_build_filtering_is_path_segment_aware() -> None:
    entities = [
        Entity(
            id=StableId("python:module:src.build_tools"),
            kind="module",
            name="build_tools.py",
            qualified_name="src.build_tools",
            source_range=SourceRange(path="src/build_tools.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId("python:module:docs._build.generated"),
            kind="module",
            name="generated.py",
            qualified_name="docs._build.generated",
            source_range=SourceRange(path="docs/_build/generated.py", start_line=1, end_line=1),
        ),
    ]

    pack = build_context_pack(
        task="Update build tools behavior",
        entities=entities,
        relations=[],
        budget_chars=4000,
    )
    selected_paths = [entity.source_range.path for entity in pack.selected_entities]

    assert "src/build_tools.py" in selected_paths
    assert "docs/_build/generated.py" not in selected_paths


def test_public_api_ranking_selects_non_src_package_exports() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()

    pack = build_context_pack(
        task="Find package public exports and init modules",
        entities=entities,
        relations=relations,
        budget_chars=6000,
    )
    selected_paths = {entity.source_range.path for entity in pack.selected_entities}

    assert "lifecore_state/__init__.py" in selected_paths
    assert "lifecore_state/state_component.py" in selected_paths
    assert "docs/_build/generated_api.py" not in selected_paths


def test_public_api_ranking_prefers_source_exports_over_docs_and_tools(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "lifecore_ros2" / "core").mkdir(parents=True)
    (repo / "src" / "lifecore_ros2" / "testing").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    (repo / "tools" / "copilot").mkdir(parents=True)

    (repo / "README.md").write_text(
        "# Public API Overview\n\nThis prose explains the public API and exports in broad terms.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "public_api.md").write_text(
        "# Public API Notes\n\nThe public API is documented here for users.\n",
        encoding="utf-8",
    )
    (repo / "tools" / "copilot" / "public_api_playbook.md").write_text(
        "# Public API Copilot Notes\n\n"
        "Tooling guidance about lifecore_ros2 public API exports and init modules.\n",
        encoding="utf-8",
    )
    (repo / "src" / "lifecore_ros2" / "__init__.py").write_text(
        "from .core import PublicNode\n"
        "from .testing import assert_public_imports\n\n"
        '__all__ = ["PublicNode", "assert_public_imports"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "lifecore_ros2" / "core" / "__init__.py").write_text(
        'from .public_surface import PublicNode\n\n__all__ = ["PublicNode"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "lifecore_ros2" / "core" / "public_surface.py").write_text(
        "class PublicNode:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "src" / "lifecore_ros2" / "testing" / "__init__.py").write_text(
        'from .helpers import assert_public_imports\n\n__all__ = ["assert_public_imports"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "lifecore_ros2" / "testing" / "helpers.py").write_text(
        "def assert_public_imports() -> None:\n    return None\n",
        encoding="utf-8",
    )
    (repo / "tests" / "public_api_checks.py").write_text(
        "from lifecore_ros2 import PublicNode\n\n"
        "def test_public_import() -> None:\n"
        "    assert PublicNode is not None\n",
        encoding="utf-8",
    )

    filesystem_entities = [
        entity
        for entity in extract_filesystem_entities(repo)
        if not (entity.kind == "module" and entity.source_range.path.endswith(".py"))
    ]
    markdown_outline = extract_markdown_outline_path(repo)
    python_entities, python_relations = index_python_path(repo)
    entities = [*filesystem_entities, *markdown_outline.entities, *python_entities]
    relations = [*markdown_outline.relations, *python_relations]

    pack = build_context_pack(
        task="Find lifecore_ros2 public API exports and init modules",
        entities=entities,
        relations=relations,
        budget_chars=20000,
    )
    selected_paths = [entity.source_range.path for entity in pack.selected_entities]

    assert "src/lifecore_ros2/__init__.py" in selected_paths
    assert "src/lifecore_ros2/core/__init__.py" in selected_paths
    assert "src/lifecore_ros2/testing/__init__.py" in selected_paths
    assert "tests/public_api_checks.py" in selected_paths

    def find_selected_path_index(path: str) -> int:
        for i, selected_path in enumerate(selected_paths):
            if selected_path == path:
                return i
        msg = f"{path} not found in selected paths: {selected_paths}"
        raise AssertionError(msg)

    root_init_index = find_selected_path_index("src/lifecore_ros2/__init__.py")
    core_init_index = find_selected_path_index("src/lifecore_ros2/core/__init__.py")
    testing_init_index = find_selected_path_index("src/lifecore_ros2/testing/__init__.py")
    readme_index = find_selected_path_index("README.md")
    docs_index = find_selected_path_index("docs/public_api.md")
    tools_index = find_selected_path_index("tools/copilot/public_api_playbook.md")

    assert root_init_index < readme_index
    assert root_init_index < docs_index
    assert root_init_index < tools_index
    assert core_init_index < readme_index
    assert testing_init_index < docs_index
    assert testing_init_index < tools_index


def test_ranking_breakdown_is_deterministic() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()

    first = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        explain_ranking=True,
    )
    second = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        explain_ranking=True,
    )

    assert first.to_dict(include_ranking=True) == second.to_dict(include_ranking=True)


def test_explain_ranking_limits_breakdowns_and_reasons_by_profile() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()

    standard_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=8000,
        explain_ranking=True,
        profile="agent_standard",
    )
    debug_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=8000,
        explain_ranking=True,
        profile="agent_debug",
    )
    full_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=8000,
        explain_ranking=True,
        profile="full",
    )

    assert 0 < len(standard_pack.ranking_breakdowns) <= 12
    assert 0 < len(debug_pack.ranking_breakdowns) <= 20
    assert 0 < len(full_pack.ranking_breakdowns) <= 40
    assert len(standard_pack.ranking_breakdowns) <= len(debug_pack.ranking_breakdowns)
    assert len(debug_pack.ranking_breakdowns) <= len(full_pack.ranking_breakdowns)
    assert all(len(reasons) <= 2 for reasons in standard_pack.why_selected.values())
    assert all(len(reasons) <= 4 for reasons in debug_pack.why_selected.values())
    assert all(len(reasons) <= 8 for reasons in full_pack.why_selected.values())
    assert all(
        len(breakdown.reasons) <= 4 for breakdown in standard_pack.ranking_breakdowns.values()
    )
    assert all(len(breakdown.reasons) <= 6 for breakdown in debug_pack.ranking_breakdowns.values())
    assert all(len(breakdown.reasons) <= 10 for breakdown in full_pack.ranking_breakdowns.values())


def test_explain_ranking_why_selected_only_covers_included_items() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()

    pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=8000,
        explain_ranking=True,
    )

    included_keys = {
        *(entity.id.value for entity in pack.selected_entities),
        *(relation_key(relation) for relation in pack.selected_relations),
    }

    assert set(pack.why_selected.keys()) <= included_keys


def test_selected_entity_ranking_breakdown_includes_matched_fields() -> None:
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="DerivedThing implementation",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        explain_ranking=True,
    )
    derived = next(entity for entity in pack.selected_entities if entity.name == "DerivedThing")
    breakdown = pack.ranking_breakdowns[derived.id.value]

    assert breakdown.matched_terms
    assert breakdown.matched_fields
    assert "name" in breakdown.matched_fields or "qualified_name" in breakdown.matched_fields


def test_explain_ranking_retains_structural_relations() -> None:
    entities, relations = _ranking_fixture_entities_and_all_relations()

    cleanup_pack = build_context_pack(
        task="Find lifecycle component ownership and cleanup rules",
        entities=entities,
        relations=relations,
        budget_chars=8000,
        explain_ranking=True,
    )
    activation_pack = build_context_pack(
        task="Find where activation gating is implemented",
        entities=entities,
        relations=relations,
        budget_chars=8000,
        explain_ranking=True,
    )
    public_api_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=8000,
        explain_ranking=True,
    )

    for pack in (cleanup_pack, activation_pack):
        assert pack.selected_relations
        assert any(
            relation.kind in {"contains", "exports", "tests"}
            for relation in pack.selected_relations
        )

    public_api_relation_kinds = {relation.kind for relation in public_api_pack.selected_relations}
    assert public_api_relation_kinds & {"exports", "contains"}, (
        "public_api explain pack must keep exports or source-code contains relations"
    )


def test_explain_ranking_agent_standard_preserves_relations_under_budget_pressure() -> None:
    entities, relations = _ranking_fixture_entities_and_all_relations()

    pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=1400,
        explain_ranking=True,
        profile="agent_standard",
    )

    included_keys = {
        *(entity.id.value for entity in pack.selected_entities),
        *(relation_key(relation) for relation in pack.selected_relations),
    }
    profile = resolve_profile("agent_standard")
    assert profile.max_ranking_breakdowns is not None

    assert pack.selected_relations
    assert any(
        relation.kind in {"exports", "tests", "contains"} for relation in pack.selected_relations
    )
    assert set(pack.why_selected.keys()) <= included_keys
    assert 0 < len(pack.ranking_breakdowns) <= profile.max_ranking_breakdowns


def test_generated_artifact_penalty_appears_in_breakdown() -> None:
    generated_entity = Entity(
        id=StableId("python:module:docs._build.generated"),
        kind="module",
        name="generated.py",
        qualified_name="docs._build.generated",
        source_range=SourceRange(path="docs/_build/generated.py", start_line=1, end_line=1),
    )
    task_tokens = _tokenize("generated api docs")
    components = infer_semantic_components(entities=[generated_entity], relations=[])
    bm25_index = _build_bm25_index(
        entities=[generated_entity],
        component_labels_by_entity=_component_labels_by_entity(components),
        relation_labels_by_entity=_relation_labels_by_entity([]),
    )
    breakdown = _score_entity(
        generated_entity,
        task_tokens,
        bm25_index=bm25_index,
        is_code_task=_is_code_task(task_tokens),
        task_hints=_task_hints(task_tokens),
        public_api_entity_ids=set(),
        export_source_entity_ids=set(),
        export_target_entity_ids=set(),
        source_roots=("src",),
    )

    assert breakdown.penalty < 0
    assert any(
        reason.message == "generated/build artifact downrank" for reason in breakdown.reasons
    )


def test_hint_driven_breakdowns_include_path_role_and_task_intent() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()
    public_api_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        explain_ranking=True,
    )
    implementation_pack = build_context_pack(
        task="Find lifecycle component ownership and cleanup rules",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        explain_ranking=True,
    )
    test_pack = build_context_pack(
        task="Find tests for lifecycle component behavior",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        explain_ranking=True,
    )

    assert any(
        'public API task hint -> boosted "__init__.py"' in reason.message
        for breakdown in public_api_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )
    assert any(
        reason.category == "task_intent" and "public API task intent boost" in reason.message
        for breakdown in public_api_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )
    assert any(
        "implementation task hint -> boosted source/package root" in reason.message
        for breakdown in implementation_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )
    assert any(
        reason.category == "task_intent" and "implementation task intent boost" in reason.message
        for breakdown in implementation_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )
    assert any(
        "test task hint -> boosted test root" in reason.message
        for breakdown in test_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )
    assert any(
        reason.category == "task_intent" and "test-like task intent boost" in reason.message
        for breakdown in test_pack.ranking_breakdowns.values()
        for reason in breakdown.reasons
    )


def test_task_hints_detect_implementation_from_core_logic_terms() -> None:
    hints = _task_hints(_tokenize("Find core and logic implementation details"))
    assert "implementation" in hints


def test_default_markdown_output_remains_compact_without_explain_lines() -> None:
    entities, relations = _indexed_entities_and_relations()
    pack = build_context_pack(
        task="DerivedThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
    )
    markdown = render_context_pack_markdown(pack)

    assert "Score: total=" not in markdown
    assert "  Reason:" not in markdown


def test_explain_markdown_includes_ranking_summary_lines() -> None:
    entities, relations = _indexed_entities_and_relations()
    pack = build_context_pack(
        task="DerivedThing implementation",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        explain_ranking=True,
    )
    markdown = render_context_pack_markdown(pack, explain_ranking=True)

    assert "Score: total=" in markdown


# ---------------------------------------------------------------------------
# Graph seed eligibility and graph-scored neighbors
# ---------------------------------------------------------------------------


def test_citation_only_entity_is_not_a_graph_seed() -> None:
    """An entity whose only signal is the source-citation bonus must not be a graph seed."""
    # Build a score for an entity that has no BM25 match, no path-role boost, no task-intent.
    citation_only_entity = Entity(
        id=StableId("python:module:unrelated"),
        kind="module",
        name="unrelated",
        qualified_name="unrelated",
        source_range=SourceRange(path="src/unrelated.py", start_line=1, end_line=1),
    )
    task_tokens = _tokenize("DerivedThing")
    bm25_index = _build_bm25_index(
        entities=[citation_only_entity],
        component_labels_by_entity=_component_labels_by_entity([]),
        relation_labels_by_entity=_relation_labels_by_entity([]),
    )
    breakdown = _score_entity(
        citation_only_entity,
        task_tokens,
        bm25_index=bm25_index,
        is_code_task=_is_code_task(task_tokens),
        task_hints=_task_hints(task_tokens),
        public_api_entity_ids=set(),
        export_source_entity_ids=set(),
        export_target_entity_ids=set(),
        source_roots=("src",),
    )

    assert not _is_graph_seed_eligible(breakdown)


def test_graph_seed_threshold_is_strictly_above_citation_bonus() -> None:
    """Lexical score exactly equal to _SOURCE_CITATION_BONUS (2) is not a seed.

    This verifies the > (not >=) boundary: the floor contributed by holding any
    source path must not be sufficient on its own to qualify as a graph seed.
    """
    from repo_semantic_memory.context.pack_builder import _SOURCE_CITATION_BONUS
    from repo_semantic_memory.context.ranking import build_breakdown

    at_floor = build_breakdown(
        lexical=float(_SOURCE_CITATION_BONUS),
        path_role=0,
        task_intent=0,
        component=0,
        graph=0,
        penalty=0,
        matched_terms=(),
        matched_fields=(),
        reasons=(),
    )
    above_floor = build_breakdown(
        lexical=float(_SOURCE_CITATION_BONUS) + 0.01,
        path_role=0,
        task_intent=0,
        component=0,
        graph=0,
        penalty=0,
        matched_terms=(),
        matched_fields=(),
        reasons=(),
    )
    assert not _is_graph_seed_eligible(at_floor)
    assert _is_graph_seed_eligible(above_floor)

    """An entity with a BM25 match on task tokens qualifies as a graph seed."""
    matched_entity = Entity(
        id=StableId("python:class:python_symbols.DerivedThing"),
        kind="class",
        name="DerivedThing",
        qualified_name="python_symbols.DerivedThing",
        source_range=SourceRange(path="src/python_symbols.py", start_line=18, end_line=28),
    )
    task_tokens = _tokenize("DerivedThing")
    bm25_index = _build_bm25_index(
        entities=[matched_entity],
        component_labels_by_entity=_component_labels_by_entity([]),
        relation_labels_by_entity=_relation_labels_by_entity([]),
    )
    breakdown = _score_entity(
        matched_entity,
        task_tokens,
        bm25_index=bm25_index,
        is_code_task=_is_code_task(task_tokens),
        task_hints=_task_hints(task_tokens),
        public_api_entity_ids=set(),
        export_source_entity_ids=set(),
        export_target_entity_ids=set(),
        source_roots=("src",),
    )

    assert _is_graph_seed_eligible(breakdown)


def test_graph_selector_adds_contains_neighbor_from_true_seed() -> None:
    """Graph selection adds contains-related neighbors that are not task seeds."""
    entities, relations = _indexed_entities_and_relations()

    # Task "DerivedThing": only the DerivedThing class has a direct BM25 match.
    # The parent module has no BM25 match → not a graph seed, but IS a contains-parent.
    pack = build_context_pack(
        task="DerivedThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        explain_ranking=True,
    )

    selected_names = {e.qualified_name for e in pack.selected_entities}
    # DerivedThing is the lexical seed.
    assert "python_symbols.DerivedThing" in selected_names
    # The parent module should be reachable as a graph neighbor (contains parent).
    assert "python_symbols" in selected_names
    # At least one entity in the pack must carry a non-zero graph score.
    assert any(bd.graph > 0 for bd in pack.ranking_breakdowns.values())


def test_graph_scored_neighbor_has_nonzero_graph_in_breakdown() -> None:
    """An entity selected as a graph neighbor has graph > 0 in its ranking breakdown."""
    entities, relations = _indexed_entities_and_relations()

    pack = build_context_pack(
        task="DerivedThing",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        explain_ranking=True,
    )

    # python_symbols module is the contains-parent of DerivedThing.
    module_entity = next(
        (e for e in pack.selected_entities if e.qualified_name == "python_symbols"), None
    )
    assert module_entity is not None, "python_symbols module must be selected"
    breakdown = pack.ranking_breakdowns.get(module_entity.id.value)
    assert breakdown is not None, "ranking breakdown must exist for python_symbols in explain mode"
    assert breakdown.graph > 0, (
        f"python_symbols graph score should be > 0 (got {breakdown.graph}); "
        "it should be selected as a graph neighbor of DerivedThing via contains"
    )


def test_profile_registry_is_deterministic() -> None:
    first = available_profile_names()
    second = available_profile_names()
    assert first == second
    expected_profiles = {
        "agent_brief",
        "agent_standard",
        "agent_debug",
        "human_review",
        "ci_summary",
        "full",
    }
    assert expected_profiles.issubset(set(first))


def test_agent_brief_profile_output_is_smaller_than_agent_debug() -> None:
    entities, relations = _indexed_entities_and_relations()
    brief_profile = resolve_profile("agent_brief")
    debug_profile = resolve_profile("agent_debug")

    brief_pack = build_context_pack(
        task="DerivedThing implementation imports inherits",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        profile=brief_profile,
    )
    debug_pack = build_context_pack(
        task="DerivedThing implementation imports inherits",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        profile=debug_profile,
    )
    brief_markdown = render_context_pack_markdown(brief_pack, explain_ranking=False)
    debug_markdown = render_context_pack_markdown(
        debug_pack, explain_ranking=debug_profile.include_ranking_breakdown
    )
    assert len(brief_markdown) < len(debug_markdown)


def test_compact_profile_preserves_direct_task_match_symbols() -> None:
    entities, relations = _indexed_entities_and_relations()
    pack = build_context_pack(
        task="Update DerivedThing behavior",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        profile="agent_brief",
    )
    selected_names = {entity.qualified_name for entity in pack.selected_entities}
    assert "python_symbols.DerivedThing" in selected_names


def test_ranking_explanation_is_enabled_by_debug_profile_only() -> None:
    entities, relations = _indexed_entities_and_relations()
    standard_pack = build_context_pack(
        task="DerivedThing implementation",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        profile="agent_standard",
    )
    debug_profile = resolve_profile("agent_debug")
    debug_pack = build_context_pack(
        task="DerivedThing implementation",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        profile=debug_profile,
    )

    standard_markdown = render_context_pack_markdown(standard_pack, explain_ranking=False)
    debug_markdown = render_context_pack_markdown(
        debug_pack, explain_ranking=debug_profile.include_ranking_breakdown
    )
    assert "Score: total=" not in standard_markdown
    assert "Score: total=" in debug_markdown


def test_full_profile_is_at_least_as_verbose_as_standard_and_debug() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()
    full_profile = resolve_profile("full")
    standard_profile = resolve_profile("agent_standard")
    debug_profile = resolve_profile("agent_debug")

    standard_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        profile=standard_profile,
    )
    debug_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        profile=debug_profile,
    )
    full_pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        profile=full_profile,
    )

    standard_markdown = render_context_pack_markdown(
        standard_pack, explain_ranking=standard_profile.include_ranking_breakdown
    )
    debug_markdown = render_context_pack_markdown(
        debug_pack, explain_ranking=debug_profile.include_ranking_breakdown
    )
    full_markdown = render_context_pack_markdown(
        full_pack, explain_ranking=full_profile.include_ranking_breakdown
    )

    assert len(full_markdown) >= len(standard_markdown)
    assert len(full_markdown) >= len(debug_markdown)


def test_generated_artifacts_remain_suppressed_under_compact_profiles() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()
    pack = build_context_pack(
        task="Find package public exports and init modules",
        entities=entities,
        relations=relations,
        budget_chars=6000,
        profile="agent_brief",
    )
    selected_paths = {entity.source_range.path for entity in pack.selected_entities}
    assert all(not path.startswith("docs/_build/") for path in selected_paths)
    assert all(".egg-info/" not in path for path in selected_paths)


# ---------------------------------------------------------------------------
# Relation-preservation helpers and fix tests
# ---------------------------------------------------------------------------


def _relation_budget_diagnostic_for_selected(
    *,
    task: str,
    budget_chars: int,
    selected_entities: list[Entity],
    selected_relations: list[Relation],
    profile: str = "agent_standard",
) -> dict[str, object]:
    """Debug-only helper to inspect relation budgeting stages for selected items.

    Failure mode mapping:
    - A: useful relations absent from candidates
    - B: useful relations exist but no both-endpoint-selected candidate
    - C: useful both-endpoint-selected candidates exist, but none survive kept-entity truncation
    - D: top-ranked candidate is markdown/tooling contains despite useful both-selected alternatives
    - E: useful both-endpoint-selected candidates are filtered out before relation budgeting
    - F: fallback rejects all candidates due estimated relation cost
    - resolved: none of A-F triggered
    """
    resolved_profile = resolve_profile(profile)
    task_hints = frozenset(_task_hints(_tokenize(task)))
    entity_by_id = {entity.id.value: entity for entity in selected_entities}
    selected_ids = frozenset(entity_by_id.keys())
    reasons_by_key: dict[str, tuple[str, ...]] = defaultdict(tuple)

    ordered_prefilter = _order_relations_for_profile_cap(
        selected_relations=selected_relations,
        prefer_structural_relations=True,
        task_hints=task_hints,
        entity_by_id=entity_by_id,
        selected_entity_ids=selected_ids,
        selected_entity_ranks={
            entity.id.value: index for index, entity in enumerate(selected_entities)
        },
    )
    filtered_relations = filter_related_relations(ordered_prefilter, profile=resolved_profile)
    filtered_relation_keys = {relation_key(rel) for rel in filtered_relations}

    top_candidates = _top_relation_candidates(
        ordered_relations=ordered_prefilter,
        selected_ids=selected_ids,
        filtered_relation_keys=filtered_relation_keys,
        entity_by_id=entity_by_id,
        task_hints=task_hints,
    )

    kept_entities, _kept_relations, _ = _truncate_to_budget(
        task=task,
        budget_chars=budget_chars,
        selected_entities=selected_entities,
        selected_relations=filtered_relations,
        reasons_by_key=reasons_by_key,
        prefer_structural_relations=True,
        preserve_at_least_one_relation=True,
        task_hints=set(task_hints),
        entity_by_id=entity_by_id,
    )
    kept_ids = frozenset(entity.id.value for entity in kept_entities)
    dropped_ids = [
        entity.id.value for entity in selected_entities if entity.id.value not in kept_ids
    ]

    both_endpoints_kept = 0
    one_kept_one_selected = 0
    for relation in filtered_relations:
        kept_coverage = _relation_endpoint_coverage(relation, kept_ids)
        selected_coverage = _relation_endpoint_coverage(relation, selected_ids)
        if kept_coverage == 2:
            both_endpoints_kept += 1
        if kept_coverage == 1 and selected_coverage == 2:
            one_kept_one_selected += 1

    ordered_after_entity_budget = sorted(
        filtered_relations,
        key=lambda relation: _relation_budget_priority(
            relation,
            prefer_structural_relations=True,
            task_hints=task_hints,
            entity_by_id=entity_by_id,
            kept_entity_ids=kept_ids,
            selected_entity_ids=selected_ids,
            kept_entity_ranks={
                entity.id.value: index for index, entity in enumerate(kept_entities)
            },
            selected_entity_ranks={
                entity.id.value: index for index, entity in enumerate(selected_entities)
            },
        ),
    )

    used_after_entities = (
        len(task)
        + _PACK_FIXED_OVERHEAD_CHARS
        + sum(_estimate_entity_chars(entity, ()) for entity in kept_entities)
    )
    normal_kept: list[Relation] = []
    used = used_after_entities
    for relation in ordered_after_entity_budget:
        coverage = _relation_endpoint_coverage(relation, kept_ids)
        if coverage == 0:
            continue
        estimate = _estimate_relation_chars(relation, ())
        if used + estimate > budget_chars:
            continue
        normal_kept.append(relation)
        used += estimate

    fallback_attempts = _simulate_fallback_attempts(
        ordered_relations=ordered_after_entity_budget,
        kept_entities=kept_entities,
        kept_ids=kept_ids,
        used_after_entities=used_after_entities,
        budget_chars=budget_chars,
        normal_kept=normal_kept,
    )

    def _is_useful(relation: Relation) -> bool:
        return (
            relation.kind in _DIAGNOSTIC_USEFUL_RELATION_KINDS
            and not _is_markdown_or_tooling_relation(relation, entity_by_id)
        )

    useful_relations = [rel for rel in ordered_prefilter if _is_useful(rel)]
    useful_both_selected = [
        rel for rel in useful_relations if _relation_endpoint_coverage(rel, selected_ids) == 2
    ]
    useful_both_kept = [
        rel for rel in useful_relations if _relation_endpoint_coverage(rel, kept_ids) == 2
    ]
    useful_filtered_out = [
        rel for rel in useful_both_selected if relation_key(rel) not in filtered_relation_keys
    ]
    failure_mode = _classify_failure_mode(
        useful_relations=useful_relations,
        useful_both_selected=useful_both_selected,
        useful_both_kept=useful_both_kept,
        useful_filtered_out=useful_filtered_out,
        top_candidates=top_candidates,
        fallback_attempts=fallback_attempts,
    )

    return {
        "before_truncation": {
            "selected_entity_count": len(selected_entities),
            "both_endpoints_selected_count": sum(
                1
                for relation in ordered_prefilter
                if _relation_endpoint_coverage(relation, selected_ids) == 2
            ),
            "top_relation_candidates": top_candidates,
        },
        "after_entity_truncation": {
            "kept_entity_count": len(kept_entities),
            "dropped_entity_ids": dropped_ids,
            "both_endpoints_kept_count": both_endpoints_kept,
            "one_kept_one_selected_count": one_kept_one_selected,
        },
        "fallback": {"attempts": fallback_attempts},
        "public_api": {
            "exports_candidates_present": any(rel.kind == "exports" for rel in ordered_prefilter),
            "exports_candidates_filtered_out": any(
                rel.kind == "exports" and relation_key(rel) not in filtered_relation_keys
                for rel in ordered_prefilter
            ),
        },
        "failure_mode": failure_mode,
    }


def _top_relation_candidates(
    *,
    ordered_relations: list[Relation],
    selected_ids: frozenset[str],
    filtered_relation_keys: set[str],
    entity_by_id: dict[str, Entity],
    task_hints: frozenset[str],
) -> list[dict[str, object]]:
    top_candidates: list[dict[str, object]] = []
    for relation in ordered_relations[:20]:
        src = entity_by_id.get(relation.source_entity_id.value)
        tgt = entity_by_id.get(relation.target_entity_id.value)
        top_candidates.append(
            {
                "kind": relation.kind,
                "source_id": relation.source_entity_id.value,
                "target_id": relation.target_entity_id.value,
                "source_path": src.source_range.path if src else "<missing>",
                "target_path": tgt.source_range.path if tgt else "<missing>",
                "budget_priority": _relation_budget_priority(
                    relation,
                    prefer_structural_relations=True,
                    task_hints=task_hints,
                    entity_by_id=entity_by_id,
                    kept_entity_ids=selected_ids,
                    selected_entity_ids=selected_ids,
                    kept_entity_ranks={
                        entity_id: index for index, entity_id in enumerate(selected_ids)
                    },
                    selected_entity_ranks={
                        entity_id: index for index, entity_id in enumerate(selected_ids)
                    },
                ),
                "selected_endpoint_coverage": _relation_endpoint_coverage(relation, selected_ids),
                "estimated_chars": _estimate_relation_chars(relation, ()),
                "filtered_out": relation_key(relation) not in filtered_relation_keys,
            }
        )
    return top_candidates


def _simulate_fallback_attempts(
    *,
    ordered_relations: list[Relation],
    kept_entities: list[Entity],
    kept_ids: frozenset[str],
    used_after_entities: int,
    budget_chars: int,
    normal_kept: list[Relation],
) -> list[dict[str, object]]:
    if normal_kept:
        return []
    fallback_attempts: list[dict[str, object]] = []
    for relation in ordered_relations:
        estimate = _estimate_relation_chars(relation, ())
        trial_entities = list(kept_entities)
        trial_ids = set(kept_ids)
        trial_used = used_after_entities
        dropped_tail_ids: list[str] = []
        while trial_entities and trial_used + estimate > budget_chars:
            removed = trial_entities.pop()
            dropped_tail_ids.append(removed.id.value)
            trial_used -= _estimate_entity_chars(removed, ())
            trial_ids.discard(removed.id.value)
        if trial_used + estimate > budget_chars:
            fallback_attempts.append(
                {
                    "candidate": relation_key(relation),
                    "result": "rejected",
                    "reason": "estimated cost too high",
                    "dropped_tail_entity_ids": dropped_tail_ids,
                }
            )
            continue
        if _relation_endpoint_coverage(relation, frozenset(trial_ids)) == 0:
            fallback_attempts.append(
                {
                    "candidate": relation_key(relation),
                    "result": "rejected",
                    "reason": "endpoint missing",
                    "dropped_tail_entity_ids": dropped_tail_ids,
                }
            )
            continue
        fallback_attempts.append(
            {
                "candidate": relation_key(relation),
                "result": "accepted",
                "reason": "fits after fallback",
                "dropped_tail_entity_ids": dropped_tail_ids,
            }
        )
        break
    return fallback_attempts


def _classify_failure_mode(
    *,
    useful_relations: list[Relation],
    useful_both_selected: list[Relation],
    useful_both_kept: list[Relation],
    useful_filtered_out: list[Relation],
    top_candidates: list[dict[str, object]],
    fallback_attempts: list[dict[str, object]],
) -> str:
    if not useful_relations:
        return "A"
    if not useful_both_selected:
        return "B"
    if useful_both_selected and not useful_both_kept:
        return "C"
    if useful_filtered_out:
        return "E"
    if (
        top_candidates
        and top_candidates[0]["kind"] == "contains"
        and isinstance(top_candidates[0]["source_path"], str)
        and top_candidates[0]["source_path"].startswith(".github/")
        and useful_both_selected
    ):
        return "D"
    if fallback_attempts and all(
        attempt["reason"] == "estimated cost too high" for attempt in fallback_attempts
    ):
        return "F"
    return "resolved"


def test_relation_budget_diagnostic_helper_reports_requested_fields() -> None:
    entities, relations = _ranking_fixture_entities_and_all_relations()
    pack = build_context_pack(
        task="Find lifecycle component ownership and cleanup rules",
        entities=entities,
        relations=relations,
        budget_chars=200000,
        explain_ranking=True,
        profile="agent_standard",
    )
    selected_entities = list(pack.selected_entities)
    selected_ids = {entity.id.value for entity in selected_entities}
    selected_relations = [
        rel
        for rel in relations
        if rel.source_entity_id.value in selected_ids or rel.target_entity_id.value in selected_ids
    ]
    diagnostic = _relation_budget_diagnostic_for_selected(
        task="Find lifecycle component ownership and cleanup rules",
        budget_chars=1400,
        selected_entities=selected_entities,
        selected_relations=selected_relations,
    )

    assert "before_truncation" in diagnostic
    assert "after_entity_truncation" in diagnostic
    assert "fallback" in diagnostic
    assert "public_api" in diagnostic
    assert diagnostic["failure_mode"] in {"A", "B", "C", "D", "E", "F", "resolved"}


def test_profile_relation_cap_keeps_task_relevant_relation_before_tooling_contains() -> None:
    profile = resolve_profile("agent_standard")
    src_module = Entity(
        id=StableId("python:module:src.pkg.core"),
        kind="module",
        name="core",
        qualified_name="src.pkg.core",
        source_range=SourceRange(path="src/pkg/core.py", start_line=1, end_line=20),
    )
    src_class = Entity(
        id=StableId("python:class:src.pkg.core.Core"),
        kind="class",
        name="Core",
        qualified_name="src.pkg.core.Core",
        source_range=SourceRange(path="src/pkg/core.py", start_line=22, end_line=80),
    )
    useful_relation = Relation(
        kind="contains",
        source_entity_id=src_module.id,
        target_entity_id=src_class.id,
    )

    entities = [src_module, src_class]
    relations: list[Relation] = [useful_relation]
    for idx in range(60):
        file_entity = Entity(
            id=StableId(f"file:.github/instructions/policy_{idx}.md"),
            kind="file",
            name=f"policy_{idx}.md",
            qualified_name=f"policy_{idx}.md",
            source_range=SourceRange(
                path=f".github/instructions/policy_{idx}.md", start_line=1, end_line=10
            ),
        )
        section_entity = Entity(
            id=StableId(f"markdown:.github/instructions/policy_{idx}.md:section:policy:{idx}"),
            kind="doc",
            name=f"policy_{idx}",
            qualified_name=f"policy_{idx}",
            source_range=SourceRange(
                path=f".github/instructions/policy_{idx}.md", start_line=1, end_line=2
            ),
        )
        entities.extend([file_entity, section_entity])
        relations.append(
            Relation(
                kind="contains",
                source_entity_id=file_entity.id,
                target_entity_id=section_entity.id,
            )
        )

    entity_by_id = {entity.id.value: entity for entity in entities}
    selected_ids = frozenset(entity_by_id.keys())
    ordered = _order_relations_for_profile_cap(
        selected_relations=relations,
        prefer_structural_relations=True,
        task_hints=frozenset({"public_api"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=selected_ids,
        selected_entity_ranks={entity.id.value: index for index, entity in enumerate(entities)},
    )
    capped = filter_related_relations(ordered, profile=profile)

    assert useful_relation in capped[: profile.max_related_symbols]


def test_relation_cap_prefers_higher_ranked_selected_relations() -> None:
    activation_module = Entity(
        id=StableId("python:module:src.pkg.activation"),
        kind="module",
        name="activation",
        qualified_name="src.pkg.activation",
        source_range=SourceRange(path="src/pkg/activation.py", start_line=1, end_line=20),
    )
    activation_func = Entity(
        id=StableId("python:function:src.pkg.activation.require_active"),
        kind="function",
        name="require_active",
        qualified_name="src.pkg.activation.require_active",
        source_range=SourceRange(path="src/pkg/activation.py", start_line=22, end_line=40),
    )
    noise_module = Entity(
        id=StableId("python:module:examples.alpha"),
        kind="module",
        name="alpha",
        qualified_name="examples.alpha",
        source_range=SourceRange(path="examples/alpha.py", start_line=1, end_line=20),
    )
    noise_func = Entity(
        id=StableId("python:function:examples.alpha.before"),
        kind="function",
        name="before",
        qualified_name="examples.alpha.before",
        source_range=SourceRange(path="examples/alpha.py", start_line=22, end_line=30),
    )
    activation_contains = Relation(
        kind="contains",
        source_entity_id=activation_module.id,
        target_entity_id=activation_func.id,
    )
    noise_contains = Relation(
        kind="contains",
        source_entity_id=noise_module.id,
        target_entity_id=noise_func.id,
    )

    entities = [activation_module, activation_func, noise_module, noise_func]
    entity_by_id = {entity.id.value: entity for entity in entities}
    selected_order = [
        activation_module.id.value,
        activation_func.id.value,
        noise_module.id.value,
        noise_func.id.value,
    ]

    ordered = _order_relations_for_profile_cap(
        selected_relations=[noise_contains, activation_contains],
        prefer_structural_relations=True,
        task_hints=frozenset({"implementation"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=frozenset(selected_order),
        selected_entity_ranks={entity_id: index for index, entity_id in enumerate(selected_order)},
    )

    assert ordered[0] == activation_contains


def test_relation_budget_priority_prefers_both_kept_relation_over_one_kept_test_relation() -> None:
    activation_module = Entity(
        id=StableId("python:module:src.pkg.activation"),
        kind="module",
        name="activation",
        qualified_name="src.pkg.activation",
        source_range=SourceRange(path="src/pkg/activation.py", start_line=1, end_line=20),
    )
    activation_func = Entity(
        id=StableId("python:function:src.pkg.activation.require_active"),
        kind="function",
        name="require_active",
        qualified_name="src.pkg.activation.require_active",
        source_range=SourceRange(path="src/pkg/activation.py", start_line=22, end_line=40),
    )
    test_module = Entity(
        id=StableId("python:module:tests.test_activation"),
        kind="module",
        name="test_activation",
        qualified_name="tests.test_activation",
        source_range=SourceRange(path="tests/test_activation.py", start_line=1, end_line=20),
    )
    entity_by_id = {
        entity.id.value: entity for entity in (activation_module, activation_func, test_module)
    }
    contains_relation = Relation(
        kind="contains",
        source_entity_id=activation_module.id,
        target_entity_id=activation_func.id,
    )
    one_kept_test_relation = Relation(
        kind="tests",
        source_entity_id=test_module.id,
        target_entity_id=activation_module.id,
    )
    selected_order = [
        activation_module.id.value,
        activation_func.id.value,
        test_module.id.value,
    ]
    kept_order = [
        activation_module.id.value,
        activation_func.id.value,
    ]

    contains_priority = _relation_budget_priority(
        contains_relation,
        prefer_structural_relations=True,
        task_hints=frozenset({"cleanup_ownership"}),
        entity_by_id=entity_by_id,
        kept_entity_ids=frozenset(kept_order),
        selected_entity_ids=frozenset(selected_order),
        kept_entity_ranks={entity_id: index for index, entity_id in enumerate(kept_order)},
        selected_entity_ranks={entity_id: index for index, entity_id in enumerate(selected_order)},
    )
    one_kept_test_priority = _relation_budget_priority(
        one_kept_test_relation,
        prefer_structural_relations=True,
        task_hints=frozenset({"cleanup_ownership"}),
        entity_by_id=entity_by_id,
        kept_entity_ids=frozenset(kept_order),
        selected_entity_ids=frozenset(selected_order),
        kept_entity_ranks={entity_id: index for index, entity_id in enumerate(kept_order)},
        selected_entity_ranks={entity_id: index for index, entity_id in enumerate(selected_order)},
    )

    assert contains_priority < one_kept_test_priority


def test_relation_helpers_classify_source_and_tooling_paths() -> None:
    """_is_source_code_relation and _is_markdown_or_tooling_relation classify paths correctly."""
    from repo_semantic_memory.context.pack_builder import (
        _is_markdown_or_tooling_relation,
        _is_source_code_relation,
    )

    src_entity = Entity(
        id=StableId("python:module:mymod"),
        kind="module",
        name="mymod",
        qualified_name="mymod",
        source_range=SourceRange(path="src/mymod.py", start_line=1, end_line=1),
    )
    github_entity = Entity(
        id=StableId("file:.github/instructions/policy.md"),
        kind="file",
        name="policy.md",
        qualified_name="policy.md",
        source_range=SourceRange(path=".github/instructions/policy.md", start_line=1, end_line=1),
    )
    copilot_entity = Entity(
        id=StableId("file:tools/copilot/playbook.md"),
        kind="file",
        name="playbook.md",
        qualified_name="playbook.md",
        source_range=SourceRange(path="tools/copilot/playbook.md", start_line=1, end_line=1),
    )
    doc_entity = Entity(
        id=StableId("file:docs/guide.md"),
        kind="file",
        name="guide.md",
        qualified_name="guide.md",
        source_range=SourceRange(path="docs/guide.md", start_line=1, end_line=1),
    )
    entity_by_id = {
        src_entity.id.value: src_entity,
        github_entity.id.value: github_entity,
        copilot_entity.id.value: copilot_entity,
        doc_entity.id.value: doc_entity,
    }

    src_rel = Relation(
        kind="contains",
        source_entity_id=StableId("python:module:mymod"),
        target_entity_id=StableId("python:class:mymod.Cls"),
    )
    github_rel = Relation(
        kind="contains",
        source_entity_id=StableId("file:.github/instructions/policy.md"),
        target_entity_id=StableId("markdown:.github/instructions/policy.md:section:x:1"),
    )
    copilot_rel = Relation(
        kind="contains",
        source_entity_id=StableId("file:tools/copilot/playbook.md"),
        target_entity_id=StableId("markdown:tools/copilot/playbook.md:section:x:1"),
    )
    doc_rel = Relation(
        kind="contains",
        source_entity_id=StableId("file:docs/guide.md"),
        target_entity_id=StableId("markdown:docs/guide.md:section:x:1"),
    )

    assert _is_source_code_relation(src_rel, entity_by_id)
    assert not _is_source_code_relation(github_rel, entity_by_id)
    assert not _is_source_code_relation(doc_rel, entity_by_id)

    assert not _is_markdown_or_tooling_relation(src_rel, entity_by_id)
    assert _is_markdown_or_tooling_relation(github_rel, entity_by_id)
    assert _is_markdown_or_tooling_relation(copilot_rel, entity_by_id)
    # docs/ is NOT a tooling path.
    assert not _is_markdown_or_tooling_relation(doc_rel, entity_by_id)


def test_relation_task_priority_public_api_ranks_exports_over_tooling_contains() -> None:
    """For public_api hints: exports has priority 0 (highest), then source contains, tests,
    .github/tooling contains (lowest).  Lower number = higher priority in the sort order."""
    from repo_semantic_memory.context.pack_builder import _relation_task_priority

    github_entity = Entity(
        id=StableId("file:.github/instructions/policy.md"),
        kind="file",
        name="policy.md",
        qualified_name="policy.md",
        source_range=SourceRange(path=".github/instructions/policy.md", start_line=1, end_line=1),
    )
    src_entity = Entity(
        id=StableId("python:module:src.mymod"),
        kind="module",
        name="mymod",
        qualified_name="src.mymod",
        source_range=SourceRange(path="src/mymod.py", start_line=1, end_line=1),
    )
    entity_by_id = {
        github_entity.id.value: github_entity,
        src_entity.id.value: src_entity,
    }

    exports_rel = Relation(
        kind="exports",
        source_entity_id=StableId("python:module:src.mymod"),
        target_entity_id=StableId("unresolved:export:src.mymod:Cls"),
    )
    tests_rel = Relation(
        kind="tests",
        source_entity_id=StableId("python:module:tests.test_mod"),
        target_entity_id=StableId("python:module:src.mymod"),
    )
    src_contains = Relation(
        kind="contains",
        source_entity_id=StableId("python:module:src.mymod"),
        target_entity_id=StableId("python:class:src.mymod.Cls"),
    )
    github_contains = Relation(
        kind="contains",
        source_entity_id=StableId("file:.github/instructions/policy.md"),
        target_entity_id=StableId("markdown:.github/instructions/policy.md:section:x:1"),
    )

    hints: frozenset[str] = frozenset({"public_api"})
    p_exports = _relation_task_priority(exports_rel, task_hints=hints, entity_by_id=entity_by_id)
    p_tests = _relation_task_priority(tests_rel, task_hints=hints, entity_by_id=entity_by_id)
    p_src_contains = _relation_task_priority(
        src_contains, task_hints=hints, entity_by_id=entity_by_id
    )
    p_github = _relation_task_priority(github_contains, task_hints=hints, entity_by_id=entity_by_id)

    assert p_exports == 0, f"exports should have highest priority (0); got {p_exports}"
    assert p_src_contains == 1, f"source contains should have priority 1; got {p_src_contains}"
    assert p_tests == 2, f"tests should have priority 2; got {p_tests}"
    assert p_github > p_src_contains, (
        f".github contains ({p_github}) must rank lower than source contains ({p_src_contains})"
    )
    assert p_github > p_exports, (
        f".github contains ({p_github}) must rank lower than exports ({p_exports})"
    )


def test_relation_task_priority_implementation_prefers_source_contains_before_tests() -> None:
    from repo_semantic_memory.context.pack_builder import _relation_task_priority

    src_entity = Entity(
        id=StableId("python:module:src.activation"),
        kind="module",
        name="activation",
        qualified_name="src.activation",
        source_range=SourceRange(path="src/activation.py", start_line=1, end_line=1),
    )
    entity_by_id = {src_entity.id.value: src_entity}
    src_contains = Relation(
        kind="contains",
        source_entity_id=StableId("python:module:src.activation"),
        target_entity_id=StableId("python:function:src.activation.require_active"),
    )
    tests_rel = Relation(
        kind="tests",
        source_entity_id=StableId("python:module:tests.test_activation"),
        target_entity_id=StableId("python:module:src.activation"),
    )

    hints: frozenset[str] = frozenset({"implementation"})
    p_src_contains = _relation_task_priority(
        src_contains, task_hints=hints, entity_by_id=entity_by_id
    )
    p_tests = _relation_task_priority(tests_rel, task_hints=hints, entity_by_id=entity_by_id)

    assert p_src_contains < p_tests, (
        f"implementation should prefer source contains over tests ({p_src_contains=} {p_tests=})"
    )


def test_relation_task_priority_cleanup_prefers_tests_then_source_contains() -> None:
    from repo_semantic_memory.context.pack_builder import _relation_task_priority

    src_entity = Entity(
        id=StableId("python:module:src.lifecycle"),
        kind="module",
        name="lifecycle",
        qualified_name="src.lifecycle",
        source_range=SourceRange(path="src/lifecycle.py", start_line=1, end_line=1),
    )
    entity_by_id = {src_entity.id.value: src_entity}
    src_contains = Relation(
        kind="contains",
        source_entity_id=StableId("python:module:src.lifecycle"),
        target_entity_id=StableId("python:class:src.lifecycle.LifecycleComponent"),
    )
    tests_rel = Relation(
        kind="tests",
        source_entity_id=StableId("python:module:tests.test_lifecycle"),
        target_entity_id=StableId("python:module:src.lifecycle"),
    )

    hints: frozenset[str] = frozenset({"cleanup_ownership"})
    p_tests = _relation_task_priority(tests_rel, task_hints=hints, entity_by_id=entity_by_id)
    p_src_contains = _relation_task_priority(
        src_contains, task_hints=hints, entity_by_id=entity_by_id
    )

    assert p_tests < p_src_contains, (
        f"cleanup/ownership should prefer tests over source contains ({p_tests=} {p_src_contains=})"
    )


def test_ensure_minimum_relation_coverage_nondestructive() -> None:
    """Failed R_big trial must not corrupt kept_entities before R_small is tried."""
    from repo_semantic_memory.context.pack_builder import (
        _ensure_minimum_relation_coverage,
        _estimate_entity_chars,
        _estimate_relation_chars,
    )

    # E_a is a cheap entity whose id is the endpoint for both relations.
    e_a = Entity(
        id=StableId("python:class:mod.A"),
        kind="class",
        name="A",
        qualified_name="mod.A",
        source_range=SourceRange(path="src/mod.py", start_line=1, end_line=3),
    )
    # E_b is heavy (long qualified name → large budget estimate).
    e_b = Entity(
        id=StableId("python:class:mod." + "B" * 180),
        kind="class",
        name="B",
        qualified_name="mod." + "B" * 180,
        source_range=SourceRange(path="src/mod.py", start_line=4, end_line=10),
    )

    # R_big: expensive relation (long source id) → forces both entities to be popped,
    # leaving e_a's id absent from the trial entity set → R_big fails.
    big_source_id = "external:" + "X" * 180
    r_big = Relation(
        kind="exports",
        source_entity_id=StableId(big_source_id),
        target_entity_id=StableId(e_a.id.value),
    )
    # R_small: cheap relation, same target endpoint (e_a).  Fits without any pops.
    r_small = Relation(
        kind="contains",
        source_entity_id=StableId("python:module:mod"),
        target_entity_id=StableId(e_a.id.value),
    )

    e_a_cost = _estimate_entity_chars(e_a, ())
    e_b_cost = _estimate_entity_chars(e_b, ())
    r_big_cost = _estimate_relation_chars(r_big, ())
    r_small_cost = _estimate_relation_chars(r_small, ())
    used = e_a_cost + e_b_cost
    budget = used + r_small_cost  # only enough room for r_small (not r_big)

    assert used + r_big_cost > budget, "R_big must require entity popping"
    assert r_big_cost <= budget, "R_big must eventually fit after all entities are popped"
    assert used + r_small_cost <= budget, "R_small must fit without any popping"

    # kept_entities ordered so e_a is last → it gets popped first in R_big's trial.
    kept_entities: list[Entity] = [e_b, e_a]
    kept_entity_ids: set[str] = {e_a.id.value, e_b.id.value}

    result, _result_used, _ = _ensure_minimum_relation_coverage(
        ordered_relations=[r_big, r_small],
        kept_entities=kept_entities,
        kept_entity_ids=kept_entity_ids,
        reasons_by_key={},
        used=used,
        budget_chars=budget,
        truncated=False,
    )

    # With the non-destructive fix: R_big trial fails (e_a popped in trial → endpoint gone)
    # but R_small trial starts fresh → e_a is still present → R_small succeeds.
    assert result == [r_small], (
        f"R_small should be selected after R_big's trial fails. Got: {[r.kind for r in result]}"
    )
    # The commit for R_small should NOT have popped e_a (it fitted without popping).
    assert e_a.id.value in kept_entity_ids, "e_a must remain in kept_entity_ids after R_small"
    assert e_b.id.value in kept_entity_ids, "e_b must remain in kept_entity_ids after R_small"


def test_truncate_to_budget_trades_tail_entity_to_keep_useful_relation() -> None:
    from repo_semantic_memory.context.pack_builder import (
        _PACK_FIXED_OVERHEAD_CHARS,
        _estimate_entity_chars,
        _estimate_relation_chars,
        _truncate_to_budget,
    )

    e_a = Entity(
        id=StableId("python:module:src.lifecycle_component"),
        kind="module",
        name="lifecycle_component",
        qualified_name="src.lifecycle_component",
        source_range=SourceRange(path="src/lifecycle_component.py", start_line=1, end_line=20),
    )
    e_b = Entity(
        id=StableId("python:class:src.lifecycle_component.LifecycleComponent"),
        kind="class",
        name="LifecycleComponent",
        qualified_name="src.lifecycle_component.LifecycleComponent",
        source_range=SourceRange(path="src/lifecycle_component.py", start_line=22, end_line=90),
    )
    useful_relation = Relation(
        kind="contains",
        source_entity_id=e_a.id,
        target_entity_id=e_b.id,
    )
    # Derive tail size from relation estimate so dropping tail reliably
    # makes room for that relation.
    tail_multiplier = max(8, (_estimate_relation_chars(useful_relation, ()) // len("Tail")) + 8)
    e_tail = Entity(
        id=StableId("python:class:src.lifecycle_component." + "Tail" * tail_multiplier),
        kind="class",
        name="Tail",
        qualified_name="src.lifecycle_component." + "Tail" * tail_multiplier,
        source_range=SourceRange(path="src/lifecycle_component.py", start_line=100, end_line=180),
    )

    task = "Find lifecycle component ownership and cleanup rules"
    used_base = len(task) + _PACK_FIXED_OVERHEAD_CHARS
    budget = (
        used_base
        + _estimate_entity_chars(e_a, ())
        + _estimate_entity_chars(e_b, ())
        + _estimate_entity_chars(e_tail, ())
    )

    kept_entities, kept_relations, truncated = _truncate_to_budget(
        task=task,
        budget_chars=budget,
        selected_entities=[e_a, e_b, e_tail],
        selected_relations=[useful_relation],
        reasons_by_key={},
        prefer_structural_relations=True,
        preserve_at_least_one_relation=True,
        task_hints={"cleanup_ownership", "implementation"},
        entity_by_id={e.id.value: e for e in (e_a, e_b, e_tail)},
    )

    kept_entity_ids = {entity.id.value for entity in kept_entities}
    assert useful_relation in kept_relations
    assert e_a.id.value in kept_entity_ids
    assert e_b.id.value in kept_entity_ids
    assert e_tail.id.value not in kept_entity_ids, "tail entity should be traded to fit relation"
    assert truncated


def test_explain_ranking_github_tooling_contains_does_not_outrank_source_relations(
    tmp_path: Path,
) -> None:
    """For public_api tasks, .github markdown contains must not outrank exports or tests."""
    repo = tmp_path / "repo"
    (repo / "src" / "mypkg").mkdir(parents=True)
    (repo / ".github" / "instructions").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)

    (repo / "src" / "mypkg" / "__init__.py").write_text(
        "from .core import MyClass\n\n__all__ = ['MyClass']\n",
        encoding="utf-8",
    )
    (repo / "src" / "mypkg" / "core.py").write_text(
        "class MyClass:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_mypkg.py").write_text(
        "from mypkg import MyClass\n\ndef test_myclass() -> None:\n    assert MyClass\n",
        encoding="utf-8",
    )
    # The .github file intentionally mentions task keywords so it competes for selection.
    (repo / ".github" / "instructions" / "policy.md").write_text(
        "# Copilot Policy\n\nThis policy governs public API and exports for MyClass usage.\n",
        encoding="utf-8",
    )

    filesystem_entities = [
        entity
        for entity in extract_filesystem_entities(repo)
        if not (entity.kind == "module" and entity.source_range.path.endswith(".py"))
    ]
    markdown_outline = extract_markdown_outline_path(repo)
    python_entities, python_relations = index_python_path(repo)
    export_relations = index_python_exports(repo)
    test_relations = extract_test_relationships(repo, [*filesystem_entities, *python_entities])
    entities = [*filesystem_entities, *markdown_outline.entities, *python_entities]
    relations = [
        *markdown_outline.relations,
        *python_relations,
        *export_relations,
        *test_relations,
    ]

    pack = build_context_pack(
        task="Find public API exported by the package",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        explain_ranking=True,
    )

    selected_relation_kinds = {r.kind for r in pack.selected_relations}
    assert selected_relation_kinds & {"exports", "tests", "contains"}, (
        f"Expected source/structural relations; got only: {selected_relation_kinds}"
    )

    # Specifically: for a public_api task, exports or tests must be present.
    assert selected_relation_kinds & {"exports", "tests"}, (
        "public_api pack must include exports or tests relation, "
        f"not only .github markdown contains. Got: {selected_relation_kinds}"
    )


def test_explain_ranking_cleanup_and_activation_nonempty_relations_tight_budget() -> None:
    """cleanup/activation-style packs must retain non-empty selected_relations at tight budget."""
    entities, relations = _ranking_fixture_entities_and_all_relations()

    for task in (
        "Find lifecycle component ownership and cleanup rules",
        "Find where activation gating is implemented",
    ):
        pack = build_context_pack(
            task=task,
            entities=entities,
            relations=relations,
            budget_chars=1400,
            explain_ranking=True,
        )
        assert pack.selected_relations, f"selected_relations must be non-empty for task: {task!r}"
        assert any(
            r.kind in {"contains", "exports", "tests", "owns", "uses"}
            for r in pack.selected_relations
        ), (
            f"Expected source/structural relations for task: {task!r}; "
            f"got: {[r.kind for r in pack.selected_relations]}"
        )


def test_public_api_relation_priority_prefers_exports_over_imports() -> None:
    package = Entity(
        id=StableId("python:module:pkg"),
        kind="module",
        name="pkg",
        qualified_name="pkg",
        source_range=SourceRange(path="src/pkg/__init__.py", start_line=1, end_line=5),
    )
    api = Entity(
        id=StableId("python:function:pkg.api"),
        kind="function",
        name="api",
        qualified_name="pkg.api",
        source_range=SourceRange(path="src/pkg/api.py", start_line=1, end_line=5),
    )
    entity_by_id = {package.id.value: package, api.id.value: api}
    import_context = build_import_scoring_context([package, api])
    export_relation = Relation(kind="exports", source_entity_id=package.id, target_entity_id=api.id)
    import_relation = Relation(
        kind="imports",
        source_entity_id=package.id,
        target_entity_id=StableId("python:imports:pkg.api"),
        metadata={"imported_name": "pkg.api"},
    )

    assert _relation_budget_priority(
        export_relation,
        prefer_structural_relations=True,
        task_hints=frozenset({"public_api"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=frozenset(entity_by_id),
        kept_entity_ids=frozenset(entity_by_id),
        import_context=import_context,
    ) < _relation_budget_priority(
        import_relation,
        prefer_structural_relations=True,
        task_hints=frozenset({"public_api"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=frozenset(entity_by_id),
        kept_entity_ids=frozenset(entity_by_id),
        import_context=import_context,
    )


def test_test_task_relation_priority_keeps_tests_above_pytest_imports() -> None:
    test_module = Entity(
        id=StableId("python:module:tests.test_core"),
        kind="module",
        name="test_core",
        qualified_name="tests.test_core",
        source_range=SourceRange(path="tests/test_core.py", start_line=1, end_line=20),
    )
    source_module = Entity(
        id=StableId("python:module:pkg.core"),
        kind="module",
        name="core",
        qualified_name="pkg.core",
        source_range=SourceRange(path="src/pkg/core.py", start_line=1, end_line=20),
    )
    entity_by_id = {test_module.id.value: test_module, source_module.id.value: source_module}
    import_context = build_import_scoring_context([test_module, source_module])
    tests_relation = Relation(
        kind="tests",
        source_entity_id=test_module.id,
        target_entity_id=source_module.id,
    )
    pytest_import = Relation(
        kind="imports",
        source_entity_id=test_module.id,
        target_entity_id=StableId("python:imports:pytest"),
        metadata={"imported_name": "pytest"},
    )

    assert _relation_budget_priority(
        tests_relation,
        prefer_structural_relations=True,
        task_hints=frozenset({"tests"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=frozenset(entity_by_id),
        kept_entity_ids=frozenset(entity_by_id),
        import_context=import_context,
    ) < _relation_budget_priority(
        pytest_import,
        prefer_structural_relations=True,
        task_hints=frozenset({"tests"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=frozenset(entity_by_id),
        kept_entity_ids=frozenset(entity_by_id),
        import_context=import_context,
    )


def test_import_weighting_does_not_change_non_import_relation_priority() -> None:
    module = Entity(
        id=StableId("python:module:pkg.core"),
        kind="module",
        name="core",
        qualified_name="pkg.core",
        source_range=SourceRange(path="src/pkg/core.py", start_line=1, end_line=20),
    )
    function = Entity(
        id=StableId("python:function:pkg.core.run"),
        kind="function",
        name="run",
        qualified_name="pkg.core.run",
        source_range=SourceRange(path="src/pkg/core.py", start_line=4, end_line=8),
    )
    dependency = Entity(
        id=StableId("python:module:pkg.dependency"),
        kind="module",
        name="dependency",
        qualified_name="pkg.dependency",
        source_range=SourceRange(path="src/pkg/dependency.py", start_line=1, end_line=20),
    )
    entity_by_id = {entity.id.value: entity for entity in (module, function, dependency)}
    contains_relation = Relation(
        kind="contains",
        source_entity_id=module.id,
        target_entity_id=function.id,
    )
    uses_relation = Relation(
        kind="uses",
        source_entity_id=function.id,
        target_entity_id=dependency.id,
    )

    assert _relation_budget_priority(
        contains_relation,
        prefer_structural_relations=True,
        task_hints=frozenset({"implementation"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=frozenset(entity_by_id),
        kept_entity_ids=frozenset(entity_by_id),
    ) < _relation_budget_priority(
        uses_relation,
        prefer_structural_relations=True,
        task_hints=frozenset({"implementation"}),
        entity_by_id=entity_by_id,
        selected_entity_ids=frozenset(entity_by_id),
        kept_entity_ids=frozenset(entity_by_id),
    )


def test_realistic_fixture_favors_local_helper_import_over_dependency_noise(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src" / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helper.py").write_text("def assist() -> str:\n    return 'ok'\n", encoding="utf-8")
    (package / "logic.py").write_text(
        "from pkg.helper import assist\n\ndef business_logic() -> str:\n    return assist()\n",
        encoding="utf-8",
    )
    (package / "numeric.py").write_text("import numpy\n", encoding="utf-8")
    (package / "paths.py").write_text("from pathlib import Path\n", encoding="utf-8")

    entities, relations = index_python_path(tmp_path)
    pack = build_context_pack(
        task="business logic",
        entities=entities,
        relations=relations,
        budget_chars=4000,
        explain_ranking=True,
        profile="agent_standard",
    )

    selected_names = [entity.qualified_name for entity in pack.selected_entities]
    assert "pkg.helper.assist" in selected_names
    missing_dependency_rank = len(selected_names) + 1
    numeric_index = (
        selected_names.index("pkg.numeric")
        if "pkg.numeric" in selected_names
        else missing_dependency_rank
    )
    paths_index = (
        selected_names.index("pkg.paths")
        if "pkg.paths" in selected_names
        else missing_dependency_rank
    )
    helper_index = selected_names.index("pkg.helper.assist")
    assert helper_index < numeric_index
    assert helper_index < paths_index
    helper_breakdown = pack.ranking_breakdowns[
        "python:src/pkg/helper.py:function:pkg.helper.assist"
    ]
    assert any("imports/local_package" in reason.message for reason in helper_breakdown.reasons)


# ---------------------------------------------------------------------------
# 58.7B regression tests: exact-name boost path-coherence guard
# ---------------------------------------------------------------------------


def _make_method_entity(
    eid: str,
    name: str,
    qualified_name: str,
    source_path: str,
) -> Entity:
    return Entity(
        id=StableId(eid),
        kind="method",
        name=name,
        qualified_name=qualified_name,
        source_range=SourceRange(path=source_path, start_line=1, end_line=5),
    )


def _make_module_entity(
    eid: str,
    name: str,
    qualified_name: str,
    source_path: str,
) -> Entity:
    return Entity(
        id=StableId(eid),
        kind="module",
        name=name,
        qualified_name=qualified_name,
        source_range=SourceRange(path=source_path, start_line=1, end_line=100),
    )


def _make_class_entity(
    eid: str,
    name: str,
    qualified_name: str,
    source_path: str,
) -> Entity:
    return Entity(
        id=StableId(eid),
        kind="class",
        name=name,
        qualified_name=qualified_name,
        source_range=SourceRange(path=source_path, start_line=1, end_line=50),
    )


def _build_pack(entities: list[Entity], task: str, budget: int = 8000) -> ContextPack:
    return build_context_pack(task=task, entities=entities, relations=[], budget_chars=budget)


def test_url_routing_module_outranks_unrelated_url_method(tmp_path: Path) -> None:
    """A url-routing module (path-coherent) must rank ahead of a bare .url attribute
    on an unrelated class that only matches via name equality.

    Regression for: Storage.url, FieldFile.url, StaticNode.url, Stylesheet.url,
    HashedFilesMixin.url getting the full exact-match boost for a URL-routing query.
    """
    # Routing module: "url" appears in source_path ("django/urls/resolvers.py")
    routing_module = _make_module_entity(
        eid="python:django/urls/resolvers.py:module:django.urls.resolvers",
        name="resolvers",
        qualified_name="django.urls.resolvers",
        source_path="django/urls/resolvers.py",
    )
    routing_class = _make_class_entity(
        eid="python:django/urls/resolvers.py:class:django.urls.resolvers.URLResolver",
        name="URLResolver",
        qualified_name="django.urls.resolvers.URLResolver",
        source_path="django/urls/resolvers.py",
    )
    # Unrelated storage method named "url": source_path does NOT contain "url" segment.
    storage_url_method = _make_method_entity(
        eid="python:django/core/files/storage.py:method:django.core.files.storage.Storage.url",
        name="url",
        qualified_name="django.core.files.storage.Storage.url",
        source_path="django/core/files/storage.py",
    )
    fieldfile_url_method = _make_method_entity(
        eid="python:django/db/models/fields/files.py:method:django.db.models.fields.files.FieldFile.url",
        name="url",
        qualified_name="django.db.models.fields.files.FieldFile.url",
        source_path="django/db/models/fields/files.py",
    )
    # Filler entities to give BM25 IDF realistic corpus diversity.
    filler = [
        _make_module_entity(
            f"filler:{i}",
            f"module{i}",
            f"pkg.module{i}",
            f"pkg/module{i}.py",
        )
        for i in range(20)
    ]

    entities = [routing_module, routing_class, storage_url_method, fieldfile_url_method, *filler]
    task = "Find how URL routing resolver implementation works"
    pack = _build_pack(entities, task)

    selected_ids = [e.id.value for e in pack.selected_entities]
    routing_index = next(
        (i for i, e in enumerate(pack.selected_entities) if "resolvers" in e.source_range.path),
        None,
    )
    storage_index = next(
        (
            i
            for i, e in enumerate(pack.selected_entities)
            if e.qualified_name == "django.core.files.storage.Storage.url"
        ),
        len(selected_ids),  # not selected = effectively last
    )
    fieldfile_index = next(
        (
            i
            for i, e in enumerate(pack.selected_entities)
            if e.qualified_name == "django.db.models.fields.files.FieldFile.url"
        ),
        len(selected_ids),
    )

    assert routing_index is not None, (
        "django.urls.resolvers module/class must be selected for a URL-routing query"
    )
    assert routing_index < storage_index, (
        f"routing module (rank {routing_index}) must precede Storage.url (rank {storage_index})"
    )
    assert routing_index < fieldfile_index, (
        f"routing module (rank {routing_index}) must precede FieldFile.url (rank {fieldfile_index})"
    )


def test_url_method_in_urls_path_retains_selection() -> None:
    """A .url method whose source_path contains 'url' as a segment is still eligible for selection.

    This ensures the path-coherence guard does not suppress legitimate URL-subsystem entities.
    """
    urls_url_method = _make_method_entity(
        eid="python:django/urls/resolvers.py:method:django.urls.resolvers.ResolverMatch.url",
        name="url",
        qualified_name="django.urls.resolvers.ResolverMatch.url",
        source_path="django/urls/resolvers.py",
    )
    unrelated_url_method = _make_method_entity(
        eid="python:django/core/files/storage.py:method:django.core.files.storage.Storage.url",
        name="url",
        qualified_name="django.core.files.storage.Storage.url",
        source_path="django/core/files/storage.py",
    )
    filler = [
        _make_module_entity(f"filler:{i}", f"module{i}", f"pkg.module{i}", f"pkg/module{i}.py")
        for i in range(20)
    ]

    task = "Find how URL routing resolver implementation works"
    pack = _build_pack([urls_url_method, unrelated_url_method, *filler], task)

    selected_names = [e.qualified_name for e in pack.selected_entities]
    urls_index = next(
        (i for i, n in enumerate(selected_names) if "ResolverMatch.url" in n),
        None,
    )
    unrelated_index = next(
        (i for i, n in enumerate(selected_names) if "Storage.url" in n),
        len(selected_names),
    )
    # The urls-subsystem method must be selected and rank ahead of the unrelated one.
    assert urls_index is not None, "url method in urls/ path must be selected"
    assert urls_index < unrelated_index, (
        f"url method in urls/ ({urls_index}) must rank before unrelated Storage.url "
        f"({unrelated_index})"
    )


def test_ansible_plugin_loader_outranks_cgroup_loads_method() -> None:
    """Ansible plugin loader module must outrank unrelated .loads methods in cgroup code.

    Regression for: MountEntry.loads and CGroupEntry.loads winning over
    lib/ansible/plugins/loader.py for an Ansible plugin-loading query.
    """
    loader_module = _make_module_entity(
        eid="python:lib/ansible/plugins/loader.py:module:ansible.plugins.loader",
        name="loader",
        qualified_name="ansible.plugins.loader",
        source_path="lib/ansible/plugins/loader.py",
    )
    cgroup_loads_method = _make_method_entity(
        eid="python:test/lib/ansible_test/_internal/cgroup.py:method:cgroup.CGroupEntry.loads",
        name="loads",
        qualified_name="cgroup.CGroupEntry.loads",
        source_path="test/lib/ansible_test/_internal/cgroup.py",
    )
    mount_loads_method = _make_method_entity(
        eid="python:test/lib/ansible_test/_internal/cgroup.py:method:cgroup.MountEntry.loads",
        name="loads",
        qualified_name="cgroup.MountEntry.loads",
        source_path="test/lib/ansible_test/_internal/cgroup.py",
    )
    filler = [
        _make_module_entity(f"filler:{i}", f"module{i}", f"pkg.module{i}", f"pkg/module{i}.py")
        for i in range(20)
    ]

    entities = [loader_module, cgroup_loads_method, mount_loads_method, *filler]
    task = "Find how Ansible plugin loading works"
    pack = _build_pack(entities, task)

    selected_names = [e.qualified_name for e in pack.selected_entities]
    loader_index = next(
        (i for i, n in enumerate(selected_names) if "ansible.plugins.loader" in n),
        None,
    )
    cgroup_index = next(
        (i for i, n in enumerate(selected_names) if "CGroupEntry.loads" in n),
        len(selected_names),
    )
    mount_index = next(
        (i for i, n in enumerate(selected_names) if "MountEntry.loads" in n),
        len(selected_names),
    )

    assert loader_index is not None, (
        "ansible.plugins.loader must be selected for a plugin-loading query"
    )
    assert loader_index < cgroup_index, (
        f"ansible loader (rank {loader_index}) must precede CGroupEntry.loads (rank {cgroup_index})"
    )
    assert loader_index < mount_index, (
        f"ansible loader (rank {loader_index}) must precede MountEntry.loads (rank {mount_index})"
    )


# ---------------------------------------------------------------------------
# 58.7C regression tests: docs/tutorial/example path noise suppression
# ---------------------------------------------------------------------------


def test_implementation_file_outranks_docs_src_tutorial_for_neutral_query() -> None:
    """docs_src/ tutorial files must not outrank source impl files for code-search queries.

    Regression for: Typer docs_src/commands/callback/tutorial001.py ranking ahead of
    typer/core.py when querying "Find how Typer callback command processing works".
    """
    tutorial = _make_module_entity(
        eid="python:docs_src/commands/callback/tutorial001.py:module:tutorial001",
        name="tutorial001",
        qualified_name="tutorial001",
        source_path="docs_src/commands/callback/tutorial001.py",
    )
    impl = _make_module_entity(
        eid="python:typer/core.py:module:typer.core",
        name="core",
        qualified_name="typer.core",
        source_path="typer/core.py",
    )
    filler = [
        _make_module_entity(f"filler:{i}", f"module{i}", f"pkg.module{i}", f"pkg/module{i}.py")
        for i in range(20)
    ]
    task = "Find how Typer callback command processing works"
    pack = _build_pack([tutorial, impl, *filler], task)

    selected_qnames = [e.qualified_name for e in pack.selected_entities]
    impl_index = next(
        (i for i, q in enumerate(selected_qnames) if q == "typer.core"),
        None,
    )
    tutorial_index = next(
        (i for i, q in enumerate(selected_qnames) if "tutorial001" in q),
        len(selected_qnames),
    )
    assert impl_index is not None, (
        "typer.core implementation module must be selected for a callback-processing query"
    )
    assert impl_index < tutorial_index, (
        f"typer.core (rank {impl_index}) must rank ahead of docs_src tutorial "
        f"(rank {tutorial_index})"
    )


def test_tutorials_path_does_not_outrank_source_for_neutral_query() -> None:
    """tutorials/ paths must be penalized for neutral code-search queries."""
    tutorial = _make_module_entity(
        eid="python:tutorials/getting_started.py:module:getting_started",
        name="getting_started",
        qualified_name="getting_started",
        source_path="tutorials/getting_started.py",
    )
    impl = _make_module_entity(
        eid="python:src/mypackage/core.py:module:mypackage.core",
        name="core",
        qualified_name="mypackage.core",
        source_path="src/mypackage/core.py",
    )
    filler = [
        _make_module_entity(f"filler:{i}", f"module{i}", f"pkg.module{i}", f"pkg/module{i}.py")
        for i in range(20)
    ]
    task = "How does core processing work in mypackage"
    pack = _build_pack([tutorial, impl, *filler], task)

    selected_qnames = [e.qualified_name for e in pack.selected_entities]
    impl_index = next(
        (i for i, q in enumerate(selected_qnames) if q == "mypackage.core"),
        None,
    )
    tutorial_index = next(
        (i for i, q in enumerate(selected_qnames) if q == "getting_started"),
        len(selected_qnames),
    )
    assert impl_index is not None, "mypackage.core must be selected for an implementation query"
    assert impl_index < tutorial_index, (
        f"source impl (rank {impl_index}) must rank ahead of tutorials/ path "
        f"(rank {tutorial_index})"
    )


def test_docs_tutorial_selectable_when_query_explicitly_requests_tutorial() -> None:
    """docs_src/ tutorial files stay selectable when the query explicitly asks for tutorials.

    This verifies the docs_examples intent gate: penalty is skipped for documentation queries.
    """
    tutorial = _make_module_entity(
        eid="python:docs_src/commands/callback/tutorial001.py:module:tutorial001",
        name="tutorial001",
        qualified_name="tutorial001",
        source_path="docs_src/commands/callback/tutorial001.py",
    )
    impl = _make_module_entity(
        eid="python:typer/core.py:module:typer.core",
        name="core",
        qualified_name="typer.core",
        source_path="typer/core.py",
    )
    filler = [
        _make_module_entity(f"filler:{i}", f"module{i}", f"pkg.module{i}", f"pkg/module{i}.py")
        for i in range(20)
    ]
    # Explicit tutorial/example request → docs_examples intent fires → no penalty
    task = "Show me the tutorial examples for callback commands"
    pack = _build_pack([tutorial, impl, *filler], task)

    selected_qnames = [e.qualified_name for e in pack.selected_entities]
    assert "tutorial001" in selected_qnames, (
        "docs_src tutorial must stay selectable when query explicitly asks for tutorials"
    )


# ---------------------------------------------------------------------------
# 58.7E — compact preview per-file cap
# ---------------------------------------------------------------------------


def _make_direct_pack(entities: list[Entity], budget: int = 8000) -> ContextPack:
    """Build a minimal ContextPack for render-layer tests; bypasses ranking."""
    return ContextPack(
        task="test task",
        budget=budget,
        selected_entities=tuple(entities),
        selected_relations=(),
        source_citations=(),
        why_selected={},
        ranking_breakdowns={},
        semantic_components=(),
        uncertainties=(),
        suggested_files_to_inspect=(),
        forbidden_assumptions=(),
    )


class TestCompactPerPathCap:
    """Compact rendering shows ≤5 entities per source_path; selected_entities unchanged."""

    def test_compact_capped_at_five_per_source_path(self) -> None:
        """Compact output shows at most 5 entities for a single source file."""
        entities = [
            _make_module_entity(
                eid=f"python:pkg/big_module.py:function:pkg.func{i}",
                name=f"func{i}",
                qualified_name=f"pkg.func{i}",
                source_path="pkg/big_module.py",
            )
            for i in range(8)
        ]
        pack = _make_direct_pack(entities)
        markdown = render_context_pack_markdown(pack)

        # Only 5 bullets for pkg/big_module.py should appear in the output
        visible_lines = [
            line
            for line in markdown.splitlines()
            if line.startswith("- `pkg.func") and "big_module.py" in line
        ]
        assert len(visible_lines) == 5, (
            f"Expected 5 visible entities for big_module.py, got {len(visible_lines)}"
        )

    def test_selected_entities_unchanged_after_compact_render(self) -> None:
        """Rendering must not touch selected_entities — internal state is always complete."""
        entities = [
            _make_module_entity(
                eid=f"python:pkg/big_module.py:function:pkg.func{i}",
                name=f"func{i}",
                qualified_name=f"pkg.func{i}",
                source_path="pkg/big_module.py",
            )
            for i in range(8)
        ]
        pack = _make_direct_pack(entities)
        _ = render_context_pack_markdown(pack)

        # All 8 entities must still be present in the pack
        assert len(pack.selected_entities) == 8, (
            "selected_entities must remain unmodified after compact rendering"
        )

    def test_cap_is_per_source_path_not_global(self) -> None:
        """Cap applies independently per source file; entities from other files are not affected."""
        entities_a = [
            _make_module_entity(
                eid=f"python:pkg/file_a.py:function:pkg.a_func{i}",
                name=f"a_func{i}",
                qualified_name=f"pkg.a_func{i}",
                source_path="pkg/file_a.py",
            )
            for i in range(7)
        ]
        entities_b = [
            _make_module_entity(
                eid=f"python:pkg/file_b.py:function:pkg.b_func{i}",
                name=f"b_func{i}",
                qualified_name=f"pkg.b_func{i}",
                source_path="pkg/file_b.py",
            )
            for i in range(3)
        ]
        pack = _make_direct_pack(entities_a + entities_b)
        markdown = render_context_pack_markdown(pack)

        lines_a = [
            line
            for line in markdown.splitlines()
            if "a_func" in line and line.startswith("- `pkg.")
        ]
        lines_b = [
            line
            for line in markdown.splitlines()
            if "b_func" in line and line.startswith("- `pkg.")
        ]
        # file_a.py has 7 → capped to 5; file_b.py has 3 → all 3 visible
        assert len(lines_a) == 5, f"file_a.py: expected 5 visible, got {len(lines_a)}"
        assert len(lines_b) == 3, f"file_b.py: expected 3 visible, got {len(lines_b)}"

    def test_hidden_count_indicator_emitted(self) -> None:
        """Compact output must emit a '... (N more from path)' indicator for capped paths."""
        entities = [
            _make_module_entity(
                eid=f"python:pkg/big_module.py:function:pkg.func{i}",
                name=f"func{i}",
                qualified_name=f"pkg.func{i}",
                source_path="pkg/big_module.py",
            )
            for i in range(8)
        ]
        pack = _make_direct_pack(entities)
        markdown = render_context_pack_markdown(pack)

        # 8 - 5 = 3 hidden; indicator line must mention 3 and the path
        assert "3 more from" in markdown and "big_module.py" in markdown, (
            f"Expected hidden-count indicator '3 more from ... big_module.py' in:\n{markdown}"
        )

    def test_compact_deterministic_ordering_respects_input_order(self) -> None:
        """First 5 entities in iteration order must be the visible ones (stable, deterministic)."""
        entities = [
            _make_module_entity(
                eid=f"python:pkg/big_module.py:function:pkg.func{i}",
                name=f"func{i}",
                qualified_name=f"pkg.func{i}",
                source_path="pkg/big_module.py",
            )
            for i in range(8)
        ]
        pack = _make_direct_pack(entities)
        markdown = render_context_pack_markdown(pack)

        # func0..func4 should appear; func5..func7 should not
        for i in range(5):
            assert f"`pkg.func{i}`" in markdown, f"pkg.func{i} must be visible"
        for i in range(5, 8):
            assert f"`pkg.func{i}` " not in markdown, f"pkg.func{i} must be hidden (capped)"

    def test_no_indicator_when_under_cap(self) -> None:
        """No hidden-count indicator when entity count is at or below the cap."""
        entities = [
            _make_module_entity(
                eid=f"python:pkg/small_module.py:function:pkg.sfunc{i}",
                name=f"sfunc{i}",
                qualified_name=f"pkg.sfunc{i}",
                source_path="pkg/small_module.py",
            )
            for i in range(5)
        ]
        pack = _make_direct_pack(entities)
        markdown = render_context_pack_markdown(pack)

        assert "more from" not in markdown, (
            "No hidden-count indicator should appear when entity count == cap"
        )
