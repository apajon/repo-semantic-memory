"""Semantic memory ECS component utilities."""

from repo_semantic_memory.memory.ecs_components import (
    CompactSemanticComponent,
    compact_component_labels,
    infer_semantic_components,
)
from repo_semantic_memory.memory.invariants import (
    InvariantsDocument,
    export_invariants_yaml,
    import_invariants_yaml,
)
from repo_semantic_memory.memory.temporal import (
    TemporalMetadataResult,
    attach_git_metadata_to_entities,
)

__all__ = [
    "CompactSemanticComponent",
    "InvariantsDocument",
    "TemporalMetadataResult",
    "attach_git_metadata_to_entities",
    "compact_component_labels",
    "export_invariants_yaml",
    "infer_semantic_components",
    "import_invariants_yaml",
]
