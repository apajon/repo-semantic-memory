"""Repo map rendering tests."""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.context.repo_map import build_repo_map_markdown
from repo_semantic_memory.extractors import extract_filesystem_entities, index_python_path
from repo_semantic_memory.model import Entity, Relation


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"


def _merged_entities() -> tuple[list[Entity], list[Relation]]:
    fixture_root = _fixture_root()
    filesystem_entities = extract_filesystem_entities(fixture_root)
    python_entities, python_relations = index_python_path(fixture_root)
    return [*filesystem_entities, *python_entities], python_relations


def test_repo_map_includes_modules_classes_methods_functions_imports_and_source_ranges() -> None:
    entities, relations = _merged_entities()

    output = build_repo_map_markdown(entities, relations, budget_chars=4000)

    assert output.startswith("# Repo map\n")
    assert "## src/python_symbols.py" in output
    assert "- module `python_symbols` src/python_symbols.py:" in output
    assert "- class `python_symbols.DerivedThing` src/python_symbols.py:18-27" in output
    assert "  - method `decorated_method` src/python_symbols.py:23-24" in output
    assert "- function `python_symbols.top_level_function` src/python_symbols.py:31-32" in output
    assert "Imports:" in output
    assert "- `os`" in output
    assert "- `pkg.base.BaseThing`" in output


def test_repo_map_prefers_ast_backed_python_module_entities() -> None:
    entities, relations = _merged_entities()

    output = build_repo_map_markdown(entities, relations, budget_chars=4000)

    assert "- module `python_symbols` src/python_symbols.py:" in output
    assert "- module `src/python_symbols.py` src/python_symbols.py:1-39" not in output


def test_repo_map_budget_is_approximately_respected() -> None:
    entities, relations = _merged_entities()

    output = build_repo_map_markdown(entities, relations, budget_chars=160)

    assert len(output) <= 160
    assert output.startswith("# Repo map")
    assert output.endswith("...")


def test_repo_map_rendering_is_deterministic() -> None:
    entities, relations = _merged_entities()

    first = build_repo_map_markdown(entities, relations, budget_chars=4000)
    second = build_repo_map_markdown(entities, relations, budget_chars=4000)

    assert first == second
