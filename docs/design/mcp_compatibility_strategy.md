# MCP Compatibility Strategy

> **Task:** 61.2 — Design-only  
> **Date:** 2026-06-06  
> **Branch:** `feat/benchmark-harness-59`  
> **Depends on:** `docs/design/mcp_tool_surface_minimization.md` (61.0),  
> `docs/design/mcp_4_tool_interface.md` (61.1)  
> **Status:** Design complete. No code changed.  
> **Correction (61.15 — 2026-06-09):** The final contract is mode-sensitive.
> Store/nav tools are public in store mode only (not in repo/db mode).
> This document is preserved as the original migration strategy.
> See `docs/reviews/mcp_surface_61x_final_report.md` for the final contract.

## 1. Purpose

This document defines how RSM migrates from the current 11-tool MCP surface to
the target 4-tool public surface **without breaking existing users or tests**.

It builds on:
- 61.0 — Tool surface minimization plan (why)
- 61.1 — Detailed 4-tool input/output schemas (what)
- 61.2 — This document (how to migrate)

**This is a design document.** No code, MCP behavior, CLI behavior, ranking,
or dependencies are changed in 61.2.

---

## 2. Current Tool Inventory

All tools are defined in `src/repo_semantic_memory/mcp/runtime.py`.

### 2.1 Phase 1 tools (PHASE1_TOOL_NAMES — 8 tools)

These are available in both `--repo` and `--store` sessions.

#### rsm_status

| Property | Value |
|---|---|
| **Purpose** | Return read-only session status: configured --repo and --db, package/schema versions, entity/relation counts, index staleness metadata |
| **Handler** | `_tool_status` in `runtime.py` — calls `SQLiteStore` for metadata, `detect_stale_from_metadata` for staleness |
| **Input** | None |
| **Output** | `repo_root`, `db_path`, `db_exists`, `package_version`, `schema_version`, `entity_count`, `relation_count`, `index_status`, `index_status_reason`, `indexed_at`, `current_git_head`, `working_tree_dirty`, `suggested_action`, `index_scope` |
| **Test coverage** | `test_invoke_status` in `test_server.py`; MCP `tools/call` with `rsm_status` in `test_stdio_tool_call` |
| **Current role** | Low-level diagnostics |

#### rsm_search_symbols

| Property | Value |
|---|---|
| **Purpose** | Search indexed entities by lexical BM25 query with optional kind/path_role filters and relation inclusion |
| **Handler** | `handle_search_symbols` in `handlers.py` — calls `FieldedBM25Index`, `classify_path_role`, `infer_source_roots` |
| **Input** | `query`, `limit` (default 10, max 100), `entity_kinds`, `path_roles`, `include_relations` |
| **Output** | `matches` (entity IDs), `results` (entity dicts with scores/paths/roles), `citations`, `uncertainties`, `budget`, `agent_instructions` |
| **Test coverage** | 9 handler tests (limit enforcement, determinism, path fields, scores, agent_instructions, field presence). MCP `tools/call` test. Enforced via `test_tool_registry_names_match_phase1_contract` |
| **Current role** | Mid-level entity search |

#### rsm_explain_entity

| Property | Value |
|---|---|
| **Purpose** | Resolve one entity with structural context, incoming/outgoing relations, semantic components, and citations |
| **Handler** | `handle_explain_entity` in `handlers.py` — entity ID lookup, relation filtering, `infer_semantic_components` |
| **Input** | `entity_id`, `include_incoming_relations`, `include_outgoing_relations`, `include_components`, `include_claims` |
| **Output** | `entity_id`, `entity` payload, `relations`, `semantic_components`, `related_entity_ids`, `citations`, `uncertainties` |
| **Test coverage** | No dedicated handler test file tests (covered implicitly by `test_handlers.py` path-rejection tests). Registered in registry assertion |
| **Current role** | Entity detail |

#### rsm_build_context_pack

| Property | Value |
|---|---|
| **Purpose** | Build a deterministic, source-cited, budget-bounded context pack for a task. Returns brief preview + result_set_id |
| **Handler** | `handle_build_context_pack` in `handlers.py` — calls `build_context_pack`, `resolve_profile`, `render_context_pack_markdown`. Runtime wrapper `_tool_build_context_pack` in `runtime.py` adds progressive retrieval and scope warnings |
| **Input** | `task`, `budget_chars` (max 20000), `format`, `profile`, `detail_level`, `explain_ranking`, `include_semantic_components`, `include_rendered`, `include_payload`, `include_ranking_breakdowns`, `max_files`, `max_entities`, `max_relations`, `max_citations` |
| **Output** | `result_set_id`, `counts`, `selected_files` (preview), `selected_entities` (preview), `selected_relations` (preview), `citations` (preview), `next`, `uncertainties`, `budget`, `omitted_sections`, `how_to_get_more`, `detail_level`, scope warnings |
| **Test coverage** | 5 handler tests (budget cap, selected_files, selected_entities, selected_relations, agent_instructions, field presence). 4 MCP integration tests (compact default, include_rendered, include_payload, include_ranking_breakdowns). Registry validated |
| **Current role** | Primary coding-agent tool |

#### rsm_get_context_page

| Property | Value |
|---|---|
| **Purpose** | Page over a previously-built context pack without recomputing. Returns a deterministic slice of the requested stream |
| **Handler** | `_tool_get_context_page` in `runtime.py` — calls `ResultStore.get()` and `slice_page()` |
| **Input** | `result_set_id`, `stream` (files/entities/relations/citations/ranking_breakdowns), `offset`, `limit` (1-20) |
| **Output** | `result_set_id`, `stream`, `offset`, `limit`, `items` (with short IDs), `total`, `next_offset`, `uncertainties` |
| **Test coverage** | Session tests in `test_session.py`. Covered by progressive retrieval MCP tests |
| **Current role** | Pagination |

#### rsm_query_graph

| Property | Value |
|---|---|
| **Purpose** | Bounded traversal of the structural relation graph from seed entity IDs |
| **Handler** | `handle_query_graph` in `handlers.py` — calls `select_graph_neighbors` |
| **Input** | `entity_ids`, `relation_kinds`, `direction` (outgoing/incoming/both), `max_hops` (max 3), `limit` (max 100) |
| **Output** | `entity_ids`, `entities`, `relations`, `relation_keys`, `citations`, `uncertainties`, `budget` |
| **Test coverage** | 1 handler test (bounded traversal). Registry validated |
| **Current role** | Graph exploration |

#### rsm_validate_patch_context

| Property | Value |
|---|---|
| **Purpose** | Check whether a candidate patch's touched paths and referenced entities are covered by the local index |
| **Handler** | `handle_validate_patch_context` in `handlers.py` — path/entity ID overlap check, follow-up query suggestion |
| **Input** | `task`, `changed_paths`, `referenced_entity_ids`, `budget_chars` |
| **Output** | `covered_paths`, `missing_paths`, `covered_entity_ids`, `missing_entity_ids`, `suggested_context_query`, `suggested_follow_up_tools`, `uncertainties`, `budget` |
| **Test coverage** | 1 handler test (coverage vs correctness). Registry validated |
| **Current role** | Specialized patch-context check |

#### rsm_get_git_summary

| Property | Value |
|---|---|
| **Purpose** | Return minimal local Git repository summary for a bounded path |
| **Handler** | `handle_get_git_summary` in `handlers.py` — calls `get_git_repository_summary` |
| **Input** | `path` (optional, defaults to repo root) |
| **Output** | `repository_root`, `branch`, `head_commit`, `dirty`, `citations`, `uncertainties` |
| **Test coverage** | 1 handler test (path rejection). Registry validated |
| **Current role** | Low-level git info |

### 2.2 Store-mode tools (STORE_ONLY_TOOL_NAMES — 3 tools)

#### rsm_list_indexes

| Property | Value |
|---|---|
| **Purpose** | List all repositories registered in the RSM Index Store |
| **Handler** | `_tool_list_indexes` in `runtime.py` — calls `IndexRegistry.list_entries()` |
| **Input** | None |
| **Output** | `indexes` (list), `count`, `agent_instructions` |
| **Test coverage** | `test_store_mode.py`: 6 tests (empty store, one index, multiple indexes, registry, determinism). MCP `tools/list` and `tools/call` integration tests |
| **Current role** | Index discovery |

#### rsm_select_index

| Property | Value |
|---|---|
| **Purpose** | Select active repository index by repo_id, repo_root, or name |
| **Handler** | `_tool_select_index` in `runtime.py` — repo_id/repo_root/name matching, active_index validation |
| **Input** | `repo_id`, `repo_root`, `name` (at least one) |
| **Output** | `selected`, `active_repo` |
| **Test coverage** | `test_store_mode.py`: 4+ tests (by repo_id, by name, by repo_root, ambiguous name, missing DB). MCP integration tests |
| **Current role** | Index activation |

#### rsm_current_index

| Property | Value |
|---|---|
| **Purpose** | Return the currently active repository index, or recoverable no_active_index uncertainty |
| **Handler** | `_tool_current_index` in `runtime.py` |
| **Input** | None |
| **Output** | `active_repo` or `active_repo: null` + `uncertainties` + `agent_instructions` |
| **Test coverage** | Covered in `test_store_mode.py` as part of select-then-query flow |
| **Current role** | Session state introspection |

### 2.3 Critical implementation invariants

1. `build_tool_registry()` asserts `tuple(registry.keys()) == PHASE1_TOOL_NAMES` (line 914–916 of runtime.py)
2. `build_store_tool_registry()` asserts `tuple(combined.keys()) == STORE_TOOL_NAMES` (line 1177–1179)
3. `test_tool_registry_names_match_phase1_contract` asserts exact set match (test_server.py)
4. `test_build_store_tool_registry_matches_store_tool_names` asserts exact tuple match (test_store_mode.py)
5. `test_tool_registry_does_not_expose_deferred_tools` checks forbidden substrings (index, export, import, etc.)
6. `test_stdio_initialize_and_tools_list` checks `tools/list` names match `PHASE1_TOOL_NAMES`
7. Deferred tools: `rsm_index`, `rsm_export_ai`, `rsm_export_jsonl`, `rsm_import_jsonl`, `rsm_invariants_import`, `rsm_invariants_export`, `rsm_run_command`, `rsm_run_tests`, `rsm_apply_patch`

---

## 3. Target Tool Mapping

| Current tool | Target destination | Migration action | Alias/deprecation behavior | Implementation reuse | Test impact | Risk |
|---|---|---|---|---|---|---|
| `rsm_status` | Internal/debug | Keep registered, mark `[INTERNAL]` in description | Remains as-is. Status info injected into new tools via `active_repo` + `warnings` | No change | None (tests already pass) | Low |
| `rsm_search_symbols` | `rsm_search` | New wrapper, keep old as deprecated alias | Old tool: remains registered, marked `[DEPRECATED - use rsm_search]`. Calls same `handle_search_symbols` internally | New `_tool_search` calls `handle_search_symbols` + adds file/target processing | Handler tests unchanged. New tests for `rsm_search` wrapper | Medium |
| `rsm_explain_entity` | `rsm_find_related` | New wrapper, keep old as deprecated alias | Old tool: remains registered, marked `[DEPRECATED - use rsm_find_related]` | New `_tool_find_related` calls `handle_explain_entity` with wrapping | Handler tests unchanged. New tests for `rsm_find_related` | Medium |
| `rsm_build_context_pack` | `rsm_prepare_context` | New wrapper, keep old as deprecated alias | Old tool: remains registered, marked `[DEPRECATED - use rsm_prepare_context]`. Same handler behind a cleaned input schema | New `_tool_prepare_context` calls `_tool_build_context_pack` internals or directly calls `handle_build_context_pack` | Handler tests unchanged. New tests for `rsm_prepare_context`. **Critical:** benchmark quality must match | Low (same handler) |
| `rsm_get_context_page` | `rsm_get_context_page` | Keep as-is | No change needed. Already has correct name and contract | Already stable | No change | None |
| `rsm_query_graph` | `rsm_find_related` | Fold into `rsm_find_related` expansion | Old tool: remains registered, marked `[DEPRECATED - use rsm_find_related with graph_neighbors]`. New `_tool_find_related` calls `handle_query_graph` for graph_neighbors requests | New `_tool_find_related` dispatches to `handle_explain_entity` or `handle_query_graph` based on anchor/relation_groups | Handler tests unchanged | Medium |
| `rsm_validate_patch_context` | Internal/debug | Keep registered, mark `[INTERNAL]` in description | Remains as-is. Not folded into any public tool | No change | None | Low |
| `rsm_get_git_summary` | Internal/debug | Keep registered, mark `[INTERNAL]` in description | Remains as-is | No change | None | Low |
| `rsm_list_indexes` | Internal/debug | Keep registered, mark `[INTERNAL]` in description | Remains as-is in store mode. Not exposed on the public 4-tool surface | No change | None | Low |
| `rsm_select_index` | Internal/debug | Keep registered, mark `[INTERNAL]` in description | Remains as-is in store mode | No change | None | Low |
| `rsm_current_index` | Internal/debug | Keep registered, mark `[INTERNAL]` in description | Remains as-is in store mode | No change | None | Low |

---

## 4. Compatibility Phases

### Phase A — Add new tools as wrappers (tasks 61.3–61.6)

| Aspect | Detail |
|---|---|
| **Goal** | Register `rsm_prepare_context`, `rsm_search`, `rsm_find_related` alongside all existing tools |
| **Code behavior** | New tools are registered in `build_tool_registry()` alongside old tools. New `PHASE1_TOOL_NAMES` tuple includes both old and new names. Old tools unchanged. New tool handlers call existing internal handlers (wrappers, not rewrites) |
| **Test expectation** | Registry tests updated to expect the larger set. Old handler tests unchanged. New tests for wrapper behavior. **Critical:** `test_tool_registry_names_match_phase1_contract` must be updated with the new name list |
| **Documentation change** | Minimal. Agent instructions in `server.py` `_initialize_result` updated to reference new tools |
| **Rollback** | Remove new tools from registry. Revert `PHASE1_TOOL_NAMES`. Old tests pass without changes |

**Key code changes needed:**
- `PHASE1_TOOL_NAMES` tuple: add `"rsm_prepare_context"`, `"rsm_search"`, `"rsm_find_related"`
- `build_tool_registry()`: add 3 new `ToolDescriptor` entries
- New handler functions: `_tool_prepare_context`, `_tool_search`, `_tool_find_related`
- `build_store_tool_registry()`: auto-includes new tools via composition
- Update registry assertion to match new tuple
- Update `test_tool_registry_names_match_phase1_contract`
- Update `test_stdio_initialize_and_tools_list`

### Phase B — Mark old tools deprecated (task 61.7)

| Aspect | Detail |
|---|---|
| **Goal** | Add `[DEPRECATED]` and `[INTERNAL]` markers to tool descriptions |
| **Code behavior** | Tool descriptions in `ToolDescriptor.input_schema.description` get prefix markers. Handler logic unchanged. All tools still work |
| **Test expectation** | No test changes needed (descriptions are not asserted in tests). New tests verify deprecation markers are present |
| **Documentation change** | `AGENTS.md` updated. MCP usage docs updated. Agent instructions updated |
| **Rollback** | Remove description markers. No functional change |

**Marker format:**
- Public deprecated: `[DEPRECATED - use rsm_<target>] <original description>`
- Internal/debug: `[INTERNAL - debug tool] <original description>`

### Phase C — Prefer new tools in examples and prompts (task 61.8)

| Aspect | Detail |
|---|---|
| **Goal** | All documentation, examples, and agent instructions reference the 4 public tools |
| **Code behavior** | No code changes. Agent-facing instructions in `_initialize_result` (server.py) reference `rsm_search`, `rsm_find_related`, `rsm_prepare_context`, `rsm_get_context_page` |
| **Test expectation** | No test changes |
| **Documentation change** | `docs/usage/mcp.md`, `AGENTS.md`, `README.md` updated to show 4-tool workflow |
| **Rollback** | Revert documentation. No functional change |

### Phase D — Hide old tools from default surface ✅ IMPLEMENTED (61.9)

**Implemented in 61.9 via `--expose-all-tools`.** The design described below
was accurate and was followed cleanly. The implementation uses a
`public_only=True` parameter on `build_tool_registry()` and
`build_store_tool_registry()`, a `SessionConfig.expose_all_tools` flag, and
invocation-level rejection in `_dispatch`. Documentation was cleaned up in
61.11.

| Aspect | Detail |
|---|---|
| **Goal** | If MCP framework supports tool filtering, default `tools/list` returns only 4 public tools |
| **Code behavior** | `build_tool_registry()` gains a `public_only` parameter. When `True`, only 4 tools returned. Debug mode (`--expose-all` or `RSM_MCP_DEBUG=1`) returns full registry |
| **Test expectation** | New tests for public-only mode. Old tests still pass in debug/full mode |
| **Documentation change** | Document debug mode |
| **Rollback** | Remove `public_only` parameter. Full registry always returned |

**Current MCP framework limitation:** The phase 1 stdio JSON-RPC server does not
support tool hiding or namespacing. Phase D depends on:
- Updating the server to support a `public_only` toggle in session config
- Or, waiting for the MCP protocol to gain tool categorization support
- Until then, Phase B (description markers) is the primary mechanism

### Phase E — Remove old tools after compatibility window (future, if ever)

| Aspect | Detail |
|---|---|
| **Goal** | Remove old tools that have zero observed usage after a documented window |
| **Code behavior** | Remove from `PHASE1_TOOL_NAMES` and `build_tool_registry()`. Remove handler functions |
| **Test expectation** | Update registry assertion. Remove old handler tests. Keep wrapper handler tests |
| **Documentation change** | Remove old tool references |
| **Rollback** | Revert removal commits. Restore old handler functions |

**Likely removal candidates (only after compatibility window):**
- `rsm_get_git_summary` (low utility, no unique functionality)
- `rsm_current_index` (redundant with inline `active_repo`)
- `rsm_validate_patch_context` (specialized, no clear agent workflow)

**Likely permanent deprecated aliases:**
- `rsm_search_symbols` (many potential callers)
- `rsm_explain_entity` (entity detail is a common pattern)
- `rsm_build_context_pack` (CLI `rsm pack` users may also use MCP)
- `rsm_query_graph` (graph-specific callers)
- `rsm_status` (diagnostic value)
- Store-mode tools (store-mode infrastructure)

---

## 5. Deprecated Alias Strategy

### 5.1 Exact alias tools

These tools remain **exact aliases**: same handler, same input/output, same behavior.
Only the description changes.

| Old tool | New tool | Alias behavior |
|---|---|---|
| `rsm_build_context_pack` | `rsm_prepare_context` | Exact alias. Both call `handle_build_context_pack`. `rsm_prepare_context` adds `active_repo` + `warnings` fields |
| `rsm_get_context_page` | `rsm_get_context_page` | No rename needed. Already correct |

### 5.2 Wrapper tools with enhanced behavior

These tools get a new handler that wraps the old handler with additional processing.

| Old tool | New tool | Wrapper strategy |
|---|---|---|
| `rsm_search_symbols` | `rsm_search` | `rsm_search` calls `handle_search_symbols` then adds `active_repo`, `warnings`, cursor pagination, and scope/kind/role filtering. `rsm_search_symbols` remains untouched |
| `rsm_explain_entity` + `rsm_query_graph` | `rsm_find_related` | `rsm_find_related` dispatches to `handle_explain_entity` or `handle_query_graph` based on anchor type and relation_groups. Both old tools remain untouched |

### 5.3 Internal/debug tools

These tools remain registered but are clearly marked as internal.

| Tool | Marker | Rationale |
|---|---|---|
| `rsm_status` | `[INTERNAL - debug tool]` | Session diagnostics. Staleness/scope info surfaced via `warnings` in new tools |
| `rsm_validate_patch_context` | `[INTERNAL - debug tool]` | Specialized patch-context check. Not a core agent workflow |
| `rsm_get_git_summary` | `[INTERNAL - debug tool]` | Git info folded into `active_repo` + staleness |
| `rsm_list_indexes` | `[INTERNAL - store mode]` | Store-mode infrastructure |
| `rsm_select_index` | `[INTERNAL - store mode]` | Store-mode infrastructure |
| `rsm_current_index` | `[INTERNAL - store mode]` | Redundant with inline `active_repo` |

### 5.4 Deprecation description format

All deprecated tools get a prefix in their MCP `description` field:

```python
# Deprecated tool
ToolDescriptor(
    name="rsm_search_symbols",
    description="[DEPRECATED - use rsm_search] Search indexed entities by lexical BM25 query.",
    ...
)

# Internal tool
ToolDescriptor(
    name="rsm_status",
    description="[INTERNAL - debug tool] Return read-only session status.",
    ...
)
```

---

## 6. Internal/Debug Tool Strategy

### 6.1 Current MCP framework capability

**The current phase 1 stdio JSON-RPC server does not support tool hiding,
categorization, or namespacing.** All registered tools appear in `tools/list`.

Relevant code path:
- `server.py` `_tools_list_result()` calls `build_tool_registry()` or `build_store_tool_registry()`
- No filtering or categorization is applied
- `tools/list` returns all registered tools

### 6.2 Recommended strategy (until framework support)

Since tool hiding is not supported:

1. **All 14 tools (old 11 + new 3) remain public in `tools/list`** during Phase A
2. **Phase B adds description markers** to guide agents toward the 4 public tools
3. **Agent instructions** in the `initialize` response explicitly recommend the 4 public tools
4. **Documentation** prioritizes the 4-tool workflow

### 6.3 Future debug tool flag (Phase D)

When the server is updated to support tool filtering:

```python
class SessionConfig:
    repo_root: Path
    db_path: Path
    index_mode: Literal["explicit_db", "store"] = "explicit_db"
    expose_all_tools: bool = False  # NEW: debug flag
```

When `expose_all_tools=False` (default):
- `tools/list` returns only 4 public tools + store-mode tools (when applicable)
- Internal/debug and deprecated tools are hidden

When `expose_all_tools=True`:
- Full registry returned (14+ tools)

This approach:
- Keeps debug tools accessible via environment flag
- Does not require a separate MCP server binary
- Does not change the transport protocol
- Can be toggled per-session without breaking existing configs

---

## 7. Store-Mode Compatibility

### 7.1 Three options analyzed

#### Option A: Keep store-mode tools public (recommended for transition)

| Aspect | Detail |
|---|---|
| **Behavior** | `rsm_list_indexes`, `rsm_select_index`, `rsm_current_index` remain registered and visible in `tools/list`. Agent instructions mention them for multi-repo discovery |
| **Pros** | No breaking change. Store mode works without new features. Users can discover repos and select one |
| **Cons** | 3 extra tools on the surface during migration. Doesn't achieve the 4-tool target in store mode |
| **Decision** | **Recommended for Phase A–C** |

#### Option B: Make `repo` an optional argument on all 4 tools

| Aspect | Detail |
|---|---|
| **Behavior** | `rsm_search`, `rsm_find_related`, `rsm_prepare_context` accept an optional `repo` parameter (by `repo_id`, name, or path). When provided, the tool switches to that repo for that call. Store-mode tools become internal |
| **Pros** | Reduces tool count to exactly 4. No session-scoped repo management needed |
| **Cons** | Multi-repo safety relies on per-call `repo` parameter. Every call must re-resolve the repo. Increases complexity of every handler. Risk of accidental cross-repo queries |
| **Decision** | **Deferred.** Design is clear (61.1) but implementation requires careful safety testing |

#### Option C: Hybrid — keep store tools during transition, then hide later

| Aspect | Detail |
|---|---|
| **Behavior** | Phase A–C: Option A. Phase D: store tools move to internal/debug. Per-call `repo` parameter added to 4 public tools as alternative |
| **Pros** | Gradual migration. Store users are not broken. Per-call repo is added when ready |
| **Cons** | Longer migration. Two code paths for repo resolution |
| **Decision** | **Recommended.** This is the phased approach already defined in §4 |

### 7.2 Recommended: Option A → C

**Phase A–C:** Keep store-mode tools public. Agents interact:
1. `rsm_list_indexes` → discover available repos
2. `rsm_select_index({name: "my-project"})` → select one
3. `rsm_prepare_context({task: "fix bug"})` → pack built against selected repo
4. Every response includes `active_repo` → agent can confirm which repo

**Phase D (future):**
- Add optional `repo` parameter to all 4 public tools
- Move store tools to internal/debug
- Deprecate store tools in descriptions

---

## 8. Wrapper vs Rename Strategy

### 8.1 Decision: New wrapper first, no internal rename

**Preferred approach for the first implementation step (61.3–61.6):**

1. **New `PHASE1_TOOL_NAMES` tuple** includes both old and new names
2. **New `ToolDescriptor` entries** for new tools with clean input schemas
3. **New handler functions** that call existing internal handlers
4. **Old handlers remain untouched** — no internal renaming, no handler refactoring
5. **Old tools remain unchanged** — same names, same schemas, same behavior

### 8.2 Rationale

| Reason | Explanation |
|---|---|
| **Zero risk to existing users** | Old tools continue to work with identical behavior. No breaking changes |
| **No handler duplication avoided** | New handlers delegate to existing `handle_*` functions. No code copied |
| **Test confidence** | All existing handler tests pass. Registry tests are the only update needed |
| **Independent rollout** | New tools can be validated independently. Old tools provide a rollback path |
| **Clear deprecation timeline** | Old tools remain functional. New tools prove themselves. Migration is additive, not subtractive |

### 8.3 Example: rsm_prepare_context wrapper

```python
# Pseudocode — not implementation
def _tool_prepare_context(args, session, store):
    # Same dispatch as _tool_build_context_pack, but:
    # - renamed function
    # - cleaned input schema (fewer advanced flags)
    # - adds active_repo to output
    # - adds warnings (staleness, scope)
    result = _tool_build_context_pack(args, session, store)
    result["active_repo"] = _build_active_repo(session)
    result["warnings"] = _build_index_warnings(session)
    return result
```

### 8.4 When internal rename would be appropriate

After Phase E (removal), if old tools are removed, the internal codebase could
be cleaned up to remove the old handler names. But this is **not recommended**
until all old tools are actually removed.

---

## 9. Test Strategy

### 9.1 Phase A tests (add new tools)

| Test category | What to test | Existing test to update |
|---|---|---|
| **Registry assertion** | `build_tool_registry()` keys include new tool names | `test_tool_registry_names_match_phase1_contract` — update expected set |
| **Registry assertion (store)** | `build_store_tool_registry()` keys include new tools | `test_build_store_tool_registry_matches_store_tool_names` — auto-updates via `STORE_TOOL_NAMES` |
| **Tool list (MCP)** | `tools/list` returns new tool names | `test_stdio_initialize_and_tools_list` — update expected list |
| **Tool call** | Each new tool responds to `tools/call` | New tests: `test_stdio_prepare_context`, `test_stdio_search`, `test_stdio_find_related` |
| **Handler equivalence** | `rsm_prepare_context` returns same core data as `rsm_build_context_pack` | New test: compare outputs for the same task |
| **Active repo** | Every new tool response includes `active_repo` | New test per tool |
| **Warnings** | Stale/scoped index produces correct warnings | New test per tool |
| **Old tools still work** | All old tools respond to `tools/call` | Existing tests already pass |

### 9.2 Phase B tests (deprecation markers)

| Test category | What to test |
|---|---|
| **Deprecation markers** | Old tool descriptions start with `[DEPRECATED` or `[INTERNAL` |
| **No functional change** | Old tools still produce identical output |

### 9.3 Phase D tests (hide tools)

| Test category | What to test |
|---|---|
| **Public-only mode** | `tools/list` returns exactly 4+store tools when `expose_all_tools=False` |
| **Debug mode** | `tools/list` returns full registry when `expose_all_tools=True` |
| **Default behavior** | Default `expose_all_tools=False` (public-only) |
| **Store mode + public-only** | Store tools remain visible in public-only mode |

### 9.4 Benchmark regression (pinned to Phase A)

```bash
# CI benchmark must pass with rsm_prepare_context
rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml --db .rsm/ci_index.sqlite

# Manual benchmark must pass
rsm eval bench --dataset benchmarks/manual_external_benchmark_cases.yaml --mode manual --db .rsm/typer.sqlite
```

**Acceptance criteria:**
- `rsm_prepare_context` with `profile=agent_standard` and `detail_level=compact`
  produces the same `selected_files`, `selected_entities`, `selected_relations`,
  and `citations` as `rsm_build_context_pack` with the same inputs
- CI benchmark metrics are preserved (central_file_found, support_files_found,
  tests_found, noise_reduced, overall)

### 9.5 Summary of test changes by phase

| Phase | New tests | Update existing | Delete existing |
|---|---|---|---|
| A | 15+ (3 new tools × 5 tests each) | 2 (registry assertion, tools/list) | 0 |
| B | 2 (deprecation markers) | 0 | 0 |
| C | 0 | 0 | 0 |
| D | 4 (public-only mode) | 0 | 0 |
| E | 0 | 0 | Per-tool removal |

---

## 10. Rollback Strategy

### 10.1 Guarantees

1. **Old handlers are never modified.** All new tools are wrappers that call
   existing `handle_*` functions. Old `_tool_*` functions remain untouched.

2. **No storage or schema migration.** The SQLite index schema is unchanged.
   The `ResultStore` in-memory cache is unchanged.

3. **No benchmark or ranking changes.** The `build_context_pack` function is
   unchanged. CI benchmarks remain valid.

4. **No CLI changes.** `rsm mcp serve`, `rsm pack`, `rsm index` all work
   identically.

### 10.2 Rollback procedure

If Phase A causes problems:

```bash
# Step 1: Revert PHASE1_TOOL_NAMES to original 8 tools
# Step 2: Remove new ToolDescriptor entries from build_tool_registry()
# Step 3: Remove new handler functions
# Step 4: Revert test assertions to original set
# Step 5: Run tests → all pass
# Step 6: Verify old tools work → yes (they were never modified)
```

This is safe at any point because:
- Old tools are never changed
- New tools are additive
- No data migration is needed
- Tests are updated in the same commit

### 10.3 Fast rollback (within a single commit)

If Phase A changes are in a single commit:

```bash
git revert <phase-a-commit>
# All old tools return to their exact previous state
# Registry assertions pass
# Handler tests pass
```

---

## 11. Implementation Sequence

| Task | Description | Dependencies | New code? | Primary file changes |
|---|---|---|---|---|
| **61.3** | Implement `rsm_prepare_context` — new wrapper calling `handle_build_context_pack`. Add to `PHASE1_TOOL_NAMES`, `build_tool_registry()`. Add `active_repo` and `warnings` to output. Update registry and tools/list tests | 61.2 | Yes | `runtime.py`, `server.py`, `test_server.py` |
| **61.4** | Stabilize `rsm_get_context_page` — verify existing implementation. No code changes needed. Update description if needed | 61.1 | No | Docs only |
| **61.5** | Implement `rsm_search` — new wrapper calling `handle_search_symbols` + file/target processing. Add cursor-based pagination. Add search result ID cache. Add to `PHASE1_TOOL_NAMES`, `build_tool_registry()` | 61.2 | Yes | `runtime.py`, `handlers.py` (new), `session.py` (search cache), `test_server.py` |
| **61.6** | Implement `rsm_find_related` — anchor resolution, relation group dispatch, cursor pagination. Add to registry. New tests for wrappers | 61.2 | Yes | `runtime.py`, `handlers.py` (new), `test_server.py` |
| **61.7** | Add `[DEPRECATED]` and `[INTERNAL]` markers to old tool descriptions. Update agent instructions in `server.py` | 61.3–61.6 | Yes | `runtime.py` (descriptions only), `server.py` |
| **61.8** | MCP migration docs and examples. Update `docs/usage/mcp.md`, `AGENTS.md`, README | 61.7 | No | Docs only |

### Key dependency: PHASE1_TOOL_NAMES growth

The `PHASE1_TOOL_NAMES` tuple must be updated exactly once (in 61.3) to include
all 3 new tools. Subsequent tasks add to the registry but don't change the tuple.

```python
# After 61.3–61.6:
PHASE1_TOOL_NAMES: tuple[str, ...] = (
    "rsm_status",                    # internal/debug
    "rsm_search_symbols",            # deprecated
    "rsm_explain_entity",            # deprecated
    "rsm_build_context_pack",        # deprecated
    "rsm_get_context_page",          # public (unchanged)
    "rsm_query_graph",              # deprecated
    "rsm_validate_patch_context",    # internal/debug
    "rsm_get_git_summary",          # internal/debug
    # --- New tools ---
    "rsm_search",                    # public
    "rsm_find_related",              # public
    "rsm_prepare_context",           # public
)
```

Number of tools after Phase A: **11 old + 3 new = 14 total** (temporarily).

---

## 12. Decisions and Open Questions

### 12.1 Validated decisions

1. **New wrappers, not internal rename.** Old handlers are never modified. New
   tools call existing handlers. Risk is minimal.

2. **4 total Phase A–D tool names** with old tools retained as aliases. Net
   tool count temporarily increases from 11 to 14, then decreases to 4 public
   tools by Phase D.

3. **Phase A is safe at any point.** Old tools are unchanged. Registry tests
   are the only update needed. Rollback is a single git revert.

4. **`rsm_get_context_page` needs no migration.** Already stable and correctly
   named.

5. **Store-mode tools remain public during migration.** Multi-repo safety
   requires explicit repo selection. Per-call `repo` parameter is deferred.

6. **Deprecation via description text, not metadata.** The MCP framework does
   not support deprecation metadata. Description prefixes are the primary
   mechanism.

### 12.2 Open decisions

1. **Should `rsm_prepare_context` and `rsm_build_context_pack` share the same
   handler function entirely, or should `rsm_prepare_context` be a separate
   function that calls the old handler?**
   - Current direction: separate function that calls the old handler. Cleaner
     for phased cleanup.

2. **Should the `PHASE1_TOOL_NAMES` tuple be renamed when old tools are
   deprecated?**
   - Current direction: keep the name. The constant refers to "all registered
     tools" not "phase 1 tools."

3. **At what release version should Phase D (hiding tools) happen?**
   - Current direction: at least one minor version after Phase C is stable.

4. **Should `rsm_get_git_summary` be removed entirely or kept forever as
   internal?**
   - Current direction: kept as internal. Zero cost to maintain.

5. **Should the `expose_all_tools` flag default to `True` during Phase A–C?**
   - Current direction: yes. This gives users time to migrate before the
     default changes to `False` in Phase D.

### 12.3 Rejected approaches

1. **Immediate removal of old tools.** Rejected because it breaks every
   existing MCP user without warning.

2. **Internal renaming before wrappers.** Rejected because it introduces risk
   of breaking old handlers during the same change that adds new ones.

3. **Hiding store-mode tools before per-call `repo` argument is stable.**
   Rejected because multi-repo safety requires explicit repo selection.

4. **Adding graph/chunk/vector tools during MCP migration.** Rejected per
   61.0 decision. The MCP surface must be simplified before new capabilities
   are added.

5. **Adding a `deprecated: True` field to `ToolDescriptor`.** Rejected because
   the MCP protocol does not support tool deprecation metadata in `tools/list`.

6. **Making internal tools completely inaccessible (no registry entry).**
   Rejected because debug capability would be lost. Description markers are
   the right mechanism.

---

## Validation

This is a documentation-only change. No code was modified.

```bash
$ git diff --stat
 docs/design/mcp_compatibility_strategy.md | 544 ++++++++++++++++++++
 1 file changed, 544 insertions(+)

$ git status --short
?? docs/design/mcp_compatibility_strategy.md
```

No doc lint checks are configured for markdown files in this repository.

---

## 61.2 — Final Report

**File created:**
- `docs/design/mcp_compatibility_strategy.md`

**Current MCP tools inspected (11):**
- `rsm_status` → internal/debug
- `rsm_search_symbols` → deprecated alias for `rsm_search`
- `rsm_explain_entity` → deprecated alias for `rsm_find_related`
- `rsm_build_context_pack` → deprecated alias for `rsm_prepare_context`
- `rsm_get_context_page` → keep (already correct)
- `rsm_query_graph` → deprecated alias (folded into `rsm_find_related`)
- `rsm_validate_patch_context` → internal/debug
- `rsm_get_git_summary` → internal/debug
- `rsm_list_indexes` → internal/debug (store mode)
- `rsm_select_index` → internal/debug (store mode)
- `rsm_current_index` → internal/debug (store mode)

**Compatibility phases defined:**
- Phase A: Add new tools as wrappers (tools temporarily grow to 14)
- Phase B: Mark old tools deprecated in descriptions
- Phase C: Prefer new tools in docs and agent instructions
- Phase D: Hide old tools from default surface (if framework allows)
- Phase E: Remove old tools after compatibility window (if ever)

**Key migration decisions:**
- New wrappers, not internal rename. Old handlers never modified
- Store-mode tools remain public during migration. Per-call `repo` deferred
- `PHASE1_TOOL_NAMES` grows from 8 to 11 (temporarily 14 with both old+new)
- Deprecation via `[DEPRECATED]` / `[INTERNAL]` description prefixes
- 61.3 is the first implementation task (rsm_prepare_context wrapper)

**Open questions:**
- Shared handler function vs separate function for rsm_prepare_context
- PHASE1_TOOL_NAMES rename after deprecation?
- Version number for Phase D (hiding tools)
- rsm_get_git_summary: keep forever or remove?
- expose_all_tools default: True during Phase A–C?

**Recommended next step:**
61.3 — Implement `rsm_prepare_context` wrapper

**Validation:**
- `git diff --stat`: 1 file created
- `git status --short`: 1 new untracked file
- No code changed, no MCP/CLI/ranking/dependencies changed

**Status:**
- 61.2 complete ✓
