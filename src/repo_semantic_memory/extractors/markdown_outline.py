"""Markdown outline extractor for deterministic doc section entities."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from repo_semantic_memory.context.path_roles import is_generated_artifact_path
from repo_semantic_memory.extractors.filesystem import (
    _build_entity,
    _is_binary_looking,
    _should_ignore_directory_name,
    _should_ignore_directory_path,
)
from repo_semantic_memory.model import Entity, Evidence, JsonValue, Relation, SourceRange, StableId

_MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
_ATX_HEADING_RE = re.compile(r"^(?P<indent> {0,3})(?P<marks>#{1,6})(?:[ \t]+|$)(?P<text>.*)$")
_PUNCTUATION_RE = re.compile(r"[^\w\s-]")
_WHITESPACE_RE = re.compile(r"\s+")
_STABLE_ID_PART_RE = re.compile(r"[^a-z0-9._/-]+")
_STABLE_ID_DASH_RE = re.compile(r"-+")


@dataclass(frozen=True)
class MarkdownOutline:
    """Markdown file and section entities with structural contains relations."""

    entities: tuple[Entity, ...]
    relations: tuple[Relation, ...]


@dataclass(frozen=True)
class _Heading:
    line: int
    level: int
    text: str
    anchor: str
    column: int


def extract_markdown_outline_path(repo_root: Path | str) -> MarkdownOutline:
    """Extract Markdown file and heading section entities from a file or directory."""
    target = Path(repo_root).resolve()
    if not target.exists():
        raise ValueError(f"Path does not exist: {target}")

    if target.is_file():
        if target.suffix.lower() not in _MARKDOWN_EXTENSIONS:
            return MarkdownOutline(entities=(), relations=())
        root = target.parent
        file_entities, file_relations = extract_markdown_file(root, target)
        return MarkdownOutline(entities=tuple(file_entities), relations=tuple(file_relations))

    root = target
    entities: list[Entity] = []
    relations: list[Relation] = []
    for markdown_file in _iter_markdown_files(root):
        file_entities, file_relations = extract_markdown_file(root, markdown_file)
        entities.extend(file_entities)
        relations.extend(file_relations)
    return MarkdownOutline(
        entities=tuple(_sort_entities(entities)),
        relations=tuple(_sort_relations(relations)),
    )


def extract_markdown_file(
    repo_root: Path | str,
    markdown_file: Path | str,
) -> tuple[list[Entity], list[Relation]]:
    """Extract one Markdown file entity plus heading section entities and contains relations."""
    root = Path(repo_root).resolve()
    path = Path(markdown_file).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository root does not exist or is not a directory: {root}")
    if not path.is_file():
        raise ValueError(f"Markdown file does not exist or is not a file: {path}")
    if path.suffix.lower() not in _MARKDOWN_EXTENSIONS:
        raise ValueError(f"Expected a Markdown file, got: {path}")
    if _is_binary_looking(path):
        return [], []

    relative_path = path.relative_to(root).as_posix()
    if is_generated_artifact_path(relative_path):
        return [], []

    lines = path.read_text(encoding="utf-8").splitlines()
    doc_entity = _build_entity(relative_path, path, kind="doc")
    headings = _extract_headings(lines)
    section_entities = _section_entities(relative_path, lines, headings)
    relations = _contains_relations(doc_entity, section_entities)
    return [doc_entity, *section_entities], relations


def _iter_markdown_files(root: Path) -> list[Path]:
    discovered: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not _should_ignore_directory_name(name)
            and not _should_ignore_directory_path(current_dir / name, root)
        )
        for filename in sorted(filenames):
            file_path = Path(dirpath) / filename
            if file_path.suffix.lower() in _MARKDOWN_EXTENSIONS:
                relative_path = file_path.relative_to(root).as_posix()
                if not is_generated_artifact_path(relative_path) and not _is_binary_looking(
                    file_path
                ):
                    discovered.append(file_path)
    return discovered


def _extract_headings(lines: list[str]) -> list[_Heading]:
    headings: list[_Heading] = []
    in_fence = False
    fence_marker = ""
    for index, line in enumerate(lines, start=1):
        stripped = line.lstrip(" ")
        if len(line) - len(stripped) <= 3 and (
            stripped.startswith("```") or stripped.startswith("~~~")
        ):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        match = _ATX_HEADING_RE.match(line)
        if match is None:
            continue
        text = _clean_heading_text(match.group("text"))
        if not text:
            continue
        headings.append(
            _Heading(
                line=index,
                level=len(match.group("marks")),
                text=text,
                anchor=_anchor_for_heading(text),
                column=len(match.group("indent")) + 1,
            )
        )
    return headings


def _clean_heading_text(raw_text: str) -> str:
    text = raw_text.strip()
    if not text:
        return ""
    text = re.sub(r"[ \t]+#+[ \t]*$", "", text)
    return " ".join(text.split())


def _anchor_for_heading(text: str) -> str:
    normalized = text.strip().lower()
    normalized = _PUNCTUATION_RE.sub("", normalized)
    normalized = _WHITESPACE_RE.sub("-", normalized)
    normalized = normalized.replace("_", "-")
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "section"


def _section_entities(
    relative_path: str, lines: list[str], headings: list[_Heading]
) -> list[Entity]:
    entities: list[Entity] = []
    for index, heading in enumerate(headings):
        end_line = _section_end_line(index, headings, len(lines))
        section_id_part = _section_id_part(relative_path, heading)
        qualified_name = f"{relative_path}#{heading.anchor}"
        entities.append(
            Entity(
                id=StableId.from_parts(
                    ["markdown", relative_path, "section", section_id_part, str(heading.line)]
                ),
                kind="doc",
                name=heading.text,
                qualified_name=qualified_name,
                source_range=SourceRange(
                    path=relative_path,
                    start_line=heading.line,
                    end_line=end_line,
                    start_col=heading.column,
                ),
                metadata=_section_metadata(heading),
            )
        )
    return entities


def _section_id_part(relative_path: str, heading: _Heading) -> str:
    normalized = heading.anchor.strip().lower().replace("\\", "/")
    normalized = _STABLE_ID_PART_RE.sub("-", normalized)
    normalized = _STABLE_ID_DASH_RE.sub("-", normalized).strip("-")
    if normalized:
        return normalized

    digest = sha256(f"{relative_path}\0{heading.text}\0{heading.line}".encode()).hexdigest()
    return f"section_{digest[:10]}"


def _section_end_line(index: int, headings: list[_Heading], line_count: int) -> int:
    heading = headings[index]
    for next_heading in headings[index + 1 :]:
        if next_heading.level <= heading.level:
            return next_heading.line - 1
    return line_count


def _section_metadata(heading: _Heading) -> dict[str, JsonValue]:
    return {
        "entity_type": "doc_section",
        "section_level": heading.level,
        "heading": heading.text,
        "anchor": heading.anchor,
    }


def _contains_relations(doc_entity: Entity, section_entities: list[Entity]) -> list[Relation]:
    relations: list[Relation] = []
    stack: list[Entity] = []
    for section in section_entities:
        relations.append(
            _contains_relation(doc_entity, section, note="document contains heading section")
        )
        level = section.metadata.get("section_level")
        while stack and isinstance(level, int) and _section_level(stack[-1]) >= level:
            stack.pop()
        if stack:
            relations.append(
                _contains_relation(stack[-1], section, note="parent heading contains child")
            )
        stack.append(section)
    return relations


def _contains_relation(source: Entity, target: Entity, *, note: str) -> Relation:
    return Relation(
        source_entity_id=source.id,
        target_entity_id=target.id,
        kind="contains",
        evidence=Evidence(
            source_range=SourceRange(
                path=target.source_range.path,
                start_line=target.source_range.start_line,
                end_line=target.source_range.start_line,
                start_col=target.source_range.start_col,
            ),
            extractor="markdown_outline",
            confidence=1.0,
            note=note,
        ),
    )


def _section_level(entity: Entity) -> int:
    level = entity.metadata.get("section_level")
    return level if isinstance(level, int) else 0


def _sort_entities(entities: list[Entity]) -> list[Entity]:
    return sorted(
        entities,
        key=lambda entity: (
            entity.source_range.path,
            entity.source_range.start_line,
            entity.source_range.start_col or 0,
            entity.id.value,
        ),
    )


def _sort_relations(relations: list[Relation]) -> list[Relation]:
    return sorted(
        relations,
        key=lambda relation: (
            relation.source_entity_id.value,
            relation.target_entity_id.value,
            relation.kind,
        ),
    )
