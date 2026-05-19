"""Repo map rendering tests."""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.context.repo_map import build_repo_map_markdown
from repo_semantic_memory.extractors import extract_filesystem_entities, index_python_path
from repo_semantic_memory.model import Entity, Relation, SourceRange, StableId


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"


def _ranking_fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "ranking_repo"


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
    assert "Static imports (unresolved):" in output
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
    assert output.endswith("[truncated: budget reached]")


def test_repo_map_rendering_is_deterministic() -> None:
    entities, relations = _merged_entities()

    first = build_repo_map_markdown(entities, relations, budget_chars=4000)
    second = build_repo_map_markdown(entities, relations, budget_chars=4000)

    assert first == second


def test_repo_map_source_citations_are_posix_paths() -> None:
    entities = [
        Entity(
            id=StableId.from_parts(["python", "src\\pkg\\module.py", "module", "pkg.module"]),
            kind="module",
            name="module",
            qualified_name="pkg.module",
            source_range=SourceRange(path="src\\pkg\\module.py", start_line=3, end_line=6),
        ),
    ]

    output = build_repo_map_markdown(entities, [], budget_chars=4000)

    assert "## src/pkg/module.py" in output
    assert "- module `pkg.module` src/pkg/module.py:3-6" in output


def test_repo_map_respects_role_priority_ordering() -> None:
    entities = [
        Entity(
            id=StableId.from_parts(["file", "misc/last.py"]),
            kind="module",
            name="last",
            qualified_name="misc.last",
            source_range=SourceRange(path="misc/last.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", ".github/workflows/ci.py"]),
            kind="module",
            name="ci",
            qualified_name="github.ci",
            source_range=SourceRange(path=".github/workflows/ci.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", "scripts/generate.py"]),
            kind="module",
            name="generate",
            qualified_name="scripts.generate",
            source_range=SourceRange(path="scripts/generate.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", "docs/guide.py"]),
            kind="module",
            name="guide",
            qualified_name="docs.guide",
            source_range=SourceRange(path="docs/guide.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", "examples/example.py"]),
            kind="module",
            name="example",
            qualified_name="examples.example",
            source_range=SourceRange(path="examples/example.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", "tests/test_feature.py"]),
            kind="module",
            name="test_feature",
            qualified_name="tests.test_feature",
            source_range=SourceRange(path="tests/test_feature.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", "src/core.py"]),
            kind="module",
            name="core",
            qualified_name="src.core",
            source_range=SourceRange(path="src/core.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", "pkg_b/__init__.py"]),
            kind="module",
            name="__init__.py",
            qualified_name="pkg_b",
            source_range=SourceRange(path="pkg_b/__init__.py", start_line=1, end_line=1),
        ),
    ]

    output = build_repo_map_markdown(entities, [], budget_chars=4000)

    src_idx = output.index("## src/core.py")
    pkg_idx = output.index("## pkg_b/__init__.py")
    tests_idx = output.index("## tests/test_feature.py")
    examples_idx = output.index("## examples/example.py")
    docs_idx = output.index("## docs/guide.py")
    github_idx = output.index("## .github/workflows/ci.py")
    scripts_idx = output.index("## scripts/generate.py")
    misc_idx = output.index("## misc/last.py")

    assert src_idx < tests_idx
    assert pkg_idx < tests_idx
    assert tests_idx < examples_idx < docs_idx < github_idx < scripts_idx < misc_idx


def test_repo_map_treats_non_src_package_root_as_source_when_markers_exist() -> None:
    entities, relations = _ranking_fixture_entities_and_relations()

    output = build_repo_map_markdown(entities, relations, budget_chars=6000)

    lifecore_state_idx = output.index("## lifecore_state/__init__.py")
    examples_idx = output.index("## examples/example_usage.py")
    tests_idx = output.index("## tests/public_api_checks.py")

    assert lifecore_state_idx < examples_idx
    assert lifecore_state_idx < tests_idx


def test_repo_map_does_not_promote_nested_test_package_init_as_source_root() -> None:
    entities = [
        Entity(
            id=StableId.from_parts(["file", "pkg_core/main.py"]),
            kind="module",
            name="main",
            qualified_name="pkg_core.main",
            source_range=SourceRange(path="pkg_core/main.py", start_line=1, end_line=1),
        ),
        Entity(
            id=StableId.from_parts(["file", "pkg_core/tests/__init__.py"]),
            kind="module",
            name="__init__.py",
            qualified_name="pkg_core.tests",
            source_range=SourceRange(path="pkg_core/tests/__init__.py", start_line=1, end_line=1),
        ),
    ]

    output = build_repo_map_markdown(entities, [], budget_chars=4000)

    source_idx = output.index("## pkg_core/main.py")
    nested_tests_idx = output.index("## pkg_core/tests/__init__.py")

    assert source_idx < nested_tests_idx


def _ranking_fixture_entities_and_relations() -> tuple[list[Entity], list[Relation]]:
    fixture_root = _ranking_fixture_root()
    filesystem_entities = extract_filesystem_entities(fixture_root)
    python_entities, python_relations = index_python_path(fixture_root)
    return [*filesystem_entities, *python_entities], python_relations
