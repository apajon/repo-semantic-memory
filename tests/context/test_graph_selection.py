"""Tests for deterministic graph neighborhood selection."""

from __future__ import annotations

import pytest

from repo_semantic_memory.context.graph_selection import (
    DEFAULT_RELATION_WEIGHTS,
    GraphSelectionConfig,
    GraphSelectionResult,
    select_graph_neighbors,
)
from repo_semantic_memory.model import Entity, Relation, SourceRange, StableId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entity(entity_id: str, kind: str = "class", name: str | None = None) -> Entity:
    label = name or entity_id.split(":")[-1]
    return Entity(
        id=StableId(entity_id),
        kind=kind,
        name=label,
        qualified_name=label,
        source_range=SourceRange(path=f"src/{label}.py", start_line=1, end_line=10),
    )


def _relation(
    src: str,
    tgt: str,
    kind: str,
    resolved: bool | None = None,
) -> Relation:
    metadata: dict[str, object] = {}
    if resolved is not None:
        metadata["resolved"] = resolved
    return Relation(
        source_entity_id=StableId(src),
        target_entity_id=StableId(tgt),
        kind=kind,  # type: ignore[arg-type]
        metadata=metadata,
    )


def _entity_id_set(*entities: Entity) -> frozenset[str]:
    return frozenset(e.id.value for e in entities)


# ---------------------------------------------------------------------------
# Basic selection tests
# ---------------------------------------------------------------------------


def test_contains_parent_class_selected_for_method_seed() -> None:
    """Parent module/class should be selected for a method seed via contains."""
    module = _entity("python:module:mymodule", kind="module", name="mymodule")
    cls = _entity("python:class:mymodule.MyClass", kind="class", name="MyClass")
    method = _entity("python:method:mymodule.MyClass.my_method", kind="method", name="my_method")

    relations = [
        _relation("python:module:mymodule", "python:class:mymodule.MyClass", "contains"),
        _relation(
            "python:class:mymodule.MyClass",
            "python:method:mymodule.MyClass.my_method",
            "contains",
        ),
    ]
    all_entities = (module, cls, method)

    result = select_graph_neighbors(
        seed_ids=["python:method:mymodule.MyClass.my_method"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(direction="both"),
        exclude_ids=frozenset(["python:method:mymodule.MyClass.my_method"]),
    )

    assert "python:class:mymodule.MyClass" in result.selected_ids
    assert "python:module:mymodule" in result.selected_ids


def test_tests_relation_preferred_over_import_relation() -> None:
    """A tests-relation neighbor scores higher than an imports-relation neighbor."""
    seed = _entity("python:module:core", kind="module", name="core")
    test_entity = _entity("python:module:test_core", kind="module", name="test_core")
    import_entity = _entity("python:module:util", kind="module", name="util")

    relations = [
        _relation("python:module:test_core", "python:module:core", "tests"),
        _relation("python:module:core", "python:module:util", "imports"),
    ]
    all_entities = (seed, test_entity, import_entity)

    result = select_graph_neighbors(
        seed_ids=["python:module:core"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(),
        exclude_ids=frozenset(["python:module:core"]),
    )

    assert "python:module:test_core" in result.selected_ids
    assert "python:module:util" in result.selected_ids
    # tests weight (0.9) > imports weight (0.3)
    tests_score = result.scores_by_id["python:module:test_core"]
    import_score = result.scores_by_id["python:module:util"]
    assert tests_score > import_score


def test_unresolved_inheritance_creates_uncertainty_and_low_score() -> None:
    """Unresolved inherits yields uncertainty flag and penalised score."""
    child = _entity("python:class:child.Child", kind="class")
    parent = _entity("python:class:parent.Parent", kind="class")

    # Unresolved: no metadata["resolved"] = True
    unresolved_rel = _relation("python:class:child.Child", "python:class:parent.Parent", "inherits")
    resolved_rel = _relation(
        "python:class:child.Child",
        "python:class:parent.Parent",
        "inherits",
        resolved=True,
    )

    cfg = GraphSelectionConfig()
    base_weight = DEFAULT_RELATION_WEIGHTS["inherits"]
    expected_unresolved_score = max(0.0, base_weight - cfg.unresolved_penalty)
    expected_resolved_score = base_weight

    result_unresolved = select_graph_neighbors(
        seed_ids=["python:class:child.Child"],
        entity_id_set=_entity_id_set(child, parent),
        relations=[unresolved_rel],
        config=cfg,
        exclude_ids=frozenset(["python:class:child.Child"]),
    )
    result_resolved = select_graph_neighbors(
        seed_ids=["python:class:child.Child"],
        entity_id_set=_entity_id_set(child, parent),
        relations=[resolved_rel],
        config=cfg,
        exclude_ids=frozenset(["python:class:child.Child"]),
    )

    assert "python:class:parent.Parent" in result_unresolved.selected_ids
    assert "python:class:parent.Parent" in result_unresolved.uncertainty_ids
    assert (
        abs(
            result_unresolved.scores_by_id["python:class:parent.Parent"] - expected_unresolved_score
        )
        < 1e-9
    )

    assert "python:class:parent.Parent" in result_resolved.selected_ids
    assert "python:class:parent.Parent" not in result_resolved.uncertainty_ids
    assert (
        abs(result_resolved.scores_by_id["python:class:parent.Parent"] - expected_resolved_score)
        < 1e-9
    )

    assert (
        result_unresolved.scores_by_id["python:class:parent.Parent"]
        < result_resolved.scores_by_id["python:class:parent.Parent"]
    )


def test_unresolved_reason_includes_marker() -> None:
    """Reason strings for unresolved neighbors include the [unresolved] marker."""
    child = _entity("python:class:child.Child", kind="class")
    parent = _entity("python:class:parent.Parent", kind="class")

    result = select_graph_neighbors(
        seed_ids=["python:class:child.Child"],
        entity_id_set=_entity_id_set(child, parent),
        relations=[_relation("python:class:child.Child", "python:class:parent.Parent", "inherits")],
        exclude_ids=frozenset(["python:class:child.Child"]),
    )

    reasons = result.reasons_by_id.get("python:class:parent.Parent", ())
    assert any("[unresolved]" in r for r in reasons)


# ---------------------------------------------------------------------------
# Depth tests
# ---------------------------------------------------------------------------


def test_max_depth_one_hop() -> None:
    """With max_depth=1, only immediate neighbors are selected."""
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")

    relations = [
        _relation("A", "B", "contains"),
        _relation("B", "C", "contains"),
    ]

    result = select_graph_neighbors(
        seed_ids=["A"],
        entity_id_set=_entity_id_set(a, b, c),
        relations=relations,
        config=GraphSelectionConfig(max_depth=1),
        exclude_ids=frozenset(["A"]),
    )

    assert "B" in result.selected_ids
    assert "C" not in result.selected_ids


def test_max_depth_two_hops() -> None:
    """With max_depth=2, two-hop neighbors are also selected."""
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")

    relations = [
        _relation("A", "B", "contains"),
        _relation("B", "C", "contains"),
    ]

    result = select_graph_neighbors(
        seed_ids=["A"],
        entity_id_set=_entity_id_set(a, b, c),
        relations=relations,
        config=GraphSelectionConfig(max_depth=2),
        exclude_ids=frozenset(["A"]),
    )

    assert "B" in result.selected_ids
    assert "C" in result.selected_ids


def test_depth_decay_reduces_score_at_depth_two() -> None:
    """Score at depth 2 should be exactly half the depth-1 score for same relation kind."""
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")

    relations = [
        _relation("A", "B", "contains"),
        _relation("B", "C", "contains"),
    ]

    result = select_graph_neighbors(
        seed_ids=["A"],
        entity_id_set=_entity_id_set(a, b, c),
        relations=relations,
        config=GraphSelectionConfig(max_depth=2),
        exclude_ids=frozenset(["A"]),
    )

    score_b = result.scores_by_id["B"]
    score_c = result.scores_by_id["C"]
    assert abs(score_c - score_b * 0.5) < 1e-9


# ---------------------------------------------------------------------------
# Max entity count test
# ---------------------------------------------------------------------------


def test_max_entity_count_limits_result() -> None:
    """max_entities limits the number of selected neighbors."""
    seed = _entity("seed")
    neighbors = [_entity(f"N{i}") for i in range(10)]
    relations = [_relation("seed", f"N{i}", "contains") for i in range(10)]
    all_entities = [seed, *neighbors]

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(max_entities=3),
        exclude_ids=frozenset(["seed"]),
    )

    assert len(result.selected_ids) == 3


def test_max_entity_count_selects_highest_scoring() -> None:
    """When limited, the highest-scoring neighbors are preferred."""
    seed = _entity("seed")
    high_a = _entity("high_a")
    high_b = _entity("high_b")
    low = _entity("low")
    relations = [
        _relation("seed", "high_a", "contains"),  # weight 0.9
        _relation("seed", "high_b", "tests"),  # weight 0.9
        _relation("seed", "low", "imports"),  # weight 0.3
    ]
    all_entities = (seed, high_a, high_b, low)

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(max_entities=2),
        exclude_ids=frozenset(["seed"]),
    )

    assert len(result.selected_ids) == 2
    assert "high_a" in result.selected_ids
    assert "high_b" in result.selected_ids
    assert "low" not in result.selected_ids


# ---------------------------------------------------------------------------
# Direction filtering tests
# ---------------------------------------------------------------------------


def test_direction_outgoing_only() -> None:
    """Direction='outgoing' follows only outgoing edges."""
    seed = _entity("seed")
    downstream = _entity("downstream")
    upstream = _entity("upstream")

    relations = [
        _relation("seed", "downstream", "contains"),  # outgoing
        _relation("upstream", "seed", "contains"),  # incoming
    ]
    all_entities = (seed, downstream, upstream)

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(direction="outgoing"),
        exclude_ids=frozenset(["seed"]),
    )

    assert "downstream" in result.selected_ids
    assert "upstream" not in result.selected_ids


def test_direction_incoming_only() -> None:
    """Direction='incoming' follows only incoming edges."""
    seed = _entity("seed")
    downstream = _entity("downstream")
    upstream = _entity("upstream")

    relations = [
        _relation("seed", "downstream", "contains"),  # outgoing
        _relation("upstream", "seed", "contains"),  # incoming
    ]
    all_entities = (seed, downstream, upstream)

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(direction="incoming"),
        exclude_ids=frozenset(["seed"]),
    )

    assert "upstream" in result.selected_ids
    assert "downstream" not in result.selected_ids


def test_direction_both() -> None:
    """Direction='both' follows edges in both directions."""
    seed = _entity("seed")
    downstream = _entity("downstream")
    upstream = _entity("upstream")

    relations = [
        _relation("seed", "downstream", "contains"),
        _relation("upstream", "seed", "contains"),
    ]
    all_entities = (seed, downstream, upstream)

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(direction="both"),
        exclude_ids=frozenset(["seed"]),
    )

    assert "downstream" in result.selected_ids
    assert "upstream" in result.selected_ids


# ---------------------------------------------------------------------------
# Kind filter tests
# ---------------------------------------------------------------------------


def test_kind_filter_restricts_traversal() -> None:
    """kind_filters limits which relation kinds are traversed."""
    seed = _entity("seed")
    contained = _entity("contained")
    imported = _entity("imported")

    relations = [
        _relation("seed", "contained", "contains"),
        _relation("seed", "imported", "imports"),
    ]
    all_entities = (seed, contained, imported)

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(kind_filters=frozenset({"contains"})),
        exclude_ids=frozenset(["seed"]),
    )

    assert "contained" in result.selected_ids
    assert "imported" not in result.selected_ids


def test_empty_kind_filter_traverses_all_kinds() -> None:
    """Empty kind_filters means all kinds are traversed."""
    seed = _entity("seed")
    contained = _entity("contained")
    imported = _entity("imported")

    relations = [
        _relation("seed", "contained", "contains"),
        _relation("seed", "imported", "imports"),
    ]
    all_entities = (seed, contained, imported)

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(kind_filters=frozenset()),
        exclude_ids=frozenset(["seed"]),
    )

    assert "contained" in result.selected_ids
    assert "imported" in result.selected_ids


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


def test_deterministic_ordering_same_input_same_output() -> None:
    """Two calls with identical input produce identical results."""
    seed = _entity("seed")
    a = _entity("A")
    b = _entity("B")
    c = _entity("C")

    relations = [
        _relation("seed", "A", "contains"),
        _relation("seed", "B", "uses"),
        _relation("seed", "C", "imports"),
        _relation("A", "B", "contains"),
    ]
    all_entities = (seed, a, b, c)

    def _run() -> GraphSelectionResult:
        return select_graph_neighbors(
            seed_ids=["seed"],
            entity_id_set=_entity_id_set(*all_entities),
            relations=relations,
            exclude_ids=frozenset(["seed"]),
        )

    first = _run()
    second = _run()

    assert first.selected_ids == second.selected_ids
    assert first.scores_by_id == second.scores_by_id
    assert first.reasons_by_id == second.reasons_by_id
    assert first.uncertainty_ids == second.uncertainty_ids


def test_deterministic_tie_breaking_by_entity_id() -> None:
    """Equal-score neighbors are ordered by ascending entity ID."""
    seed = _entity("seed")
    # All connected with same relation kind and weight
    n_c = _entity("C_entity")
    n_a = _entity("A_entity")
    n_b = _entity("B_entity")

    relations = [
        _relation("seed", "C_entity", "contains"),
        _relation("seed", "A_entity", "contains"),
        _relation("seed", "B_entity", "contains"),
    ]
    all_entities = (seed, n_c, n_a, n_b)

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        config=GraphSelectionConfig(max_entities=3),
        exclude_ids=frozenset(["seed"]),
    )

    assert result.selected_ids == ("A_entity", "B_entity", "C_entity")


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_config_invalid_max_depth_raises() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        GraphSelectionConfig(max_depth=0)


def test_config_invalid_max_entities_raises() -> None:
    with pytest.raises(ValueError, match="max_entities"):
        GraphSelectionConfig(max_entities=0)


def test_config_invalid_direction_raises() -> None:
    with pytest.raises(ValueError, match="direction"):
        GraphSelectionConfig(direction="sideways")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_seeds_returns_empty_result() -> None:
    """No seeds → no neighbors."""
    a = _entity("A")
    result = select_graph_neighbors(
        seed_ids=[],
        entity_id_set=_entity_id_set(a),
        relations=[],
    )

    assert result.selected_ids == ()
    assert result.scores_by_id == {}
    assert result.uncertainty_ids == frozenset()


def test_dangling_relation_target_is_skipped() -> None:
    """Neighbors not present in entity_id_set are silently skipped."""
    seed = _entity("seed")
    relations = [
        _relation("seed", "nonexistent_entity", "contains"),
    ]

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(seed),
        relations=relations,
        exclude_ids=frozenset(["seed"]),
    )

    assert "nonexistent_entity" not in result.selected_ids


def test_multi_seed_expansion() -> None:
    """Multiple seeds each contribute neighbors independently."""
    seed_a = _entity("seed_a")
    seed_b = _entity("seed_b")
    neighbor_a = _entity("neighbor_a")
    neighbor_b = _entity("neighbor_b")

    relations = [
        _relation("seed_a", "neighbor_a", "contains"),
        _relation("seed_b", "neighbor_b", "contains"),
    ]
    all_entities = (seed_a, seed_b, neighbor_a, neighbor_b)

    result = select_graph_neighbors(
        seed_ids=["seed_a", "seed_b"],
        entity_id_set=_entity_id_set(*all_entities),
        relations=relations,
        exclude_ids=frozenset(["seed_a", "seed_b"]),
    )

    assert "neighbor_a" in result.selected_ids
    assert "neighbor_b" in result.selected_ids


def test_best_score_wins_when_reachable_via_multiple_paths() -> None:
    """When a neighbor is reachable via two paths, the best (highest) score wins."""
    seed = _entity("seed")
    neighbor = _entity("neighbor")

    relations = [
        _relation("seed", "neighbor", "contains"),  # weight 0.9
        _relation("seed", "neighbor", "imports"),  # weight 0.3
    ]

    result = select_graph_neighbors(
        seed_ids=["seed"],
        entity_id_set=_entity_id_set(seed, neighbor),
        relations=relations,
        config=GraphSelectionConfig(max_depth=1),
        exclude_ids=frozenset(["seed"]),
    )

    assert "neighbor" in result.selected_ids
    assert abs(result.scores_by_id["neighbor"] - DEFAULT_RELATION_WEIGHTS["contains"]) < 1e-9
