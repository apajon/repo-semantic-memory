"""Filesystem extractor tests."""

from __future__ import annotations

from pathlib import Path

from repo_semantic_memory.extractors.filesystem import extract_filesystem_entities
from repo_semantic_memory.model import StableId


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "simple_repo"


def test_filesystem_extractor_ignores_common_directories(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "keep.py").write_text("print('keep')", encoding="utf-8")
    for ignored_directory in (
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".idea",
        ".vscode",
    ):
        directory = repo_root / ignored_directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "ignored.py").write_text("print('ignored')", encoding="utf-8")

    entities = extract_filesystem_entities(repo_root)
    paths = [entity.source_range.path for entity in entities]
    ignored_directory_tokens = (
        ".git/",
        ".venv/",
        "__pycache__/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        "dist/",
        "build/",
        ".idea/",
        ".vscode/",
    )
    assert not any(token in path for path in paths for token in ignored_directory_tokens)
    assert paths == ["keep.py"]


def test_filesystem_extractor_output_is_deterministic_and_sorted() -> None:
    first = extract_filesystem_entities(_fixture_root())
    second = extract_filesystem_entities(_fixture_root())
    first_paths = [entity.source_range.path for entity in first]
    second_paths = [entity.source_range.path for entity in second]

    assert first_paths == sorted(first_paths)
    assert first_paths == second_paths


def test_filesystem_extractor_assigns_expected_kinds() -> None:
    entities = extract_filesystem_entities(_fixture_root())
    kinds_by_path = {entity.source_range.path: entity.kind for entity in entities}

    assert kinds_by_path["src/app.py"] == "module"
    assert kinds_by_path["docs/guide.md"] == "doc"
    assert kinds_by_path["docs/notes.rst"] == "doc"
    assert kinds_by_path["docs/data.txt"] == "doc"
    assert kinds_by_path["config/settings.yaml"] == "doc"
    assert kinds_by_path["config/values.yml"] == "doc"
    assert kinds_by_path["config/data.json"] == "doc"
    assert "src/skip.csv" not in kinds_by_path


def test_filesystem_extractor_uses_stable_ids_from_relative_paths() -> None:
    entities = extract_filesystem_entities(_fixture_root())
    ids_by_path = {entity.source_range.path: entity.id.value for entity in entities}

    for path, stable_id in ids_by_path.items():
        assert stable_id == StableId.from_parts(["file", path]).value


def test_filesystem_extractor_ignores_binary_looking_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    text_file = repo_root / "notes.md"
    binary_file = repo_root / "binary.md"
    text_file.write_text("text", encoding="utf-8")
    binary_file.write_bytes(b"\x00\x01\x02")

    entities = extract_filesystem_entities(repo_root)
    paths = [entity.source_range.path for entity in entities]

    assert paths == ["notes.md"]
