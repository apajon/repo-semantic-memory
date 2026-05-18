"""Context pack builder tests."""

from __future__ import annotations

import json
from pathlib import Path

from repo_semantic_memory.context import build_context_pack, render_context_pack_markdown
from repo_semantic_memory.extractors import extract_filesystem_entities, index_python_path
from repo_semantic_memory.model import Entity, Relation, SourceRange, StableId


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"


def _indexed_entities_and_relations() -> tuple[list[Entity], list[Relation]]:
    fixture_root = _fixture_root()
    filesystem_entities = [
        entity
        for entity in extract_filesystem_entities(fixture_root)
        if not (entity.kind == "module" and entity.source_range.path.endswith(".py"))
    ]
    python_entities, python_relations = index_python_path(fixture_root)
    return [*filesystem_entities, *python_entities], python_relations


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
