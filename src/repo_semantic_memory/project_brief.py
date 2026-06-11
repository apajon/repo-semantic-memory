"""Project brief generator for RSM.

Produces a compact, deterministic Markdown summary of an indexed repository
suitable for coding agents to read before using MCP tools.

The generator is pure local computation: no LLM, no network, no new extractors.
It reads existing SQLite index metadata, entities, and freshness status.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from repo_semantic_memory.context.path_roles import (
    PathRole,
    classify_path_role,
)
from repo_semantic_memory.index_status import (
    IndexStatus,
    detect_index_status,
)
from repo_semantic_memory.store import SQLiteStore
from repo_semantic_memory.version import get_version_info

if TYPE_CHECKING:
    from repo_semantic_memory.model import Entity

_SECTION_SEPARATOR = "\n\n"

# ── character budget ───────────────────────────────────────────────────────
DEFAULT_MAX_CHARS = 15000
_MIN_CHARS_PER_SECTION = 50

# ── static workflow instructions ────────────────────────────────────────────

_REPO_MODE_WORKFLOW = """\
1. `rsm_search("<query>")` — broad discovery across files, symbols, docs, tests
2. `rsm_find_related(source_path="...")` — find tests, imports, exports for a file
3. `rsm_prepare_context(task="...")` — build a task-centered ContextPack
4. `rsm_get_context_page(result_set_id, stream="...")` — page over large packs"""

_STORE_MODE_WORKFLOW = """\
1. `rsm_store_list_indexes` — list all registered repositories
2. `rsm_store_select_index(repo_id="...")` — select this repo as active
3. `rsm_store_current_index` — confirm the active index
4. `rsm_search("<query>")` — broad discovery
5. `rsm_find_related(source_path="...")` — find related code/tests
6. `rsm_prepare_context(task="...")` — build task-centered ContextPack
7. `rsm_get_context_page(result_set_id, stream="...")` — page over large packs"""

# ── doc path detection (broader than classify_path_role) ────────────────────

# Prefixes and patterns that indicate documentation, review, planning, or RFC files.
_BROAD_DOC_PREFIXES = (
    "docs/",
    "doc/",
    "docs_src/",
    "tutorials/",
    "tutorial/",
)
_RFC_DIR_PATTERNS = ("/rfcs/", "/rfc/")
_RFC_FILE_PREFIXES = ("rfcs/", "rfc/")
_ROOT_DOC_NAMES = frozenset(
    {
        "README.md",
        "README.rst",
        "CHANGELOG.md",
        "CHANGELOG.rst",
        "CONTRIBUTING.md",
        "CONTRIBUTING.rst",
        "ARCHITECTURE.md",
        "ARCHITECTURE.rst",
        "LICENSE",
        "LICENSE.md",
        "LICENSE.rst",
        "SECURITY.md",
        "SUPPORT.md",
        "CODE_OF_CONDUCT.md",
    }
)
_DOC_EXTENSIONS = (".rst", ".md")
_MAX_DOC_ENTRIES = 12

# Priority groups for doc ordering (lower = higher priority).
_DOC_PRIORITY: dict[str, int] = {
    "docs/reviews": 0,
    "docs/design": 1,
    "docs/planning": 2,
    "docs/concepts": 2,
    "docs/usage": 2,
    "docs/design_notes": 1,
    "docs/api": 2,
}
# Special priority for RFCs (anywhere in path)
_RFC_PRIORITY = 1


def _is_doc_path(path: str) -> bool:
    """Return True if *path* is likely a documentation, review, planning, or RFC file.

    Broader than :func:`classify_path_role` — captures project-specific doc
    directories (e.g. ``lifecore_state/``), RFC directories, root-level
    ``README.md``, and ``.rst``/``.md`` files outside source/test trees.
    """
    normalized = path.strip("/")

    # Standard doc prefixes
    if normalized.startswith(_BROAD_DOC_PREFIXES):
        return True

    # RFC directories (any level)
    for pattern in _RFC_DIR_PATTERNS:
        if pattern in f"/{normalized}/":
            return True
    if normalized.startswith(_RFC_FILE_PREFIXES):
        return True

    # Root-level doc files
    if "/" not in normalized and normalized in _ROOT_DOC_NAMES:
        return True

    # .md and .rst files that are NOT in source or test directories
    if normalized.endswith(_DOC_EXTENSIONS):
        # Skip source/test dirs (handled by classify_path_role)
        if normalized.startswith(("src/", "tests/", "test/", "lib/", "packages/")):
            return False
        # Skip CI configs
        if normalized.startswith((".github/", ".gitlab/", "ci/")):
            return False
        # Skip generated/build
        if any(s in normalized for s in ("_build/", "__pycache__/", ".egg-info/", "/dist/")):
            return False
        return True

    return False


def _doc_priority(path: str) -> int:
    """Return a deterministic sort priority for a doc path (lower = higher)."""
    # Check prefix-based priority groups
    for prefix, prio in _DOC_PRIORITY.items():
        if path.startswith(prefix):
            return prio

    # Check for /rfcs/ or /rfc/ anywhere in path (e.g., lifecore_state/rfcs/...)
    for pattern in _RFC_DIR_PATTERNS:
        if pattern in f"/{path}/":
            return _RFC_PRIORITY

    # Root-level .md/.rst is high priority
    if "/" not in path and path.endswith(_DOC_EXTENSIONS):
        return 0

    # Other docs/ prefixed files
    if path.startswith("docs/"):
        return 3

    # Other project-specific doc files (e.g., lifecore_state/)
    if path.endswith(_DOC_EXTENSIONS):
        return 4

    return 10


def _sort_doc_paths(paths: set[str]) -> list[str]:
    """Sort doc paths deterministically: priority group first, then path."""
    return sorted(paths, key=lambda p: (_doc_priority(p), p))


# ── helpers ─────────────────────────────────────────────────────────────────


def _entity_source_path(entity: Entity) -> str:
    """Extract the source path from an entity, defaulting to ""."""
    if entity.source_range is not None:
        return entity.source_range.path
    return ""


def _count_entities_by_path_role(entities: list[Entity]) -> dict[PathRole, int]:
    """Count entities grouped by their path role."""
    counts: dict[PathRole, int] = {}
    for ent in entities:
        path = _entity_source_path(ent)
        role = classify_path_role(path=path, source_roots=())
        counts[role] = counts.get(role, 0) + 1
    return counts


def _group_module_entities(
    entities: list[Entity], max_per_group: int = 8
) -> dict[str, list[Entity]]:
    """Group module-level entities by their parent directory.

    Returns a dict mapping directory path → list of module/class-level entities,
    limited to *max_per_group* entries per directory.
    """
    groups: dict[str, list[Entity]] = {}

    for ent in entities:
        path = _entity_source_path(ent)
        role = classify_path_role(path=path, source_roots=())
        # Only include source-code entities, not docs/tests/generated
        if role not in ("source", "artifact"):
            continue
        # Skip non-modular entities (file-level docs, etc.)
        if ent.kind in ("file",):
            continue
        # Use parent directory as grouping key
        parent = Path(path).parent.as_posix() if "/" in path else "."
        if parent not in groups:
            groups[parent] = []
        if len(groups[parent]) < max_per_group:
            groups[parent].append(ent)

    return groups


def _build_readiness_section(
    index_status: IndexStatus,
    index_status_reason: str,
    indexed_at: str | None,
    current_git_head: str | None,
    working_tree_dirty: bool | None,
    schema_version: str | None,
) -> str:
    """Build the Readiness / Freshness section."""
    parts: list[str] = [
        "## Readiness / Freshness",
        "",
        f"- **Index status:** `{index_status.value}`",
        f"- **Reason:** {index_status_reason}",
    ]

    if schema_version:
        parts.append(f"- **Schema version:** `{schema_version}`")
    if indexed_at:
        parts.append(f"- **Indexed at:** {indexed_at}")
    if current_git_head:
        short_head = current_git_head[:8] if len(current_git_head) >= 8 else current_git_head
        parts.append(f"- **Current HEAD:** `{short_head}`")
    if working_tree_dirty is not None:
        parts.append(f"- **Working tree dirty:** {'yes' if working_tree_dirty else 'no'}")

    if index_status == IndexStatus.STALE:
        parts.append("")
        parts.append(
            "> ⚠️ **Warning:** This index is stale. The repository has changed since "
            "indexing. Re-index before trusting entity-level details."
        )
    elif index_status == IndexStatus.MAYBE_STALE:
        parts.append("")
        parts.append(
            "> ⚠️ **Warning:** This index may be stale (working tree is dirty). "
            "Re-index if you need guaranteed accuracy."
        )
    elif index_status == IndexStatus.UNKNOWN:
        parts.append("")
        parts.append(
            "> ⚠️ **Warning:** Index freshness could not be determined. "
            "Verify entity accuracy against source files."
        )

    return "\n".join(parts)


def _build_workflows_section(mode: str) -> str:
    """Build the Common Agent Workflows section."""
    if mode == "store":
        workflow_text = _STORE_MODE_WORKFLOW
        mode_note = (
            "Store mode — select this repo with `rsm_store_select_index` before "
            "using repository-specific tools."
        )
    else:
        workflow_text = _REPO_MODE_WORKFLOW
        mode_note = "Repo/db mode — the target index is fixed for this session."

    return "\n".join(
        [
            "## Common Agent Workflows",
            "",
            mode_note,
            "",
            workflow_text,
            "",
            "Check [Readiness / Freshness](#readiness--freshness) before trusting this brief.",
        ]
    )


def _build_caveats_section(
    index_status: IndexStatus,
) -> str:
    """Build the Known Caveats section."""
    lines: list[str] = [
        "## Known Caveats",
        "",
    ]

    if index_status == IndexStatus.STALE:
        lines.append("- **Stale index:** The repository has changed since indexing.")
    elif index_status == IndexStatus.MAYBE_STALE:
        lines.append(
            "- **Maybe-stale index:** Working tree is dirty; index may not reflect current state."
        )
    elif index_status == IndexStatus.UNKNOWN:
        lines.append("- **Unknown freshness:** Could not determine if the index is up to date.")
    elif index_status == IndexStatus.SCHEMA_MISMATCH:
        lines.append(
            "- **Schema mismatch:** The index schema version differs from the current RSM version."
        )

    lines.append(
        "- **Generated-artifact suppression:** `_build/` and `__pycache__/` paths are excluded."
    )
    lines.append(
        "- **Lexical ranking:** BM25 search may amplify common terms across unrelated files."
    )
    lines.append("- **Test-heavy bias:** Some queries may return test files disproportionately.")

    return "\n".join(lines)


def _build_benchmark_section() -> str:
    """Build the Suggested Benchmark Tasks section."""
    return "\n".join(
        [
            "## Suggested Benchmark Tasks",
            "",
            "Benchmark cases for this repository are defined in the RSM benchmark harness.",
            "Run `rsm eval bench --dataset benchmarks/lifecore_ros2_benchmark_cases.yaml` "
            "to evaluate retrieval quality.",
        ]
    )


# ── public API ──────────────────────────────────────────────────────────────


def generate_project_brief(
    *,
    db_path: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Generate a deterministic project brief Markdown document.

    Args:
        db_path: Path to an existing RSM SQLite index database.
        max_chars: Hard character budget for the output. The generator
            will stop adding sections once the budget is exceeded.

    Returns:
        A Markdown string suitable for writing to ``PROJECT_CONTEXT.md``.

    Raises:
        FileNotFoundError: If *db_path* does not exist.
        ValueError: If *db_path* is not a valid SQLite index.
    """
    db_path_obj = Path(db_path)
    if not db_path_obj.is_file():
        raise FileNotFoundError(f"Index database not found: {db_path}")

    # Derive repo root from the DB path location or metadata
    store = SQLiteStore(db_path_obj)
    try:
        store.initialize()
        metadata = store.get_metadata()
        entities = store.list_entities()
    finally:
        store.close()

    # Extract metadata fields
    repo_root = metadata.get("repo_root") or metadata.get("repository_root", "(unknown)")
    indexed_at = metadata.get("indexed_at")
    schema_version = metadata.get("schema_version")
    context_pack_version = metadata.get("context_pack_version")

    version_info = get_version_info()

    # ── readiness ───────────────────────────────────────────────────────
    # Detect freshness using the existing status module
    index_mode: str = metadata.get("index_mode", "store")
    try:
        repo_root_path = Path(repo_root) if repo_root != "(unknown)" else Path.cwd()
        status_report = detect_index_status(
            repo_root=repo_root_path,
            db_path=db_path_obj,
            index_mode="explicit_db" if index_mode == "explicit_db" else "store",
        )
    except Exception:
        # Graceful fallback if freshness detection fails
        from repo_semantic_memory.index_status import IndexStatus, IndexStatusReport

        status_report = IndexStatusReport(
            index_status=IndexStatus.UNKNOWN,
            index_status_reason="detection_error",
            repo_root=repo_root_path,
            db_path=db_path_obj,
            index_mode="explicit_db",
            indexed_at=indexed_at,
            indexed_git_head=None,
            current_git_head=None,
            working_tree_dirty=None,
            schema_version=schema_version,
            context_pack_version=context_pack_version,
            suggested_action=None,
        )

    # ── entity analysis ─────────────────────────────────────────────────
    role_counts = _count_entities_by_path_role(entities)
    module_groups = _group_module_entities(entities)

    # ── build the document ──────────────────────────────────────────────
    sections: list[str] = []

    # Header
    repo_name = Path(repo_root).name if repo_root != "(unknown)" else "unknown-repo"
    header = f"# RSM Project Brief: {repo_name}"
    sections.append(header)

    # 1. Repository Identity
    identity_lines = [
        "## Repository Identity",
        "",
        f"- **Root:** `{repo_root}`",
        f"- **Index DB:** `{db_path_obj}`",
        f"- **RSM version:** `{version_info.package_version}`",
    ]
    if schema_version:
        identity_lines.append(f"- **Schema version:** `{schema_version}`")
    if context_pack_version:
        identity_lines.append(f"- **Context pack version:** `{context_pack_version}`")
    identity_lines.append(f"- **Total entities:** {len(entities)}")
    src_count = role_counts.get("source", 0)
    test_count = role_counts.get("test", 0)
    doc_count = role_counts.get("doc", 0)
    identity_lines.append(
        f"- **Entity breakdown:** source={src_count}, test={test_count}, doc={doc_count}"
    )
    sections.append("\n".join(identity_lines))

    # 2. Readiness / Freshness
    sections.append(
        _build_readiness_section(
            index_status=status_report.index_status,
            index_status_reason=status_report.index_status_reason,
            indexed_at=indexed_at,
            current_git_head=status_report.current_git_head,
            working_tree_dirty=status_report.working_tree_dirty,
            schema_version=schema_version,
        )
    )

    # 3. Purpose / Scope
    purpose_lines = [
        "## Purpose / Scope",
        "",
        "This project brief was generated deterministically from the local RSM index.",
        "It provides orientation for coding agents: main modules, tests, docs, and workflows.",
    ]
    sections.append("\n".join(purpose_lines))

    # 4. Main Code Areas
    code_lines = ["## Main Code Areas", ""]
    if module_groups:
        for dir_path in sorted(module_groups.keys()):
            ents = module_groups[dir_path]
            code_lines.append(f"### `{dir_path}/` ({len(ents)} key entities)")
            for ent in ents[:5]:
                code_lines.append(f"- `{ent.kind}` **{ent.name}** — `{_entity_source_path(ent)}`")
            if len(ents) > 5:
                code_lines.append(f"  - ... and {len(ents) - 5} more entities")
            code_lines.append("")
    else:
        code_lines.append("No indexed source modules found.")
    sections.append("\n".join(code_lines))

    # 5. Important Entry Points
    entry_lines = ["## Important Entry Points", ""]
    # Find __init__.py modules and top-level classes
    init_entities = [
        e for e in entities if "__init__.py" in _entity_source_path(e) and e.kind == "module"
    ]
    top_classes = [
        e for e in entities if e.kind == "class" and _entity_source_path(e).count("/") <= 3
    ]
    if init_entities:
        for ent in init_entities[:6]:
            entry_lines.append(f"- `{ent.name}` — `{_entity_source_path(ent)}`")
    elif top_classes:
        for ent in top_classes[:6]:
            entry_lines.append(f"- `{ent.kind}` **{ent.name}** — `{_entity_source_path(ent)}`")
    else:
        entry_lines.append("No clear entry points identified.")
    sections.append("\n".join(entry_lines))

    # 6. Test Areas
    test_lines = ["## Test Areas", ""]
    test_paths: set[str] = set()
    for ent in entities:
        path = _entity_source_path(ent)
        role = classify_path_role(path=path, source_roots=())
        if role == "test" and ent.kind in ("module", "class"):
            parent = Path(path).parent.as_posix()
            test_paths.add(parent)
    if test_paths:
        for tp in sorted(test_paths)[:10]:
            test_lines.append(f"- `{tp}/`")
    else:
        test_lines.append("No indexed test areas found.")
    sections.append("\n".join(test_lines))

    # 7. Docs / Reviews / Planning Notes
    doc_lines = ["## Docs / Reviews / Planning Notes", ""]
    # Collect all unique file paths that match our broader doc detection
    doc_paths: set[str] = set()
    for e in entities:
        path = _entity_source_path(e)
        if _is_doc_path(path):
            doc_paths.add(path)

    sorted_docs = _sort_doc_paths(doc_paths)
    shown = sorted_docs[:_MAX_DOC_ENTRIES]
    omitted = len(sorted_docs) - len(shown)

    if shown:
        for dp in shown:
            doc_lines.append(f"- `{dp}`")
        if omitted > 0:
            doc_lines.append(f"  ... {omitted} more documentation files omitted")
    else:
        doc_lines.append("No indexed documentation found.")
    sections.append("\n".join(doc_lines))

    # 8. Common Agent Workflows
    sections.append(_build_workflows_section(index_mode))

    # 9. Known Caveats
    sections.append(_build_caveats_section(status_report.index_status))

    # 10. Suggested Benchmark Tasks
    sections.append(_build_benchmark_section())

    # ── character budget enforcement ─────────────────────────────────────
    output = _SECTION_SEPARATOR.join(sections)

    if len(output) > max_chars:
        # Truncate deterministically: keep sections until budget exceeded
        truncated_sections: list[str] = []
        current_len = 0
        truncated = False
        for section in sections:
            section_len = len(section) + len(_SECTION_SEPARATOR)
            if current_len + section_len <= max_chars - 150:
                truncated_sections.append(section)
                current_len += section_len
            else:
                truncated = True
                break

        if truncated:
            truncated_sections.append(
                "> **Note:** This project brief was truncated to fit the character budget "
                f"({max_chars} chars). Re-generate with `--max-chars` for a larger budget "
                "or consult individual RSM tools for full details."
            )
        output = _SECTION_SEPARATOR.join(truncated_sections)

    return output


__all__ = [
    "DEFAULT_MAX_CHARS",
    "generate_project_brief",
]
