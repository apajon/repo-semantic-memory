"""Command-line interface for repo-semantic-memory."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repo_semantic_memory.indexing.executor import IncrementalResult

from repo_semantic_memory.config import DEFAULT_CONFIG
from repo_semantic_memory.context import (
    build_context_pack,
    build_repo_map_markdown,
    render_context_pack_markdown,
)
from repo_semantic_memory.context.compression import available_profile_names, resolve_profile
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
from repo_semantic_memory.exporters import AiDirectoryExporter, export_jsonl_directory
from repo_semantic_memory.extractors import (
    ScopeFilter,
    extract_filesystem_entities,
    extract_markdown_outline_path,
    extract_test_relationships,
    get_git_repository_summary,
    index_python_exports,
    index_python_path,
)
from repo_semantic_memory.importers import import_jsonl_directory
from repo_semantic_memory.indexing import IncrementalFallbackReason
from repo_semantic_memory.indexing.profiler import IndexProfiler, _AnyProfiler, _NullProfiler
from repo_semantic_memory.memory import (
    attach_git_metadata_to_entities,
    export_invariants_yaml,
    import_invariants_yaml,
    infer_semantic_components,
)
from repo_semantic_memory.model import Entity, Relation, SemanticComponent
from repo_semantic_memory.store import SQLiteStore, build_default_extraction_metadata
from repo_semantic_memory.version import CONTEXT_PACK_VERSION, SCHEMA_VERSION, get_version_info


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
        default=None,
        help=(
            "SQLite database file path. "
            "Defaults to the RSM Index Store canonical path when --register is set, "
            "otherwise defaults to .rsm/index.sqlite in the current directory."
        ),
    )
    index_parser.add_argument(
        "--with-git",
        action="store_true",
        help="Attach optional local Git temporal metadata to indexed entities.",
    )
    index_parser.add_argument(
        "--register",
        action="store_true",
        help=(
            "Register the repository in the RSM Index Store after successful indexing. "
            "Records the repo/db mapping so --db can be omitted from rsm mcp serve."
        ),
    )
    index_parser.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "Attempt an incremental index update using local Git signals. "
            "Falls back to a full rebuild if incremental safety cannot be proven. "
            "Full rebuild is the default."
        ),
    )
    index_parser.add_argument(
        "--profile",
        action="store_true",
        help=(
            "Emit a per-phase timing summary to stderr after indexing completes. "
            "Observational only: does not change indexing behavior or output."
        ),
    )
    index_parser.add_argument(
        "--profile-report",
        metavar="PATH",
        default=None,
        help=(
            "Write a machine-readable JSON profiling report to PATH. "
            "Implies --profile. Observational only: does not change indexing behavior or output."
        ),
    )
    index_parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        dest="include",
        help=(
            "Limit indexing to files matching this glob pattern (repository-relative). "
            "May be repeated. Excludes are applied first. "
            "Example: --include 'src/**' --include 'tests/**'"
        ),
    )
    index_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        dest="exclude",
        help=(
            "Skip files matching this glob pattern (repository-relative). "
            "May be repeated. Excludes take precedence over includes. "
            "Example: --exclude 'docs/**'"
        ),
    )

    git_parser = subparsers.add_parser(
        "git",
        help="Inspect minimal local Git repository metadata.",
    )
    git_subparsers = git_parser.add_subparsers(dest="git_target")
    git_summary_parser = git_subparsers.add_parser(
        "summary",
        help="Show minimal Git repository summary for a path.",
    )
    git_summary_parser.add_argument("path", help="Path to inspect.")
    git_summary_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit summary as JSON.",
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
    repo_map_parser.add_argument(
        "--profile",
        choices=available_profile_names(),
        default="agent_standard",
        help="Compression profile controlling deterministic context noise filtering.",
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
    pack_parser.add_argument(
        "--explain-ranking",
        action="store_true",
        help="Include deterministic ranking breakdown details in pack output.",
    )
    pack_parser.add_argument(
        "--profile",
        choices=available_profile_names(),
        default="agent_standard",
        help="Compression profile controlling deterministic context noise filtering.",
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
        help="Export claims/invariants to JSON-style YAML 1.2-compatible output.",
    )
    invariants_export_parser.add_argument(
        "--db",
        default=None,
        help=(
            "SQLite database file path checked for index availability/schema compatibility only; "
            "claim/invariant data currently lives in standalone YAML files. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
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
        default=None,
        help=(
            "SQLite database file path checked for index availability/schema compatibility only; "
            "claim/invariant data currently lives in standalone YAML files. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
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
    export_jsonl_parser = subparsers.add_parser(
        "export-jsonl",
        help="Export indexed entities/relations as JSONL for machine interop.",
    )
    export_jsonl_parser.add_argument(
        "--db",
        default=None,
        help=(
            "SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted for the current directory."
        ),
    )
    export_jsonl_parser.add_argument(
        "--out",
        default=".rsm/export",
        help="Output directory for JSONL export files.",
    )
    import_jsonl_parser = subparsers.add_parser(
        "import-jsonl",
        help="Import JSONL export files into SQLite.",
    )
    import_jsonl_parser.add_argument(
        "--in",
        dest="input_dir",
        required=True,
        help="Input directory containing JSONL export files.",
    )
    import_jsonl_parser.add_argument(
        "--db",
        required=True,
        help="SQLite database file path to create or update.",
    )

    mcp_parser = subparsers.add_parser(
        "mcp",
        help="Local MCP runtime commands (read-only, stdio).",
    )
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_target")
    mcp_serve_parser = mcp_subparsers.add_parser(
        "serve",
        help=(
            "Run the read-only local stdio MCP-compatible JSON-RPC prototype. "
            "Use --repo for a single repository or --store for all registered repositories. "
            "Does not auto-index or mutate state; external MCP client conformance not yet "
            "validated."
        ),
    )
    mcp_serve_mode = mcp_serve_parser.add_mutually_exclusive_group(required=True)
    mcp_serve_mode.add_argument(
        "--repo",
        default=None,
        help=("Absolute path to the target repository root. Mutually exclusive with --store."),
    )
    mcp_serve_mode.add_argument(
        "--store",
        action="store_true",
        default=False,
        help=(
            "Serve all repositories registered in the RSM Index Store. "
            "No repository is pre-selected; the agent calls rsm_list_indexes then "
            "rsm_select_index before using repository-specific tools. "
            "Mutually exclusive with --repo."
        ),
    )
    mcp_serve_parser.add_argument(
        "--db",
        default=None,
        help=(
            "Path to an existing SQLite index database (only valid with --repo). "
            "When omitted with --repo, the RSM Index Store registry is consulted. "
            "Build an index first with: rsm index <repo> [--register] or "
            "rsm store register <repo> --index"
        ),
    )

    store_parser = subparsers.add_parser(
        "store",
        help="Manage the central local RSM Index Store.",
    )
    store_subparsers = store_parser.add_subparsers(dest="store_target")
    store_subparsers.add_parser(
        "path",
        help="Print the RSM Index Store home directory.",
    )
    store_list_parser = store_subparsers.add_parser(
        "list",
        help="List all repositories registered in the RSM Index Store.",
    )
    store_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit entries as JSON.",
    )
    store_register_parser = store_subparsers.add_parser(
        "register",
        help="Register a repository in the RSM Index Store.",
    )
    store_register_parser.add_argument("repo", help="Repository root path to register.")
    store_register_parser.add_argument(
        "--index",
        action="store_true",
        help=(
            "Also run rsm index on the repository and write the index to the store's "
            "canonical DB path. Does not modify the target repository."
        ),
    )
    store_unregister_parser = store_subparsers.add_parser(
        "unregister",
        help="Remove a repository from the RSM Index Store registry.",
    )
    store_unregister_parser.add_argument("repo", help="Repository root path to unregister.")
    store_db_parser = store_subparsers.add_parser(
        "db",
        help="Print the registered index DB path for a repository.",
    )
    store_db_parser.add_argument("repo", help="Repository root path.")

    store_status_parser = store_subparsers.add_parser(
        "status",
        help="Report the staleness status of a repository's index.",
    )
    store_status_parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Repository root path (default: current directory).",
    )
    store_status_parser.add_argument(
        "--db",
        default=None,
        help=(
            "Explicit SQLite database file path. "
            "When omitted, the RSM Index Store registry is consulted."
        ),
    )
    store_status_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit status as JSON.",
    )

    return parser


def _format_version_output() -> str:
    info = get_version_info()
    return (
        f"package_version: {info.package_version}\n"
        f"schema_version: {info.schema_version}\n"
        f"context_pack_version: {info.context_pack_version}"
    )


def _build_index_plan_parser() -> argparse.ArgumentParser:
    """Create the parser for the ``rsm index plan`` advisory subcommand."""
    parser = argparse.ArgumentParser(
        prog=f"{DEFAULT_CONFIG.cli_name} index plan",
        description=(
            "Advisory scope planner. Inspect a repository cheaply and recommend "
            "a safe indexing scope. Does not create or modify an index."
        ),
    )
    parser.add_argument("path", help="Repository root path to inspect.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the scope plan as deterministic JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if raw_argv[:2] == ["index", "plan"]:
        plan_args = _build_index_plan_parser().parse_args(raw_argv[2:])
        return _run_index_plan_command(path=plan_args.path, emit_json=plan_args.json)

    parser = build_parser()
    args = parser.parse_args(raw_argv)

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
        if args.db is None:
            if args.register:
                from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

                repo_root = Path(args.path).resolve()
                resolved_db = str(IndexRegistry(resolve_store_home()).default_db_path(repo_root))
            else:
                resolved_db = ".rsm/index.sqlite"
        else:
            resolved_db = args.db
        return _run_index_command(
            path=args.path,
            db=resolved_db,
            with_git=args.with_git,
            register=args.register,
            incremental=args.incremental,
            profile=args.profile or bool(args.profile_report),
            profile_report=args.profile_report,
            includes=args.include or [],
            excludes=args.exclude or [],
        )
    if args.command == "git":
        if args.git_target == "summary":
            return _run_git_summary_command(path=args.path, emit_json=args.json)
        parser.print_help()
        return 2
    if args.command == "inspect":
        if args.inspect_target == "entities":
            return _run_inspect_entities_command(
                db=_resolve_reader_db(args.db), emit_json=args.json
            )
        if args.inspect_target == "relations":
            return _run_inspect_relations_command(
                db=_resolve_reader_db(args.db), emit_json=args.json
            )
        parser.print_help()
        return 2
    if args.command == "repo-map":
        return _run_repo_map_command(
            path=args.path,
            db=args.db,
            budget=args.budget,
            profile=args.profile,
        )
    if args.command == "pack":
        return _run_pack_command(
            task=args.task,
            db=_resolve_reader_db(args.db),
            budget=args.budget,
            output_format=args.format,
            explain_ranking=args.explain_ranking,
            profile=args.profile,
        )
    if args.command == "components":
        if args.components_target == "infer":
            return _run_components_infer_command(
                db=_resolve_reader_db(args.db), emit_json=args.json
            )
        if args.components_target == "list":
            return _run_components_list_command(db=_resolve_reader_db(args.db), emit_json=args.json)
        parser.print_help()
        return 2
    if args.command == "invariants":
        if args.invariants_target == "export":
            return _run_invariants_export_command(db=_resolve_reader_db(args.db), out=args.out)
        if args.invariants_target == "import":
            return _run_invariants_import_command(db=_resolve_reader_db(args.db), path=args.path)
        parser.print_help()
        return 2
    if args.command == "eval":
        if args.eval_target == "retrieval":
            return _run_eval_retrieval_command(
                db=_resolve_reader_db(args.db),
                dataset=args.dataset,
                emit_json=args.json,
                markdown_report=args.markdown_report,
            )
        if args.eval_target == "compare":
            return _run_eval_compare_command(
                db=_resolve_reader_db(args.db),
                dataset=args.dataset,
                budget=args.budget,
                emit_json=args.json,
                markdown_report=args.markdown_report,
            )
        parser.print_help()
        return 2
    if args.command == "export-ai":
        return _run_export_ai_command(
            db=_resolve_reader_db(args.db), out=args.out, force=args.force
        )
    if args.command == "export-jsonl":
        return _run_export_jsonl_command(db=_resolve_reader_db(args.db), out=args.out)
    if args.command == "import-jsonl":
        return _run_import_jsonl_command(input_dir=args.input_dir, db=args.db)
    if args.command == "mcp":
        if args.mcp_target == "serve":
            if getattr(args, "store", False):
                from repo_semantic_memory.mcp.server import run_serve_store

                return run_serve_store()
            from repo_semantic_memory.mcp.server import run_serve

            return run_serve(repo=args.repo, db=args.db)
        parser.print_help()
        return 2
    if args.command == "store":
        if args.store_target == "path":
            return _run_store_path_command()
        if args.store_target == "list":
            return _run_store_list_command(emit_json=args.json)
        if args.store_target == "register":
            return _run_store_register_command(repo=args.repo, do_index=args.index)
        if args.store_target == "unregister":
            return _run_store_unregister_command(repo=args.repo)
        if args.store_target == "db":
            return _run_store_db_command(repo=args.repo)
        if args.store_target == "status":
            return _run_store_status_command(
                repo=args.repo,
                db=args.db,
                emit_json=args.json,
            )
        parser.print_help()
        return 2

    parser.print_help()
    return 0


def _resolve_reader_db(db: str | None) -> str:
    """Resolve the SQLite DB path for read-only commands.

    Delegates to :func:`~repo_semantic_memory.store_home.resolve_reader_db`
    and returns the result as a string for CLI compatibility.
    """
    from repo_semantic_memory.store_home import resolve_reader_db

    return str(resolve_reader_db(db).path)


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


def _run_index_plan_command(*, path: str, emit_json: bool) -> int:
    """Run the advisory ``rsm index plan`` command.

    Inspects the repository cheaply and prints a recommended scope.  Never
    creates or modifies an index.
    """
    from repo_semantic_memory.indexing.scope_planner import (
        format_scope_plan,
        plan_index_scope,
    )

    try:
        plan = plan_index_scope(path)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if emit_json:
        print(json.dumps(plan.to_json_dict(), indent=2, sort_keys=False))
        return 0
    print(format_scope_plan(plan))
    return 0


def _run_index_command(
    *,
    path: str,
    db: str,
    with_git: bool,
    register: bool = False,
    incremental: bool = False,
    profile: bool = False,
    profile_report: str | None = None,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
) -> int:
    repository_root = Path(path).resolve()
    db_path = Path(db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if incremental:
        if with_git:
            print(
                "info: incremental index fallback: --with-git is not supported"
                " with incremental; running full rebuild",
                file=sys.stderr,
            )
        elif db_path.exists():
            result = _attempt_incremental_index(
                repository_root, db_path, with_git=with_git, includes=includes, excludes=excludes
            )
            if result is not None:
                if register:
                    _do_register(repository_root, db_path)
                mode_suffix = " mode=incremental"
                print(
                    f"entities={result.entity_count} relations={result.relation_count}{mode_suffix}"
                )
                return 0
            # result is None: planner or executor rejected incremental; fall through to full
            # rebuild.
        else:
            _reason = IncrementalFallbackReason.INDEX_MISSING
            print(
                f"info: incremental index fallback: {_reason}; running full rebuild",
                file=sys.stderr,
            )
    profiler: _AnyProfiler = IndexProfiler() if profile else _NullProfiler()
    # Build a ScopeFilter only when at least one pattern is present. Empty
    # lists are falsy, so ``includes or excludes`` is False when both are
    # empty/None — preserving the zero-overhead passthrough path.
    scope_filter: ScopeFilter | None = (
        ScopeFilter(includes or [], excludes or []) if includes or excludes else None
    )

    _index_start = time.monotonic()
    _started_at = datetime.now(tz=UTC).isoformat()
    print("indexing: scanning files...", file=sys.stderr)
    with profiler.phase("file_discovery") as _ph_discovery:
        filesystem_entities = extract_filesystem_entities(
            repository_root, scope_filter=scope_filter
        )

    # Compute per-type counts for the scan summary and progress callbacks.
    python_count = sum(1 for e in filesystem_entities if e.kind == "module")
    md_count = sum(
        1
        for e in filesystem_entities
        if e.kind == "doc" and e.qualified_name.endswith((".md", ".markdown"))
    )
    init_count = sum(
        1 for e in filesystem_entities if e.kind == "module" and e.name == "__init__.py"
    )
    other_count = len(filesystem_entities) - python_count - md_count
    _ph_discovery.files_processed = len(filesystem_entities)
    _ph_discovery.entities_created = len(filesystem_entities)
    print(
        f"indexing: discovered files: python={python_count} markdown={md_count}"
        f" other={other_count} total={len(filesystem_entities)}",
        file=sys.stderr,
    )

    filesystem_entities = _drop_python_module_file_entities(filesystem_entities)

    print("indexing: extracting Markdown...", file=sys.stderr)
    _t = time.monotonic()
    with profiler.phase("markdown_extraction") as _ph_md:
        markdown_outline = extract_markdown_outline_path(
            repository_root,
            progress=_make_progress_callback("Markdown"),
            scope_filter=scope_filter,
        )
    _ph_md.files_processed = md_count
    _ph_md.entities_created = len(markdown_outline.entities)
    _ph_md.relations_created = len(markdown_outline.relations)
    print(
        f"indexing: Markdown complete: {md_count}/{md_count} files,"
        f" elapsed={time.monotonic() - _t:.1f}s",
        file=sys.stderr,
    )

    print("indexing: parsing Python...", file=sys.stderr)
    _t = time.monotonic()
    with profiler.phase("python_ast") as _ph_py:
        python_entities, python_relations = index_python_path(
            repository_root,
            progress=_make_progress_callback("Python"),
            scope_filter=scope_filter,
        )
    _ph_py.files_processed = python_count
    _ph_py.entities_created = len(python_entities)
    _ph_py.relations_created = len(python_relations)
    print(
        f"indexing: Python complete: {python_count}/{python_count} files,"
        f" elapsed={time.monotonic() - _t:.1f}s",
        file=sys.stderr,
    )

    print("indexing: extracting exports...", file=sys.stderr)
    _t = time.monotonic()
    with profiler.phase("exports_extraction") as _ph_exp:
        export_relations = index_python_exports(
            repository_root,
            progress=_make_progress_callback("exports"),
            scope_filter=scope_filter,
        )
    _ph_exp.files_processed = init_count
    _ph_exp.relations_created = len(export_relations)
    print(
        f"indexing: exports complete: {init_count}/{init_count} files,"
        f" elapsed={time.monotonic() - _t:.1f}s",
        file=sys.stderr,
    )

    all_entities = _merge_entities(
        filesystem_entities, [*markdown_outline.entities, *python_entities]
    )
    all_relations = [*markdown_outline.relations, *python_relations, *export_relations]
    print(
        f"indexing: computing test relationships"
        f" from entities={len(all_entities)} relations={len(all_relations)}...",
        file=sys.stderr,
    )
    _t = time.monotonic()
    with profiler.phase("test_relationships") as _ph_test:
        test_relations = extract_test_relationships(
            repository_root,
            all_entities,
            all_relations,
        )
    _ph_test.relations_created = len(test_relations)
    all_relations = [*all_relations, *test_relations]
    print(
        f"indexing: test relationships complete:"
        f" added={len(test_relations)} total_relations={len(all_relations)},"
        f" elapsed={time.monotonic() - _t:.1f}s",
        file=sys.stderr,
    )

    # Always fetch a lightweight git summary for staleness metadata.
    # This is a bounded local call; it does not attach per-file history.
    git_summary = get_git_repository_summary(repository_root)

    git_status = "disabled"
    if with_git:
        with profiler.phase("git_metadata") as _ph_git:
            temporal_result = attach_git_metadata_to_entities(
                all_entities,
                repository_root=repository_root,
                summary=git_summary,
            )
        all_entities = temporal_result.entities
        _ph_git.entities_created = len(all_entities)
        git_status = temporal_result.status
        if temporal_result.warning:
            print(f"git metadata: {temporal_result.warning}", file=sys.stderr)

    now_iso = datetime.now(tz=UTC).isoformat()
    metadata = build_default_extraction_metadata(
        repository_root=repository_root,
        extractor_names=(
            "filesystem",
            "git_history",
            "markdown_outline",
            "python_ast",
            "python_exports",
            "test_relationships",
        )
        if with_git
        else (
            "filesystem",
            "markdown_outline",
            "python_ast",
            "python_exports",
            "test_relationships",
        ),
        timestamp=now_iso,
    )

    # Build staleness metadata rows.  git_head / git_dirty are left empty
    # when git is unavailable so the detector can return "unknown" safely.
    extra_meta: dict[str, str] = {
        "indexed_at": now_iso,
        "entity_count": str(len(all_entities)),
        "relation_count": str(len(all_relations)),
        "schema_version": SCHEMA_VERSION,
        "context_pack_version": CONTEXT_PACK_VERSION,
        "last_index_mode": "full",
    }
    if git_summary.in_git_repo and git_summary.current_commit:
        extra_meta["git_head"] = git_summary.current_commit.strip()
        extra_meta["git_dirty"] = "true" if git_summary.is_dirty else "false"
    else:
        extra_meta["git_head"] = ""
        extra_meta["git_dirty"] = ""

    # Scope metadata — always written so consumers can distinguish full vs scoped indexes.
    if includes or excludes:
        extra_meta["index_scope"] = "scoped"
        extra_meta["include_patterns"] = json.dumps(includes or [])
        extra_meta["exclude_patterns"] = json.dumps(excludes or [])
    else:
        extra_meta["index_scope"] = "full"
        extra_meta["include_patterns"] = "[]"
        extra_meta["exclude_patterns"] = "[]"

    store = SQLiteStore(db_path)
    print("indexing: writing index...", file=sys.stderr)
    _t = time.monotonic()
    try:
        store.initialize()
        with profiler.phase("sqlite_persist") as _ph_sqlite:
            store.persist_index(entities=all_entities, relations=all_relations, metadata=metadata)
        _ph_sqlite.entities_created = len(all_entities)
        _ph_sqlite.relations_created = len(all_relations)
        with profiler.phase("metadata_write"):
            store.write_extra_metadata(extra_meta)
    finally:
        store.close()
    print(
        f"indexing: writing index complete:"
        f" entities={len(all_entities)} relations={len(all_relations)},"
        f" elapsed={time.monotonic() - _t:.1f}s",
        file=sys.stderr,
    )
    if register:
        from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

        IndexRegistry(resolve_store_home()).register(
            repository_root, db_path.resolve(), indexed=True
        )
    print(
        f"indexing: complete:"
        f" entities={len(all_entities)} relations={len(all_relations)},"
        f" elapsed={time.monotonic() - _index_start:.1f}s",
        file=sys.stderr,
    )
    if profile:
        print(profiler.format_summary(), file=sys.stderr)
    if profile_report:
        _completed_at = datetime.now(tz=UTC).isoformat()
        report_path = Path(profile_report)
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report = profiler.to_json_report(
                repo_root=str(repository_root),
                started_at=_started_at,
                completed_at=_completed_at,
            )
            report_path.write_text(json.dumps(report, indent=2))
        except OSError as exc:
            print(
                f"error: could not write profile report to {profile_report!r}: {exc}",
                file=sys.stderr,
            )
            return 1
    if with_git:
        print(
            f"entities={len(all_entities)} relations={len(all_relations)} git_metadata={git_status}"
        )
        return 0
    print(f"entities={len(all_entities)} relations={len(all_relations)}")
    return 0


def _do_register(repository_root: Path, db_path: Path) -> None:
    """Register *repository_root* / *db_path* in the RSM Index Store."""
    from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

    IndexRegistry(resolve_store_home()).register(repository_root, db_path.resolve(), indexed=True)


# ---------------------------------------------------------------------------
# Indexing progress helpers
# ---------------------------------------------------------------------------

# Default interval and minimum total for per-file progress emission.
_PROGRESS_INTERVAL = 100
_PROGRESS_MIN_TOTAL = 100

# Backward-compatible alias used by tests that import the old name.
_PYTHON_PROGRESS_INTERVAL = _PROGRESS_INTERVAL


def should_emit_progress(
    done: int,
    total: int,
    *,
    interval: int = _PROGRESS_INTERVAL,
    min_total: int = _PROGRESS_MIN_TOTAL,
) -> bool:
    """Return whether a per-file progress line should be emitted.

    Returns ``False`` when *total* is below *min_total* so that small
    repositories stay quiet.  Otherwise returns ``True`` on the first file,
    every *interval*-th file, and on the last file.
    """
    if total < min_total:
        return False
    return done == 1 or done % interval == 0 or done == total


def _make_progress_callback(phase: str) -> Callable[[int, int], None]:
    """Return a progress callback for an extraction phase.

    Emits ``indexing: <phase> N/M files...`` on the first file and every
    :data:`_PROGRESS_INTERVAL` files.  The completion line is printed by the
    caller so this callback suppresses the ``done == total`` case to avoid
    duplication.  Entirely silent when total < :data:`_PROGRESS_MIN_TOTAL`.
    """

    def _callback(done: int, total: int) -> None:
        if should_emit_progress(done, total) and done != total:
            print(f"indexing: {phase} {done}/{total} files...", file=sys.stderr)

    return _callback


def _make_python_progress_callback() -> Callable[[int, int], None]:
    """Backward-compatible wrapper around :func:`_make_progress_callback`.

    Kept for callers that import this name directly.
    """
    return _make_progress_callback("Python")


def _scope_matches_metadata(
    meta: dict[str, str],
    includes: list[str] | None,
    excludes: list[str] | None,
) -> bool:
    """Return ``True`` when the stored scope matches the requested scope.

    A stored scope of ``None`` (old index built before 57.5) is treated as
    ``"full"`` so that legacy indexes remain compatible with full incremental
    runs.
    """
    stored_scope = meta.get("index_scope") or "full"
    req_includes = sorted(includes or [])
    req_excludes = sorted(excludes or [])
    requested_scope = "scoped" if (req_includes or req_excludes) else "full"

    if stored_scope != requested_scope:
        return False

    if requested_scope == "scoped":
        try:
            stored_includes = sorted(json.loads(meta.get("include_patterns", "[]")))
            stored_excludes = sorted(json.loads(meta.get("exclude_patterns", "[]")))
        except (json.JSONDecodeError, TypeError):
            return False  # malformed stored patterns → treat as mismatch

        return stored_includes == req_includes and stored_excludes == req_excludes

    return True  # both "full"


def _attempt_incremental_index(
    repo_root: Path,
    db_path: Path,
    *,
    with_git: bool,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
) -> IncrementalResult | None:
    """Try an incremental index update.

    Returns an :class:`~repo_semantic_memory.indexing.executor.IncrementalResult`
    on success, or ``None`` when the planner rejects or the executor raises
    (in both cases a fallback message is printed to stderr).

    When the requested scope (``includes``/``excludes``) differs from the scope
    stored in the existing index metadata, the function falls back immediately
    with reason :attr:`~repo_semantic_memory.indexing.incremental
    .IncrementalFallbackReason.SCOPE_MISMATCH`.
    """
    from repo_semantic_memory.indexing import plan_incremental_update
    from repo_semantic_memory.indexing.executor import run_incremental_index

    # Read existing metadata to feed the planner.
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        meta = store.get_metadata()
    finally:
        store.close()

    # Scope mismatch check — must precede Git planning so that a full rebuild
    # rewrites scope metadata correctly rather than proceeding with a stale scope.
    if not _scope_matches_metadata(meta, includes, excludes):
        print(
            f"info: incremental index fallback: {IncrementalFallbackReason.SCOPE_MISMATCH};"
            " running full rebuild",
            file=sys.stderr,
        )
        return None

    indexed_head = meta.get("git_head") or None
    plan = plan_incremental_update(
        repo_root,
        indexed_head,
        indexed_git_dirty=meta.get("git_dirty"),
        indexed_schema_version=meta.get("schema_version"),
        indexed_context_pack_version=meta.get("context_pack_version"),
    )

    if not plan.can_incremental:
        print(
            f"info: incremental index fallback: {plan.fallback_reason}; running full rebuild",
            file=sys.stderr,
        )
        return None

    try:
        return run_incremental_index(repo_root, db_path, plan, with_git=with_git)
    except Exception as exc:  # noqa: BLE001
        import traceback

        print(
            f"info: incremental index fallback:"
            f" {IncrementalFallbackReason.INTERNAL_ERROR} ({exc}); running full rebuild",
            file=sys.stderr,
        )
        traceback.print_exc(file=sys.stderr)
        return None


def _run_git_summary_command(*, path: str, emit_json: bool) -> int:
    summary = get_git_repository_summary(path)
    if emit_json:
        print(json.dumps(summary.to_dict(), separators=(",", ":")))
        return 0
    if not summary.in_git_repo:
        print(
            "Path is not inside a Git repository. "
            f"path={summary.path} reason={summary.unavailable_reason or 'unknown'}"
        )
        return 0
    print(f"repository_root: {summary.repository_root}")
    print(f"current_commit: {summary.current_commit}")
    print(f"dirty: {summary.is_dirty}")
    print(f"tracked_files: {summary.tracked_file_count}")
    if summary.unavailable_reason:
        print(f"note: {summary.unavailable_reason}")
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


def _run_repo_map_command(*, path: str | None, db: str | None, budget: int, profile: str) -> int:
    if path is not None:
        entities, relations = _index_for_repo_map(path=path)
        print(build_repo_map_markdown(entities, relations, budget_chars=budget, profile=profile))
        return 0

    db_path = _resolve_reader_db(db)
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        entities = store.list_entities()
        relations = store.list_relations()
        metadata = store.get_metadata()
    finally:
        store.close()

    _warn_if_stale(db=db_path, metadata=metadata)
    print(build_repo_map_markdown(entities, relations, budget_chars=budget, profile=profile))
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


def _run_pack_command(
    *,
    task: str,
    db: str,
    budget: int,
    output_format: str,
    explain_ranking: bool,
    profile: str,
) -> int:
    store = SQLiteStore(db)
    try:
        store.initialize()
        entities = store.list_entities()
        relations = store.list_relations()
        metadata = store.get_metadata()
    finally:
        store.close()

    _warn_if_stale(db=db, metadata=metadata)

    resolved_profile = resolve_profile(profile)
    include_ranking = explain_ranking or resolved_profile.include_ranking_breakdown
    context_pack = build_context_pack(
        task=task,
        entities=entities,
        relations=relations,
        budget_chars=budget,
        explain_ranking=include_ranking,
        profile=resolved_profile,
    )
    if output_format == "yaml":
        print(context_pack.to_yaml(include_ranking=include_ranking))
        return 0
    print(render_context_pack_markdown(context_pack, explain_ranking=include_ranking))
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


def _run_export_jsonl_command(*, db: str, out: str) -> int:
    db_path = Path(db)
    output_dir = Path(out)
    entities, relations = _load_index_from_db(db)
    store = SQLiteStore(db_path)
    try:
        store.initialize()
        metadata = store.get_metadata()
    finally:
        store.close()
    result = export_jsonl_directory(
        output_dir=output_dir,
        entities=entities,
        relations=relations,
        metadata=metadata,
    )
    print(
        f"exported jsonl to {output_dir} "
        f"entities={result.entity_count} relations={result.relation_count} "
        f"components={result.component_count} files_written={len(result.files_written)}"
    )
    return 0


def _run_import_jsonl_command(*, input_dir: str, db: str) -> int:
    try:
        result = import_jsonl_directory(input_dir=input_dir, db_path=db)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        f"imported jsonl from {result.input_dir} "
        f"entities={result.entity_count} relations={result.relation_count} db={result.db_path}"
    )
    if result.components_snapshot_ignored:
        print(
            "ignored components.jsonl: semantic components are derived snapshots and "
            "component import is not supported in the current schema",
            file=sys.stderr,
        )
    return 0


def _index_for_repo_map(*, path: str) -> tuple[list[Entity], list[Relation]]:
    repository_root = Path(path).resolve()
    filesystem_entities = extract_filesystem_entities(repository_root)
    filesystem_entities = _drop_python_module_file_entities(filesystem_entities)
    markdown_outline = extract_markdown_outline_path(repository_root)
    python_entities, python_relations = index_python_path(repository_root)
    all_entities = _merge_entities(
        filesystem_entities, [*markdown_outline.entities, *python_entities]
    )
    return all_entities, [*markdown_outline.relations, *python_relations]


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


# ---------------------------------------------------------------------------
# RSM Index Store commands
# ---------------------------------------------------------------------------


def _run_store_path_command() -> int:
    from repo_semantic_memory.store_home import resolve_store_home

    print(resolve_store_home())
    return 0


def _run_store_list_command(*, emit_json: bool) -> int:
    from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

    store_home = resolve_store_home()
    registry = IndexRegistry(store_home)
    entries = registry.list_entries()

    if emit_json:
        payload = {
            key: {
                "db": entry.db_relative,
                "registered_at": entry.registered_at,
                "last_indexed_at": entry.last_indexed_at,
                "db_exists": (
                    store_home / entry.db_relative
                    if not Path(entry.db_relative).is_absolute()
                    else Path(entry.db_relative)
                ).exists(),
            }
            for key, entry in entries.items()
        }
        print(json.dumps(payload, separators=(",", ":")))
        return 0

    if not entries:
        print("No repositories registered in the RSM Index Store.")
        print(f"Store home: {store_home}")
        return 0

    rows: list[tuple[str, str, str, str]] = [("REPO", "DB (relative)", "EXISTS", "LAST INDEXED")]
    for repo_key, entry in entries.items():
        db_abs = (
            Path(entry.db_relative)
            if Path(entry.db_relative).is_absolute()
            else store_home / entry.db_relative
        )
        exists = "yes" if db_abs.exists() else "no"
        last_indexed = entry.last_indexed_at[:10] if entry.last_indexed_at else "never"
        rows.append((repo_key, entry.db_relative, exists, last_indexed))

    columns = zip(*rows, strict=True)
    widths = [max(len(v) for v in col) for col in columns]
    print("\n".join("  ".join(v.ljust(widths[i]) for i, v in enumerate(row)) for row in rows))
    return 0


def _run_store_register_command(*, repo: str, do_index: bool) -> int:
    from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

    repo_root = Path(repo).expanduser().resolve()
    if not repo_root.exists():
        print(f"error: repository path does not exist: {repo_root}", file=sys.stderr)
        return 2
    if not repo_root.is_dir():
        print(f"error: repository path is not a directory: {repo_root}", file=sys.stderr)
        return 2

    store_home = resolve_store_home()
    registry = IndexRegistry(store_home)
    db_path = registry.default_db_path(repo_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if do_index:
        exit_code = _run_index_command(
            path=str(repo_root), db=str(db_path), with_git=False, register=False
        )
        if exit_code != 0:
            return exit_code
        registry.register(repo_root, db_path, indexed=True)
    else:
        registry.register(repo_root, db_path, indexed=False)

    print(f"Registered: {repo_root}")
    print(f"Index DB:   {db_path}")
    if not do_index and not db_path.exists():
        print(f"Note: index not yet built. Run: rsm store register {repo_root} --index")
    return 0


def _run_store_unregister_command(*, repo: str) -> int:
    from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

    repo_root = Path(repo).expanduser().resolve()
    registry = IndexRegistry(resolve_store_home())
    removed = registry.unregister(repo_root)
    if not removed:
        print(f"error: no entry found for {repo_root}", file=sys.stderr)
        return 2
    print(f"Unregistered: {repo_root}")
    return 0


def _run_store_db_command(*, repo: str) -> int:
    from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

    repo_root = Path(repo).expanduser().resolve()
    registry = IndexRegistry(resolve_store_home())
    db_path = registry.lookup(repo_root)
    if db_path is None:
        print(f"error: no entry found for {repo_root}", file=sys.stderr)
        return 2
    print(db_path)
    return 0


def _warn_if_stale(*, db: str, metadata: dict[str, str]) -> None:
    """Print a single-line stderr warning when the index is stale or maybe_stale.

    Never raises; errors are silently suppressed so the main command always
    continues.  This is the minimal behavioral nudge described in §7 of
    ``docs/design/index_staleness.md``.
    """
    from repo_semantic_memory.index_status import IndexStatus, detect_stale_from_metadata

    try:
        repo_root_str = metadata.get("repository_root")
        if not repo_root_str:
            return
        report = detect_stale_from_metadata(
            repo_root=Path(repo_root_str),
            db_path=Path(db),
            index_mode="explicit_db",
            metadata=metadata,
        )
        if report.index_status in (IndexStatus.STALE, IndexStatus.MAYBE_STALE):
            action = f" Suggested: {report.suggested_action}" if report.suggested_action else ""
            print(
                f"warning: index is {report.index_status.value} "
                f"({report.index_status_reason}).{action}",
                file=sys.stderr,
            )
    except Exception:  # noqa: BLE001 — warnings must never block the main command
        pass


def _run_store_status_command(*, repo: str, db: str | None, emit_json: bool) -> int:
    """Implement ``rsm store status [REPO] [--db PATH] [--json]``."""
    from typing import Literal

    from repo_semantic_memory.index_status import detect_index_status

    repo_root = Path(repo).expanduser().resolve()
    if not repo_root.exists():
        print(f"error: repository path does not exist: {repo_root}", file=sys.stderr)
        return 2
    if not repo_root.is_dir():
        print(f"error: repository path is not a directory: {repo_root}", file=sys.stderr)
        return 2

    # Determine index mode and DB path.
    index_mode: Literal["explicit_db", "store"]
    resolved_db: Path | None
    if db is not None:
        index_mode = "explicit_db"
        resolved_db = Path(db).expanduser()
    else:
        from repo_semantic_memory.store_home import IndexRegistry, resolve_store_home

        index_mode = "store"
        resolved_db = IndexRegistry(resolve_store_home()).lookup(repo_root)

    report = detect_index_status(
        repo_root=repo_root,
        db_path=resolved_db,
        index_mode=index_mode,
    )

    if emit_json:
        payload: dict[str, object] = {
            "repo": str(report.repo_root),
            "db": str(report.db_path) if report.db_path else None,
            "index_mode": report.index_mode,
            "index_status": report.index_status.value,
            "index_status_reason": report.index_status_reason,
            "indexed_at": report.indexed_at,
            "indexed_git_head": report.indexed_git_head,
            "current_git_head": report.current_git_head,
            "working_tree_dirty": report.working_tree_dirty,
            "schema_version": report.schema_version,
            "context_pack_version": report.context_pack_version,
            "suggested_action": report.suggested_action,
            "index_scope": report.index_scope,
            "include_patterns": list(report.include_patterns),
            "exclude_patterns": list(report.exclude_patterns),
        }
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return 0

    # Human output
    db_display = str(report.db_path) if report.db_path else "<none>"
    print(f"Repo:   {report.repo_root}")
    print(f"Index:  {db_display}")
    print(f"Mode:   {report.index_mode}")
    print(f"Status: {report.index_status.value}")
    if report.index_scope:
        print(f"Scope:  {report.index_scope}")
        if report.index_scope == "scoped":
            if report.include_patterns:
                print("Includes:")
                for pat in report.include_patterns:
                    print(f"  - {pat}")
            if report.exclude_patterns:
                print("Excludes:")
                for pat in report.exclude_patterns:
                    print(f"  - {pat}")
    if report.indexed_at:
        print(f"Indexed at: {report.indexed_at}")
    if report.indexed_git_head:
        print(f"Indexed HEAD:  {report.indexed_git_head}")
    if report.current_git_head:
        print(f"Current HEAD:  {report.current_git_head}")
    if report.working_tree_dirty is not None:
        print(f"Working tree dirty: {'yes' if report.working_tree_dirty else 'no'}")
    if report.schema_version:
        print(f"Schema version: {report.schema_version}")
    if report.context_pack_version:
        print(f"Context pack version: {report.context_pack_version}")
    if report.suggested_action:
        print(f"Suggested action: {report.suggested_action}")
    return 0
