"""Tests for temporal metadata attachment."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_semantic_memory.extractors.git_history import GitFileMetadata, GitRepositorySummary
from repo_semantic_memory.memory.temporal import attach_git_metadata_to_entities
from repo_semantic_memory.model import Entity, SourceRange, StableId


def _entity(identifier: str, relative_path: str) -> Entity:
    return Entity(
        id=StableId(identifier),
        kind="module",
        name=Path(relative_path).name,
        qualified_name=relative_path,
        source_range=SourceRange(path=relative_path, start_line=1, end_line=1),
        metadata={},
    )


def test_attach_git_metadata_to_entities_returns_unavailable_for_non_repo() -> None:
    entities = [_entity("id:a", "src/a.py")]
    summary = GitRepositorySummary(
        path="/tmp/not-repo",
        in_git_repo=False,
        repository_root=None,
        current_commit=None,
        is_dirty=None,
        tracked_file_count=None,
        unavailable_reason="path is not inside a Git repository",
    )
    result = attach_git_metadata_to_entities(
        entities,
        repository_root="/tmp/not-repo",
        summary=summary,
    )
    assert result.status == "unavailable"
    assert result.files_with_metadata == 0
    assert result.warning == "path is not inside a Git repository"
    assert result.entities == entities


def test_attach_git_metadata_to_entities_attaches_file_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entities = [_entity("id:a", "src/a.py"), _entity("id:b", "README.md")]
    summary = GitRepositorySummary(
        path="/repo",
        in_git_repo=True,
        repository_root="/repo",
        current_commit="abc123",
        is_dirty=False,
        tracked_file_count=2,
    )

    def _fake_collect(
        *,
        repository_root: Path | str,
        relative_paths: list[str],
    ) -> dict[str, GitFileMetadata]:
        del repository_root, relative_paths
        return {
            "src/a.py": GitFileMetadata(
                last_commit_hash="def456",
                last_commit_date="2026-05-18T00:00:00+00:00",
                commit_count=3,
            )
        }

    monkeypatch.setattr(
        "repo_semantic_memory.memory.temporal.collect_git_file_metadata", _fake_collect
    )
    result = attach_git_metadata_to_entities(entities, repository_root="/repo", summary=summary)

    assert result.status == "attached"
    assert result.files_with_metadata == 1
    entity_by_id = {entity.id.value: entity for entity in result.entities}
    assert entity_by_id["id:a"].metadata["git"] == {
        "last_commit_hash": "def456",
        "last_commit_date": "2026-05-18T00:00:00+00:00",
        "commit_count": 3,
    }
    assert entity_by_id["id:b"].metadata == {}
