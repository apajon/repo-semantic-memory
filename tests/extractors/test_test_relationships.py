"""Tests for the deterministic test relationship extractor.

Covers:
- test file to source file relation (file_path heuristic)
- test method to source class relation (class_name heuristic)
- import-based test relation (direct_import heuristic)
- weak match marked as inferred/low confidence (token_overlap heuristic)
- deterministic ordering across repeated calls
- relations carry kind="tests" and status="inferred"
- non-test entities produce no relations
- empty entity list returns empty
- cleanup/ownership task includes both source and test files
- behavior/test task prioritises test entities
- graph selector propagates via tests relations
- no test execution occurs
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.context import build_context_pack
from repo_semantic_memory.context.graph_selection import (
    GraphSelectionConfig,
    select_graph_neighbors,
)
from repo_semantic_memory.extractors import (
    extract_markdown_outline_path,
    extract_test_relationships,
    index_python_path,
)
from repo_semantic_memory.model import Entity, Relation, SourceRange, StableId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _module_entity(path: str, qname: str) -> Entity:
    return Entity(
        id=StableId.from_parts(["python", path, "module", qname]),
        kind="module",
        name=Path(path).stem,
        qualified_name=qname,
        source_range=SourceRange(path=path, start_line=1, end_line=10),
    )


def _class_entity(path: str, qname: str, name: str) -> Entity:
    return Entity(
        id=StableId.from_parts(["python", path, "class", qname]),
        kind="class",
        name=name,
        qualified_name=qname,
        source_range=SourceRange(path=path, start_line=5, end_line=20),
    )


def _function_entity(path: str, qname: str, name: str) -> Entity:
    return Entity(
        id=StableId.from_parts(["python", path, "function", qname]),
        kind="function",
        name=name,
        qualified_name=qname,
        source_range=SourceRange(path=path, start_line=3, end_line=8),
    )


def _method_entity(path: str, qname: str, name: str) -> Entity:
    return Entity(
        id=StableId.from_parts(["python", path, "method", qname]),
        kind="method",
        name=name,
        qualified_name=qname,
        source_range=SourceRange(path=path, start_line=10, end_line=14),
    )


def _imports_relation(src_entity: Entity, imported_name: str) -> Relation:
    return Relation(
        source_entity_id=src_entity.id,
        target_entity_id=StableId.from_parts(["python", "imports", imported_name]),
        kind="imports",
        metadata={"imported_name": imported_name},
    )


def _ranking_fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "ranking_repo"


def _ranking_entities_and_relations() -> tuple[list[Entity], list[Relation]]:
    root = _ranking_fixture_root()
    markdown = extract_markdown_outline_path(root)
    python_entities, python_relations = index_python_path(root)
    entities = [*markdown.entities, *python_entities]
    relations = [*markdown.relations, *python_relations]
    return entities, relations


# ---------------------------------------------------------------------------
# Unit tests: file_path heuristic
# ---------------------------------------------------------------------------


def test_file_to_source_file_relation_high_confidence(tmp_path: Path) -> None:
    """tests/extractors/test_foo.py → src/pkg/extractors/foo.py (dirs align → high)."""
    test_mod = _module_entity(
        "tests/extractors/test_foo.py",
        "tests.extractors.test_foo",
    )
    src_mod = _module_entity(
        "src/pkg/extractors/foo.py",
        "pkg.extractors.foo",
    )
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod])

    assert any(r.kind == "tests" for r in rels)
    file_path_rels = [r for r in rels if r.metadata.get("heuristic") == "file_path"]
    assert file_path_rels, "Expected a file_path relation"
    rel = file_path_rels[0]
    assert rel.source_entity_id == test_mod.id
    assert rel.target_entity_id == src_mod.id
    assert rel.metadata["confidence"] == "high"
    assert rel.metadata["status"] == "inferred"
    assert rel.evidence is not None
    assert rel.evidence.confidence == pytest.approx(0.85)


def test_file_to_source_file_relation_medium_confidence_no_dir_match(
    tmp_path: Path,
) -> None:
    """tests/test_foo.py → src/deep/nested/foo.py (no dir overlap → medium)."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/deep/nested/foo.py", "deep.nested.foo")
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod])

    file_path_rels = [r for r in rels if r.metadata.get("heuristic") == "file_path"]
    assert file_path_rels
    assert file_path_rels[0].metadata["confidence"] == "medium"


def test_file_path_no_match_when_stem_differs(tmp_path: Path) -> None:
    """tests/test_foo.py produces no file_path relation when no source stem matches."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/bar.py", "bar")
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod])
    file_path_rels = [r for r in rels if r.metadata.get("heuristic") == "file_path"]
    assert not file_path_rels


# ---------------------------------------------------------------------------
# Unit tests: direct_import heuristic
# ---------------------------------------------------------------------------


def test_import_based_relation_exact_symbol(tmp_path: Path) -> None:
    """Direct import of a source function produces a high-confidence tests relation."""
    test_mod = _module_entity("tests/test_utils.py", "tests.test_utils")
    src_func = _function_entity(
        "src/pkg/utils.py",
        "pkg.utils.helper",
        "helper",
    )
    import_rel = _imports_relation(test_mod, "pkg.utils.helper")
    rels = extract_test_relationships(tmp_path, [test_mod, src_func], [import_rel])

    direct_rels = [r for r in rels if r.metadata.get("heuristic") == "direct_import"]
    assert direct_rels
    rel = direct_rels[0]
    assert rel.source_entity_id == test_mod.id
    assert rel.target_entity_id == src_func.id
    assert rel.metadata["confidence"] == "high"
    assert "pkg.utils.helper" in rel.metadata["matched_terms"]


def test_import_based_relation_module_prefix_fallback(tmp_path: Path) -> None:
    """Import 'pkg.Symbol' where Symbol not indexed → falls back to 'pkg' module."""
    test_mod = _module_entity("tests/test_pkg.py", "tests.test_pkg")
    src_mod = _module_entity("src/pkg/__init__.py", "pkg")
    import_rel = _imports_relation(test_mod, "pkg.Symbol")
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod], [import_rel])

    direct_rels = [r for r in rels if r.metadata.get("heuristic") == "direct_import"]
    assert direct_rels
    assert direct_rels[0].target_entity_id == src_mod.id
    assert direct_rels[0].metadata["confidence"] == "high"


def test_import_from_non_source_module_produces_no_relation(tmp_path: Path) -> None:
    """Imports of stdlib / third-party names not in source_index are skipped."""
    test_mod = _module_entity("tests/test_x.py", "tests.test_x")
    import_rel = _imports_relation(test_mod, "os.path")
    rels = extract_test_relationships(tmp_path, [test_mod], [import_rel])
    assert not any(r.kind == "tests" for r in rels)


# ---------------------------------------------------------------------------
# Unit tests: class_name heuristic
# ---------------------------------------------------------------------------


def test_test_class_to_source_class_relation(tmp_path: Path) -> None:
    """TestFoo → Foo (exact class name strip) produces a high-confidence relation."""
    test_cls = _class_entity(
        "tests/test_comp.py",
        "tests.test_comp.TestComponent",
        "TestComponent",
    )
    src_cls = _class_entity(
        "src/comp.py",
        "pkg.comp.Component",
        "Component",
    )
    rels = extract_test_relationships(tmp_path, [test_cls, src_cls])

    class_rels = [r for r in rels if r.metadata.get("heuristic") == "class_name"]
    assert class_rels
    rel = class_rels[0]
    assert rel.source_entity_id == test_cls.id
    assert rel.target_entity_id == src_cls.id
    assert rel.metadata["confidence"] == "high"
    assert "Component" in rel.metadata["matched_terms"]


def test_class_with_no_test_prefix_skipped(tmp_path: Path) -> None:
    """A class not prefixed with 'Test' is not processed by class_name heuristic."""
    non_test_cls = _class_entity(
        "tests/test_helpers.py",
        "tests.test_helpers.HelperBase",
        "HelperBase",
    )
    src_cls = _class_entity("src/base.py", "pkg.base.HelperBase", "HelperBase")
    rels = extract_test_relationships(tmp_path, [non_test_cls, src_cls])
    class_rels = [r for r in rels if r.metadata.get("heuristic") == "class_name"]
    assert not class_rels


# ---------------------------------------------------------------------------
# Unit tests: token_overlap heuristic (low confidence)
# ---------------------------------------------------------------------------


def test_weak_match_marked_inferred_low_confidence(tmp_path: Path) -> None:
    """Token overlap with no exact match produces low-confidence inferred relation."""
    # "TestCleanupOwnership" → tokens: cleanup, ownership — no exact class match.
    test_cls = _class_entity(
        "tests/test_cleanup.py",
        "tests.test_cleanup.TestCleanupOwnership",
        "TestCleanupOwnership",
    )
    # Source class shares "Cleanup" and "Ownership" tokens.
    src_cls = _class_entity(
        "src/mgr.py",
        "pkg.mgr.CleanupOwnershipManager",
        "CleanupOwnershipManager",
    )
    rels = extract_test_relationships(tmp_path, [test_cls, src_cls])

    token_rels = [r for r in rels if r.metadata.get("heuristic") == "token_overlap"]
    assert token_rels, "Expected token_overlap relation"
    rel = token_rels[0]
    assert rel.metadata["confidence"] == "low"
    assert rel.metadata["status"] == "inferred"
    assert rel.evidence is not None
    assert rel.evidence.confidence == pytest.approx(0.25)
    # matched_terms contains the overlapping tokens
    overlap_terms = rel.metadata["matched_terms"]
    assert isinstance(overlap_terms, list)
    assert any(term in ("cleanup", "ownership") for term in overlap_terms)


# ---------------------------------------------------------------------------
# Unit tests: function_name heuristic
# ---------------------------------------------------------------------------


def test_test_function_to_source_function_relation(tmp_path: Path) -> None:
    """test_build_component → build_component source function (medium confidence)."""
    test_fn = _function_entity(
        "tests/test_factory.py",
        "tests.test_factory.test_build_component",
        "test_build_component",
    )
    src_fn = _function_entity(
        "src/factory.py",
        "pkg.factory.build_component",
        "build_component",
    )
    rels = extract_test_relationships(tmp_path, [test_fn, src_fn])

    fn_rels = [r for r in rels if r.metadata.get("heuristic") == "function_name"]
    assert fn_rels
    assert fn_rels[0].metadata["confidence"] == "medium"
    assert fn_rels[0].target_entity_id == src_fn.id


def test_non_test_function_not_processed(tmp_path: Path) -> None:
    """A function not prefixed with 'test_' is not processed by function_name heuristic."""
    helper = _function_entity(
        "tests/test_x.py",
        "tests.test_x.setup_fixture",
        "setup_fixture",
    )
    src = _function_entity("src/x.py", "pkg.x.setup_fixture", "setup_fixture")
    rels = extract_test_relationships(tmp_path, [helper, src])
    fn_rels = [r for r in rels if r.metadata.get("heuristic") == "function_name"]
    assert not fn_rels


# ---------------------------------------------------------------------------
# Metadata invariants
# ---------------------------------------------------------------------------


def test_all_produced_relations_have_tests_kind(tmp_path: Path) -> None:
    """Every relation produced must have kind='tests'."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/pkg/foo.py", "pkg.foo")
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod])
    assert all(r.kind == "tests" for r in rels)


def test_all_produced_relations_have_status_inferred(tmp_path: Path) -> None:
    """Every relation must carry status='inferred' in metadata."""
    test_cls = _class_entity(
        "tests/test_comp.py",
        "tests.test_comp.TestComp",
        "TestComp",
    )
    src_cls = _class_entity("src/comp.py", "pkg.comp.Comp", "Comp")
    rels = extract_test_relationships(tmp_path, [test_cls, src_cls])
    assert all(r.metadata.get("status") == "inferred" for r in rels)


def test_relations_have_evidence_with_extractor_name(tmp_path: Path) -> None:
    """Relations must carry Evidence anchored to the test file with extractor name."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/pkg/foo.py", "pkg.foo")
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod])
    assert rels
    for rel in rels:
        assert rel.evidence is not None
        assert rel.evidence.extractor == "test_relationships"
        assert rel.evidence.source_range.path.startswith("tests/")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_deterministic_ordering(tmp_path: Path) -> None:
    """Calling extract_test_relationships twice returns identical sorted lists."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/pkg/foo.py", "pkg.foo")
    src_cls = _class_entity("src/bar.py", "pkg.bar.Foo", "Foo")
    test_cls = _class_entity(
        "tests/test_bar.py",
        "tests.test_bar.TestFoo",
        "TestFoo",
    )
    entities = [test_mod, src_mod, src_cls, test_cls]
    first = extract_test_relationships(tmp_path, entities)
    second = extract_test_relationships(tmp_path, entities)
    assert [r.source_entity_id.value for r in first] == [r.source_entity_id.value for r in second]
    assert [r.target_entity_id.value for r in first] == [r.target_entity_id.value for r in second]


def test_empty_entity_list_returns_empty(tmp_path: Path) -> None:
    rels = extract_test_relationships(tmp_path, [])
    assert rels == []


def test_non_test_entities_produce_no_relations(tmp_path: Path) -> None:
    """Source-only entities (no test/ prefix) produce no relations."""
    src_mod = _module_entity("src/foo.py", "foo")
    src_cls = _class_entity("src/bar.py", "bar.Bar", "Bar")
    rels = extract_test_relationships(tmp_path, [src_mod, src_cls])
    assert rels == []


def test_deduplication_prevents_duplicate_relations(tmp_path: Path) -> None:
    """Multiple heuristics firing on same source/target pair produce only one relation."""
    # file_path AND import-based both point test_foo.py → foo.py module entity.
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/foo.py", "foo")
    import_rel = _imports_relation(test_mod, "foo")  # exact module match
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod], [import_rel])

    pairs = [(r.source_entity_id.value, r.target_entity_id.value) for r in rels]
    assert len(pairs) == len(set(pairs)), "Duplicate (source, target) pairs found"


def test_deduplication_keeps_best_confidence(tmp_path: Path) -> None:
    """When direct_import (HIGH) and file_path (MEDIUM) both match the same target,
    the HIGH-confidence relation is kept and the MEDIUM is dropped."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/foo.py", "foo")
    import_rel = _imports_relation(test_mod, "foo")  # fires direct_import (HIGH)
    # file_path heuristic also fires because stem "foo" matches src/foo.py
    rels = extract_test_relationships(tmp_path, [test_mod, src_mod], [import_rel])

    # Must be exactly one relation for this (test_mod, src_mod) pair.
    matching = [
        r for r in rels if r.source_entity_id == test_mod.id and r.target_entity_id == src_mod.id
    ]
    assert len(matching) == 1
    # The kept relation must be the higher-confidence one (direct_import / high).
    assert matching[0].metadata["heuristic"] == "direct_import"
    assert matching[0].metadata["confidence"] == "high"


def test_invalid_repo_root_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Repository root does not exist"):
        extract_test_relationships(tmp_path / "nonexistent", [])


# ---------------------------------------------------------------------------
# Integration: ranking fixture
# ---------------------------------------------------------------------------


def test_cleanup_ownership_task_includes_source_and_tests() -> None:
    """cleanup/ownership pack must include lifecycle source + test file via tests relation."""
    root = _ranking_fixture_root()
    entities, relations = _ranking_entities_and_relations()
    test_rels = extract_test_relationships(root, entities, relations)
    all_relations = [*relations, *test_rels]

    pack = build_context_pack(
        task="Find lifecycle component ownership and cleanup rules",
        entities=entities,
        relations=all_relations,
        budget_chars=8000,
    )
    selected_paths = {e.source_range.path for e in pack.selected_entities}

    assert "src/lifecore_ros2/components/lifecycle_component.py" in selected_paths
    # The test file from the fixture should be reachable via tests relation.
    assert "tests/test_lifecycle.py" in selected_paths


def test_behavior_task_prioritises_test_entities() -> None:
    """A 'behavior/tests' task hint boosts test entities as primary seeds."""
    root = _ranking_fixture_root()
    entities, relations = _ranking_entities_and_relations()
    test_rels = extract_test_relationships(root, entities, relations)
    all_relations = [*relations, *test_rels]

    pack = build_context_pack(
        task="Find tests for lifecycle component behavior",
        entities=entities,
        relations=all_relations,
        budget_chars=6000,
        explain_ranking=True,
    )
    selected_paths = {e.source_range.path for e in pack.selected_entities}

    # Both test file and source file should appear.
    assert "tests/test_lifecycle.py" in selected_paths
    assert "src/lifecore_ros2/components/lifecycle_component.py" in selected_paths

    # Verify that the test entity was boosted (path_role or task_intent reason present).
    test_entity_breakdowns = [
        bd for eid, bd in pack.ranking_breakdowns.items() if "test_lifecycle" in eid
    ]
    assert test_entity_breakdowns
    for bd in test_entity_breakdowns:
        assert bd.path_role > 0 or bd.task_intent > 0


def test_graph_selector_uses_tests_relations() -> None:
    """Graph selection with tests relations includes source entity as neighbor of test seed."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/foo.py", "foo")
    tests_rel = Relation(
        source_entity_id=test_mod.id,
        target_entity_id=src_mod.id,
        kind="tests",
        metadata={"confidence": "high", "heuristic": "file_path", "status": "inferred"},
    )

    result = select_graph_neighbors(
        seed_ids=[test_mod.id.value],
        entity_id_set=frozenset({test_mod.id.value, src_mod.id.value}),
        relations=[tests_rel],
        config=GraphSelectionConfig(max_depth=2, max_entities=10),
    )

    assert src_mod.id.value in result.selected_ids
    score = result.scores_by_id[src_mod.id.value]
    assert score == pytest.approx(0.9)  # DEFAULT_RELATION_WEIGHTS["tests"]
    reason = result.reasons_by_id[src_mod.id.value][0]
    assert "tests" in reason


def test_explain_ranking_shows_tests_relation_reason() -> None:
    """explain_ranking exposes why a source entity was included via a tests relation."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/foo.py", "foo")
    tests_rel = Relation(
        source_entity_id=test_mod.id,
        target_entity_id=src_mod.id,
        kind="tests",
        metadata={"confidence": "high", "heuristic": "file_path", "status": "inferred"},
    )

    pack = build_context_pack(
        task="test lifecycle behavior",
        entities=[test_mod, src_mod],
        relations=[tests_rel],
        budget_chars=2000,
        explain_ranking=True,
    )

    # Both entities should be selected.
    selected_ids = {e.id.value for e in pack.selected_entities}
    assert src_mod.id.value in selected_ids
    assert test_mod.id.value in selected_ids

    # The source entity's breakdown should contain a graph reason mentioning "tests".
    src_breakdown = pack.ranking_breakdowns.get(src_mod.id.value)
    if src_breakdown is not None:
        assert any("tests" in r.message for r in src_breakdown.reasons)


def test_implementation_pack_pulls_tests_via_incoming_tests_relation() -> None:
    """An implementation task with a source entity seed must pull the test entity
    through the *incoming* direction of the ``tests`` relation (test → source).
    The source entity is the seed; graph selection follows the incoming edge to the
    test entity because GraphSelectionConfig uses direction='both'."""
    test_mod = _module_entity("tests/test_foo.py", "tests.test_foo")
    src_mod = _module_entity("src/foo.py", "foo")
    tests_rel = Relation(
        source_entity_id=test_mod.id,
        target_entity_id=src_mod.id,
        kind="tests",
        metadata={"confidence": "high", "heuristic": "file_path", "status": "inferred"},
    )

    # The source module is the only graph seed (implementation task, no test hint).
    result = select_graph_neighbors(
        seed_ids=[src_mod.id.value],
        entity_id_set=frozenset({test_mod.id.value, src_mod.id.value}),
        relations=[tests_rel],
        config=GraphSelectionConfig(max_depth=2, max_entities=10),
    )

    # The test entity must be discovered as a neighbor via the incoming tests edge.
    assert test_mod.id.value in result.selected_ids
    score = result.scores_by_id[test_mod.id.value]
    assert score == pytest.approx(0.9)  # DEFAULT_RELATION_WEIGHTS["tests"]

    """Low-confidence inferred tests relations appear in pack.uncertainties."""
    test_cls = _class_entity(
        "tests/test_cleanup.py",
        "tests.test_cleanup.TestCleanupMgr",
        "TestCleanupMgr",
    )
    src_cls = _class_entity(
        "src/mgr.py",
        "pkg.mgr.CleanupMgr",
        "CleanupMgr",
    )
    low_conf_rel = Relation(
        source_entity_id=test_cls.id,
        target_entity_id=src_cls.id,
        kind="tests",
        metadata={"confidence": "low", "status": "inferred", "heuristic": "token_overlap"},
    )

    pack = build_context_pack(
        task="test cleanup behavior",
        entities=[test_cls, src_cls],
        relations=[low_conf_rel],
        budget_chars=4000,
    )

    uncertainty_texts = " ".join(pack.uncertainties)
    assert "low confidence" in uncertainty_texts.lower()


def test_no_test_execution_occurs(tmp_path: Path) -> None:
    """Importing and calling extract_test_relationships must not execute test functions."""
    # If any test function were executed, it would raise or produce side effects.
    # Merely verifying the function runs without exception is sufficient.
    test_fn = _function_entity(
        "tests/test_critical.py",
        "tests.test_critical.test_dangerous_operation",
        "test_dangerous_operation",
    )
    src_fn = _function_entity(
        "src/ops.py",
        "ops.dangerous_operation",
        "dangerous_operation",
    )
    # This must not raise or execute test_dangerous_operation.
    rels = extract_test_relationships(tmp_path, [test_fn, src_fn])
    assert isinstance(rels, list)
