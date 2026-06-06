# MCP Tool Surface Minimization

> **Task:** 61.0 — Design-only  
> **Date:** 2026-06-06  
> **Branch:** `feat/benchmark-harness-59`  
> **Status:** Design complete. No code changed.

## 1. Purpose

RSM currently exposes **11 MCP tools** (8 repo-mode + 3 store-mode). This is too many.

The 60.0 Semble / CodeGraph / Cartog engineering review identified tool surface
size as a product-level architecture problem:

- **Agent tool overload.** Coding agents presented with 11 tools must choose among
  low-level status queries, graph traversals, symbol searches, and context-pack
  builders that overlap in purpose. This creates decision cost for every tool call.

- **Confusion between low-level and task-level tools.** `rsm_search_symbols`,
  `rsm_explain_entity`, `rsm_query_graph`, and `rsm_validate_patch_context` each
  address a useful operation, but agents should not need to compose them manually
  to get useful results. The current surface exposes internal retrieval mechanics
  rather than agent workflows.

- **Semble demonstrates a better model.** Semble exposes **2 tools** (`search`,
  `find_related`) that map directly to the agent workflow: initial discovery,
  then follow-up expansion. RSM has a different product identity (ContextPack
  compilation, not snippet search), but the principle of fewer, higher-level
  tools applies.

- **Debug capabilities do not belong on the public interface.** Low-level tools
  like `rsm_status`, `rsm_current_index`, and `rsm_get_git_summary` are useful
  for debugging and diagnostics, but they should not dominate the tool list that
  coding agents see by default.

- **Preservation of existing workflows.** The 59.x benchmark harness validates
  `rsm_build_context_pack` quality. The new surface must preserve benchmark
  quality and the CLI `rsm pack` command unchanged.

The target is a **maximum 4 public MCP tools**:

| Tool | Role |
|---|---|
| `rsm_search` | Broad discovery of files, symbols, docs, and tests |
| `rsm_find_related` | Relation-centered expansion around a known file, entity, or result |
| `rsm_prepare_context` | Primary coding-agent tool: builds a task-centered ContextPack |
| `rsm_get_context_page` | Pagination and continuation for prepared ContextPacks |

This is a **design document only**. No code, MCP behavior, CLI behavior, ranking,
or dependencies are changed in 61.0.

---

## 2. Current MCP Surface

All tools are defined in `src/repo_semantic_memory/mcp/runtime.py` (tool descriptors
and handlers) and `src/repo_semantic_memory/mcp/handlers.py` (pure handler functions).

### 2.1 Repo-mode tools (PHASE1_TOOL_NAMES)

These are available in both `--repo` and `--store` sessions.

#### rsm_status

| Property | Value |
|---|---|
| **Purpose** | Return read-only session status: configured --repo and --db, package/schema versions, entity/relation counts, index staleness metadata |
| **Input** | None |
| **Output** | `repo_root`, `db_path`, `db_exists`, `package_version`, `schema_version`, `entity_count`, `relation_count`, `index_status`, `index_status_reason`, `indexed_at`, `current_git_head`, `working_tree_dirty`, `suggested_action`, `index_scope` |
| **Workflow role** | Session initialization and diagnostics |
| **Level** | Low-level (infrastructure) |
| **Target** | Internal/debug |

#### rsm_search_symbols

| Property | Value |
|---|---|
| **Purpose** | Search indexed entities by lexical BM25 query with optional kind/path_role filters and relation inclusion |
| **Input** | `query`, `limit` (default 10, max 100), `entity_kinds`, `path_roles`, `include_relations` |
| **Output** | `matches` (entity IDs), `results` (entity dicts with scores/paths/roles), `citations`, `uncertainties`, `budget` |
| **Workflow role** | Initial discovery of symbols/files |
| **Level** | Mid-level (narrow: entities only, no files/docs/tests expansion) |
| **Target** | Fold into `rsm_search` |

#### rsm_explain_entity

| Property | Value |
|---|---|
| **Purpose** | Resolve one entity with structural context, incoming/outgoing relations, semantic components, and citations |
| **Input** | `entity_id`, `include_incoming_relations`, `include_outgoing_relations`, `include_components`, `include_claims` |
| **Output** | `entity_id`, `entity` payload, `relations`, `semantic_components`, `related_entity_ids`, `citations`, `uncertainties` |
| **Workflow role** | Follow-up detail on a specific entity found via search |
| **Level** | Mid-level (entity-focused) |
| **Target** | Fold into `rsm_find_related` |

#### rsm_build_context_pack

| Property | Value |
|---|---|
| **Purpose** | Build a deterministic, source-cited, budget-bounded context pack for a task. Returns a brief first-page preview by default plus a session-scoped `result_set_id` |
| **Input** | `task`, `budget_chars` (max 20000), `format`, `profile`, `detail_level` (brief/compact), `explain_ranking`, `include_semantic_components`, `include_rendered`, `include_payload`, `include_ranking_breakdowns`, `max_files`, `max_entities`, `max_relations`, `max_citations` |
| **Output** | `result_set_id`, `counts` (per stream), `selected_files` (preview), `selected_entities` (preview), `selected_relations` (preview), `citations` (preview), `next` (available streams for paging), `uncertainties`, `budget`, plus scope/staleness warnings |
| **Workflow role** | Primary coding-agent tool: task → context |
| **Level** | High-level |
| **Target** | Rename to `rsm_prepare_context`, keep as primary tool |

#### rsm_get_context_page

| Property | Value |
|---|---|
| **Purpose** | Page over a previously-built context pack without recomputing. Returns a deterministic slice of the requested stream |
| **Input** | `result_set_id`, `stream` (files/entities/relations/citations/ranking_breakdowns), `offset`, `limit` (1-20) |
| **Output** | `result_set_id`, `stream`, `offset`, `limit`, `items` (with short IDs), `total`, `next_offset`, `uncertainties` |
| **Workflow role** | Progressive retrieval continuation |
| **Level** | High-level (session-bound) |
| **Target** | Keep as-is, rename to match new surface convention |

#### rsm_query_graph

| Property | Value |
|---|---|
| **Purpose** | Bounded traversal of the structural relation graph from seed entity IDs |
| **Input** | `entity_ids`, `relation_kinds`, `direction` (outgoing/incoming/both), `max_hops` (max 3), `limit` (max 100) |
| **Output** | `entity_ids`, `entities`, `relations`, `relation_keys`, `citations`, `uncertainties`, `budget` |
| **Workflow role** | Graph exploration around known entities |
| **Level** | Mid-level (graph traversal) |
| **Target** | Fold into `rsm_find_related` |

#### rsm_validate_patch_context

| Property | Value |
|---|---|
| **Purpose** | Check whether a candidate patch's touched paths and referenced entities are covered by the local index |
| **Input** | `task`, `changed_paths`, `referenced_entity_ids`, `budget_chars` |
| **Output** | `covered_paths`, `missing_paths`, `covered_entity_ids`, `missing_entity_ids`, `suggested_context_query`, `suggested_follow_up_tools`, `uncertainties`, `budget` |
| **Workflow role** | Patch context sufficiency check |
| **Level** | Mid-level (specialized) |
| **Target** | Internal/debug. The validation logic is useful but does not belong on the public 4-tool surface |

#### rsm_get_git_summary

| Property | Value |
|---|---|
| **Purpose** | Return minimal local Git repository summary for a bounded path |
| **Input** | `path` (optional, defaults to repo root) |
| **Output** | `repository_root`, `branch`, `head_commit`, `dirty`, `citations`, `uncertainties` |
| **Workflow role** | Git context for the session |
| **Level** | Low-level (infrastructure) |
| **Target** | Fold into `rsm_status` output (internal). Not needed as standalone public tool |

### 2.2 Store-mode tools (STORE_ONLY_TOOL_NAMES)

#### rsm_list_indexes

| Property | Value |
|---|---|
| **Purpose** | List all repositories registered in the RSM Index Store with best-effort status |
| **Input** | None |
| **Output** | `indexes` (list of repo_id, name, repo_root, db_path, status), `count`, `agent_instructions` |
| **Workflow role** | Index discovery in store mode |
| **Level** | Low-level (infrastructure) |
| **Target** | Internal/debug. Store mode itself is a deployment concern, not an agent workflow |

#### rsm_select_index

| Property | Value |
|---|---|
| **Purpose** | Select the active repository index for this MCP session by repo_id, repo_root, or name |
| **Input** | `repo_id`, `repo_root`, `name` (at least one) |
| **Output** | `selected`, `active_repo` |
| **Workflow role** | Index activation in store mode |
| **Level** | Low-level (infrastructure) |
| **Target** | Internal/debug |

#### rsm_current_index

| Property | Value |
|---|---|
| **Purpose** | Return the currently active repository index, or a recoverable no_active_index uncertainty |
| **Input** | None |
| **Output** | `active_repo` or `active_repo: null` + `uncertainties` |
| **Workflow role** | Session state introspection |
| **Level** | Low-level (infrastructure) |
| **Target** | Internal/debug |

### 2.3 Deferred tools (not yet exposed)

These tools are listed in `DEFERRED_TOOL_NAMES` and are intentionally not
registered in phase 1: `rsm_index`, `rsm_export_ai`, `rsm_export_jsonl`,
`rsm_import_jsonl`, `rsm_invariants_import`, `rsm_invariants_export`,
`rsm_run_command`, `rsm_run_tests`, `rsm_apply_patch`.

---

## 3. Target MCP Surface

### 3.1 rsm_search — Broad Discovery

| Property | Value |
|---|---|
| **Role** | Initial discovery of files, symbols, docs, and tests relevant to a task or query |
| **Primary use case** | "Find where X is implemented", "Find tests for Y", "Find docs about Z" |
| **Input schema concept** | `query` (string, required), `scope` (enum: files/symbols/tests/docs/all, default all), `limit` (int, default 10, max 25), `profile` (string, default agent_standard) |
| **Output schema concept** | `results` (list of matched items with path, kind, name, score, selection_reason), `total`, `uncertainties` (broad_query, no_results, index_scope_warning), `active_repo` |
| **Pagination** | Results are a flat list with `total`; no session-scoped result sets. Re-call with refined query for more |
| **Error behavior** | No active repo → `no_active_index` uncertainty. Stale index → warning in uncertainties. Empty query → `empty_query` error |
| **Active repo behavior** | Requires an active index (explicit `--repo`/`--db` or store-mode selection). `active_repo` is included in every response |
| **Benchmark relevance** | Needs new benchmark cases (61.5). Existing 59.x benchmarks validate context-pack quality, not search quality |
| **Relationship to internals** | Unifies `rsm_search_symbols` (BM25 entity search) with path-role-aware file discovery. Files are first-class results, not just entities. Does NOT include graph traversal or entity detail — those belong to `rsm_find_related` |

**What rsm_search should NOT do:**
- Build a full ContextPack (use `rsm_prepare_context`)
- Traverse relation graphs (use `rsm_find_related`)
- Return entity details with relations/components (use `rsm_find_related`)
- Return unpaged results beyond the limit
- Modify the index

### 3.2 rsm_find_related — Relation-Centered Expansion

| Property | Value |
|---|---|
| **Role** | Expand around a known file, entity, or search result to find related code, tests, docs, and dependencies |
| **Primary use case** | "What tests cover this file?", "What imports this symbol?", "What is related to entity X?" |
| **Input schema concept** | `target` (file path or entity_id, required), `relation_kinds` (list of relation kind strings, optional), `direction` (outgoing/incoming/both, default both), `max_depth` (int, default 1, max 3), `limit` (int, default 10, max 50) |
| **Output schema concept** | `target` (what was expanded from), `related` (list of related items with path, kind, name, relation_kind, direction), `total`, `uncertainties`, `active_repo` |
| **Pagination** | Flat list with `total`. For deeper expansions, re-call with a different target |
| **Error behavior** | Unknown target → `target_not_found` uncertainty. Too-broad expansion → `expansion_capped` uncertainty |
| **Active repo behavior** | Same as `rsm_search` |
| **Benchmark relevance** | Needs new benchmark cases (61.6) for relation accuracy |
| **Relationship to internals** | Unifies `rsm_explain_entity` (entity detail) and `rsm_query_graph` (graph traversal). The entity-centric detail view becomes one mode of `rsm_find_related`. Graph traversal becomes relation-centric expansion from any anchor point |

**What rsm_find_related should NOT do:**
- Perform broad search (use `rsm_search`)
- Build a ContextPack (use `rsm_prepare_context`)
- Return unbounded graph expansions
- Return all relations for an entity without filtering

### 3.3 rsm_prepare_context — Primary Coding-Agent Tool

| Property | Value |
|---|---|
| **Role** | Build a task-centered, budget-bounded, source-cited ContextPack for a coding agent |
| **Primary use case** | "Prepare context for implementing feature X", "Give me the relevant files for fixing bug Y" |
| **Input schema concept** | `task` (string, required), `budget_chars` (int, default 8000, max 20000), `detail_level` (brief/compact, default brief), `profile` (string, default agent_standard) |
| **Output schema concept** | `result_set_id`, `task`, `counts` (files/entities/relations/citations), `preview` (first page of each stream), `next` (streams with more items), `uncertainties`, `budget`, `active_repo`, `index_scope` |
| **Pagination** | Via `rsm_get_context_page` with `result_set_id` |
| **Error behavior** | No active repo → `no_active_index`. Stale index → scope warning. Budget exceeded → `budget_capped` |
| **Active repo behavior** | Same as `rsm_search` |
| **Benchmark relevance** | Directly validated by 59.x benchmarks (central_file_found, support_files_found, tests_found, noise_reduced, overall). Must preserve benchmark quality |
| **Relationship to internals** | Direct replacement for `rsm_build_context_pack`. Same handler logic, cleaner name. The current `build_context_pack` handler in `handlers.py` is the foundation. CLI `rsm pack` is unchanged |

**What rsm_prepare_context should NOT do:**
- Return full unpaged payloads (use `rsm_get_context_page`)
- Modify the index
- Accept arbitrary `include_*` flags that mirror internal implementation details
- Return rendered Markdown by default (opt-in only, for backward compatibility)

**Key differences from current `rsm_build_context_pack`:**
- Cleaner name: `prepare_context` signals intent (preparation for the agent), not mechanics (building)
- Reduced input surface: remove `include_semantic_components`, `include_ranking_breakdowns`, `format` from the default input schema. Keep them as opt-in advanced parameters
- `include_rendered` and `include_payload` remain as advanced opt-in flags for backward compatibility

### 3.4 rsm_get_context_page — Pagination

| Property | Value |
|---|---|
| **Role** | Page over a previously-prepared ContextPack without recomputing |
| **Primary use case** | "Show me more files from the context pack", "Give me the citations I missed" |
| **Input schema concept** | `result_set_id` (string, required), `stream` (files/entities/relations/citations/ranking_breakdowns, required), `offset` (int, default 0), `limit` (int, default 5, max 20) |
| **Output schema concept** | `result_set_id`, `stream`, `offset`, `limit`, `items` (with short IDs), `total`, `next_offset`, `uncertainties` |
| **Pagination** | This IS the pagination tool |
| **Error behavior** | Unknown/expired result_set_id → `result_set_unknown` uncertainty (recoverable). Invalid stream → tool-call error. Out-of-range offset → tool-call error |
| **Active repo behavior** | Does not depend on active repo (operates on session-local result sets) |
| **Benchmark relevance** | Must be tested for pagination correctness. Does not affect ranking metrics |
| **Relationship to internals** | Identical to current `rsm_get_context_page`. Keep as-is |

---

## 4. Tool Responsibilities

### Clear boundaries

```
┌─────────────────────────────────────────────────────┐
│                  Agent workflow                       │
│                                                       │
│  1. rsm_search("find LifecycleComponent")             │
│     → broad discovery, returns file/symbol list       │
│                                                       │
│  2. rsm_find_related("src/.../lifecycle_component.py")│
│     → what tests, imports, dependencies relate?       │
│                                                       │
│  3. rsm_prepare_context("implement activation gating")│
│     → build full ContextPack, get result_set_id       │
│                                                       │
│  4. rsm_get_context_page(result_set_id, entities)     │
│     → page more entities from the same pack           │
└─────────────────────────────────────────────────────┘
```

### rsm_search boundaries

```
SHOULD:
- Return files, symbols, docs, and tests matching a query
- Support broad and narrow scopes
- Return compact results with paths, kinds, names, and selection reasons
- Include active_repo in every response
- Signal index scope/staleness in uncertainties

SHOULD NOT:
- Return entity detail (use rsm_find_related)
- Return relations or graph expansions
- Build a ContextPack (use rsm_prepare_context)
- Return unpaged large payloads
```

### rsm_find_related boundaries

```
SHOULD:
- Start from a file path or entity_id
- Return related files/symbols with relation kind and direction
- Support depth-bounded expansion
- Support relation kind filtering

SHOULD NOT:
- Do broad search (use rsm_search)
- Build a ContextPack (use rsm_prepare_context)
- Return unbounded graph (max depth is enforced)
- Return entity detail for every related item (compact by default)
```

### rsm_prepare_context boundaries

```
SHOULD:
- Accept a natural-language task description
- Return a budget-bounded ContextPack with preview and result_set_id
- Support progressive retrieval via rsm_get_context_page
- Preserve all 59.x benchmark quality metrics
- Include active_repo and index scope warnings

SHOULD NOT:
- Return full rendered output by default
- Expose internal ranking/selection parameters as required inputs
- Modify the index
- Require pagination for basic use (preview is sufficient)
```

### rsm_get_context_page boundaries

```
SHOULD:
- Page over any stream from a stored result set
- Return deterministic slices with stable short IDs
- Handle expired result sets gracefully

SHOULD NOT:
- Recompute the context pack
- Access the index or filesystem
- Depend on active repo state
```

---

## 5. Mapping from Current Tools to Target Tools

| Current tool | Current role | Target destination | Migration strategy | Compatibility risk | Notes |
|---|---|---|---|---|---|
| `rsm_status` | Session diagnostics, index metadata, staleness | Internal/debug | Keep available but mark as internal. Fold staleness/scope into `rsm_search`/`rsm_prepare_context` output | Low: no agent workflow depends on `rsm_status` | Status info is useful for debugging but not for agent workflows |
| `rsm_search_symbols` | BM25 entity search | Fold into `rsm_search` | `rsm_search` subsumes entity search and adds file/docs/test discovery. Keep `rsm_search_symbols` as deprecated alias during migration | Medium: agents that use `rsm_search_symbols` need to migrate to `rsm_search` | The BM25 entity search is the core engine; `rsm_search` wraps it with broader output |
| `rsm_explain_entity` | Entity detail with relations | Fold into `rsm_find_related` | `rsm_find_related` with `target=entity_id` returns entity detail + relations. Keep `rsm_explain_entity` as deprecated alias | Medium: entity detail is a common follow-up pattern | The entity detail view is useful; it becomes one mode of `rsm_find_related` |
| `rsm_build_context_pack` | ContextPack builder | Rename to `rsm_prepare_context` | Same handler, cleaner name. Keep `rsm_build_context_pack` as deprecated alias | Low: same behavior, different name | The handler logic is unchanged; only the tool name and input schema are refined |
| `rsm_get_context_page` | Pagination | Keep as `rsm_get_context_page` | No change | None | Already clean and stable |
| `rsm_query_graph` | Graph traversal | Fold into `rsm_find_related` | `rsm_find_related` with `max_depth > 1` provides bounded graph expansion. Keep `rsm_query_graph` as deprecated alias | Medium: graph traversal callers need to use `rsm_find_related` with depth | Graph expansion is valuable but should not be a separate tool |
| `rsm_validate_patch_context` | Patch context check | Internal/debug | Keep available but mark as internal. The validation logic is useful for debugging context sufficiency | Low: specialized tool, rarely used by agents | May be exposed as an advanced mode later |
| `rsm_get_git_summary` | Git metadata | Internal/debug | Git info folded into `rsm_status` output. Not needed as standalone tool | Low: low agent utility | Repository metadata is infrastructure, not agent workflow |
| `rsm_list_indexes` | Store index discovery | Internal/debug | Keep for store-mode debugging. Not exposed to coding agents | Low: store mode is a deployment concern | Agents that need multi-repo discovery should use a separate mechanism |
| `rsm_select_index` | Store index selection | Internal/debug | Same as above | Low | Same rationale |
| `rsm_current_index` | Active index query | Internal/debug | Same as above. `active_repo` is included in every `rsm_search`/`rsm_find_related`/`rsm_prepare_context` response | Low | Redundant with inline `active_repo` fields |

---

## 6. Public vs Internal/Debug Tools

### Categories

| Category | Definition | Tools |
|---|---|---|
| **Public stable** | The 4-tool surface exposed to coding agents. Semver-protected. Changes require deprecation notices | `rsm_search`, `rsm_find_related`, `rsm_prepare_context`, `rsm_get_context_page` |
| **Public deprecated** | Current tools kept as aliases during migration, marked deprecated in descriptions | `rsm_search_symbols`, `rsm_explain_entity`, `rsm_build_context_pack`, `rsm_query_graph` |
| **Internal/debug** | Tools available but not advertised as public. Useful for diagnostics, not for agent workflows | `rsm_status`, `rsm_validate_patch_context`, `rsm_get_git_summary`, `rsm_list_indexes`, `rsm_select_index`, `rsm_current_index` |
| **Removed later** | Tools that may be removed after a compatibility window if no usage is observed | `rsm_get_git_summary` (redundant with status), `rsm_current_index` (redundant with inline fields) |

### Important design principle

Low-level capabilities remain available for debugging, but they should not
dominate the public agent interface. The MCP `tools/list` response should
prioritize the 4 public tools. If the MCP framework supports tool
categorization or hiding, internal tools should be gated behind a debug
flag or a separate tool namespace.

**Current limitation:** The phase 1 JSON-RPC server does not support tool
categorization or hiding. All registered tools appear in `tools/list`.
Until this is addressed (61.7), the deprecation strategy relies on:
- Tool descriptions marked with `[DEPRECATED]` prefix
- Agent instructions that guide toward the 4 public tools
- Documentation that lists the public surface

---

## 7. Compatibility Plan

### Phase A — Add new high-level tools while keeping old tools (61.3–61.6)

```
- Implement rsm_prepare_context (wraps existing build_context_pack handler)
- Implement rsm_get_context_page (already exists, keep as-is)
- Implement rsm_search (wraps search_symbols + file discovery)
- Implement rsm_find_related (wraps explain_entity + query_graph)
- All old tools remain available and unchanged
- Registry includes both old and new tools
```

### Phase B — Mark old tools deprecated (61.7)

```
- Add [DEPRECATED] prefix to old tool descriptions
- Add agent instructions pointing to new tools
- Document migration path in AGENTS.md and MCP usage docs
- Old tools continue to work with identical behavior
```

### Phase C — Hide old tools from default interface (61.7, if framework allows)

```
- If MCP framework supports tool filtering/hiding:
  - Default tools/list returns only the 4 public tools
  - Debug flag (--expose-all or similar) returns full registry
- If not supported:
  - Stay in Phase B until the framework or transport supports it
```

### Phase D — Remove only after compatibility window (future, if ever)

```
- Remove only if zero observed usage after a documented window
- Likely candidates: rsm_get_git_summary, rsm_current_index
- Keep deprecated aliases indefinitely for tools that agents may have scripted
```

### Current MCP framework limitation

The phase 1 stdio JSON-RPC server does not support tool categorization,
hiding, or namespacing. Until this is addressed:
- All tools appear in `tools/list`
- Agent instructions and documentation are the primary mechanism for
  guiding agents toward the 4 public tools
- The `instructions` field in the `initialize` response should list the
  4 recommended tools

---

## 8. Output Schema Design Principles

All target tools should follow these output principles:

| Principle | Implementation |
|---|---|
| **Stable source_path fields** | Every file reference uses `path` (repo-relative, POSIX separators). Consistent across all tools |
| **Explicit active_repo** | `rsm_search`, `rsm_find_related`, `rsm_prepare_context` include `active_repo` in every response |
| **Index status/staleness/scope warnings** | Present in `uncertainties` when relevant. Never fatal — always recoverable |
| **Compact summaries by default** | First response is small (2-4 KB). Details available via pagination or follow-up calls |
| **Page tokens for large payloads** | `rsm_prepare_context` returns `result_set_id`. `rsm_get_context_page` pages over streams |
| **Machine-readable reason codes** | Every uncertainty has a stable `code` (e.g., `no_active_index`, `budget_capped`, `result_set_unknown`) |
| **Human-readable explanation strings** | Every uncertainty has a `message` field |
| **Deterministic ordering** | Results are sorted lexicographically or by deterministic score. No random ordering |
| **No huge unpaged MCP payloads** | All large outputs are behind `result_set_id` + pagination or explicit `limit` caps |
| **agent_instructions in responses** | Every response includes `agent_instructions` or `uncertainties` that guide the next action |

---

## 9. Error Model

### Common error patterns

| Error condition | Type | Tool(s) affected | Handling |
|---|---|---|---|
| **No active repo** | Recoverable uncertainty | `rsm_search`, `rsm_find_related`, `rsm_prepare_context` | Return `no_active_index` uncertainty with agent instructions |
| **Unknown repo/index** | Fatal tool error | `rsm_select_index` (store mode only) | Tool-call error with message |
| **Stale index** | Warning uncertainty | All repo tools | Return `stale_index` uncertainty, results still served |
| **Missing index** | Fatal tool error | All repo tools (startup) | Server startup error, not a per-call error |
| **Invalid page token** | Recoverable uncertainty | `rsm_get_context_page` | Return `result_set_unknown` uncertainty |
| **Expired context pack** | Recoverable uncertainty | `rsm_get_context_page` | Return `result_set_unknown` uncertainty, suggest re-calling `rsm_prepare_context` |
| **Query too broad** | Warning uncertainty | `rsm_search` | Return `broad_query` uncertainty, results still served up to limit |
| **No results** | Informational uncertainty | `rsm_search`, `rsm_find_related` | Return `no_results` uncertainty, empty results |

### Fatal vs warning distinction

- **Fatal:** The request cannot be satisfied at all. Return a tool-call error (JSON-RPC error or `isError: true`).
- **Warning/recoverable:** The request was processed but with caveats. Return results + uncertainties. The agent can proceed or adjust.

---

## 10. Benchmark and Regression Strategy

### rsm_prepare_context must preserve 59.x benchmark quality

The 59.x benchmark harness validates `build_context_pack` quality. Since
`rsm_prepare_context` uses the same handler, benchmark quality should be
preserved by construction. Metrics to preserve:

- `central_file_found` — at least one central file in selected files
- `support_files_found` — support files present when expected
- `tests_found` — test files present when expected
- `noise_reduced` — forbidden files absent
- `overall` — composite score

Validation command after 61.3:

```bash
rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml --db .rsm/ci_index.sqlite
```

### rsm_search and rsm_find_related need future benchmarks

Current benchmarks only validate context-pack quality. New benchmark cases needed:

- **rsm_search cases (61.5):** file discovery, symbol discovery, doc discovery,
  test discovery, broad query handling, no-results handling
- **rsm_find_related cases (61.6):** test-to-impl relation, import adjacency,
  graph depth bounding, unknown target handling

### rsm_get_context_page pagination tests

Not a ranking concern, but pagination correctness must be tested:
- Page boundaries match stream totals
- Short IDs are stable within a result set
- Expired result sets produce recoverable uncertainties
- All streams (files, entities, relations, citations, ranking_breakdowns)
  paginate correctly

---

## 11. Implementation Sequence

This is the proposed task order. Do not implement now (61.0 is design-only).

| Task | Description | Dependencies |
|---|---|---|
| **61.1** | Design 4-tool RSM MCP interface (detailed input/output schemas) | 61.0 |
| **61.2** | Existing MCP compatibility strategy (deprecation notices, agent instructions) | 61.0 |
| **61.3** | Implement `rsm_prepare_context` (rename + clean input schema) | 61.1, 61.2 |
| **61.4** | Stabilize `rsm_get_context_page` (already exists, verify + document) | 61.1 |
| **61.5** | Implement `rsm_search` (unify search_symbols + file/docs/tests discovery) | 61.1, 61.2 |
| **61.6** | Implement `rsm_find_related` (unify explain_entity + query_graph) | 61.1, 61.2 |
| **61.7** | Deprecate/hide low-level MCP tools (descriptions, docs, agent instructions) | 61.3–61.6 |
| **61.8** | MCP migration docs and examples | 61.3–61.7 |

### Why this order?

1. `rsm_prepare_context` first because it's the lowest-risk change (rename only)
   and preserves all benchmark quality.
2. `rsm_get_context_page` next because it already exists and needs no change.
3. `rsm_search` and `rsm_find_related` require new handler logic and benchmarks.
4. Deprecation comes last, after the new tools are stable and benchmarked.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| **Breaking existing MCP users** | Phase A keeps all old tools. Deprecation notices are additive. No removal without a compatibility window |
| **Hiding useful debug tools too early** | Internal tools remain available. Only the default `tools/list` narrows (Phase C). Debug flag restores full registry |
| **Creating too-large high-level payloads** | `rsm_prepare_context` keeps the progressive retrieval model. `rsm_search` has a hard limit. `rsm_find_related` has depth/limit caps |
| **Making rsm_prepare_context too magical** | The tool accepts a natural-language task and returns deterministic results. Selection is transparent via selection_reasons. No hidden LLM calls |
| **Duplicating CLI behavior inconsistently** | MCP handlers call the same pure functions as CLI. CLI `rsm pack` is unchanged |
| **Increasing tool count instead of reducing it** | Hard rule: net tool count must decrease. New tools replace old tools, not add to them |
| **Losing explicit repo/index control** | `active_repo` is in every response. Store-mode selection is still available for debugging |
| **Poor page-token lifecycle** | `result_set_id` is session-scoped and LRU-evicted. `result_set_unknown` is recoverable |
| **Stale context packs across repo changes** | Scope/staleness warnings are in every `rsm_prepare_context` response. Agents are told to re-prepare after repo changes |

---

## 13. Decisions and Open Questions

### Validated decisions

1. **Target is 4 public tools, not 2.** RSM's product identity is ContextPack
   compilation, not snippet search. Two tools (like Semble) would hide too much
   useful capability. Four tools is the right balance.

2. **`rsm_prepare_context` replaces `rsm_build_context_pack`.** Same handler,
   cleaner name. The current progressive retrieval model (result_set_id +
   `rsm_get_context_page`) is preserved.

3. **`rsm_search` and `rsm_find_related` subsume 4 current tools.** This is
   the core simplification: `rsm_search_symbols` → `rsm_search`,
   `rsm_explain_entity` + `rsm_query_graph` → `rsm_find_related`.

4. **Low-level tools are kept available but demoted to internal/debug.**
   Removing them entirely would hurt debuggability. Hiding them from the
   default interface is sufficient.

5. **CLI `rsm pack` is unchanged.** The MCP surface minimization does not
   affect the CLI, which remains the scriptable, full-output interface.

### Open decisions

1. **Should `rsm_search` include entity detail in results, or only file/symbol references?**
   - Option A: Compact results (path, kind, name, score). Details via `rsm_find_related`.
   - Option B: Include entity detail inline for top-K results.
   - Default direction: Option A, consistent with compact-by-default principle.

2. **Should `rsm_find_related` anchor on file path, entity_id, or both?**
   - Current thinking: both. `target` accepts a file path or entity_id string.
   - If both are provided, entity_id takes precedence.

3. **Should `rsm_search` and `rsm_find_related` use the same result_set_id pagination model?**
   - Current thinking: no. These tools return flat lists with `total`.
   - Re-calling with refined parameters is simpler than session-scoped result sets for discovery.
   - Only `rsm_prepare_context` needs session-scoped result sets (the pack is expensive to recompute).

4. **Should store-mode tools (`rsm_list_indexes`, `rsm_select_index`, `rsm_current_index`) be hidden or kept?**
   - Current thinking: hidden from default interface, available in debug mode.
   - Store mode is a deployment concern, not a coding-agent workflow.

5. **Should `include_rendered` and `include_payload` remain on `rsm_prepare_context`?**
   - Current thinking: keep as advanced opt-in parameters for backward compatibility.
   - Default behavior stays compact (brief preview).

### Rejected approaches

1. **Exposing every internal operation as an MCP tool.**
   - Rejected. This is the current state. It creates agent tool overload.

2. **Removing low-level tools immediately.**
   - Rejected. Debuggability matters. Phase A keeps everything; later phases hide, not remove.

3. **Adding graph/chunk/vector tools before the 4-tool interface is stable.**
   - Rejected. The 60.0 review identified MCP surface minimization as the
     highest-leverage improvement. New capabilities (chunks, embeddings, graph
     storage) should come after the interface is stable and benchmarked.

4. **Copying Semble's 2-tool surface exactly.**
   - Rejected. RSM is a ContextPack compiler, not a snippet search engine.
     Two tools would hide context-pack preparation and pagination, which are
     core RSM capabilities.

5. **Making `rsm_prepare_context` fully automated (no task parameter).**
   - Rejected. The task description is essential for ranking and selection.
     Removing it would make the tool a generic repo dump, not a task-centered pack.

---

## Validation

This is a documentation-only change. No code was modified.

```bash
$ git diff --stat
 docs/design/mcp_tool_surface_minimization.md | 476 ++++++++++++++++++++
 1 file changed, 476 insertions(+)

$ git status --short
?? docs/design/mcp_tool_surface_minimization.md
```

No doc lint checks are configured in this repository for markdown files.
The file is valid Markdown with no YAML frontmatter requirements.

---

## 61.0 — Final Report

**File created:**
- `docs/design/mcp_tool_surface_minimization.md`

**Current MCP tools inspected:**
- `rsm_status` — session diagnostics (→ internal/debug)
- `rsm_search_symbols` — BM25 entity search (→ fold into `rsm_search`)
- `rsm_explain_entity` — entity detail (→ fold into `rsm_find_related`)
- `rsm_build_context_pack` — ContextPack builder (→ rename to `rsm_prepare_context`)
- `rsm_get_context_page` — pagination (→ keep as-is)
- `rsm_query_graph` — graph traversal (→ fold into `rsm_find_related`)
- `rsm_validate_patch_context` — patch context check (→ internal/debug)
- `rsm_get_git_summary` — git metadata (→ internal/debug)
- `rsm_list_indexes` — store index discovery (→ internal/debug)
- `rsm_select_index` — store index selection (→ internal/debug)
- `rsm_current_index` — active index query (→ internal/debug)

**Target tools defined:**
- `rsm_search` — broad discovery of files/symbols/docs/tests
- `rsm_find_related` — relation-centered expansion
- `rsm_prepare_context` — primary coding-agent ContextPack tool
- `rsm_get_context_page` — pagination

**Key decisions:**
- 4 public tools maximum (not 2, not 11)
- `rsm_prepare_context` replaces `rsm_build_context_pack` with same handler
- `rsm_search` and `rsm_find_related` subsume 4 current tools
- Low-level tools kept as internal/debug, not removed
- CLI `rsm pack` unchanged
- 59.x benchmark quality preserved by construction

**Open questions:**
- Entity detail in `rsm_search` results: compact vs inline?
- `rsm_find_related` anchor: file path, entity_id, or both?
- Pagination model for `rsm_search`/`rsm_find_related`: flat lists or result sets?
- Store-mode tools: hidden or kept?
- Advanced `include_*` flags on `rsm_prepare_context`: keep or remove?

**Recommended next step:**
61.1 — Design detailed input/output schemas for the 4 target tools

**Validation:**
- `git diff --stat`: 1 file created
- `git status --short`: 1 new untracked file
- No doc checks configured
- No code changed
- No MCP behavior changed
- No CLI changed
- No ranking changed
- No dependencies added

**Status:**
- 61.0 complete ✓
