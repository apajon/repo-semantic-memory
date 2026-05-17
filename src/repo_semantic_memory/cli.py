"""Command-line interface for repo-semantic-memory."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from repo_semantic_memory.config import DEFAULT_CONFIG
from repo_semantic_memory.extractors import extract_filesystem_entities, index_python_path
from repo_semantic_memory.model import Entity, Relation
from repo_semantic_memory.version import get_version_info


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog=DEFAULT_CONFIG.cli_name,
        description="Semantic compiler foundation for repository memory artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version", help="Show package, schema, and context pack versions.")
    scan_parser = subparsers.add_parser("scan", help="Discover repository files.")
    scan_parser.add_argument("path", help="Repository root path to scan.")
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit discovered file entities as JSON.",
    )
    index_python_parser = subparsers.add_parser(
        "index-python", help="Extract Python symbols and structural relations."
    )
    index_python_parser.add_argument("path", help="Python file or directory to index.")
    index_python_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit extracted entities and relations as JSON.",
    )
    return parser


def _format_version_output() -> str:
    info = get_version_info()
    return (
        f"package_version: {info.package_version}\n"
        f"schema_version: {info.schema_version}\n"
        f"context_pack_version: {info.context_pack_version}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "version":
        print(_format_version_output())
        return 0
    if args.command == "scan":
        entities = extract_filesystem_entities(args.path)
        if args.json:
            payload = [
                {"id": entity.id.value, "kind": entity.kind, "path": entity.source_range.path}
                for entity in entities
            ]
            print(json.dumps(payload))
            return 0
        print(_format_scan_table(entities))
        return 0
    if args.command == "index-python":
        entities, relations = index_python_path(args.path)
        if args.json:
            payload = {
                "entities": [entity.to_dict() for entity in entities],
                "relations": [relation.to_dict() for relation in relations],
            }
            print(json.dumps(payload, separators=(",", ":")))
            return 0
        print(_format_index_python_table(entities, relations))
        return 0

    parser.print_help()
    return 0


def _format_scan_table(entities: Sequence[Entity]) -> str:
    rows = [("kind", "id", "path")]
    for entity in entities:
        rows.append((str(entity.kind), str(entity.id.value), str(entity.source_range.path)))

    columns = zip(*rows, strict=True)
    widths = [max(len(value) for value in column) for column in columns]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows
    )


def _format_index_python_table(entities: Sequence[Entity], relations: Sequence[Relation]) -> str:
    return f"entities={len(entities)} relations={len(relations)}"


if __name__ == "__main__":
    raise SystemExit(main())
