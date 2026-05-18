"""Temporal metadata enrichment helpers for entities."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repo_semantic_memory.extractors.git_history import (
    GitFileMetadata,
    GitRepositorySummary,
    collect_git_file_metadata,
    get_git_repository_summary,
)
from repo_semantic_memory.model import Entity

GIT_METADATA_KEY = "git"


@dataclass(frozen=True)
class TemporalMetadataResult:
    """Result of optional Git metadata attachment on indexed entities."""

    entities: list[Entity]
    status: str
    files_with_metadata: int
    warning: str | None = None


def attach_git_metadata_to_entities(
    entities: Sequence[Entity],
    *,
    repository_root: Path | str,
    summary: GitRepositorySummary | None = None,
) -> TemporalMetadataResult:
    """Attach file-level Git metadata to entity metadata when available."""
    git_summary = summary or get_git_repository_summary(repository_root)
    if not git_summary.in_git_repo or git_summary.repository_root is None:
        return TemporalMetadataResult(
            entities=_sorted_entities(entities),
            status="unavailable",
            files_with_metadata=0,
            warning=git_summary.unavailable_reason or "path is not inside a Git repository",
        )

    relative_paths = sorted({entity.source_range.path for entity in entities})
    file_metadata = collect_git_file_metadata(
        repository_root=Path(git_summary.repository_root),
        relative_paths=relative_paths,
    )
    enriched_entities = _attach_metadata(entities=entities, file_metadata=file_metadata)
    warning = git_summary.unavailable_reason
    return TemporalMetadataResult(
        entities=enriched_entities,
        status="attached",
        files_with_metadata=len(file_metadata),
        warning=warning,
    )


def _attach_metadata(
    *,
    entities: Sequence[Entity],
    file_metadata: dict[str, GitFileMetadata],
) -> list[Entity]:
    updated: list[Entity] = []
    for entity in entities:
        metadata_payload = file_metadata.get(entity.source_range.path)
        if metadata_payload is None:
            updated.append(entity)
            continue
        metadata = dict(entity.metadata)
        metadata[GIT_METADATA_KEY] = metadata_payload.to_dict()
        updated.append(
            Entity(
                id=entity.id,
                kind=entity.kind,
                name=entity.name,
                qualified_name=entity.qualified_name,
                source_range=entity.source_range,
                metadata=metadata,
            )
        )
    return _sorted_entities(updated)


def _sorted_entities(entities: Sequence[Entity]) -> list[Entity]:
    return sorted(entities, key=lambda entity: entity.id.value)
