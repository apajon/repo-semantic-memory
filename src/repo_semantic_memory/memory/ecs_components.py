"""Deterministic ECS-style semantic component inference."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from repo_semantic_memory.model import (
    Entity,
    Evidence,
    JsonValue,
    Relation,
    SemanticComponent,
    SemanticComponentType,
)

_HEURISTIC_EXTRACTOR = "ecs_heuristic"
_INFERRED_CONFIDENCE = 0.6
_ROS_LIKE_TOKENS = ("publisher", "subscriber", "service", "client", "timer")

CompactComponentStatus = Literal["confirmed", "inferred", "needs_review"]


@dataclass(frozen=True)
class CompactSemanticComponent:
    """Compact semantic component label for context-pack integration."""

    entity_id: str
    component_type: str
    status: CompactComponentStatus

    def to_dict(self) -> dict[str, str]:
        """Serialize to deterministic dictionary payload."""
        return {
            "entity_id": self.entity_id,
            "component_type": self.component_type,
            "status": self.status,
        }


def infer_semantic_components(
    *, entities: Sequence[Entity], relations: Sequence[Relation]
) -> list[SemanticComponent]:
    """Infer deterministic semantic components from indexed entities and relations."""
    normalized_entities = sorted(entities, key=lambda entity: entity.id.value)
    normalized_relations = sorted(
        relations,
        key=lambda relation: (
            relation.kind,
            relation.source_entity_id.value,
            relation.target_entity_id.value,
        ),
    )
    entity_by_id = {entity.id.value: entity for entity in normalized_entities}
    components: dict[tuple[str, str], SemanticComponent] = {}

    _infer_test_components(normalized_entities, components)
    _infer_lifecycle_components(normalized_entities, components)
    _infer_integration_components(normalized_entities, components)
    _infer_public_api_components(normalized_relations, entity_by_id, components)

    return sorted(
        components.values(),
        key=lambda component: (component.entity_id.value, component.component_type),
    )


def compact_component_labels(
    components: Sequence[SemanticComponent],
) -> tuple[CompactSemanticComponent, ...]:
    """Return compact deterministic component labels for lightweight payloads."""
    compact = [
        CompactSemanticComponent(
            entity_id=component.entity_id.value,
            component_type=component.component_type,
            status=component.status,
        )
        for component in components
    ]
    compact_sorted = sorted(
        compact, key=lambda item: (item.entity_id, item.component_type, item.status)
    )
    return tuple(compact_sorted)


def _infer_test_components(
    entities: list[Entity], components: dict[tuple[str, str], SemanticComponent]
) -> None:
    for entity in entities:
        path = _normalized_path(entity.source_range.path)
        name_lower = entity.name.lower()
        in_tests_path = "/tests/" in f"/{path}"
        starts_with_test = name_lower.startswith("test_")

        if entity.kind == "module" and in_tests_path:
            _upsert(
                components,
                _build_inferred_component(
                    entity=entity,
                    component_type="TestFile",
                    properties={"heuristic": "module_path_contains_tests"},
                ),
            )
        if entity.kind != "module" and (starts_with_test or in_tests_path):
            reason = (
                "name_starts_with_test_prefix" if starts_with_test else "entity_path_contains_tests"
            )
            _upsert(
                components,
                _build_inferred_component(
                    entity=entity,
                    component_type="TestTarget",
                    properties={"heuristic": reason},
                ),
            )


def _infer_lifecycle_components(
    entities: list[Entity], components: dict[tuple[str, str], SemanticComponent]
) -> None:
    for entity in entities:
        if entity.kind != "class":
            continue
        if "lifecycle" not in entity.name.lower():
            continue
        _upsert(
            components,
            _build_inferred_component(
                entity=entity,
                component_type="LifecycleManaged",
                properties={"heuristic": "class_name_contains_lifecycle"},
            ),
        )


def _infer_integration_components(
    entities: list[Entity], components: dict[tuple[str, str], SemanticComponent]
) -> None:
    for entity in entities:
        if entity.kind not in {"class", "function", "method"}:
            continue
        haystack = " ".join(
            [
                entity.name.lower(),
                entity.qualified_name.lower(),
                _normalized_path(entity.source_range.path).lower(),
            ]
        )
        matched_token = next((token for token in _ROS_LIKE_TOKENS if token in haystack), None)
        if matched_token is None:
            continue
        is_ros_like = "ros" in haystack
        _upsert(
            components,
            _build_inferred_component(
                entity=entity,
                component_type="ROSLikeIntegration" if is_ros_like else "ExternalIntegration",
                properties={"heuristic": f"name_contains_{matched_token}"},
            ),
        )


def _infer_public_api_components(
    relations: list[Relation],
    entity_by_id: dict[str, Entity],
    components: dict[tuple[str, str], SemanticComponent],
) -> None:
    init_module_ids = {
        entity.id.value
        for entity in entity_by_id.values()
        if entity.kind == "module"
        and PurePosixPath(_normalized_path(entity.source_range.path)).name == "__init__.py"
    }
    if not init_module_ids:
        return

    for relation in relations:
        source_id = relation.source_entity_id.value
        target_id = relation.target_entity_id.value
        if source_id not in init_module_ids:
            continue
        target_entity = entity_by_id.get(target_id)
        if target_entity is None or target_entity.kind in {"repository", "package", "module"}:
            continue
        if relation.kind == "imports" and relation.metadata.get("resolved") is not True:
            continue
        if relation.kind not in {"contains", "imports"}:
            continue

        _upsert(
            components,
            _build_inferred_component(
                entity=target_entity,
                component_type="PublicAPI",
                properties={
                    "heuristic": "__init___export_relation",
                    "relation_kind": relation.kind,
                    "exporter_module_id": source_id,
                },
                inference_note=(
                    "Derived from __init__.py relation; export intent may be incomplete."
                ),
            ),
        )


def _build_inferred_component(
    *,
    entity: Entity,
    component_type: SemanticComponentType,
    properties: dict[str, JsonValue],
    inference_note: str | None = None,
) -> SemanticComponent:
    return SemanticComponent(
        component_type=component_type,
        entity_id=entity.id,
        properties=properties,
        evidence=(
            Evidence(
                source_range=entity.source_range,
                extractor=_HEURISTIC_EXTRACTOR,
                confidence=_INFERRED_CONFIDENCE,
                note="heuristic_name_based_inference",
            ),
        ),
        confidence=_INFERRED_CONFIDENCE,
        status="inferred",
        inference_note=inference_note,
    )


def _upsert(
    components: dict[tuple[str, str], SemanticComponent], component: SemanticComponent
) -> None:
    key = (component.entity_id.value, component.component_type)
    if key in components:
        return
    components[key] = component


def _normalized_path(path: str) -> str:
    return path.replace("\\", "/")
