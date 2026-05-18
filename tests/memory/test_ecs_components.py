"""ECS semantic component inference tests."""

from __future__ import annotations

from repo_semantic_memory.memory import infer_semantic_components
from repo_semantic_memory.model import Entity, EntityKind, Relation, SourceRange, StableId


def _entity(
    *,
    identifier: str,
    kind: EntityKind,
    name: str,
    qualified_name: str,
    path: str,
) -> Entity:
    return Entity(
        id=StableId(identifier),
        kind=kind,
        name=name,
        qualified_name=qualified_name,
        source_range=SourceRange(path=path, start_line=1, end_line=1),
    )


def test_inference_is_deterministic() -> None:
    entities = [
        _entity(
            identifier="python:module:tests.test_mod",
            kind="module",
            name="test_mod",
            qualified_name="tests.test_mod",
            path="pkg/tests/test_mod.py",
        ),
        _entity(
            identifier="python:function:tests.test_mod.test_case",
            kind="function",
            name="test_case",
            qualified_name="tests.test_mod.test_case",
            path="pkg/tests/test_mod.py",
        ),
    ]
    first = infer_semantic_components(entities=entities, relations=[])
    second = infer_semantic_components(entities=entities, relations=[])
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]


def test_inferred_components_include_evidence_or_inference_note() -> None:
    entities = [
        _entity(
            identifier="python:class:pkg.worker.lifecycle_manager",
            kind="class",
            name="LifecycleManager",
            qualified_name="pkg.worker.LifecycleManager",
            path="pkg/worker.py",
        )
    ]
    components = infer_semantic_components(entities=entities, relations=[])
    assert components
    assert all(component.status == "inferred" for component in components)
    for component in components:
        assert component.evidence or component.inference_note


def test_init_exports_infer_public_api_only_when_relation_is_resolved() -> None:
    init_module = _entity(
        identifier="python:module:pkg",
        kind="module",
        name="pkg",
        qualified_name="pkg",
        path="pkg/__init__.py",
    )
    exported = _entity(
        identifier="python:function:pkg.api",
        kind="function",
        name="api",
        qualified_name="pkg.api",
        path="pkg/api.py",
    )
    unresolved_target = _entity(
        identifier="python:function:pkg.unresolved",
        kind="function",
        name="unresolved",
        qualified_name="pkg.unresolved",
        path="pkg/unresolved.py",
    )
    relations = [
        Relation(
            source_entity_id=init_module.id,
            target_entity_id=exported.id,
            kind="contains",
            metadata={"resolved": True},
        ),
        Relation(
            source_entity_id=init_module.id,
            target_entity_id=unresolved_target.id,
            kind="imports",
            metadata={"resolved": False},
        ),
    ]

    components = infer_semantic_components(
        entities=[init_module, exported, unresolved_target],
        relations=relations,
    )
    public_api = [component for component in components if component.component_type == "PublicAPI"]
    assert len(public_api) == 1
    assert public_api[0].entity_id.value == exported.id.value
    assert all(component.status != "confirmed" for component in components)


def test_no_project_specific_hardcoding_for_ros_namespaces() -> None:
    plain_entity = _entity(
        identifier="python:function:lifecycle.worker.run",
        kind="function",
        name="run",
        qualified_name="lifecycle.worker.run",
        path="lifecycle/lifecore_ros2/worker.py",
    )
    components = infer_semantic_components(entities=[plain_entity], relations=[])
    assert components == []


def test_ros_like_and_external_integration_are_inferred_from_generic_tokens() -> None:
    ros_entity = _entity(
        identifier="python:class:pkg.ros_timer_client",
        kind="class",
        name="ROSTimerClient",
        qualified_name="pkg.ros.ROSTimerClient",
        path="pkg/ros_node.py",
    )
    ext_entity = _entity(
        identifier="python:function:pkg.event_service",
        kind="function",
        name="EventService",
        qualified_name="pkg.integration.EventService",
        path="pkg/integration.py",
    )

    components = infer_semantic_components(entities=[ros_entity, ext_entity], relations=[])
    by_type = {(component.entity_id.value, component.component_type) for component in components}
    assert (ros_entity.id.value, "ROSLikeIntegration") in by_type
    assert (ext_entity.id.value, "ExternalIntegration") in by_type
