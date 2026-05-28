"""Markdown outline extractor tests."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from repo_semantic_memory.extractors.markdown_outline import (
    extract_markdown_file,
    extract_markdown_outline_path,
)
from repo_semantic_memory.model import Entity, StableId


def _doc_sections(entities: list[Entity]) -> list[Entity]:
    return [entity for entity in entities if entity.metadata.get("entity_type") == "doc_section"]


def test_markdown_outline_extracts_headings_with_metadata_and_ranges(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "guide.md"
    doc.write_text(
        "\n".join(
            [
                "# Overview",
                "",
                "intro body",
                "## Install plan ##",
                "install body",
                "# API",
                "api body",
            ]
        ),
        encoding="utf-8",
    )

    entities, relations = extract_markdown_file(repo, doc)
    sections = [
        entity for entity in entities if entity.metadata.get("entity_type") == "doc_section"
    ]

    assert [section.name for section in sections] == ["Overview", "Install plan", "API"]
    assert [section.metadata["section_level"] for section in sections] == [1, 2, 1]
    assert [section.metadata["anchor"] for section in sections] == [
        "overview",
        "install-plan",
        "api",
    ]
    assert [
        (section.source_range.start_line, section.source_range.end_line) for section in sections
    ] == [
        (1, 5),
        (4, 5),
        (6, 7),
    ]
    assert all(relation.kind == "contains" for relation in relations)


def test_markdown_outline_extracts_nested_contains_relations(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "docs" / "guide.md"
    doc.parent.mkdir()
    doc.write_text("# Parent\n## Child\n### Grandchild\n# Sibling\n", encoding="utf-8")

    entities, relations = extract_markdown_file(repo, doc)
    by_name = {entity.name: entity for entity in entities}
    relation_pairs = {
        (relation.source_entity_id.value, relation.target_entity_id.value) for relation in relations
    }

    assert (by_name["guide.md"].id.value, by_name["Parent"].id.value) in relation_pairs
    assert (by_name["guide.md"].id.value, by_name["Child"].id.value) in relation_pairs
    assert (by_name["Parent"].id.value, by_name["Child"].id.value) in relation_pairs
    assert (by_name["Child"].id.value, by_name["Grandchild"].id.value) in relation_pairs
    assert (by_name["guide.md"].id.value, by_name["Sibling"].id.value) in relation_pairs


def test_markdown_outline_uses_stable_section_ids(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "guide.md"
    doc.write_text("# Repeated\n# Repeated\n", encoding="utf-8")

    first_entities, _ = extract_markdown_file(repo, doc)
    second_entities, _ = extract_markdown_file(repo, doc)
    first_sections = [
        entity for entity in first_entities if entity.metadata.get("entity_type") == "doc_section"
    ]
    second_sections = [
        entity for entity in second_entities if entity.metadata.get("entity_type") == "doc_section"
    ]

    assert [section.id.value for section in first_sections] == [
        StableId.from_parts(["markdown", "guide.md", "section", "repeated", "1"]).value,
        StableId.from_parts(["markdown", "guide.md", "section", "repeated", "2"]).value,
    ]
    assert [section.id.value for section in first_sections] == [
        section.id.value for section in second_sections
    ]


def test_markdown_outline_uses_fallback_id_for_non_ascii_heading(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "README.cn.md"
    doc.write_text("# 兼容性\n\nSome content.\n", encoding="utf-8")

    entities, _ = extract_markdown_file(repo, doc)
    sections = _doc_sections(entities)

    digest_seed = f"README.cn.md\0兼容性\0{1}"
    digest = sha256(digest_seed.encode()).hexdigest()[:10]
    assert len(sections) == 1
    assert (
        sections[0].id.value
        == StableId.from_parts(
            ["markdown", "README.cn.md", "section", f"section_{digest}", "1"]
        ).value
    )
    assert sections[0].name == "兼容性"
    assert sections[0].source_range.path == "README.cn.md"
    assert sections[0].source_range.start_line == 1
    assert sections[0].source_range.end_line == 3
    assert sections[0].metadata["heading"] == "兼容性"


def test_markdown_outline_preserves_ascii_id_part_for_mixed_heading(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "guide.md"
    doc.write_text("# API 兼容性\n", encoding="utf-8")

    entities, _ = extract_markdown_file(repo, doc)
    sections = _doc_sections(entities)

    assert [section.id.value for section in sections] == [
        StableId.from_parts(["markdown", "guide.md", "section", "api", "1"]).value
    ]
    assert sections[0].metadata["anchor"] == "api-兼容性"


def test_markdown_outline_non_ascii_fallback_ids_are_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "README.cn.md"
    doc.write_text("# 兼容性\n\nSome content.\n", encoding="utf-8")

    first_entities, _ = extract_markdown_file(repo, doc)
    second_entities, _ = extract_markdown_file(repo, doc)

    assert [section.id.value for section in _doc_sections(first_entities)] == [
        section.id.value for section in _doc_sections(second_entities)
    ]


def test_markdown_outline_non_ascii_fallback_ids_avoid_line_collisions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "README.cn.md"
    doc.write_text("# 兼容性\n\n# 快速开始\n", encoding="utf-8")

    entities, _ = extract_markdown_file(repo, doc)
    section_ids = [section.id.value for section in _doc_sections(entities)]

    assert len(section_ids) == 2
    assert len(set(section_ids)) == 2
    assert all(":section_" in section_id for section_id in section_ids)


def test_markdown_outline_ignores_generated_docs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    generated = repo / "docs" / "_build" / "generated.md"
    kept = repo / "docs" / "guide.md"
    generated.parent.mkdir(parents=True)
    kept.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("# Generated\n", encoding="utf-8")
    kept.write_text("# Kept\n", encoding="utf-8")

    outline = extract_markdown_outline_path(repo)
    paths = {entity.source_range.path for entity in outline.entities}

    assert "docs/guide.md" in paths
    assert "docs/_build/generated.md" not in paths


def test_markdown_outline_is_deterministic_and_source_ordered(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "b.md").write_text("# B\n", encoding="utf-8")
    (repo / "a.md").write_text("# First\n## Second\n", encoding="utf-8")

    first = extract_markdown_outline_path(repo)
    second = extract_markdown_outline_path(repo)

    assert first == second
    section_positions = [
        (entity.source_range.path, entity.source_range.start_line)
        for entity in first.entities
        if entity.metadata.get("entity_type") == "doc_section"
    ]
    assert section_positions == [("a.md", 1), ("a.md", 2), ("b.md", 1)]


def test_markdown_outline_ignores_headings_inside_fenced_code(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "guide.md"
    doc.write_text("# Real\n```markdown\n# Not heading\n```\n## Also real\n", encoding="utf-8")

    entities, _ = extract_markdown_file(repo, doc)
    sections = [
        entity.name for entity in entities if entity.metadata.get("entity_type") == "doc_section"
    ]

    assert sections == ["Real", "Also real"]
