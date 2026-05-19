"""Deterministic weighted graph neighborhood selection for context packs.

Provides explicit, inspectable relation expansion with configurable weights,
depth limits, direction filtering, and budget-aware neighbor selection.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from repo_semantic_memory.model import Relation

Direction = Literal["outgoing", "incoming", "both"]

# Default relation weights — higher value means a stronger reason to include the neighbor.
DEFAULT_RELATION_WEIGHTS: dict[str, float] = {
    "contains": 0.9,
    "tests": 0.9,
    "documents": 0.6,
    "inherits": 0.6,
    "uses": 0.6,
    "owns": 0.6,
    "requires": 0.6,
    "calls": 0.3,
    "imports": 0.3,
    "violates": 0.2,
}

_DEFAULT_RELATION_WEIGHT = 0.3
_DEPTH_DECAY = 0.5
_DEFAULT_UNRESOLVED_PENALTY = 0.25
_DEFAULT_MAX_DEPTH = 2
_DEFAULT_MAX_ENTITIES = 30

# Relation kinds whose unresolved targets are flagged as uncertain.
_UNRESOLVED_KINDS: frozenset[str] = frozenset({"imports", "inherits"})


@dataclass(frozen=True)
class GraphSelectionConfig:
    """Configuration for deterministic graph neighborhood selection.

    Attributes:
        max_depth: Maximum BFS depth from seed entities (inclusive).
        max_entities: Maximum number of graph neighbors to return.
        direction: Which relation directions to follow from each node.
        kind_filters: Restrict traversal to these relation kinds.  Empty set means all.
        relation_weights: Override per-kind base weights (0.0–1.0 scale).
        unresolved_penalty: Subtracted from base weight for unresolved relations.
    """

    max_depth: int = _DEFAULT_MAX_DEPTH
    max_entities: int = _DEFAULT_MAX_ENTITIES
    direction: Direction = "both"
    kind_filters: frozenset[str] = field(default_factory=frozenset)
    relation_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_RELATION_WEIGHTS)
    )
    unresolved_penalty: float = _DEFAULT_UNRESOLVED_PENALTY

    def __post_init__(self) -> None:
        if self.max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if self.max_entities < 1:
            raise ValueError("max_entities must be >= 1")
        if self.direction not in ("outgoing", "incoming", "both"):
            raise ValueError(
                f"direction must be 'outgoing', 'incoming', or 'both'; got: {self.direction!r}"
            )


@dataclass(frozen=True)
class GraphNeighbor:
    """A graph-selected neighbor with its provenance information.

    Attributes:
        entity_id: The neighbor entity's stable identifier.
        score: Computed graph relevance score for this neighbor.
        depth: BFS depth at which this neighbor was first reached.
        via_kind: Relation kind used to reach this neighbor.
        from_entity_id: The entity from which this neighbor was reached.
        is_unresolved: True when reached via an unresolved relation.
    """

    entity_id: str
    score: float
    depth: int
    via_kind: str
    from_entity_id: str
    is_unresolved: bool

    def reason(self) -> str:
        """Build a human-readable selection reason string."""
        base = (
            f"graph neighbor via {self.via_kind} "
            f"(depth={self.depth}, score={self.score:.3f}) "
            f"from {self.from_entity_id}"
        )
        if self.is_unresolved:
            base += " [unresolved]"
        return base


@dataclass(frozen=True)
class GraphSelectionResult:
    """Result of graph neighborhood selection.

    Attributes:
        selected_ids: Neighbor entity IDs, ordered by (-score, entity_id).
        scores_by_id: Graph relevance score for each selected neighbor.
        reasons_by_id: Provenance reason strings per selected neighbor.
        uncertainty_ids: Subset of selected_ids reached via unresolved relations.
    """

    selected_ids: tuple[str, ...]
    scores_by_id: dict[str, float]
    reasons_by_id: dict[str, tuple[str, ...]]
    uncertainty_ids: frozenset[str]


def select_graph_neighbors(
    *,
    seed_ids: Sequence[str],
    entity_id_set: frozenset[str],
    relations: Sequence[Relation],
    config: GraphSelectionConfig | None = None,
    exclude_ids: frozenset[str] | None = None,
) -> GraphSelectionResult:
    """Select graph neighbors from seed entities using weighted BFS.

    Performs a breadth-first traversal starting from ``seed_ids``, following
    typed relations with configurable weights and depth decay.  Tie-breaks are
    resolved by entity ID to ensure deterministic output across runs.

    Args:
        seed_ids: Starting entity IDs for the traversal.
        entity_id_set: All entity IDs known to the index (bounds validity).
        relations: Full relation list to build adjacency from.
        config: Selection parameters; defaults to ``GraphSelectionConfig()``.
        exclude_ids: Entity IDs to skip as neighbors (defaults to seed_ids).

    Returns:
        A :class:`GraphSelectionResult` with up to ``config.max_entities``
        neighbors sorted by descending score then ascending entity ID.
    """
    cfg = config or GraphSelectionConfig()
    exclude_set: frozenset[str] = exclude_ids if exclude_ids is not None else frozenset(seed_ids)

    # Build adjacency lists from sorted relations for deterministic traversal order.
    outgoing: dict[str, list[Relation]] = defaultdict(list)
    incoming: dict[str, list[Relation]] = defaultdict(list)
    for relation in sorted(
        relations,
        key=lambda r: (r.kind, r.source_entity_id.value, r.target_entity_id.value),
    ):
        outgoing[relation.source_entity_id.value].append(relation)
        incoming[relation.target_entity_id.value].append(relation)

    # BFS state
    # visited tracks nodes whose expansions are already queued or done.
    visited: set[str] = set(seed_ids)
    # queue: (depth, entity_id) — seeds start at depth 0.
    queue: list[tuple[int, str]] = [(0, eid) for eid in sorted(seed_ids)]

    # Accumulate best score and all reasons per neighbor.
    best_score: dict[str, float] = {}
    all_reasons: dict[str, list[str]] = defaultdict(list)
    uncertainty_ids: set[str] = set()

    while queue:
        depth, current_id = queue.pop(0)
        if depth >= cfg.max_depth:
            continue

        # Collect edges in the configured directions, filtered by kind.
        edges: list[tuple[str, Relation]] = []
        if cfg.direction in ("outgoing", "both"):
            for rel in outgoing.get(current_id, []):
                if not cfg.kind_filters or rel.kind in cfg.kind_filters:
                    edges.append((rel.target_entity_id.value, rel))
        if cfg.direction in ("incoming", "both"):
            for rel in incoming.get(current_id, []):
                if not cfg.kind_filters or rel.kind in cfg.kind_filters:
                    edges.append((rel.source_entity_id.value, rel))

        # Deterministic edge ordering: kind then neighbor_id.
        edges.sort(key=lambda e: (e[1].kind, e[0]))

        for neighbor_id, rel in edges:
            if neighbor_id not in entity_id_set:
                # Skip dangling references not in the current index.
                continue

            next_depth = depth + 1

            # Compute per-relation score with depth decay.
            base_weight = cfg.relation_weights.get(rel.kind, _DEFAULT_RELATION_WEIGHT)
            is_unresolved = (
                rel.kind in _UNRESOLVED_KINDS and rel.metadata.get("resolved") is not True
            )
            if is_unresolved:
                base_weight = max(0.0, base_weight - cfg.unresolved_penalty)

            score = base_weight * (_DEPTH_DECAY ** (next_depth - 1))

            if neighbor_id not in exclude_set:
                # Keep the best (highest) score across all paths to this neighbor.
                if score > best_score.get(neighbor_id, -1.0):
                    best_score[neighbor_id] = score
                neighbor = GraphNeighbor(
                    entity_id=neighbor_id,
                    score=score,
                    depth=next_depth,
                    via_kind=rel.kind,
                    from_entity_id=current_id,
                    is_unresolved=is_unresolved,
                )
                all_reasons[neighbor_id].append(neighbor.reason())
                if is_unresolved:
                    uncertainty_ids.add(neighbor_id)

            # Enqueue for further expansion if not yet scheduled.
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                queue.append((next_depth, neighbor_id))

    # Sort by descending score, then ascending entity_id for deterministic tie-breaks.
    sorted_neighbors = sorted(
        best_score.items(),
        key=lambda item: (-item[1], item[0]),
    )[: cfg.max_entities]

    selected_ids = tuple(item[0] for item in sorted_neighbors)
    final_selected = frozenset(selected_ids)

    return GraphSelectionResult(
        selected_ids=selected_ids,
        scores_by_id=dict(sorted_neighbors),
        reasons_by_id={eid: tuple(dict.fromkeys(all_reasons.get(eid, []))) for eid in selected_ids},
        uncertainty_ids=frozenset(uncertainty_ids) & final_selected,
    )
