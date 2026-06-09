# 61.x MCP Surface Simplification — Final Closure Report

> **Status:** Complete.  
> **Last updated:** 2026-06-09.  
> **61.13 — Final closure report**

## 1. Summary

61.x completed the MCP surface simplification sequence.

The final public surface is **mode-sensitive**:

- **repo/db mode** defaults to **4 task tools**
- **store mode** defaults to **7 tools**, adding 3 explicit `rsm_store_*` navigation tools
- **`--expose-all-tools`** adds legacy/debug tools to the active mode

All 4 tool/mode combinations are validated by contract tests, lint, type-checking, and the full test suite.

## 2. Before / Transition / Correction / Final State

### Before

A broad MCP surface with 11+ legacy and internal tools visible by default.
No mode separation — repo/db and store shared the same tool set.
Store navigation tools were not prefixed and were grouped with legacy/debug tools.

### Transition

Wrapper tools (`rsm_search`, `rsm_find_related`, `rsm_prepare_context`) were
added while legacy tools remained available. Default surface was reduced to 4
tools for repo/db mode.

### Correction

- Store/navigation tools were separated from legacy/debug tools (61.14).
- The MCP public surface was made mode-sensitive: store mode exposes
  store/navigation tools by default; repo/db mode does not (61.15).
- Store/navigation tools were renamed with the `rsm_store_*` prefix to
  distinguish them from task-context tools (61.16).
- Real `--store` startup exposure was fixed — `build_store_tool_registry` no
  longer deleted store tools in public-only mode, and `_dispatch` used the
  correct store-mode public tool set (61.16).

### Final

| Mode | Tools |
|---|---|
| `--repo` / `--db` default | 4 public task tools |
| `--repo` / `--db --expose-all-tools` | 11 tools (4 task + 7 legacy/debug) |
| `--store` default | 7 public tools (4 task + 3 `rsm_store_*`) |
| `--store --expose-all-tools` | 14 tools (4 task + 3 `rsm_store_*` + 7 legacy/debug) |

## 3. Public Task Tools

### `rsm_search`

- **Purpose:** Broad discovery across indexed files, symbols, docs, and tests.
- **Main usage:** Preferred high-level replacement for `rsm_search_symbols`.
  Returns compact, deterministic results with source paths, entity kinds, and
  scoring reasons. Every response includes `active_repo` metadata.
- **Known limitations:**
  - Limit-only (no pagination — deferred).
  - `result_id` is response-local.

### `rsm_find_related`

- **Purpose:** Anchor-based expansion around a known file, entity, or qualified
  name. Resolves anchor via `entity_id`, `qualified_name`, or `source_path`
  (priority: `entity_id` > `qualified_name` > `source_path`).
- **Main usage:** Preferred high-level replacement for `rsm_explain_entity` and
  `rsm_query_graph`. Returns compact related items classified by relation group
  (tests, imports, exports, inherits, implementation_support) and strength
  (strong/medium/weak). Every response includes `active_repo` metadata.
- **Known limitations:**
  - Limit-only (no pagination — deferred).
  - `result_id` anchor deferred.
  - Relation group filter deferred.

### `rsm_prepare_context`

- **Purpose:** Prepare a task-centered ContextPack for a coding agent.
- **Main usage:** Preferred high-level replacement for `rsm_build_context_pack`.
  Returns a brief first-page preview by default (5 files, 5 entities,
  3 relations, 0 citations) plus a session-scoped `result_set_id`. Use
  `rsm_get_context_page` to page over omitted items. Every response includes
  `active_repo` metadata.
- **Known limitations:**
  - Wrapper/evolution of `rsm_build_context_pack` — identical output with
    added `active_repo` metadata.

### `rsm_get_context_page`

- **Purpose:** Page over a previously-built context pack stored in this MCP
  session by `result_set_id`, without recomputing the pack.
- **Main usage:** Returns a deterministic slice of the requested stream
  (files, entities, relations, citations, or ranking_breakdowns) with short
  stable per-entry IDs. Unknown or expired `result_set_id` surfaces as a
  recoverable `result_set_unknown` uncertainty.
- **Known limitations:**
  - `result_set_id` is session-scoped — lost when the MCP server process
    restarts.

## 4. Public Store/Navigation Tools

### `rsm_store_list_indexes`

- **Purpose:** List all repositories registered in the RSM Index Store.
  Returns `repo_id`, `name`, `repo_root`, `db_path`, and best-effort status
  for each registered index.
- **Visibility:** Public by default only in `--store` mode.
- **Not available in** `--repo` / `--db` mode (with or without `--expose-all-tools`).

### `rsm_store_select_index`

- **Purpose:** Select the active repository index for this MCP session.
  Accepts `repo_id` (preferred), `repo_root` (absolute path), or `name`
  (basename of `repo_root`; rejected if ambiguous). Validates that the
  selected DB exists. Active selection is session-scoped — lost when the
  MCP server process restarts.
- **Visibility:** Public by default only in `--store` mode.
- **Not available in** `--repo` / `--db` mode (with or without `--expose-all-tools`).

### `rsm_store_current_index`

- **Purpose:** Return the currently active repository index for this MCP
  session. If no index has been selected, returns `active_repo: null` and a
  recoverable `no_active_index` uncertainty.
- **Visibility:** Public by default only in `--store` mode.
- **Not available in** `--repo` / `--db` mode (with or without `--expose-all-tools`).

**Key design decisions:**

- Public by default only in `--store` mode.
- Not available in `--repo` / `--db` mode.
- Not legacy/debug — these tools are needed for normal store-mode navigation.
- Prefixed with `rsm_store_*` so agents can distinguish store navigation from
  task-context tools.

## 5. Removed Old Store Tool Names

| Old name | New name |
|---|---|
| `rsm_list_indexes` | `rsm_store_list_indexes` |
| `rsm_select_index` | `rsm_store_select_index` |
| `rsm_current_index` | `rsm_store_current_index` |

Old names are **not exposed by default or with `--expose-all-tools`**. Strict
rename — no aliases kept.

## 6. Legacy/Debug Tools

The following 7 tools are hidden by default and available only with
`--expose-all-tools`:

| Tool | Status | Notes |
|---|---|---|
| `rsm_status` | `[INTERNAL/DEBUG]` | Session diagnostics |
| `rsm_search_symbols` | `[DEPRECATED]` | Use `rsm_search` |
| `rsm_explain_entity` | `[DEPRECATED]` | Use `rsm_find_related` |
| `rsm_build_context_pack` | `[DEPRECATED]` | Use `rsm_prepare_context` |
| `rsm_query_graph` | `[DEPRECATED]` | Use `rsm_find_related` |
| `rsm_validate_patch_context` | `[INTERNAL/DEBUG]` | Patch context check |
| `rsm_get_git_summary` | `[INTERNAL/DEBUG]` | Git repository summary |

**Key design decisions:**

- Hidden by default — not part of the normal public agent workflow.
- Available with `--expose-all-tools` for compatibility and debugging.
- Preserved indefinitely unless zero observed usage after a documented
  deprecation window.

## 7. Implementation Summary

| Task | Deliverable |
|---|---|
| 61.0 | MCP tool surface minimization plan |
| 61.1 | Design 4-tool RSM MCP interface |
| 61.2 | Existing MCP compatibility strategy |
| 61.3 | Implement `rsm_prepare_context` |
| 61.4 | Stabilize `rsm_get_context_page` hardening |
| 61.5 | Implement `rsm_search` |
| 61.6 | Implement `rsm_find_related` |
| 61.7 | Add deprecation/internal descriptions |
| 61.9 | Public/default filtering and `--expose-all-tools` |
| 61.10 | Public/debug compatibility tests |
| 61.11 | Documentation cleanup |
| 61.12 | Test naming/section cleanup |
| 61.14 | Store/navigation tools separated from legacy/debug |
| 61.15 | Mode-sensitive MCP surface contract |
| 61.16 | `rsm_store_*` rename and real store-mode exposure fix |

## 8. Validation Summary

Latest validation (61.16):

| Check | Result |
|---|---|
| `tests/mcp/` | 213 passed |
| `tests/test_cli.py` | 90 passed |
| `tests/context/` | All passed |
| `tests/eval/` | All passed |
| `ruff check` | All checks passed |
| `ruff format --check` | 142 files already formatted |
| `mypy src` | Success, no issues found in 70 source files |

## 9. Compatibility Guarantees

- `--repo` / `--db` default mode exposes only 4 task tools.
- `--store` default mode exposes 7 tools (4 task + 3 `rsm_store_*` navigation).
- Legacy/debug tools are hidden by default in all modes.
- Legacy/debug tools are available with `--expose-all-tools` in both modes.
- Old store tool names (`rsm_list_indexes`, `rsm_select_index`,
  `rsm_current_index`) are removed from the MCP surface.
- No ranking behavior changed.
- No ContextPack schema changed.
- No DB/index schema changed.
- No dependencies added.

## 10. Remaining Open Questions

1. Whether legacy/debug tools are removed later or kept indefinitely.
2. When `rsm_search` pagination should be implemented.
3. When `rsm_find_related` pagination should be implemented.
4. Whether result IDs should become persistent (cross-session).
5. Whether per-call repo/project selection should be revisited.
6. Whether a SKILL-like project summary should be explored after lifecore
   validation.

## 11. Recommendation

**Proceed to 62.0 — Index lifecore_ros2 manually.**

No MCP blocker remains. The surface is stable, validated, and mode-sensitive.

## 12. Scope Confirmation

61.x did **not** introduce:

- Chunks
- Embeddings
- Graph export
- Backend integrations
- ContextPack schema migration
- Ranking changes
- DB/index schema changes
- Per-call repo selection
