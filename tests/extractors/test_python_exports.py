"""Tests for the Python __init__.py export resolver.

Covers:
- direct re-export extraction (from .module import Name)
- alias extraction (from .module import Name as Alias)
- __all__ extraction
- import module as Alias
- unresolved export target representation
- public API query selects package exports
- generated docs do not dominate
- deterministic ordering
- public import tests remain useful supporting evidence
- no import execution occurs
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from repo_semantic_memory.extractors.python_exports import (
    extract_python_exports,
    index_python_exports,
)
from repo_semantic_memory.model import Relation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_file(tmp_path: Path, rel: str, content: str) -> Path:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content), encoding="utf-8")
    return target


def _exports_by_name(relations: list[Relation]) -> dict[str, Relation]:
    return {str(r.metadata["exported_name"]): r for r in relations if r.kind == "exports"}


# ---------------------------------------------------------------------------
# Basic extraction tests
# ---------------------------------------------------------------------------


def test_non_init_file_returns_empty(tmp_path: Path) -> None:
    """Non-__init__.py files must return an empty list without raising."""
    f = _write_file(tmp_path, "mymod.py", "from .sub import Thing\n")
    result = extract_python_exports(tmp_path, f)
    assert result == []


def test_direct_re_export(tmp_path: Path) -> None:
    """from .module import Name produces an exports relation for Name."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        from .module import ClassName
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    by_name = _exports_by_name(relations)
    assert "ClassName" in by_name
    rel = by_name["ClassName"]
    assert rel.metadata["exported_name"] == "ClassName"
    assert rel.metadata["source_module"] == ".module"
    assert rel.metadata["resolved"] is False
    assert "original_name" not in rel.metadata


def test_alias_extraction(tmp_path: Path) -> None:
    """from .module import Name as Alias produces exports relation with alias as exported_name."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        from .sub.module import InternalClass as PublicClass
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    by_name = _exports_by_name(relations)
    assert "PublicClass" in by_name
    rel = by_name["PublicClass"]
    assert rel.metadata["exported_name"] == "PublicClass"
    assert rel.metadata["original_name"] == "InternalClass"
    assert rel.metadata["source_module"] == ".sub.module"
    assert rel.metadata["resolved"] is False


def test_import_module_as_alias(tmp_path: Path) -> None:
    """import module as Alias produces exports relation with Alias as exported_name."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        import mypackage.utils as utils
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    by_name = _exports_by_name(relations)
    assert "utils" in by_name
    rel = by_name["utils"]
    assert rel.metadata["exported_name"] == "utils"
    assert rel.metadata["original_name"] == "mypackage.utils"
    assert rel.metadata["resolved"] is False


def test_import_module_plain(tmp_path: Path) -> None:
    """import module produces exports relation with module name as exported_name."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        import os
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    by_name = _exports_by_name(relations)
    assert "os" in by_name
    rel = by_name["os"]
    assert rel.metadata["exported_name"] == "os"
    assert rel.metadata["resolved"] is False


def test_all_extraction(tmp_path: Path) -> None:
    """__all__ = [...] marks matching exports with via_all=True."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        from .component import MyClass

        __all__ = ["MyClass"]
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    by_name = _exports_by_name(relations)
    assert "MyClass" in by_name
    rel = by_name["MyClass"]
    assert rel.metadata["via_all"] is True


def test_all_only_names_get_separate_relation(tmp_path: Path) -> None:
    """Names in __all__ without a matching import still get an exports relation."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        # LocalClass defined elsewhere or dynamically
        __all__ = ["LocalClass"]
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    by_name = _exports_by_name(relations)
    assert "LocalClass" in by_name
    rel = by_name["LocalClass"]
    assert rel.metadata["via_all"] is True
    assert rel.metadata["resolved"] is False


def test_not_in_all_via_all_false(tmp_path: Path) -> None:
    """Exports not listed in __all__ have via_all=False."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        from .utils import helper, main_func

        __all__ = ["main_func"]
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    by_name = _exports_by_name(relations)
    assert by_name["main_func"].metadata["via_all"] is True
    assert by_name["helper"].metadata["via_all"] is False


def test_star_import_skipped(tmp_path: Path) -> None:
    """Star imports (from .module import *) are silently skipped."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        from .module import *
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    assert relations == []


def test_unresolved_target_id_is_stable_and_deterministic(tmp_path: Path) -> None:
    """Export target IDs must be deterministic unresolved placeholders."""
    _write_file(
        tmp_path,
        "mypkg/__init__.py",
        """\
        from .core import MyApi
        """,
    )
    _write_file(tmp_path, "mypkg/core.py", "class MyApi: pass\n")
    relations = extract_python_exports(tmp_path, tmp_path / "mypkg/__init__.py")
    by_name = _exports_by_name(relations)
    rel = by_name["MyApi"]
    # Target is unresolved; ID must start with "unresolved:"
    assert rel.target_entity_id.value.startswith("unresolved:")
    # Calling again must produce the same ID.
    relations2 = extract_python_exports(tmp_path, tmp_path / "mypkg/__init__.py")
    by_name2 = _exports_by_name(relations2)
    assert by_name2["MyApi"].target_entity_id.value == rel.target_entity_id.value


def test_evidence_references_init_py_source_range(tmp_path: Path) -> None:
    """Export relation evidence must reference the __init__.py source range."""
    _write_file(
        tmp_path,
        "pkg/__init__.py",
        """\
        from .component import Component
        """,
    )
    _write_file(tmp_path, "pkg/component.py", "class Component: pass\n")
    relations = extract_python_exports(tmp_path, tmp_path / "pkg/__init__.py")
    by_name = _exports_by_name(relations)
    rel = by_name["Component"]
    assert rel.evidence is not None
    assert rel.evidence.extractor == "python_exports"
    assert rel.evidence.source_range.path.endswith("__init__.py")
    assert rel.evidence.source_range.start_line == 1


def test_exports_kind_is_exports(tmp_path: Path) -> None:
    """All produced relations must have kind='exports'."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        from .a import A
        from .b import B
        """,
    )
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    assert all(r.kind == "exports" for r in relations)


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


def test_deterministic_ordering(tmp_path: Path) -> None:
    """Results must be deterministically sorted on repeated calls."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        from .z import ZClass
        from .a import AClass
        from .m import MClass
        """,
    )
    result1 = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    result2 = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    assert result1 == result2
    names = [str(r.metadata["exported_name"]) for r in result1]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# index_python_exports (directory traversal)
# ---------------------------------------------------------------------------


def test_index_python_exports_finds_all_init_files(tmp_path: Path) -> None:
    """index_python_exports recurses and collects exports from all __init__.py files."""
    _write_file(tmp_path, "pkga/__init__.py", "from .core import A\n")
    _write_file(tmp_path, "pkga/core.py", "class A: pass\n")
    _write_file(tmp_path, "pkgb/__init__.py", "from .impl import B\n")
    _write_file(tmp_path, "pkgb/impl.py", "class B: pass\n")
    relations = index_python_exports(tmp_path)
    names = {str(r.metadata["exported_name"]) for r in relations}
    assert "A" in names
    assert "B" in names


def test_index_python_exports_ignores_non_init_files(tmp_path: Path) -> None:
    """index_python_exports must not extract from non-__init__.py files."""
    _write_file(tmp_path, "regular_module.py", "from .other import X\n")
    relations = index_python_exports(tmp_path)
    assert relations == []


# ---------------------------------------------------------------------------
# No import execution
# ---------------------------------------------------------------------------


def test_no_import_execution(tmp_path: Path) -> None:
    """Extraction must not execute any import; side effects must not occur."""
    _write_file(
        tmp_path,
        "__init__.py",
        """\
        # This would fail if executed at runtime
        from .nonexistent_module import SomeClass
        import nonexistent_package as np_alias
        """,
    )
    # Must not raise, even though the imports would fail at runtime
    relations = extract_python_exports(tmp_path, tmp_path / "__init__.py")
    names = {str(r.metadata["exported_name"]) for r in relations}
    assert "SomeClass" in names
    assert "np_alias" in names


# ---------------------------------------------------------------------------
# Ranking fixture integration: public API query selects package exports
# ---------------------------------------------------------------------------


def _ranking_fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "ranking_repo"


def test_ranking_fixture_exports_extracted() -> None:
    """Exports from ranking fixture __init__.py files are correctly extracted."""
    fixture = _ranking_fixture_root()
    relations = index_python_exports(fixture)
    exported_names = {str(r.metadata["exported_name"]) for r in relations}
    # lifecore_ros2 exports LifecycleComponent
    assert "LifecycleComponent" in exported_names
    # lifecore_state exports StateComponent
    assert "StateComponent" in exported_names


def test_ranking_fixture_via_all_set() -> None:
    """Exports listed in __all__ in the ranking fixture are marked via_all=True."""
    fixture = _ranking_fixture_root()
    relations = index_python_exports(fixture)
    for rel in relations:
        name = str(rel.metadata.get("exported_name", ""))
        if name in ("LifecycleComponent", "StateComponent"):
            assert rel.metadata.get("via_all") is True, f"Expected via_all=True for {name}"


def test_ranking_fixture_exports_have_evidence() -> None:
    """Every exports relation from the ranking fixture has non-None evidence."""
    fixture = _ranking_fixture_root()
    relations = index_python_exports(fixture)
    for rel in relations:
        assert rel.evidence is not None, (
            f"Missing evidence on exports relation for {rel.metadata.get('exported_name')}"
        )
        assert rel.evidence.source_range.path.endswith("__init__.py")


# ---------------------------------------------------------------------------
# Syntax error resilience
# ---------------------------------------------------------------------------


def test_syntax_error_returns_empty(tmp_path: Path) -> None:
    """Files with syntax errors must return an empty list without raising."""
    bad_init = tmp_path / "__init__.py"
    bad_init.write_text("def broken(\n", encoding="utf-8")
    result = extract_python_exports(tmp_path, bad_init)
    assert result == []


# ---------------------------------------------------------------------------
# PublicAPI component integration
# ---------------------------------------------------------------------------


def test_public_api_component_confirmed_for_exported_symbol() -> None:
    """Exported symbols from __init__.py must produce confirmed PublicAPI components."""
    from repo_semantic_memory.extractors.python_ast import index_python_path
    from repo_semantic_memory.extractors.python_exports import index_python_exports
    from repo_semantic_memory.memory.ecs_components import infer_semantic_components

    fixture = _ranking_fixture_root()
    entities, relations = index_python_path(fixture)
    export_relations = index_python_exports(fixture)
    all_relations = [*relations, *export_relations]

    components = infer_semantic_components(entities=entities, relations=all_relations)
    confirmed_ids = {
        c.entity_id.value
        for c in components
        if c.component_type == "PublicAPI" and c.status == "confirmed"
    }
    # LifecycleComponent should be confirmed
    lifecycle_entities = [
        e for e in entities if e.name == "LifecycleComponent" and e.kind == "class"
    ]
    assert lifecycle_entities, "LifecycleComponent class not found in fixture"
    for entity in lifecycle_entities:
        assert entity.id.value in confirmed_ids, (
            f"Expected LifecycleComponent ({entity.id.value}) to be confirmed PublicAPI"
        )


def test_public_api_component_init_module_confirmed() -> None:
    """__init__.py modules with explicit exports get confirmed PublicAPI status."""
    from repo_semantic_memory.extractors.python_ast import index_python_path
    from repo_semantic_memory.extractors.python_exports import index_python_exports
    from repo_semantic_memory.memory.ecs_components import infer_semantic_components

    fixture = _ranking_fixture_root()
    entities, relations = index_python_path(fixture)
    export_relations = index_python_exports(fixture)
    all_relations = [*relations, *export_relations]

    components = infer_semantic_components(entities=entities, relations=all_relations)
    confirmed_ids = {
        c.entity_id.value
        for c in components
        if c.component_type == "PublicAPI" and c.status == "confirmed"
    }
    # The lifecore_ros2 __init__.py module should itself be confirmed
    init_modules = [
        e
        for e in entities
        if e.kind == "module"
        and e.source_range.path.endswith("__init__.py")
        and "lifecore_ros2" in e.source_range.path
    ]
    assert init_modules, "lifecore_ros2 __init__.py module not found in fixture"
    for entity in init_modules:
        assert entity.id.value in confirmed_ids, (
            f"Expected {entity.qualified_name} ({entity.id.value}) to be confirmed PublicAPI"
        )


def test_public_api_inferred_without_exports() -> None:
    """Without exports relations, PublicAPI components remain inferred, not confirmed."""
    from repo_semantic_memory.extractors.python_ast import index_python_path
    from repo_semantic_memory.memory.ecs_components import infer_semantic_components

    fixture = _ranking_fixture_root()
    entities, relations = index_python_path(fixture)
    # No export_relations - only heuristic relations

    components = infer_semantic_components(entities=entities, relations=relations)
    # None should be confirmed without export relations
    public_api = [c for c in components if c.component_type == "PublicAPI"]
    confirmed = [c for c in public_api if c.status == "confirmed"]
    confirmed_ids = [c.entity_id.value for c in confirmed]
    assert confirmed == [], f"Expected no confirmed PublicAPI without exports; got {confirmed_ids}"
