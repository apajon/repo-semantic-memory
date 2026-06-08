# RSM MCP Usage

> **Status:** Default 4-tool surface active (61.9).  
> **Last updated:** 2026-06-08 (61.11).  
> **Next step:** 61.12 — MCP test cleanup and consolidation.

## 1. Purpose

RSM's intended public MCP workflow is centered on **four tools**:

| Tool | Role |
|---|---|
| `rsm_prepare_context` | Build a task-centered ContextPack for a coding agent |
| `rsm_get_context_page` | Page over a prepared ContextPack without recomputing |
| `rsm_search` | Broad discovery across indexed files, symbols, docs and tests |
| `rsm_find_related` | Anchor-based expansion around a known file, entity, or qualified name |

These four tools replace an earlier 11-tool surface. The migration is complete:

- ✅ The four new tools are implemented (61.3–61.6).
- ✅ Old tools are marked `[DEPRECATED]` or `[INTERNAL/DEBUG]` in their MCP descriptions (61.7).
- ✅ Default public tool filtering is **active** — `tools/list` returns only the 4 public tools (61.9).
- ✅ `--expose-all-tools` flag enables the full legacy surface for debugging (61.9).
- ✅ Compatibility tests validate both modes (61.10).

**Default `tools/list` returns 4 tools.** Legacy/internal tools require
`rsm mcp serve --expose-all-tools`.

## 2. Recommended Agent Workflow

### 2.1 Primary workflow: task-first

```
1. rsm_prepare_context  →  Get a brief ContextPack for a concrete task.
2. rsm_get_context_page →  Fetch additional files/entities/relations/citations
                            from the same pack if needed.
```

**When to use this:** You have a concrete coding task ("fix the auth bug",
"implement feature X", "refactor Y"). `rsm_prepare_context` gives you the
files, entities, relations, and citations that matter.

### 2.2 Discovery workflow: explore-first

```
1. rsm_search          →  Find files/symbols matching a broad query.
2. rsm_find_related    →  Expand around a promising result to find tests,
                            imports, exports, and related entities.
3. rsm_prepare_context →  Build a ContextPack once the target area is clear.
```

**When to use this:** You're exploring an unfamiliar repository or are unsure
where the relevant code lives.

### 2.3 When NOT to use each tool

| Tool | Don't do this |
|---|---|
| `rsm_search` | Don't call it repeatedly when the task is already concrete. Use `rsm_prepare_context` instead. |
| `rsm_find_related` | Don't use it as a generic graph explorer. Anchor it on a specific file, entity, or qualified name. |
| `rsm_prepare_context` | Don't call it with `include_rendered=true` unless you need the full Markdown pack for debugging. |
| `rsm_get_context_page` | Don't fetch all pages blindly. Only fetch more when the current page indicates useful remaining context. |

## 3. Public Tool Reference

### 3.1 `rsm_prepare_context`

**Purpose:** Build a deterministic, source-cited, budget-bounded ContextPack
for a coding task.

**When to use:** You have a concrete task description. This is the primary
tool for coding agents.

**Key inputs:**

| Argument | Required | Default | Description |
|---|---|---|---|
| `task` | yes | — | Natural-language task description |
| `budget_chars` | no | `8000` | Character budget (max 20000) |
| `profile` | no | `agent_standard` | Ranking/compression profile |
| `detail_level` | no | `brief` | `brief` (small preview) or `compact` (larger one-shot) |

**Key outputs:** `result_set_id`, `active_repo`, `counts`, preview of
`selected_files`/`selected_entities`/`selected_relations`/`citations`,
`next` (paging hints), `uncertainties`, `warnings`.

**Typical example:**

```jsonc
{
  "name": "rsm_prepare_context",
  "arguments": {
    "task": "Fix the authentication race condition in login flow",
    "budget_chars": 8000
  }
}
// → result_set_id, compact preview, paging hints
```

**Common mistakes:**
- Calling with `include_rendered=true` by default (generates large output).
- Not checking `warnings` for stale/scoped index notices.
- Ignoring `next` hints when the preview is truncated.

**Current limitations:**
- Preferred replacement for `rsm_build_context_pack`. Both tools produce
  identical output; `rsm_prepare_context` adds `active_repo` metadata.
- `detail_level` controls preview size; paging via `rsm_get_context_page`
  is the recommended way to get additional items.

### 3.2 `rsm_get_context_page`

**Purpose:** Page over a previously-built ContextPack without recomputing.

**When to use:** You have a `result_set_id` from `rsm_prepare_context` or
`rsm_build_context_pack` and need more items from a specific stream.

**Key inputs:**

| Argument | Required | Default | Description |
|---|---|---|---|
| `result_set_id` | yes | — | Opaque ID from a prior `rsm_prepare_context` call |
| `stream` | yes | — | `files`, `entities`, `relations`, `citations`, or `ranking_breakdowns` |
| `offset` | no | `0` | Zero-based start offset |
| `limit` | no | `5` | Max entries (hard cap: 20) |

**Key outputs:** `result_set_id`, `stream`, `items` (with short IDs like `e1`,
`f2`), `total`, `next_offset`.

**Typical example:**

```jsonc
{
  "name": "rsm_get_context_page",
  "arguments": {
    "result_set_id": "pack_a3f91c2b8",
    "stream": "citations",
    "offset": 0,
    "limit": 5
  }
}
// → citations 1-5, total: 14, next_offset: 5
```

**Common mistakes:**
- Calling without a valid `result_set_id` (must be from the same MCP session).
- Assuming `result_set_id` persists across sessions (it does not).
- Using an expired ID (LRU-evicted after 8 result sets).

**Current limitations:**
- Works with `result_set_id` from both `rsm_prepare_context` and
  `rsm_build_context_pack`.
- `result_set_id` is session-scoped; not reproducible across restarts.
- Expired IDs return a recoverable `result_set_unknown` uncertainty.

### 3.3 `rsm_search`

**Purpose:** Broad discovery across indexed files, symbols, docs and tests.

**When to use:** You're exploring an unfamiliar area or formulating a query
before building a ContextPack.

**Key inputs:**

| Argument | Required | Default | Description |
|---|---|---|---|
| `query` | yes | — | Natural-language or keyword query |
| `limit` | no | `10` | Max results |
| `kind` | no | `[]` | Entity kind filters (module, class, function, etc.) |
| `path_role` | no | `[]` | Path role filters (source, test, doc, etc.) |

**Key outputs:** `active_repo`, `query`, `results` (with `result_id`, `path`,
`kind`, `name`, `score`, `reasons`), `count`, `uncertainties`, `warnings`.

**Typical example:**

```jsonc
{
  "name": "rsm_search",
  "arguments": {
    "query": "authentication login token",
    "limit": 5
  }
}
// → 5 results sorted by BM25 score
```

**Common mistakes:**
- Using `rsm_search` when the task is already concrete (use
  `rsm_prepare_context`).
- Assuming `result_id` from `rsm_search` is valid across independent calls
  (it is response-local only).
- Not checking `warnings` for stale index notices.

**Current limitations:**
- Pagination deferred; limit-only behavior for now.
- `result_id` is deterministic only within a single response
  (`search_0001`, `search_0002`, …).
- No source snippets; results include entity metadata only.

### 3.4 `rsm_find_related`

**Purpose:** Anchor-based expansion around a known file, entity, or qualified
name.

**When to use:** You have a specific file, entity ID, or qualified name and
want to find related tests, imports, exports, or dependencies.

**Key inputs:**

| Argument | Required | Default | Description |
|---|---|---|---|
| `entity_id` | no* | — | Full entity ID (e.g. `python:function:src.auth:login`) |
| `qualified_name` | no* | — | Dotted qualified name (e.g. `src.auth.login`) |
| `source_path` | no* | — | Repo-relative file path (e.g. `src/auth/login.py`) |
| `limit` | no | `10` | Max results (1–50) |

*At least one anchor must be provided. Priority: `entity_id` > `qualified_name` > `source_path`.

**Key outputs:** `active_repo`, `anchor`, `related` (with `relation_group`,
`relation_strength`, `relation_kinds`, `direction`, `reasons`), `count`,
`total`, `uncertainties`.

**Typical example:**

```jsonc
{
  "name": "rsm_find_related",
  "arguments": {
    "entity_id": "python:function:src.auth.login:authenticate",
    "limit": 10
  }
}
// → tests, imports, exports related to authenticate()
```

**Relation groups:** `tests`, `imports`, `exports`, `inherits`,
`implementation_support`, `other`.

**Relation strength:** `strong` (tests, imports, exports, inherits),
`medium` (contains, calls), `weak` (other).

**Common mistakes:**
- Using as a generic graph explorer without a specific anchor.
- Providing multiple anchors and expecting all to be used (only one anchor
  is resolved based on priority).
- Assuming `result_id` from `rsm_search` works as an anchor (deferred).

**Current limitations:**
- Pagination deferred; limit-only behavior for now.
- `result_id` anchor deferred (search result IDs are response-local).
- `relation_groups` filter deferred (all groups returned).

---

## 4. Migration From Legacy Tools

Legacy tools still work and are not removed, but they are **hidden by default**.
They require `--expose-all-tools` on `rsm mcp serve` to be visible and
invocable.

### Enabling debug/compat mode

```bash
rsm mcp serve --repo /path/to/repo --db /path/to/repo/.rsm/index.sqlite --expose-all-tools
```

With `--expose-all-tools`, `tools/list` returns all 14 tools (4 public + 10 legacy),
and all tools are invocable. This is intended for debugging and migration
compatibility only.

### Deprecated tools

| Legacy tool | Status | Use instead | Notes |
|---|---|---|---|
| `rsm_search_symbols` | `[DEPRECATED]` | `rsm_search` | Same BM25 engine; `rsm_search` adds `active_repo` and cleaner output |
| `rsm_explain_entity` | `[DEPRECATED]` | `rsm_find_related` | Same entity resolution; `rsm_find_related` adds group/strength classification |
| `rsm_build_context_pack` | `[DEPRECATED]` | `rsm_prepare_context` | Identical output; `rsm_prepare_context` adds `active_repo` |
| `rsm_query_graph` | `[DEPRECATED]` | `rsm_find_related` | Same graph data; `rsm_find_related` with anchor-based expansion |

### Internal/debug tools

| Tool | Status | Notes |
|---|---|---|
| `rsm_status` | `[INTERNAL/DEBUG]` | Session diagnostics; staleness/scope surfaced via `warnings` in public tools |
| `rsm_validate_patch_context` | `[INTERNAL/DEBUG]` | Patch context sufficiency check |
| `rsm_get_git_summary` | `[INTERNAL/DEBUG]` | Repository git metadata |
| `rsm_list_indexes` | `[INTERNAL/DEBUG - store mode]` | Index discovery in store mode |
| `rsm_select_index` | `[INTERNAL/DEBUG - store mode]` | Index activation in store mode |
| `rsm_current_index` | `[INTERNAL/DEBUG - store mode]` | Session state introspection |

### Public tools (unchanged)

| Tool | Status |
|---|---|
| `rsm_get_context_page` | Public, unchanged since phase 1 |
| `rsm_prepare_context` | Public, new in 61.3 |
| `rsm_search` | Public, new in 61.5 |
| `rsm_find_related` | Public, new in 61.6 |

---

## 5. Example Workflows

### A. Implement a feature (task-first)

```
1. rsm_prepare_context("Add rate limiting to the login endpoint")
   → preview shows 5 files, 5 entities, 3 relations
   → next shows citations has 14 items available

2. Read the preview files

3. rsm_get_context_page(result_set_id, stream="citations")
   → get the full citation list for source verification

4. rsm_get_context_page(result_set_id, stream="entities", offset=5)
   → get the next 5 entities if needed
```

### B. Explore an unfamiliar repository area (search-first)

```
1. rsm_search("authentication flow session management")
   → results show src/auth/session.py, src/auth/login.py, etc.

2. rsm_find_related(source_path="src/auth/login.py")
   → shows tests/auth/test_login.py, imports, exports

3. rsm_prepare_context("Understand the authentication login pipeline")
   → ContextPack with login.py, session.py, test_login.py, and relations
```

### C. Find tests related to a component

```
1. rsm_search("LifecycleComponent activation", kind=["class"])
   → finds the class entity

2. rsm_find_related(entity_id="python:class:...:LifecycleComponent")
   → related items with relation_group="tests"

3. rsm_prepare_context("Write regression tests for LifecycleComponent activation")
   → ContextPack includes implementation files and test files
```

### D. Continue reading a large ContextPack

```
1. rsm_prepare_context("Refactor the entire auth module")
   → brief preview: 5 files, 5 entities, 3 relations, 0 citations
   → counts shows 23 files, 87 entities, 45 relations, 32 citations

2. rsm_get_context_page(result_set_id, stream="files", offset=5, limit=10)
   → files 6-15

3. rsm_get_context_page(result_set_id, stream="relations", offset=0, limit=10)
   → relations 1-10
```

---

## 6. Error and Warning Handling

### 6.1 Common error codes

| Code | Tool(s) | Meaning | Agent action |
|---|---|---|---|
| `no_active_index` | All repo tools | No index selected in store mode | Call `rsm_list_indexes` then `rsm_select_index` |
| `result_set_unknown` | `rsm_get_context_page` | `result_set_id` expired or invalid | Call `rsm_prepare_context` again |
| `anchor_not_found` | `rsm_find_related` | Anchor entity/path not in index | Check spelling, try a different anchor |
| `empty_query_tokens` | `rsm_search` | Query has no searchable tokens | Use more specific terms |
| `ambiguous_qualified_name` | `rsm_find_related` | Name matches multiple entities | Use `entity_id` instead |

### 6.2 Common warning codes

| Warning | Severity | Meaning | Agent action |
|---|---|---|---|
| `STALE_INDEX` | warning | Index predates current HEAD | Results may not reflect latest code. Re-index if critical |
| `SCOPED_INDEX` | warning | Index has include/exclude patterns | Results are limited to indexed paths |
| `TRUNCATED_RESULTS` | warning | Results were capped by the limit | Use a larger limit or paging |
| `BUDGET_CAPPED` | warning | Budget exceeded maximum | Results are budget-limited |

**Agents should treat stale and scoped index warnings seriously.**
A stale index may mean the selected files no longer represent the current
code. A scoped index means some files were excluded from indexing.

---

## 7. Store Mode Notes

Store mode (`rsm mcp serve --store`) enables multi-repository workspaces with
one MCP server config. The current state:

- Store-mode tools (`rsm_list_indexes`, `rsm_select_index`,
  `rsm_current_index`) are marked `[INTERNAL/DEBUG - store mode]`.
- Store-mode tools are **hidden by default**. They are visible only
  with `--expose-all-tools`.
- `active_repo` is included in every repo-scoped response from the 4 public
  tools (where implemented).
- Per-call `repo` parameter is **deferred** (not yet implemented).
- When running in store mode with `--expose-all-tools`, the full 17-tool
  surface is available (4 public + 3 store + 10 repo).

For `--store` CLI usage, prerequisites, and configuration, see the original
phase 1 documentation preserved at the end of this document.

---

## 8. Compatibility Notes

- **Old tools are hidden by default.** `tools/list` returns only 4 public tools.
- **Old tools are not removed.** They are available via `--expose-all-tools`.
- **Deprecation is description-based.** `[DEPRECATED]` and `[INTERNAL/DEBUG]`
  prefixes in tool descriptions are visible in expose-all mode.
- **Compatibility mode is explicit.** `--expose-all-tools` enables the full
  14-tool surface.
- **Migration is complete.** The default 4-tool surface is stable.

---

## 9. Anti-Patterns

| Anti-pattern | Why it's bad | What to do instead |
|---|---|---|
| Calling legacy tools first (`rsm_search_symbols`, `rsm_explain_entity`) | Legacy tools are marked deprecated | Use `rsm_search` and `rsm_find_related` |
| Repeatedly using `rsm_search` when the task is concrete | Search is for discovery, not task preparation | Use `rsm_prepare_context` for concrete tasks |
| Using `rsm_search` when the task is already clear | Wastes tool calls on a solved problem | Go straight to `rsm_prepare_context` |
| Ignoring stale/scoped index warnings | Results may be wrong or incomplete | Check warnings, re-index if needed |
| Fetching all pages blindly | Large context packs can exceed token budgets | Page incrementally, stop when context is sufficient |
| Using `rsm_find_related` as a generic graph explorer | No anchor means no useful results | Always provide a specific anchor |
| Relying on response-local `result_id` across independent calls | IDs are not stable across calls | Use `entity_id` for cross-call references |

---

## 10. Remaining 61.x Work

| Task | Description |
|---|---|
| **61.9** | ✅ MCP default tool surface reduction — `tools/list` returns 4 public tools by default |
| **61.10** | ✅ MCP public/debug compatibility tests — validate both modes |
| **61.11** | ✅ MCP documentation cleanup after surface reduction |
| **61.12** | MCP test cleanup and consolidation |
| **61.13** | Final 61.x MCP surface report |

The 4-tool default surface is active and validated.

---

## 11. Future Direction

- **Default `tools/list`** exposes only 4 public tools.
- **Legacy/internal tools** are available behind `--expose-all-tools`.
- **Search/find_related benchmarks** are planned to complement the existing
  ContextPack benchmark harness.
- **ContextPack v2** may refine output shape after the MCP surface is stable.
- **Cursor-based pagination** is deferred for `rsm_search` and
  `rsm_find_related`; the current limit-only behavior is sufficient for
  reasonable query sizes.
- **Per-call `repo` parameter** is deferred; session-scoped repo selection
  (via store mode or `--repo`/`--db` flags) is the current workflow.

---

## Appendix: Phase 1 Reference

The sections below are preserved from the original phase 1 documentation
for reference on server startup, prerequisites, client configuration,
and safety model.

### Prerequisites

```bash
uv run rsm index /path/to/target-repo --db /path/to/target-repo/.rsm/index.sqlite
# or
uv run rsm index /path/to/target-repo --register
```

### Starting the server

```bash
uv run rsm mcp serve --repo /absolute/path/to/target-repo \
  --db /absolute/path/to/target-repo/.rsm/index.sqlite
```

### From-source MCP client configuration

```json
{
  "mcpServers": {
    "repo-semantic-memory": {
      "command": "uv",
      "args": [
        "run", "--directory", "/absolute/path/to/repo-semantic-memory",
        "rsm", "mcp", "serve",
        "--repo", "/absolute/path/to/target-repo",
        "--db", "/absolute/path/to/target-repo/.rsm/index.sqlite"
      ]
    }
  }
}
```

### Safety summary

- No arbitrary shell command execution.
- No network access.
- No mutation of repository or database state.
- No auto-indexing.
- Explicit `--repo`/`--db` validation.
- Read-only by design.
