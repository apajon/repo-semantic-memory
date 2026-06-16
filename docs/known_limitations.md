# Known Limitations

RSM is an experimental pre-1.0 tool. This document describes what it supports well today, what it does not support yet, and what that means for your workflow.

It is honest but not self-defeating — many of these limitations do not block current use.

## Summary

RSM is strongest today for **Python and documentation-heavy repositories**. It provides deterministic, source-cited context to coding agents through a local CLI and a read-only MCP server.

RSM is not a general-purpose code intelligence platform and does not aim to become one.

## Current Strengths

- **Python indexing**: Extracts modules, classes, functions, methods, and their structural relations (imports, exports, calls, inheritance) using the standard library `ast` module.
- **Markdown indexing**: Extracts document outlines, headings, and structural references.
- **Test relationship extraction**: Links source entities to their related tests.
- **ContextPack generation**: Builds task-specific, budget-bounded context packages with symbols, files, citations, and uncertainty markers.
- **Project briefs**: Generates deterministic Markdown summaries of indexed repositories.
- **MCP server**: Exposes search, find-related, context pack, and paging tools through a local read-only stdio MCP server.
- **Benchmarks**: Internal benchmark suite validates retrieval quality against task examples.
- **Deterministic**: All extraction and ranking is deterministic — no LLM calls, no network access, no randomized ordering.

## Current Limitations

### Language Support

- **Python-first, Markdown-second.** RSM indexes Python source files and Markdown documents. Other file types are indexed as file-level entities only (no symbol extraction).
- **Limited non-Python support.** Languages such as TypeScript, Rust, Go, C++, and others are not currently extracted. They appear as file-level entities only.
- **No ROS interface file indexing.** `.msg`, `.srv`, and `.action` files (common in ROS 2 projects) are not indexed. This is a planned future feature (see [Roadmap](design/roadmap.md), 68.x track).

### Search and Ranking

- **BM25 lexical scoring.** Search uses BM25, a lexical (keyword-based) ranking algorithm. It is benchmark-backed but not perfect. Queries with ambiguous terms may return noise alongside relevant results.
- **No embeddings or vector search.** RSM does not use embeddings, vector databases, or semantic similarity. This is an explicit architectural decision, not a missing feature.

### Tooling and Integration

- **No automatic background indexing.** You must run `rsm index` explicitly when the repository changes.
- **No automatic refresh or watch mode.** There is no file watcher that re-indexes on changes.
- **No GUI.** RSM is CLI and MCP only.
- **MCP server is local and read-only.** It does not modify your repository, does not auto-index, and is not designed for remote or multi-user access.

### ContextPack Quality

- **ContextPacks are retrieval aids, not correctness guarantees.** They select files and symbols that are likely relevant based on lexical and structural signals. Always verify important claims against the actual source files.
- **Project brief depends on index freshness.** If the index is stale, the project brief may be outdated. Check the freshness section at the top of each brief.

### Schema and Interoperability

- **Pre-1.0 schema.** The SQLite schema and ContextPack format may evolve between versions. JSONL exports are the recommended interchange format for now.
- **No full semantic graph export.** RSM does not export a complete graph in a standard format (RDF, GraphML, etc.).

## Not Supported Yet

These capabilities are planned or deferred but not implemented:

- Embeddings / vector search (architecturally out of scope)
- Non-Python language extraction (planned, see roadmap)
- ROS interface file indexing (`.msg`, `.srv`, `.action` — planned, see 68.x)
- Automatic background indexing or watch mode
- GUI or web dashboard
- Remote or multi-user MCP access
- Full semantic graph export (RDF, GraphML)
- Snippets / code chunk extraction (feasibility deferred)

## Experimental Areas

These features are implemented and working but should be considered experimental:

- **Incremental indexing** (`rsm index --incremental`): Attempts to update only changed files using Git signals. Falls back to a full rebuild if safety cannot be proven.
- **MCP store mode** (`rsm mcp serve --store`): Lets an agent switch between multiple registered repository indexes at runtime.
- **Index scope planner** (`rsm index plan`): Recommends safe indexing scopes for large repositories. Advisory only.
- **Compression profiles**: The `agent_standard` profile is the recommended default. Other profiles (`agent_brief`, `agent_debug`, `human_review`, `ci_summary`, `full`) are less tested.
- **JSONL export/import**: Works for the current schema version but is not yet a stable interchange contract.

## What This Means in Practice

### RSM is useful today when

- You work primarily with Python repositories.
- You want to give a coding agent focused, source-cited context before it starts editing.
- You need deterministic, repeatable retrieval (same index → same results).
- You want orientation (repo map, project brief) before exploring a codebase.
- You work with documentation-heavy repos and want docs surfaced alongside code.

### RSM may be less useful when

- Your repository is primarily in a non-Python language and you need symbol-level indexing.
- You rely heavily on ROS 2 interface files (`.msg`, `.srv`, `.action`) for task context.
- You need semantic search (embeddings, vector similarity).
- You want a zero-config background indexer that stays up to date automatically.

### These limitations do not block current use for

- Python codebase exploration and task context preparation.
- Documentation-heavy repository orientation.
- Deterministic, benchmark-backed retrieval evaluation.
- Local agent workflows through CLI or MCP.

## Related Roadmap Items

See [Roadmap](design/roadmap.md) for the full plan. Key tracks:

- **68.x**: Non-Python / interface-file indexing (`.msg`, `.srv`, `.action`, and others).
- **63.x**: Search refinement.
- **64.x**: `find_related` refinement.
- **65.x**: ContextPack refinement.
- **66.x**: Snippets/chunks feasibility study.
- **70.x**: Post-announcement hardening.
