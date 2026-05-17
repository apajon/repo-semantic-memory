"""Python AST extractor tests."""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.extractors.python_ast import extract_python_file, index_python_path
from repo_semantic_memory.model import Entity, Relation, StableId


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"


def _fixture_python_file() -> Path:
    return _fixture_root() / "src" / "python_symbols.py"


def _entities_by_qualified_name(entities: list[Entity]) -> dict[str, Entity]:
    return {entity.qualified_name: entity for entity in entities}


def _relations_by_kind(relations: list[Relation], kind: str) -> list[Relation]:
    return [relation for relation in relations if relation.kind == kind]


def test_extract_python_file_extracts_expected_entity_kinds() -> None:
    entities, _ = extract_python_file(_fixture_root(), _fixture_python_file())
    kinds = {entity.kind for entity in entities}
    assert kinds == {"module", "class", "function", "method"}


def test_extract_python_file_extracts_expected_entities_and_docstring_metadata() -> None:
    entities, _ = extract_python_file(_fixture_root(), _fixture_python_file())
    by_qname = _entities_by_qualified_name(entities)

    assert "python_symbols" in by_qname
    assert "python_symbols.NoDocClass" in by_qname
    assert "python_symbols.DerivedThing" in by_qname
    assert "python_symbols.top_level_function" in by_qname
    assert "python_symbols.top_level_async" in by_qname
    assert "python_symbols.DerivedThing.decorated_method" in by_qname
    assert "python_symbols.DerivedThing.async_method" in by_qname

    assert by_qname["python_symbols.NoDocClass"].metadata["has_docstring"] is False
    assert by_qname["python_symbols.DerivedThing"].metadata["has_docstring"] is True
    assert by_qname["python_symbols.top_level_function"].metadata["has_docstring"] is False
    assert by_qname["python_symbols.top_level_async"].metadata["is_async"] is True
    assert by_qname["python_symbols.DerivedThing.decorated_method"].metadata["decorators"] == [
        "staticmethod",
        "decorated",
    ]


def test_extract_python_file_source_ranges() -> None:
    entities, _ = extract_python_file(_fixture_root(), _fixture_python_file())
    by_qname = _entities_by_qualified_name(entities)

    assert by_qname["python_symbols"].source_range.start_line == 1
    assert by_qname["python_symbols.DerivedThing"].source_range.start_line == 18
    assert by_qname["python_symbols.DerivedThing"].source_range.end_line == 27
    assert by_qname["python_symbols.top_level_function"].source_range.start_line == 31
    assert by_qname["python_symbols.top_level_async"].source_range.start_line == 35


def test_extract_python_file_relations_contains_imports_and_inherits() -> None:
    entities, relations = extract_python_file(_fixture_root(), _fixture_python_file())
    by_qname = _entities_by_qualified_name(entities)
    contains = _relations_by_kind(relations, "contains")
    imports = _relations_by_kind(relations, "imports")
    inherits = _relations_by_kind(relations, "inherits")

    module_id = by_qname["python_symbols"].id
    class_id = by_qname["python_symbols.DerivedThing"].id
    method_id = by_qname["python_symbols.DerivedThing.decorated_method"].id
    function_id = by_qname["python_symbols.top_level_function"].id

    contains_pairs = {
        (relation.source_entity_id.value, relation.target_entity_id.value) for relation in contains
    }
    assert (module_id.value, class_id.value) in contains_pairs
    assert (module_id.value, function_id.value) in contains_pairs
    assert (class_id.value, method_id.value) in contains_pairs

    imported_names = {str(relation.metadata["imported_name"]) for relation in imports}
    assert imported_names == {"os", "pkg.base.BaseThing"}

    base_names = {str(relation.metadata["base_name"]) for relation in inherits}
    assert base_names == {"BaseThing"}
    assert {str(relation.target_entity_id.value) for relation in inherits} == {
        "unresolved:python:basething"
    }
    assert {relation.metadata["resolved"] for relation in inherits} == {False}


def test_extract_python_file_is_deterministic() -> None:
    first_entities, first_relations = extract_python_file(_fixture_root(), _fixture_python_file())
    second_entities, second_relations = extract_python_file(_fixture_root(), _fixture_python_file())

    assert [entity.to_dict() for entity in first_entities] == [
        entity.to_dict() for entity in second_entities
    ]
    assert [relation.to_dict() for relation in first_relations] == [
        relation.to_dict() for relation in second_relations
    ]


def test_extract_python_file_stable_ids_include_relative_path_and_qualified_name() -> None:
    entities, _ = extract_python_file(_fixture_root(), _fixture_python_file())
    by_qname = _entities_by_qualified_name(entities)

    for qname, entity in by_qname.items():
        expected = StableId.from_parts(
            ["python", "src/python_symbols.py", entity.kind, qname]
        ).value
        assert entity.id.value == expected


def test_index_python_path_directory_ignores_ignored_directories(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "keep.py").write_text("def keep() -> None:\n    pass\n", encoding="utf-8")
    ignored = repo_root / ".venv"
    ignored.mkdir()
    (ignored / "skip.py").write_text("def skip() -> None:\n    pass\n", encoding="utf-8")

    entities, _ = index_python_path(repo_root)
    paths = {entity.source_range.path for entity in entities}
    assert "keep.py" in paths
    assert all(not path.startswith(".venv/") for path in paths)
