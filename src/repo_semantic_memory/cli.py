"""Command-line interface for repo-semantic-memory."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from repo_semantic_memory.config import DEFAULT_CONFIG
from repo_semantic_memory.context import (
    build_context_pack,
    build_repo_map_markdown,
    render_context_pack_markdown,
)
from repo_semantic_memory.eval import (
    render_compact_table,
    render_compare_compact_table,
    run_baseline_comparison,
    run_retrieval_benchmark,
    to_compare_json_payload,
    to_json_payload,
    write_compare_markdown_report,
    write_markdown_report,
)
from repo_semantic_memory.exporters import AiDirectoryExporter
from repo_semantic_memory.extractors import extract_filesystem_entities, index_python_path
from repo_semantic_memory.memory import (
    export_invariants_yaml,
    import_invariants_yaml,
    infer_semantic_components,
)
from repo_semantic_memory.model import Entity, Relation, SemanticComponent
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata
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
    index_parser = subparsers.add_parser(
        "index",
        help="Extract and persist semantic data to SQLite.",
    )
    index_parser.add_argument("path", help="Repository root path to index.")
    index_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect stored entities or relations.",
    )
    inspect_subparsers = inspect_parser.add_subparsers(dest="inspect_target")
    inspect_entities_parser = inspect_subparsers.add_parser(
        "entities",
        help="List stored entities.",
    )
    inspect_entities_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    inspect_entities_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit rows as JSON.",
    )
    inspect_relations_parser = inspect_subparsers.add_parser(
        "relations",
        help="List stored relations.",
    )
    inspect_relations_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    inspect_relations_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit rows as JSON.",
    )
    repo_map_parser = subparsers.add_parser(
        "repo-map",
        help="Generate a compact Markdown repository map.",
    )
    repo_map_source_group = repo_map_parser.add_mutually_exclusive_group()
    repo_map_source_group.add_argument(
        "--db",
        help="SQLite database file path.",
    )
    repo_map_source_group.add_argument(
        "--path",
        help="Repository root path to index in-memory before generating the map.",
    )
    repo_map_parser.add_argument(
        "--budget",
        type=int,
        default=4000,
        help="Approximate character budget for map output (not tokenizer-based token count).",
    )
    pack_parser = subparsers.add_parser(
        "pack",
        help="Generate a task-specific context pack.",
    )
    pack_parser.add_argument(
        "--task",
        required=True,
        help="Task prompt used for lexical selection.",
    )
    pack_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    pack_parser.add_argument(
        "--budget",
        type=int,
        default=4000,
        help="Approximate character budget for pack output (not tokenizer-based token count).",
    )
    pack_parser.add_argument(
        "--format",
        choices=("markdown", "yaml"),
        default="markdown",
        help="Output format.",
    )
    components_parser = subparsers.add_parser(
        "components",
        help="Infer and inspect ECS-style semantic components.",
    )
    components_subparsers = components_parser.add_subparsers(dest="components_target")
    components_infer_parser = components_subparsers.add_parser(
        "infer",
        help="Infer semantic components from indexed entities and relations.",
    )
    components_infer_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    components_infer_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit inferred semantic components as JSON.",
    )
    components_list_parser = components_subparsers.add_parser(
        "list",
        help="List derived semantic components (recomputed from entities/relations).",
    )
    components_list_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    components_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit inferred semantic components as JSON.",
    )
    invariants_parser = subparsers.add_parser(
        "invariants",
        help="Import and export standalone claim/invariant YAML documents.",
    )
    invariants_subparsers = invariants_parser.add_subparsers(dest="invariants_target")
    invariants_export_parser = invariants_subparsers.add_parser(
        "export",
        help="Export claims/invariants to YAML-compatible output.",
    )
    invariants_export_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help=(
            "SQLite database file path used only to validate index availability/schema; "
            "claims/invariants are not persisted yet."
        ),
    )
    invariants_export_parser.add_argument(
        "--out",
        required=True,
        help="Output YAML file path.",
    )
    invariants_import_parser = invariants_subparsers.add_parser(
        "import",
        help="Import and validate claims/invariants YAML payload.",
    )
    invariants_import_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help=(
            "SQLite database file path used only to validate index availability/schema; "
            "claims/invariants are not persisted yet."
        ),
    )
    invariants_import_parser.add_argument(
        "path",
        help="Input YAML file path.",
    )
    eval_parser = subparsers.add_parser(
        "eval", help="Run local deterministic benchmark evaluation."
    )
    eval_subparsers = eval_parser.add_subparsers(dest="eval_target")
    eval_retrieval_parser = eval_subparsers.add_parser(
        "retrieval",
        help="Benchmark lexical retrieval quality for known tasks.",
    )
    eval_retrieval_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    eval_retrieval_parser.add_argument(
        "--dataset",
        required=True,
        help="YAML benchmark dataset file path.",
    )
    eval_retrieval_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit benchmark result payload as JSON.",
    )
    eval_retrieval_parser.add_argument(
        "--markdown-report",
        help="Write a Markdown report to this path.",
    )
    eval_compare_parser = eval_subparsers.add_parser(
        "compare",
        help="Compare repo-map and lexical context-pack baselines.",
    )
    eval_compare_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    eval_compare_parser.add_argument(
        "--dataset",
        required=True,
        help="YAML benchmark dataset file path.",
    )
    eval_compare_parser.add_argument(
        "--budget",
        type=int,
        default=4000,
        help="Approximate character budget shared by both baselines.",
    )
    eval_compare_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit comparison payload as JSON.",
    )
    eval_compare_parser.add_argument(
        "--markdown-report",
        help="Write a Markdown comparison report to this path.",
    )
    export_ai_parser = subparsers.add_parser(
        "export-ai",
        help="Export semantic memory as a portable .ai/ directory.",
    )
    export_ai_parser.add_argument(
        "--db",
        default=".rsm/index.sqlite",
        help="SQLite database file path.",
    )
    export_ai_parser.add_argument(
        "--out",
        default=".ai",
        help="Output directory path for generated .ai/ files.",
    )
    export_ai_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in the output directory.",
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
            # Keep legacy list output for scan to preserve existing automation contracts.
            scan_payload = [
                {"id": entity.id.value, "kind": entity.kind, "path": entity.source_range.path}
                for entity in entities
            ]
            print(json.dumps(scan_payload, separators=(",", ":")))
            return 0
        print(_format_scan_table(entities))
        return 0
    if args.command == "index-python":
        entities, relations = index_python_path(args.path)
        if args.json:
            index_payload = {
                "entities": [entity.to_dict() for entity in entities],
                "relations": [relation.to_dict() for relation in relations],
            }
            print(json.dumps(index_payload, separators=(",", ":")))
            return 0
        print(_format_index_python_summary(entities, relations))
        return 0
    if args.command == "index":
        return _run_index_command(path=args.path, db=args.db)
    if args.command == "inspect":
        if args.inspect_target == "entities":
            return _run_inspect_entities_command(db=args.db, emit_json=args.json)
        if args.inspect_target == "relations":
            return _run_inspect_relations_command(db=args.db, emit_json=args.json)
        parser.print_help()
        return 2
    if args.command == "repo-map":
        return _run_repo_map_command(path=args.path, db=args.db, budget=args.budget)
    if args.command == "pack":
        return _run_pack_command(
            task=args.task, db=args.db, budget=args.budget, output_format=args.format
        )
    if args.command == "components":
        if args.components_target == "infer":
            return _run_components_infer_command(db=args.db, emit_json=args.json)
        if args.components_target == "list":
            return _run_components_list_command(db=args.db, emit_json=args.json)
        parser.print_help()
        return 2
    if args.command == "invariants":
        if args.invariants_target == "export":
            return _run_invariants_export_command(db=args.db, out=args.out)
        if args.invariants_target == "import":
            return _run_invariants_import_command(db=args.db, path=args.path)
        parser.print_help()
        return 2
    if args.command == "eval":
        if args.eval_target == "retrieval":
            return _run_eval_retrieval_command(
                db=args.db,
                dataset=args.dataset,
                emit_json=args.json,
                markdown_report=args.markdown_report,
            )
        if args.eval_target == "compare":
            return _run_eval_compare_command(
                db=args.db,
                dataset=args.dataset,
                budget=args.budget,
                emit_json=args.json,
                markdown_report=args.markdown_report,
            )
        parser.print_help()
        return 2
    if args.command == "export-ai":
        return _run_export_ai_command(db=args.db, out=args.out, force=args.force)

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


def _format_index_python_summary(entities: Sequence[Entity], relations: Sequence[Relation]) -> str:
    return f"entities={len(entities)} relations={len(relations)}"


def _run_index_command(*, path: str, db: str) -> int:
    repository_root = Path(path).resolve()
    db_path = Path(db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    filesystem_entities = extract_filesystem_entities(repository_root)
    filesystem_entities = _drop_python_module_file_entities(filesystem_entities)
    python_entities, python_relations = index_python_path(repository_root)
    all_entities = _merge_entities(filesystem_entities, python_entities)
    metadata = build_default_extraction_metadata(
        repository_root=repository_root,
        extractor_names=("filesystem", "python_ast"),
        timestamp=datetime.now(tz=UTC).isoformat(),
    )
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        store.persist_index(entities=all_entities, relations=python_relations, metadata=metadata)
    finally:
        store.close()
    print(f"entities={len(all_entities)} relations={len(python_relations)}")
    return 0


def _run_inspect_entities_command(*, db: str, emit_json: bool) -> int:
    store = SQLiteStore(db)
    try:
        store.initialize()
        entities = store.list_entities()
    finally:
        store.close()

    if emit_json:
        print(json.dumps([entity.to_dict() for entity in entities], separators=(",", ":")))
        return 0
    print(_format_scan_table(entities))
    return 0


def _run_inspect_relations_command(*, db: str, emit_json: bool) -> int:
    store = SQLiteStore(db)
    try:
        store.initialize()
        relations = store.list_relations()
    finally:
        store.close()

    if emit_json:
        print(json.dumps([relation.to_dict() for relation in relations], separators=(",", ":")))
        return 0
    print(_format_relations_table(relations))
    return 0


def _run_repo_map_command(*, path: str | None, db: str | None, budget: int) -> int:
    if path is not None:
        entities, relations = _index_for_repo_map(path=path)
        print(build_repo_map_markdown(entities, relations, budget_chars=budget))
        return 0

    db_path = db if db is not None else ".rsm/index.sqlite"
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        entities = store.list_entities()
        relations = store.list_relations()
    finally:
        store.close()
    print(build_repo_map_markdown(entities, relations, budget_chars=budget))
    return 0


def _run_eval_retrieval_command(
    *,
    db: str,
    dataset: str,
    emit_json: bool,
    markdown_report: str | None,
) -> int:
    try:
        result = run_retrieval_benchmark(db_path=db, dataset_path=dataset)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if markdown_report:
        write_markdown_report(markdown_report, result)

    if emit_json:
        print(json.dumps(to_json_payload(result), separators=(",", ":")))
        return 0
    print(render_compact_table(result))
    return 0


def _run_eval_compare_command(
    *,
    db: str,
    dataset: str,
    budget: int,
    emit_json: bool,
    markdown_report: str | None,
) -> int:
    try:
        result = run_baseline_comparison(
            db_path=db,
            dataset_path=dataset,
            budget_chars=budget,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if markdown_report:
        write_compare_markdown_report(markdown_report, result)

    if emit_json:
        print(json.dumps(to_compare_json_payload(result), separators=(",", ":")))
        return 0
    print(render_compare_compact_table(result))
    return 0


def _run_pack_command(*, task: str, db: str, budget: int, output_format: str) -> int:
    store = SQLiteStore(db)
    try:
        store.initialize()
        entities = store.list_entities()
        relations = store.list_relations()
    finally:
        store.close()

    context_pack = build_context_pack(
        task=task,
        entities=entities,
        relations=relations,
        budget_chars=budget,
    )
    if output_format == "yaml":
        print(context_pack.to_yaml())
        return 0
    print(render_context_pack_markdown(context_pack))
    return 0


def _run_components_infer_command(*, db: str, emit_json: bool) -> int:
    entities, relations = _load_index_from_db(db)
    components = infer_semantic_components(entities=entities, relations=relations)
    if emit_json:
        print(json.dumps([component.to_dict() for component in components], separators=(",", ":")))
        return 0
    print(_format_components_table(components))
    return 0


def _run_components_list_command(*, db: str, emit_json: bool) -> int:
    """List the same derived component view as infer (components are not persisted)."""
    return _run_components_infer_command(db=db, emit_json=emit_json)


def _run_invariants_export_command(*, db: str, out: str) -> int:
    _load_index_from_db(db)
    document = export_invariants_yaml(out_path=out)
    print(
        f"exported invariants document to {out} "
        f"claims={len(document.claims)} invariants={len(document.invariants)} "
        "(standalone YAML; SQLite persistence not yet implemented)"
    )
    return 0


def _run_invariants_import_command(*, db: str, path: str) -> int:
    _load_index_from_db(db)
    document = import_invariants_yaml(path)
    print(
        f"validated invariants document from {path} "
        f"claims={len(document.claims)} invariants={len(document.invariants)} "
        "(standalone YAML; SQLite persistence not yet implemented)"
    )
    return 0


def _run_export_ai_command(*, db: str, out: str, force: bool) -> int:
    db_path = Path(db)
    output_dir = Path(out)
    entities, relations = _load_index_from_db(db)
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = store.get_metadata()
    finally:
        store.close()
    generated_at = datetime.now(tz=UTC).isoformat()
    exporter = AiDirectoryExporter(
        db_path=db_path,
        output_dir=output_dir,
        entities=entities,
        relations=relations,
        metadata=metadata,
        generated_at=generated_at,
    )
    result = exporter.export(force=force)
    written = len(result.files_written)
    skipped = len(result.files_skipped)
    print(
        f"exported to {output_dir} "
        f"entities={result.entity_count} relations={result.relation_count} "
        f"components={result.component_count} invariants={result.invariant_count} "
        f"files_written={written} files_skipped={skipped}"
    )
    if result.files_skipped:
        print(
            f"skipped (use --force to overwrite): {', '.join(sorted(result.files_skipped))}",
            file=sys.stderr,
        )
    return 0


def _index_for_repo_map(*, path: str) -> tuple[list[Entity], list[Relation]]:
    repository_root = Path(path).resolve()
    filesystem_entities = extract_filesystem_entities(repository_root)
    filesystem_entities = _drop_python_module_file_entities(filesystem_entities)
    python_entities, python_relations = index_python_path(repository_root)
    all_entities = _merge_entities(filesystem_entities, python_entities)
    return all_entities, python_relations


def _load_index_from_db(db: str) -> tuple[list[Entity], list[Relation]]:
    store = SQLiteStore(db)
    try:
        store.initialize()
        entities = store.list_entities()
        relations = store.list_relations()
    finally:
        store.close()
    return entities, relations


def _merge_entities(first: Sequence[Entity], second: Sequence[Entity]) -> list[Entity]:
    merged: dict[str, Entity] = {}
    for entity in [*first, *second]:
        merged[entity.id.value] = entity
    return sorted(merged.values(), key=lambda entity: entity.id.value)


def _drop_python_module_file_entities(entities: Sequence[Entity]) -> list[Entity]:
    return [
        entity
        for entity in entities
        if not (entity.kind == "module" and Path(entity.source_range.path).suffix == ".py")
    ]


def _format_relations_table(relations: Sequence[Relation]) -> str:
    rows = [("kind", "source_id", "target_id")]
    for relation in relations:
        rows.append(
            (
                str(relation.kind),
                str(relation.source_entity_id.value),
                str(relation.target_entity_id.value),
            )
        )
    columns = zip(*rows, strict=True)
    widths = [max(len(value) for value in column) for column in columns]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows
    )


def _format_components_table(components: Sequence[SemanticComponent]) -> str:
    rows = [("component_type", "entity_id", "status", "confidence", "evidence_count")]
    for component in components:
        rows.append(
            (
                str(component.component_type),
                str(component.entity_id.value),
                str(component.status),
                f"{component.confidence:.2f}",
                str(len(component.evidence)),
            )
        )
    columns = zip(*rows, strict=True)
    widths = [max(len(value) for value in column) for column in columns]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows
    )


if __name__ == "__main__":
    raise SystemExit(main())
