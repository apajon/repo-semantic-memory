# MCP Surface 61.x Final Report

> **Date:** 2026-06-09  
> **Branch:** `feat/tool-reductioin-61`  
> **Status:** Updated. 61.14 correction applied — store/navigation tools are now public.

## 1. Summary

**61.x completed the transition from a broad 11-tool MCP surface to a 7-tool
public default surface (4 task + 3 store/navigation).** Legacy, internal, and
debug tools remain available through an explicit `--expose-all-tools`
debug/compatibility mode but are hidden from `tools/list` and blocked at
invocation by default.

The primary change is that coding agents now see seven tools:

| Category | Tool | Role |
|---|---|---|
| Task | `rsm_search` | Broad discovery across files, symbols, docs, and tests |
| Task | `rsm_find_related` | Anchor-based expansion around a known file, entity, or qualified name |
| Task | `rsm_prepare_context` | Build a task-centered ContextPack |
| Task | `rsm_get_context_page` | Page over a prepared ContextPack without recomputing |
| Store/nav | `rsm_list_indexes` | List all repositories registered in the RSM Index Store |
| Store/nav | `rsm_select_index` | Activate a repository index for this MCP session |
| Store/nav | `rsm_current_index` | Return the currently active repository index |

## 2. Before / Transition / After

| Phase | State | Tool count (default store mode) |
|---|---|---|
| **Before main** (≤0.34.0) | 11 tools visible by default | 11 |
| **Transition** (61.3–61.6) | New wrappers added alongside old tools | 14 |
| **61.9** | 4 task tools visible, store tools hidden behind flag | 4 |
| **61.14** | 4 task + 3 store/nav = 7 tools visible | 7 |

**Store mode note:** With `--store --expose-all-tools`, the full surface is
14 tools (7 public + 7 legacy/internal).

## 3. Final Public MCP Surface

### 3.1 Public task tools

| Tool | Role |
|---|---|
| `rsm_search` | Broad discovery across files, symbols, docs, and tests |
| `rsm_find_related` | Anchor-based expansion around a known file, entity, or qualified name |
| `rsm_prepare_context` | Build a task-centered ContextPack |
| `rsm_get_context_page` | Page over a prepared ContextPack without recomputing |

### 3.2 Public store/navigation tools

| Tool | Role |
|---|---|
| `rsm_list_indexes` | List all repositories registered in the RSM Index Store |
| `rsm_select_index` | Activate a repository index for this MCP session |
| `rsm_current_index` | Return the currently active repository index |

**Main input:** `query` (required), `limit`, `kind`, `path_role`.

**Main output:** `active_repo`, `query`, `results` (with `result_id`, `path`,
`kind`, `name`, `score`, `reasons`), `count`, `uncertainties`, `warnings`.

**Current limitations:**
- Limit-only behavior; cursor pagination deferred.
- `result_id` is deterministic within a single response only
  (`search_0001`, `search_0002`, …).
- No source snippets; results include entity metadata only.

### 3.2 `rsm_find_related`

**Purpose:** Anchor-based expansion around a known file, entity, or qualified
name.

**Main input:** `entity_id`, `qualified_name`, `source_path` (at least one),
`limit`. Priority: `entity_id` > `qualified_name` > `source_path`.

**Main output:** `active_repo`, `anchor`, `related` (with `relation_group`,
`relation_strength`, `relation_kinds`, `direction`, `reasons`), `count`,
`total`, `uncertainties`.

**Current limitations:**
- Limit-only behavior; cursor pagination deferred.
- `result_id` anchor deferred (search result IDs are response-local).
- `relation_groups` filter deferred (all groups returned).

### 3.3 `rsm_prepare_context`

**Purpose:** Build a deterministic, source-cited, budget-bounded ContextPack
for a coding task.

**Main input:** `task` (required), `budget_chars`, `profile`, `detail_level`.

**Main output:** `result_set_id`, `active_repo`, `counts`, preview streams
(`selected_files`, `selected_entities`, `selected_relations`, `citations`),
`next` (paging hints), `uncertainties`, `warnings`.

**Current limitations:**
- Preferred replacement for `rsm_build_context_pack`. Both produce identical
  output; `rsm_prepare_context` adds `active_repo` metadata.
- `detail_level` controls preview size; paging via `rsm_get_context_page` is
  the recommended way to get additional items.

### 3.4 `rsm_get_context_page`

**Purpose:** Page over a previously-built ContextPack without recomputing.

**Main input:** `result_set_id` (required), `stream`, `offset`, `limit`.

**Main output:** `result_set_id`, `stream`, `items` (with short stable IDs),
`total`, `next_offset`.

**Current limitations:**
- `result_set_id` is session-scoped; not reproducible across MCP restarts.
- Max 8 result sets cached per session (LRU eviction).
- Expired IDs return a recoverable `result_set_unknown` uncertainty.

## 4. Debug / Compatibility Surface

Enabled with `rsm mcp serve --expose-all-tools`.

### Deprecated compatibility tools

| Tool | Deprecated replacement |
|---|---|
| `rsm_search_symbols` | `rsm_search` |
| `rsm_explain_entity` | `rsm_find_related` |
| `rsm_build_context_pack` | `rsm_prepare_context` |
| `rsm_query_graph` | `rsm_find_related` |

These tools are hidden by default but not removed. They produce identical
output to their replacements (or superset, in the case of `rsm_find_related`
which combines `rsm_explain_entity` and `rsm_query_graph`).

### Internal/debug tools

| Tool | Purpose |
|---|---|
| `rsm_status` | Session diagnostics (repo/db paths, entity/relation counts, staleness) |
| `rsm_validate_patch_context` | Patch context sufficiency check |
| `rsm_get_git_summary` | Repository git metadata |

### Store-mode/navigation tools (public by default since 61.14)

| Tool | Purpose |
|---|---|
| `rsm_list_indexes` | Discover registered repositories in Index Store |
| `rsm_select_index` | Activate a repository index for the session |
| `rsm_current_index` | Return the currently active index |

These are public store/navigation tools available by default in `--store` mode. They are not legacy/debug tools.

## 5. Implementation Summary

| Task | Description | Type |
|---|---|---|
| **61.0** | MCP tool surface minimization plan | Design |
| **61.1** | Design 4-tool RSM MCP interface (detailed schemas) | Design |
| **61.2** | Existing MCP compatibility strategy (5-phase migration) | Design |
| **61.3** | Implement `rsm_prepare_context` wrapper | Code |
| **61.4** | Stabilize `rsm_get_context_page` | Code |
| **61.5** | Implement `rsm_search` wrapper | Code |
| **61.6** | Implement `rsm_find_related` wrapper | Code |
| **61.7** | Add `[DEPRECATED]`/`[INTERNAL/DEBUG]` description markers | Code |
| **61.8** | MCP migration docs and examples | Docs |
| **61.9** | Default tool surface reduction (`--expose-all-tools` flag) | Code |
| **61.10** | Public/debug compatibility tests | Tests |
| **61.11** | Documentation cleanup after surface reduction | Docs |
| **61.12** | Test cleanup and consolidation | Tests |
| **61.13** | Final 61.x MCP surface report | Docs |
| **61.14** | Promote store/navigation tools to default public surface | Code |

**Key files changed across 61.x:**
- `src/repo_semantic_memory/mcp/runtime.py` — new tools, tool filtering, deprecation markers, store/nav promotion
- `src/repo_semantic_memory/mcp/server.py` — `--expose-all-tools` flag, surface filtering
- `src/repo_semantic_memory/mcp/__init__.py` — new exports
- `src/repo_semantic_memory/cli.py` — `--expose-all-tools` CLI flag
- `docs/usage/mcp.md` — complete rewrite for 7-tool surface
- `docs/design/mcp_tool_surface_minimization.md` — 61.0 design (with 61.14 correction note)
- `docs/design/mcp_4_tool_interface.md` — 61.1 design (with 61.14 correction note)
- `docs/design/mcp_compatibility_strategy.md` — 61.2 design + Phase D note
- `docs/reviews/mcp_surface_61x_final_report.md` — Updated for 61.14
- `tests/mcp/test_server.py` — Updated for 61.14
- `tests/mcp/test_store_mode.py` — Updated for 61.14

## 6. Validation Summary

All results from 2026-06-08, commit `ca65d1d`:

| Suite | Collected | Status |
|---|---|---|
| `tests/mcp/` | 196 | All passing |
| `tests/test_cli.py` | 90 | All passing |
| `tests/context/` | 422 | All passing |
| `tests/eval/` | 77 | All passing |
| **Total** | **785** | **All passing** |

**Lint & type checks:**

| Check | Result |
|---|---|
| `ruff check` | All checks passed |
| `ruff format --check` | 142 files already formatted |
| `mypy src` | Success, no issues found in 70 source files |

**CI benchmark (59.x harness):** No regression confirmed in 61.3
(`rsm_prepare_context` produces identical output to `rsm_build_context_pack`).

## 7. Compatibility Guarantees

- ✅ Default `tools/list` exposes 7 public tools (4 task + 3 store/navigation).
- ✅ Store/navigation tools are available by default (not hidden behind flag).
- ✅ Legacy tools callable only with `--expose-all-tools`.
- ✅ Legacy/deprecated tools are hidden by default but not removed.
- ✅ Old behavior is preserved in expose-all mode (all 14 tools functional).
- ✅ No ranking behavior changed throughout 61.x.
- ✅ No ContextPack schema changed.
- ✅ No DB/index schema changed.
- ✅ CLI `rsm pack` unchanged.
- ✅ `invoke_tool()` test helper still allows all tools (bypasses MCP filtering).

## 8. Remaining Open Questions

| Question | Status |
|---|---|
| Should legacy tools be removed or kept indefinitely? | Deferred (Phase E not implemented) |
| When should `rsm_search` cursor pagination be implemented? | Deferred |
| When should `rsm_find_related` cursor pagination be implemented? | Deferred |
| Should `result_id` from `rsm_search` persist across calls? | Deferred (current: response-local only) |
| Should per-call `repo` parameter be revisited? | Deferred |
| Should project brief / SKILL-like summary be added? | Candidate for post-62.x |
| Should `rsm_find_related` `relation_groups` filter be implemented? | Deferred |
| Should `rsm_find_related` `result_id` anchor be implemented? | Deferred |

## 9. Recommendation

**Proceed to 62.0 — Index lifecore_ros2 manually and validate RSM against a
real ROS 2 project.**

The MCP surface is stable:

- 7 public tools by default (4 task + 3 store/navigation), tested across 196 MCP tests.
- `--expose-all-tools` preserves backward compatibility.
- All 785 tests pass, no regressions.
- Documentation reflects the current state.
- No known MCP blockers remain.

62.0 should focus on indexing `lifecore_ros2` (the ROS 2 lifecycle framework
in the same workspace), running RSM's ContextPack and search tools against
real code, and validating agent usefulness on concrete ROS 2 development tasks.

## 10. Scope Confirmation

**61.x did not add:**
- Chunks or chunk-based retrieval
- Embeddings or vector search
- Graph export or graph database
- Backend integrations (Neo4j, vector DB, web UI)
- ContextPack schema migration
- Ranking changes
- Snippet-level source output
- Multi-hop graph traversal beyond existing `rsm_query_graph` internals

**No dependencies were added** throughout the 61.x sequence.
