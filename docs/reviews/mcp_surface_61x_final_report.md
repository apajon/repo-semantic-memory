# MCP Surface 61.x Final Report

> **Task:** 61.13 — Final closure report  
> **Date:** 2026-06-09  
> **Branch:** `fix/61.15-mode-sensitive-surface`  
> **Status:** Complete. All 61.x tasks done. Final mode-sensitive contract active.
> **Next step:** 62.0 — Index lifecore_ros2 manually.

## 1. Summary

**61.x completed the transition from a broad 11-tool MCP surface to a
mode-sensitive public surface.** The tools exposed depend on launch mode.

| Mode | Default surface | `--expose-all-tools` |
|---|---|---|
| `--repo` / `--db` | 4 task tools | 11 tools (4 task + 7 legacy) |
| `--store` | 7 tools (4 task + 3 store/nav) | 14 tools (4 task + 3 store/nav + 7 legacy) |

Legacy, internal, and debug tools remain available through an explicit
`--expose-all-tools` flag but are hidden from `tools/list` and blocked at
invocation by default. Store/navigation tools are public in store mode
but unavailable in repo/db mode (the repository is already fixed).

The primary change is that coding agents now see a mode-appropriate surface:

**Repo/db mode (4 tools):**

| Tool | Role |
|---|---|
| `rsm_search` | Broad discovery across files, symbols, docs, and tests |
| `rsm_find_related` | Anchor-based expansion |
| `rsm_prepare_context` | Build a task-centered ContextPack |
| `rsm_get_context_page` | Page over a prepared ContextPack |

**Store mode adds 3 store/nav tools (7 total):**

| Tool | Role |
|---|---|
| `rsm_list_indexes` | List all repositories in the RSM Index Store |
| `rsm_select_index` | Activate a repository index for this session |
| `rsm_current_index` | Return the currently active repository index |

## 2. Before / Transition / After

| Phase | State | Repo/db default | Store default |
|---|---|---|---|
| **Before main** (≤0.34.0) | 11 tools visible by default | 11 | 11 |
| **Transition** (61.3–61.6) | New wrappers added alongside old tools | 14 | 14 |
| **61.9** | 4 task tools visible, store hidden behind flag | 4 | 4 |
| **61.14** | Store/nav promoted to public in store mode | 4 | 7 |
| **61.15** | Mode-sensitive contract finalized | 4 | 7 |

## 3. Final Public MCP Surface

### 3.1 Public task tools (both modes)

| Tool | Role |
|---|---|
| `rsm_search` | Broad discovery across files, symbols, docs, and tests |
| `rsm_find_related` | Anchor-based expansion around a known file, entity, or qualified name |
| `rsm_prepare_context` | Build a task-centered ContextPack |
| `rsm_get_context_page` | Page over a prepared ContextPack without recomputing |

### 3.2 Public store/navigation tools (store mode only)

| Tool | Role |
|---|---|
| `rsm_list_indexes` | List all repositories registered in the RSM Index Store |
| `rsm_select_index` | Activate a repository index for this MCP session |
| `rsm_current_index` | Return the currently active repository index |

### 3.3 `rsm_search`

**Purpose:** Broad discovery across indexed files, symbols, docs and tests.

**Main input:** `query` (required), `limit`, `kind`, `path_role`.

**Main output:** `active_repo`, `query`, `results` (with `result_id`, `path`,
`kind`, `name`, `score`, `reasons`), `count`, `uncertainties`, `warnings`.

**Current limitations:**
- Limit-only behavior; cursor pagination deferred.
- `result_id` is deterministic within a single response only
  (`search_0001`, `search_0002`, …).
- No source snippets; results include entity metadata only.

### 3.4 `rsm_find_related`

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

### 3.5 `rsm_prepare_context`

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

### 3.6 `rsm_get_context_page`

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

### Store-mode/navigation tools (public in store mode only since 61.15)

| Tool | Purpose |
|---|---|
| `rsm_list_indexes` | Discover registered repositories in Index Store |
| `rsm_select_index` | Activate a repository index for the session |
| `rsm_current_index` | Return the currently active index |

These are public in `--store` mode (7-tool default surface). They are
**not available** in repo/db mode — the repository is already fixed.

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
| **61.13** | ✅ Final 61.x MCP surface closure report | Docs |
| **61.14** | Promote store/navigation tools to store mode default surface | Code |
| **61.15** | Mode-sensitive contract: repo/db=4, store=7, expose-all adds legacy | Code |

**Key files changed across 61.x:**
- `src/repo_semantic_memory/mcp/runtime.py` — tool categories, filtering, deprecation markers, `STORE_PUBLIC_TOOL_NAMES`
- `src/repo_semantic_memory/mcp/server.py` — `--expose-all-tools` flag, mode-sensitive dispatch
- `src/repo_semantic_memory/mcp/__init__.py` — updated exports
- `src/repo_semantic_memory/cli.py` — `--expose-all-tools` CLI flag
- `docs/usage/mcp.md` — mode-sensitive docs
- `docs/design/mcp_tool_surface_minimization.md` — 61.0 design (with 61.15 correction note)
- `docs/design/mcp_4_tool_interface.md` — 61.1 design (with 61.15 correction note)
- `docs/design/mcp_compatibility_strategy.md` — 61.2 design (with 61.15 correction note)
- `docs/reviews/mcp_surface_61x_final_report.md` — This report (61.13 final closure)
- `tests/mcp/test_server.py` — Mode-sensitive surface tests (199 tests)
- `tests/mcp/test_store_mode.py` — Store mode surface tests

## 6. Validation Summary

All results from 2026-06-09, branch `fix/61.15-mode-sensitive-surface`:

| Suite | Collected | Status |
|---|---|---|
| `tests/mcp/` | 199 | All passing |
| `tests/test_cli.py` | 90 | All passing |
| `tests/context/` | 422 | All passing |
| `tests/eval/` | 77 | All passing |
| **Total** | **788** | **All passing** |

**Lint & type checks:**

| Check | Result |
|---|---|
| `ruff check` | All checks passed |
| `ruff format --check` | All files formatted |
| `mypy src` | Success, no issues found in 70 source files |

**CI benchmark (59.x harness):** No regression confirmed in 61.3
(`rsm_prepare_context` produces identical output to `rsm_build_context_pack`).

## 7. Compatibility Guarantees

- ✅ **Mode-sensitive default surface:**
  - Repo/db mode: 4 task tools.
  - Store mode: 4 task + 3 store/nav tools.
- ✅ Store/navigation tools are public in store mode, unavailable in repo/db mode.
- ✅ Legacy tools callable only with `--expose-all-tools`.
- ✅ Legacy/deprecated tools are hidden by default but not removed.
- ✅ Old behavior is preserved in expose-all mode (all tools functional).
- ✅ No ranking behavior changed throughout 61.x.
- ✅ No ContextPack schema changed.
- ✅ No DB/index schema changed.
- ✅ No new tools added.
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

The MCP surface is stable and mode-sensitive:

- Repo/db mode: 4 task tools by default, 11 with `--expose-all-tools`.
- Store mode: 7 tools (4 task + 3 store/nav) by default, 14 with `--expose-all-tools`.
- Tested across 199 MCP tests, 788 total.
- `--expose-all-tools` preserves backward compatibility.
- All tests pass, no regressions.
- Documentation reflects the mode-sensitive contract.
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
