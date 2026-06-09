# MCP 4-Tool Interface

> **Task:** 61.1 — Design-only  
> **Date:** 2026-06-06  
> **Branch:** `feat/benchmark-harness-59`  
> **Depends on:** `docs/design/mcp_tool_surface_minimization.md` (61.0)  
> **Status:** Design complete. No code changed.  
> **Correction (61.14 — 2026-06-09):** The target surface was revised to 7 tools: 4 task + 3 store/navigation. This document describes the 4 task tools only. Store/navigation tools are documented in `docs/usage/mcp.md`. See `docs/reviews/mcp_surface_61x_final_report.md` for the final corrected contract.

## 1. Purpose

This document defines the **concrete public MCP contracts** for the 4-tool RSM
interface designed in `docs/design/mcp_tool_surface_minimization.md` (61.0).

It provides implementation-ready input/output schemas, shared error/warning
models, pagination strategy, result-ID design, and a concrete mapping from the
current 11-tool surface to the target 4-tool surface.

**This is a design document.** No code, MCP behavior, CLI behavior, ranking,
or dependencies are changed in 61.1.

**Files inspected for grounding:**

| File/Dir | Status | Role |
|---|---|---|
| `docs/design/mcp_tool_surface_minimization.md` | exists | Parent design (61.0) |
| `docs/RSM_HANDOFF.md` | does not exist | — |
| `docs/RSM_DECISIONS.md` | does not exist | — |
| `docs/RSM_GLOSSARY.md` | does not exist | — |
| `docs/reviews/semble_codegraph_cartog_feature_comparison_v2.md` | exists | 60.0 review |
| `src/repo_semantic_memory/mcp/` | exists | Current MCP implementation |
| `src/repo_semantic_memory/context/` | exists | Context pack, ranking, BM25, graph selection |
| `src/repo_semantic_memory/store/` | exists | SQLite store |
| `tests/mcp/` | exists | MCP handler/server/session tests |
| `tests/context/` | exists | Context pack, ranking, BM25 tests |

---

## 2. Shared Design Principles

All 4 public tools follow these principles, derived from the current
implementation patterns in `src/repo_semantic_memory/mcp/`:

| Principle | Source grounding | Implementation rule |
|---|---|---|
| **active_repo in every repo-scoped response** | `rsm_status` includes `repo_root`/`db_path`; `rsm_select_index` returns `active_repo` | Every response from `rsm_search`, `rsm_find_related`, `rsm_prepare_context` includes an `active_repo` block |
| **Index status/staleness warnings** | `index_status.py` → `detect_stale_from_metadata()`, already surfaced in `rsm_status` and `rsm_build_context_pack` | Staleness and scope warnings appear in `.warnings` of every response, never fatal |
| **Deterministic ordering** | All current handlers sort results lexicographically or by deterministic score | No random ordering. Sort keys are documented per-tool |
| **Stable `source_path` fields** | `Entity.source_range.path` uses POSIX separators; `_compact_entity_dict` flattens to `path` | Field name is always `path` (not `source_path`, `file_path`, `filepath`) |
| **Machine-readable reason codes** | `SelectionReason.code` closed vocabulary; `Uncertainty.code` stable strings | Error codes: `UPPER_SNAKE_CASE`. Warning codes: `UPPER_SNAKE_CASE`. Reason codes: `snake_case` |
| **Human-readable summaries** | `Uncertainty.message`; `RankingReason.message` | Every code is accompanied by a `message` field |
| **Compact by default** | `detail_level="brief"` defaults (5 files, 5 entities, 3 relations, 0 citations) | First response is small. Details via pagination or follow-up |
| **Pagination for large results** | `ResultStore` + `rsm_get_context_page` (session.py) | `rsm_search` and `rsm_find_related` use cursor-based pagination. `rsm_prepare_context` uses `result_set_id` + `rsm_get_context_page` |
| **Explicit error payloads** | `_tool_error_result()` returns `isError: true` | Distinguish tool-call errors (fatal) from uncertainties (recoverable) |
| **No hidden repository switching** | `SessionConfig` is frozen; `StoreSessionState.active_index` is explicit | `active_repo` is explicit. Multi-repo discovery is via store-mode tools (internal) |
| **No huge unpaged MCP payloads** | `_PACK_STORE_CAP=1000`, `_PACK_PREVIEW_SAFETY_CAP=200`, `_MAX_SEARCH_LIMIT=100` | Every tool has documented default and maximum limits |

---

## 3. Shared Error Model

### 3.1 Fatal errors (tool-call errors)

Raised via `ToolInvocationError` → `isError: true` in the MCP response.
The request cannot be satisfied.

```jsonc
{
  "content": [{"type": "text", "text": "<human-readable message>"}],
  "isError": true
}
```

The current implementation does not attach a structured error code to
`isError: true` responses (the message is free-text). The target design
should add a structured `error` block:

```jsonc
{
  "content": [{"type": "text", "text": "<summary>"}],
  "isError": true,
  "_error": {
    "code": "UNKNOWN_REPO",
    "message": "The requested repository is not registered in the index store.",
    "recoverable": false
  }
}
```

| Code | When | Fatal? |
|---|---|---|
| `INVALID_QUERY` | Empty or malformed query string | Fatal |
| `INVALID_ARGUMENT` | Wrong type, out-of-range value | Fatal |
| `UNKNOWN_REPO` | `repo` parameter doesn't match any registered index | Fatal |
| `MISSING_INDEX` | Index file doesn't exist for the active repo | Fatal |
| `INTERNAL_ERROR` | Unexpected runtime failure | Fatal |

### 3.2 Recoverable errors (uncertainties in response payload)

Returned as `.uncertainties` in the response body. The tool call succeeded
but results may be incomplete.

```jsonc
{
  "uncertainties": [
    {
      "code": "NO_ACTIVE_REPO",
      "message": "No active index selected. Call rsm_list_indexes then rsm_select_index.",
      "recoverable": true
    }
  ]
}
```

| Code | When | Tool(s) |
|---|---|---|
| `NO_ACTIVE_REPO` | No index selected in store mode | `rsm_search`, `rsm_find_related`, `rsm_prepare_context` |
| `INVALID_PAGE_TOKEN` | Cursor/page token is malformed or expired | `rsm_search`, `rsm_find_related`, `rsm_get_context_page` |
| `EXPIRED_CONTEXT_PACK` | `result_set_id` has been evicted or session ended | `rsm_get_context_page` |
| `NO_RESULTS` | Query matched nothing | `rsm_search`, `rsm_find_related` |

### 3.3 Warnings (non-blocking advisory)

Returned as `.warnings` in the response body. Results are complete but
may have quality caveats.

```jsonc
{
  "warnings": [
    {
      "code": "STALE_INDEX",
      "message": "Index was built 3 days ago. Repository may have changed.",
      "severity": "warning",
      "details": {
        "indexed_at": "2026-06-03T12:00:00Z",
        "current_git_head": "abc1234",
        "indexed_git_head": "def5678"
      }
    }
  ]
}
```

| Code | Severity | When |
|---|---|---|
| `STALE_INDEX` | warning | Index predates current HEAD or working tree is dirty |
| `SCOPED_INDEX` | warning | Index was built with include/exclude patterns |
| `LARGE_RESULT_SET` | info | Result count exceeds a threshold; consider refining query |
| `TRUNCATED_RESULTS` | warning | Results were truncated by the limit |
| `LOW_CONFIDENCE_MATCH` | info | Some results have low BM25/ranking scores |
| `BUDGET_CAPPED` | warning | Requested budget exceeded maximum; results capped |
| `QUERY_TOO_BROAD` | info | Query contains only stop-words or very common terms |

---

## 4. Shared Warning Model

Every repo-scoped response includes a `warnings` array. Warnings are
non-blocking: the response payload is complete and usable, but the agent
should be aware of quality caveats.

```jsonc
{
  "active_repo": { "repo_id": "a1b2c3d4", "name": "my-repo", "repo_root": "/path/to/repo" },
  "warnings": [
    {
      "code": "STALE_INDEX",
      "message": "Index is 3 commits behind HEAD.",
      "severity": "warning",
      "details": { "indexed_git_head": "def5678", "current_git_head": "abc1234" }
    }
  ],
  "results": [ /* ... */ ]
}
```

### Warning shape

```typescript
type Warning = {
  code: string;         // UPPER_SNAKE_CASE, stable
  message: string;      // Human-readable
  severity: "info" | "warning";  // "error" reserved but not used in warnings
  details: Record<string, unknown>;  // Optional structured context
};
```

### Warning inclusion rules

| Warning | `rsm_search` | `rsm_find_related` | `rsm_prepare_context` | `rsm_get_context_page` |
|---|---|---|---|---|
| `STALE_INDEX` | ✅ | ✅ | ✅ | — |
| `SCOPED_INDEX` | ✅ | ✅ | ✅ | — |
| `LARGE_RESULT_SET` | ✅ | — | — | — |
| `TRUNCATED_RESULTS` | ✅ | ✅ | ✅ | — |
| `LOW_CONFIDENCE_MATCH` | ✅ | ✅ | — | — |
| `BUDGET_CAPPED` | — | — | ✅ | — |
| `QUERY_TOO_BROAD` | ✅ | — | — | — |

---

## 5. rsm_prepare_context

### 5.1 Role

Primary coding-agent tool. Accepts a natural-language task description and
returns a budget-bounded, source-cited ContextPack with progressive retrieval
support.

Direct replacement for `rsm_build_context_pack`. Uses the same handler
(`handle_build_context_pack` in `handlers.py`), same `build_context_pack`
function in `pack_builder.py`, and same `ResultStore` in `session.py`.

### 5.2 Input schema

```jsonc
{
  "task": "string (required)",             // Natural-language task description
  "budget_chars": 8000,                    // int, default 8000, min 1, max 20000
  "profile": "agent_standard",             // string, default "agent_standard"
  "detail_level": "brief",                 // "brief" | "compact", default "brief"
  "include_rendered": false,               // bool, default false
  "include_payload": false,                // bool, default false
  "include_ranking_breakdowns": false      // bool, default false
}
```

**Design decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| `task` required? | Yes | Task description is essential for ranking. No default query |
| `repo` parameter? | Not in tool input | `active_repo` is session-scoped (set at server startup or via `rsm_select_index`). `repo` is not per-call |
| `include_tests` / `include_docs`? | Not in tool input | Test/doc inclusion is driven by ranking and query intent, not explicit flags. The pack builder already expands support/tests automatically |
| `include_graph`? | Reserved, not yet | Graph expansion is internal to the pack builder. Exposing it would leak implementation details |
| Defaults match current? | Yes | `budget_chars=8000`, `profile="agent_standard"`, `detail_level="brief"` match current `rsm_build_context_pack` defaults |

**Removed from current `rsm_build_context_pack` input:**
- `format` (markdown/yaml) — only relevant for rendered output, which is opt-in
- `explain_ranking` — renamed to `include_ranking_breakdowns` (clearer)
- `include_semantic_components` — always included; removed noise from the interface
- `max_files`, `max_entities`, `max_relations`, `max_citations` — controlled by `detail_level` profile (brief/compact), not individual knobs

### 5.3 Output schema

```jsonc
{
  "active_repo": {
    "repo_id": "a1b2c3d4e5f6a7b8",        // Stable hex ID
    "name": "my-repo",                      // Basename of repo root
    "repo_root": "/path/to/repo"            // Resolved absolute path
  },
  "task": "Fix the authentication bug in login flow",
  "result_set_id": "pack_a3f91c2b8",       // Opaque session-scoped ID
  "budget": {
    "requested_chars": 8000,
    "used_chars": 0,
    "truncated": false
  },
  "counts": {
    "files": 12,
    "entities": 30,
    "relations": 18,
    "citations": 14
  },
  "preview": {
    "files": [
      { "id": "f1", "path": "src/auth/login.py" },
      { "id": "f2", "path": "src/auth/session.py" }
    ],
    "entities": [
      {
        "id": "e1",
        "entity_id": "python:function:src.auth.login:authenticate",
        "kind": "function",
        "name": "authenticate",
        "qualified_name": "src.auth.login.authenticate",
        "path": "src/auth/login.py",
        "start_line": 42,
        "end_line": 68
      }
    ],
    "relations": [
      {
        "id": "r1",
        "kind": "calls",
        "source_entity_id": "python:function:...",
        "target_entity_id": "python:function:..."
      }
    ],
    "citations": []                         // Empty in brief mode
  },
  "next": {
    "entities": {
      "stream": "entities",
      "available": 30,
      "shown": 5,
      "tool": "rsm_get_context_page"
    },
    "citations": {
      "stream": "citations",
      "available": 14,
      "shown": 0,
      "tool": "rsm_get_context_page"
    }
  },
  "warnings": [
    {
      "code": "STALE_INDEX",
      "message": "Index is 3 commits behind HEAD.",
      "severity": "warning",
      "details": { "indexed_git_head": "def5678", "current_git_head": "abc1234" }
    }
  ],
  "uncertainties": [],
  "agent_instructions": [
    "Use only paths listed in this response.",
    "Do not infer missing paths, symbols, or class names.",
    "Call rsm_find_related for details about a selected entity.",
    "Call rsm_get_context_page for more files/entities/relations from this result set."
  ],
  "omitted_sections": ["rendered", "payload", "ranking_breakdowns"]
}
```

**Preview sizes per `detail_level`:**

| Stream | `brief` (default) | `compact` |
|---|---|---|
| files | 5 | all (up to store cap) |
| entities | 5 | 15 |
| relations | 3 | 10 |
| citations | 0 | 12 |

**Mapping to current `rsm_build_context_pack`:**

| Current field | Target field | Notes |
|---|---|---|
| `result_set_id` | `result_set_id` | Unchanged |
| `counts` | `counts` | Unchanged |
| `selected_files` | `preview.files` | Wrapped in preview, IDs added |
| `selected_entities` | `preview.entities` | Wrapped in preview, IDs added |
| `selected_relations` | `preview.relations` | Wrapped in preview, IDs added |
| `citations` | `preview.citations` | Wrapped in preview, IDs added |
| `next` | `next` | Unchanged |
| `uncertainties` | `uncertainties` | Unchanged |
| (new) | `active_repo` | Added |
| (new) | `warnings` | Added (staleness, scope) |
| `omitted_sections` | `omitted_sections` | Unchanged |
| `agent_instructions` | `agent_instructions` | Updated to reference new tools |
| `budget` | `budget` | Unchanged |
| `truncated` | `budget.truncated` | Nested under budget |

---

## 6. rsm_get_context_page

### 6.1 Role

Pagination for an existing ContextPack identified by `result_set_id`.
Returns a deterministic slice of one stream without recomputing the pack.

This tool is **unchanged** from the current implementation. It already has
a clean, stable contract.

### 6.2 Input schema

```jsonc
{
  "result_set_id": "pack_a3f91c2b8",       // string (required)
  "stream": "entities",                     // "files" | "entities" | "relations" | "citations" | "ranking_breakdowns"
  "offset": 0,                              // int, default 0, min 0
  "limit": 5                                // int, default 5, min 1, max 20
}
```

### 6.3 Output schema

```jsonc
{
  "result_set_id": "pack_a3f91c2b8",
  "stream": "entities",
  "offset": 0,
  "limit": 5,
  "items": [
    {
      "id": "e6",
      "entity_id": "python:class:src.auth.session:SessionManager",
      "kind": "class",
      "name": "SessionManager",
      "qualified_name": "src.auth.session.SessionManager",
      "path": "src/auth/session.py",
      "start_line": 10,
      "end_line": 95
    }
  ],
  "total": 30,
  "next_offset": 5,
  "uncertainties": []
}
```

**Design decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| Page token shape | Integer `offset` + `limit` | Already implemented. Simple, deterministic, debuggable |
| Context pack cache lifecycle | Session-scoped (`ResultStore`, max 8 sets, LRU eviction) | Already implemented. No disk persistence needed |
| Expiration behavior | `result_set_unknown` uncertainty, agent told to re-call `rsm_prepare_context` | Already implemented. Recoverable |
| Repo/index mismatch | Not applicable | `rsm_get_context_page` does not touch the index or filesystem |
| Page number vs token | `offset` is canonical; `limit` controls page size | No opaque page token needed for this tool |

---

## 7. rsm_search

### 7.1 Role

Broad discovery across files, symbols, docs, and tests. Replaces
`rsm_search_symbols` with a higher-level interface that returns
file-level and symbol-level results in a unified list.

### 7.2 Input schema

```jsonc
{
  "query": "string (required)",            // Natural-language or keyword query
  "scope": "all",                           // "all" | "files" | "symbols" | "tests" | "docs", default "all"
  "kind": [],                               // list of entity kinds (module, class, function, method, field, test, ...)
  "path_role": [],                          // list of path roles (source, test, example, doc, config, ...)
  "limit": 10,                              // int, default 10, min 1, max 25
  "cursor": null                            // string | null, for pagination
}
```

**Design decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| `query` required? | Yes | No default query |
| Compact vs inline entity detail | Compact (path, kind, name, score). Detail via `rsm_find_related` | Follows compact-by-default principle. Entity detail bloats search results |
| Max default limit | 10 (was 10 in `rsm_search_symbols`) | Keep it small for MCP |
| Search engine | Same BM25 + fielded index as `rsm_search_symbols` | No new search path. Reuses existing `FieldedBM25Index` |
| Result IDs | `"search_{short_hex}"` — opaque, session-stable | Distinguished from `pack_*` ContextPack IDs |
| Source snippets? | Not in initial version | Reserved for future chunk integration (post-61.x) |
| `cursor` pagination | Token-based (not offset-based) | Matches large result sets better than offset pagination |

**Removed from current `rsm_search_symbols`:**
- `include_relations` — relation expansion belongs to `rsm_find_related`
- `entity_kinds` → `kind` (simpler name, same semantics)
- `path_roles` → `path_role` (singular for consistency)

### 7.3 Path roles for search filtering

These are the same `PathRole` values from `src/repo_semantic_memory/context/path_roles.py`:

| Role | Meaning | Example paths |
|---|---|---|
| `source` | Implementation source code | `src/`, `lib/`, top-level packages |
| `test` | Test files | `tests/`, `test/` |
| `example` | Example/demo code | `examples/`, `example/` |
| `doc` | Documentation | `docs/`, `doc/` |
| `ci` | CI/CD configuration | `.github/`, `.gitlab/` |
| `tool` | Internal tooling | `tools/`, `scripts/` |
| `config` | Configuration files | `config/`, `pyproject.toml` |
| `generated` | Generated/build artifacts | `_build/`, `dist/`, `.egg-info/` |
| `other` | Unclassified | Everything else |

### 7.4 Output schema

```jsonc
{
  "active_repo": {
    "repo_id": "a1b2c3d4e5f6a7b8",
    "name": "my-repo",
    "repo_root": "/path/to/repo"
  },
  "query": "authentication login flow",
  "results": [
    {
      "result_id": "search_a3f91c2b8",        // Opaque ID for rsm_find_related anchoring
      "path": "src/auth/login.py",
      "kind": "function",
      "name": "authenticate",
      "qualified_name": "src.auth.login.authenticate",
      "source_range": {
        "start_line": 42,
        "end_line": 68,
        "start_col": 4,
        "end_col": null
      },
      "path_role": "source",
      "score": 12.456,
      "reasons": [
        { "code": "lexical_match", "detail": "matched: authenticate, login" },
        { "code": "path_prior", "detail": "source role bonus" }
      ]
    }
  ],
  "summary": "Found 8 results for 'authentication login flow' (showing 1–8).",
  "page": {
    "has_next": false,
    "next_cursor": null
  },
  "warnings": [],
  "uncertainties": []
}
```

**Result ordering:** By descending score, then by path (lexicographic tiebreak).

**When `scope="files"`:** Results omit entity-level detail (`kind`, `name`, `qualified_name`, `source_range` may be null). Only `path` and `path_role` are populated.

**When `scope="tests"`:** Only results with `path_role="test"` are returned.

### 7.5 Pagination

Cursor-based. The `cursor` is an opaque string encoding the last returned
`result_id` and score. Sending `cursor` in the next call resumes after that result.

```jsonc
// First call
{ "query": "auth", "limit": 25 }
→ { "page": { "has_next": true, "next_cursor": "cursor_abc123" } }

// Next page
{ "query": "auth", "limit": 25, "cursor": "cursor_abc123" }
→ { "page": { "has_next": false, "next_cursor": null } }
```

Invalid/expired cursor → `INVALID_PAGE_TOKEN` uncertainty. Agent should re-query
without the cursor.

---

## 8. rsm_find_related

### 8.1 Role

Relation-centered expansion around a known anchor: a file path, entity ID,
qualified name, or search result ID. Replaces `rsm_explain_entity` and
`rsm_query_graph` with a unified expansion interface.

### 8.2 Input schema

```jsonc
{
  "anchor": {
    "path": "src/auth/login.py",            // string (optional) — file path
    "entity_id": null,                       // string (optional) — full entity ID
    "qualified_name": null,                  // string (optional) — dotted qualified name
    "result_id": null                        // string (optional) — from rsm_search results
  },
  "relation_groups": [],                     // list of relation group names, empty = all
  "direction": "both",                       // "incoming" | "outgoing" | "both"
  "limit": 10,                               // int, default 10, min 1, max 50
  "cursor": null                             // string | null, for pagination
}
```

**Anchor resolution priority (when multiple fields are provided):**

| Priority | Field | Resolution |
|---|---|---|
| 1 (highest) | `entity_id` | Direct lookup in entity index |
| 2 | `result_id` | Look up in session-scoped search result cache |
| 3 | `qualified_name` | Resolve via index lookup (may be ambiguous → returns all matches) |
| 4 (lowest) | `path` | Find all entities in that file |

At least one anchor field must be provided.

**Design decisions:**

| Decision | Choice | Rationale |
|---|---|---|
| Anchor priority | `entity_id` > `result_id` > `qualified_name` > `path` | Most precise to least precise |
| File path alone enough? | Yes, but returns ALL entities in that file and their relations | Useful for "what tests cover this file?" |
| Ambiguous qualified names | Return all matching entities, with `AMBIGUOUS_ANCHOR` warning | Better to give all matches than guess |
| Relation strength | `strong` (direct tests/imports/exports), `medium` (same-package), `weak` (lexical/name overlap) | Derived from existing `SelectionReason` codes |
| `relation_groups` | Pre-defined groups (see below) | Filters the expansion. Empty = all groups |

### 8.3 Relation groups

| Group | Description | Underlying relation kinds / selection reasons |
|---|---|---|
| `tests` | Test files and test relations | `test_relation`, `test_path_proximity`, `test_stem_match`, `test_lexical_match` |
| `imports` | Imported and importing modules | `imports` relations, `support_import` |
| `exports` | Public API exports | `support_export`, `support_public_api` |
| `inherits` | Class inheritance | `inherits` relations, `support_inherits` |
| `same_package` | Files in the same package/directory | `support_same_package` |
| `calls` | Function/method call graph | `calls` relations |
| `docs` | Documentation files | `path_role=doc` adjacency |
| `examples` | Example files | `path_role=example` adjacency |
| `graph_neighbors` | Bounded graph traversal | `select_graph_neighbors()` with `max_depth=1` |

Multiple groups can be combined: `["tests", "imports"]`.

### 8.4 Output schema

```jsonc
{
  "active_repo": {
    "repo_id": "a1b2c3d4e5f6a7b8",
    "name": "my-repo",
    "repo_root": "/path/to/repo"
  },
  "anchor": {
    "path": "src/auth/login.py",
    "entity_id": "python:function:src.auth.login:authenticate",
    "kind": "function",
    "name": "authenticate"
  },
  "related": [
    {
      "path": "tests/auth/test_login.py",
      "kind": "test",
      "name": "test_authenticate_success",
      "qualified_name": "tests.auth.test_login.test_authenticate_success",
      "source_range": { "start_line": 15, "end_line": 32 },
      "relation_group": "tests",
      "relation_kind": "tests",
      "direction": "incoming",
      "strength": "strong",
      "score": null,
      "reasons": [
        { "code": "test_relation", "detail": "tests auth.login.authenticate" }
      ]
    }
  ],
  "summary": "Found 5 related items for src/auth/login.py (tests, imports).",
  "page": {
    "has_next": false,
    "next_cursor": null
  },
  "warnings": [],
  "uncertainties": []
}
```

**Relation strength rules:**

| Strength | Condition |
|---|---|
| `strong` | Direct relation (tests, imports, exports, inherits, calls) with evidence |
| `medium` | Same-package, path proximity, name overlap |
| `weak` | Lexical token overlap without structural relation |

### 8.5 Pagination

Same cursor-based model as `rsm_search`. The `cursor` encodes the last
returned item's path + relation group.

---

## 9. Mapping From Existing Tools

| Existing tool | Current input summary | Current output summary | Target tool | Mapping behavior | Compatibility strategy | Open issue |
|---|---|---|---|---|---|---|
| `rsm_status` | None | repo_root, db_path, entity_count, relation_count, index_status, staleness | Internal/debug | Not mapped to public tools. Staleness/scope surfaced as `warnings` in other tools | Keep available, mark `[INTERNAL]` | Should `active_repo` be a separate tool or always inline? → inline |
| `rsm_search_symbols` | query, limit, entity_kinds, path_roles, include_relations | matches, results (entity dicts), citations, uncertainties | `rsm_search` | `query` → `query`, `entity_kinds` → `kind`, `path_roles` → `path_role`. `include_relations` removed (use `rsm_find_related`) | Keep as deprecated alias | Result ID format: `search_{hex}` vs `entity_id`? → `search_{hex}` |
| `rsm_explain_entity` | entity_id, include_incoming/outgoing, include_components, include_claims | entity payload, relations, semantic_components, related_entity_ids | `rsm_find_related` | `entity_id` → `anchor.entity_id`. Relations become `related` items. Semantic components inlined in entity detail | Keep as deprecated alias | Entity detail shape: full entity payload in `rsm_find_related` output? → compact by default, full via `include_detail` flag (future) |
| `rsm_build_context_pack` | task, budget_chars, format, profile, detail_level, explain_ranking, include_*, max_* | result_set_id, counts, preview (files/entities/relations/citations), next, uncertainties | `rsm_prepare_context` | Direct rename. Same handler. Cleaned input schema | Keep as deprecated alias | Should `include_rendered`/`include_payload` stay? → yes, as opt-in advanced params |
| `rsm_get_context_page` | result_set_id, stream, offset, limit | items, total, next_offset | `rsm_get_context_page` | Unchanged | Unchanged | None |
| `rsm_query_graph` | entity_ids, relation_kinds, direction, max_hops, limit | entity_ids, entities, relations, citations | `rsm_find_related` | `entity_ids[0]` → `anchor.entity_id`, `max_hops=1` → `relation_groups=["graph_neighbors"]`, `max_hops>1` → not supported in v1 (reserved) | Keep as deprecated alias | Multi-hop graph traversal: expose or reserve? → reserve for v1 |
| `rsm_validate_patch_context` | task, changed_paths, referenced_entity_ids, budget_chars | covered_paths, missing_paths, suggested_context_query | Internal/debug | Not mapped. Logic may be exposed as a `rsm_prepare_context` option later | Keep available, mark `[INTERNAL]` | Is patch validation a core agent workflow? → no, it's specialized |
| `rsm_get_git_summary` | path | repository_root, branch, head_commit, dirty | Internal/debug | Git info folded into `active_repo` + staleness warnings | Keep available, mark `[INTERNAL]` | Standalone git tool adds no value for agents |
| `rsm_list_indexes` | None | indexes list, count | Internal/debug | Store-mode infrastructure. Not part of 4-tool public surface | Keep available, mark `[INTERNAL]` | Store mode is a deployment concern |
| `rsm_select_index` | repo_id, repo_root, name | selected, active_repo | Internal/debug | Store-mode infrastructure | Keep available, mark `[INTERNAL]` | Per-call repo switching: expose or keep session-scoped? → session-scoped |
| `rsm_current_index` | None | active_repo or null | Internal/debug | Redundant with `active_repo` in every response | Keep available, mark `[INTERNAL]` | Remove after deprecation window |

---

## 10. Result ID and ContextPack ID Strategy

### 10.1 ID types

| ID type | Format | Scope | Lifetime | Example |
|---|---|---|---|---|
| `result_id` | `search_{token_hex(5)}` | `rsm_search` results | Session (search result cache) | `search_a3f91` |
| `context_pack_id` / `result_set_id` | `pack_{token_hex(5)}` | `rsm_prepare_context` results | Session (ResultStore) | `pack_a3f91` |
| `entity_id` | `{extractor}:{kind}:{path}:{name}` | Index-wide | Index lifetime | `python:function:src.auth.login:authenticate` |
| `page_token` / `cursor` | `cursor_{base64(json)}` | Per-query | Until results change or token expires | `cursor_eyJvZmZzZXQiOjI1fQ==` |

### 10.2 ContextPack lifecycle

```
rsm_prepare_context("fix auth bug")
  → context_pack_id: "pack_a3f91"
  → stored in ResultStore (max 8 sets, LRU eviction, max 256 KB/set)

rsm_get_context_page("pack_a3f91", stream="entities", offset=5)
  → returns items 6-10
  → marks "pack_a3f91" as most-recently-used

Session ends or LRU evicts
  → "pack_a3f91" is gone
  → next rsm_get_context_page → EXPIRED_CONTEXT_PACK uncertainty
```

### 10.3 Search result ID lifecycle

```
rsm_search("auth login")
  → results have result_id: "search_b1c2d"
  → stored in a smaller session cache for rsm_find_related anchoring

rsm_find_related({ anchor: { result_id: "search_b1c2d" } })
  → resolves to the entity behind that search result
  → expands relations

Session ends → cache cleared
```

### 10.4 Invalidation

When `active_repo` changes (store mode: `rsm_select_index`), all session-scoped
IDs (search results and context packs) are invalidated. The agent receives
`EXPIRED_CONTEXT_PACK` or `INVALID_PAGE_TOKEN` and must re-query.

---

## 11. Pagination Strategy

### 11.1 rsm_prepare_context

- **Model:** Result set + offset-based paging via `rsm_get_context_page`
- **Default page:** `detail_level="brief"` (5 files, 5 entities, 3 relations, 0 citations)
- **Max page:** `limit=20` on `rsm_get_context_page`
- **Ordering:** Deterministic (the order produced by `build_context_pack`)
- **Token:** Integer `offset` (not an opaque token)
- **Invalid token:** `EXPIRED_CONTEXT_PACK` uncertainty

### 11.2 rsm_get_context_page

- **Model:** Offset-based slice over an already-computed stream
- **Default page:** `limit=5`
- **Max page:** `limit=20`
- **Ordering:** Preserved from the original pack
- **Token:** Integer `offset`
- **Invalid token:** Out-of-range offset → tool-call error. Expired result_set_id → uncertainty

### 11.3 rsm_search

- **Model:** Cursor-based pagination
- **Default page:** `limit=10`
- **Max page:** `limit=25`
- **Ordering:** By descending score, then path (lexicographic tiebreak)
- **Token:** `cursor_{base64(json)}` encoding `{last_result_id, last_score}`
- **Invalid token:** `INVALID_PAGE_TOKEN` uncertainty

Cursor encoding (conceptual):

```python
def encode_cursor(last_result_id: str, last_score: float) -> str:
    payload = {"rid": last_result_id, "s": last_score}
    return "cursor_" + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

def decode_cursor(cursor: str) -> tuple[str, float]:
    raw = base64.urlsafe_b64decode(cursor.removeprefix("cursor_"))
    data = json.loads(raw)
    return data["rid"], data["s"]
```

### 11.4 rsm_find_related

- **Model:** Cursor-based pagination
- **Default page:** `limit=10`
- **Max page:** `limit=50`
- **Ordering:** By strength (strong > medium > weak), then path, then relation_kind
- **Token:** `cursor_{base64(json)}` encoding `{last_path, last_relation_group, last_strength}`
- **Invalid token:** `INVALID_PAGE_TOKEN` uncertainty

---

## 12. Compatibility and Migration Notes

### 12.1 Migration phases (from 61.0)

| Phase | Task | What changes |
|---|---|---|
| **A** (61.3–61.6) | Add new tools | `rsm_prepare_context`, `rsm_search`, `rsm_find_related` added to registry. Old tools unchanged |
| **B** (61.7) | Deprecation notices | Old tools get `[DEPRECATED]` prefix in descriptions. Agent instructions updated |
| **C** (61.7) | Hide old tools | If framework supports it, default `tools/list` returns only 4 tools. Debug flag exposes full registry |
| **D** (future) | Remove | Only after observed zero usage |

### 12.2 Implementation constraints

1. **New tools are thin wrappers.** `rsm_prepare_context` calls the same
   `handle_build_context_pack`. `rsm_search` calls `handle_search_symbols`
   with broader output processing. `rsm_find_related` calls
   `handle_explain_entity` or `handle_query_graph` based on anchor type.

2. **No handler duplication.** New tool handlers compose existing pure
   handler functions. No copy-paste of business logic.

3. **Benchmark preservation.** `rsm_prepare_context` must pass the same
   59.x CI benchmark cases as `rsm_build_context_pack`.

4. **Backward compatibility.** Deprecated tools continue to work with
   identical behavior throughout Phase B.

---

## 13. Benchmark and Test Plan

### 13.1 Schema contract tests (per tool)

| Test | Tool | What it validates |
|---|---|---|
| Required fields present | All 4 | Every response includes `active_repo` (where applicable) and required top-level fields |
| Input validation | All 4 | Missing required fields → `ToolInvocationError`. Wrong types → `ToolInvocationError` |
| Limit/budget caps | `rsm_search`, `rsm_prepare_context` | Values above max are capped with warning |
| Cursor format | `rsm_search`, `rsm_find_related` | Valid cursor resumes correctly. Invalid cursor → `INVALID_PAGE_TOKEN` |
| Result ID uniqueness | `rsm_search` | Two different results never share the same `result_id` |
| ContextPack ID uniqueness | `rsm_prepare_context` | Two different packs never share the same `result_set_id` |

### 13.2 MCP integration tests

| Test | What it validates |
|---|---|
| `tools/list` returns 4+ tools | New tools are registered. Old tools present (Phase A) or hidden (Phase C) |
| `tools/call` with new tools | Each tool responds with correct schema |
| `tools/call` with old tools | Deprecated tools still respond (Phase A/B) |
| `initialize` instructions | Instructions reference new tool names |
| `active_repo` in all responses | `rsm_search`, `rsm_find_related`, `rsm_prepare_context` include `active_repo` |

### 13.3 Benchmark regression (59.x)

| Test | What it validates |
|---|---|
| `rsm_prepare_context` = `rsm_build_context_pack` | Same central/support/test/forbidden files selected |
| CI benchmark cases pass | `rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml` |
| Manual benchmark cases pass | Same results as before rename |

### 13.4 Pagination correctness

| Test | What it validates |
|---|---|
| `rsm_get_context_page` boundary | `offset=total` returns empty, `offset>total` → error |
| `rsm_search` cursor continuity | Next page starts after last result of previous page |
| `rsm_find_related` cursor continuity | Same |
| Expired context pack | `rsm_get_context_page` with evicted `result_set_id` → `EXPIRED_CONTEXT_PACK` |

### 13.5 Warning/staleness tests

| Test | What it validates |
|---|---|
| Stale index warning | When index HEAD ≠ repo HEAD, `STALE_INDEX` warning present |
| Scoped index warning | When index has include/exclude patterns, `SCOPED_INDEX` warning present |
| Budget capped warning | When `budget_chars > 20000`, `BUDGET_CAPPED` uncertainty present |

---

## 14. Implementation Sequence

| Task | Description | Depends on | New code? |
|---|---|---|---|
| **61.2** | Existing MCP compatibility strategy — register new tools alongside old, update instructions | 61.1 | Yes (runtime.py) |
| **61.3** | Implement `rsm_prepare_context` — thin wrapper calling `handle_build_context_pack`, add `active_repo` and `warnings` to output | 61.2 | Yes (runtime.py) |
| **61.4** | Stabilize `rsm_get_context_page` — verify existing implementation, update description | 61.1 | No (code complete) |
| **61.5** | Implement `rsm_search` — wrapper over `handle_search_symbols` + file discovery, cursor-based pagination, search result ID cache | 61.2 | Yes (runtime.py, new handler logic) |
| **61.6** | Implement `rsm_find_related` — anchor resolution, relation group dispatch to `handle_explain_entity` / `handle_query_graph`, cursor pagination | 61.2 | Yes (runtime.py, new handler logic) |
| **61.7** | Deprecate/hide low-level tools — `[DEPRECATED]` descriptions, `[INTERNAL]` markers, updated agent instructions | 61.3–61.6 | Yes (runtime.py descriptions only) |
| **61.8** | MCP migration docs — update `docs/usage/mcp.md`, `AGENTS.md`, examples | 61.7 | No (docs only) |

---

## 15. Decisions and Open Questions

### 15.1 Validated decisions

1. **`rsm_prepare_context` is a direct rename of `rsm_build_context_pack`.** Same handler, same behavior, cleaner name. `active_repo` and `warnings` are additive fields.

2. **`rsm_get_context_page` is unchanged.** Already has a clean, stable contract.

3. **`rsm_search` uses cursor-based pagination.** Matches large result sets better than offset pagination. Cursor is `cursor_{base64(json)}`.

4. **`rsm_find_related` uses anchor priority: `entity_id` > `result_id` > `qualified_name` > `path`.** Most precise to least precise.

5. **`relation_groups` is the filter mechanism for `rsm_find_related`.** Pre-defined groups (tests, imports, exports, etc.) are more agent-friendly than raw relation kinds.

6. **Search results are compact by default.** No inline entity detail. Detail is available via `rsm_find_related`.

7. **No per-call `repo` parameter.** `active_repo` is session-scoped. Multi-repo workflows use store mode (internal).

### 15.2 Open decisions

1. **Should `rsm_search` include a `summary` string or only structured results?**
   - Current direction: include a brief `summary` (e.g., "Found 8 results for 'auth login'").

2. **Should `rsm_find_related` accept multiple anchors for batch expansion?**
   - Current direction: single anchor per call. Batch expansion can be done with multiple calls.

3. **Should `include_rendered` on `rsm_prepare_context` remain as an advanced flag?**
   - Current direction: yes, for backward compatibility. CLI `rsm pack` is unchanged.

4. **Should `graph_neighbors` (multi-hop) be supported in `rsm_find_related` v1 or reserved?**
   - Current direction: reserve for v1. Single-hop expansion covers the most common use cases.

5. **Should search result IDs be stable across different queries for the same entity?**
   - Current direction: no. `search_{hex}` IDs are unique per query. Cross-query stability comes from `entity_id`.

### 15.3 Rejected approaches

1. **Exposing raw `entity_id` as the result ID in search.** Rejected because different queries may return the same entity in different positions, and cursor pagination needs per-result uniqueness.

2. **Offset-based pagination for `rsm_search`/`rsm_find_related`.** Rejected because scores may shift between pages with offset pagination if the index changes. Cursor pagination is stable for the same query.

3. **Adding `include_graph` flag to `rsm_prepare_context` in v1.** Rejected because graph expansion is internal to the pack builder. Exposing it would leak implementation details.

4. **Making `relation_groups` a free-form string field.** Rejected because a closed vocabulary of pre-defined groups is more predictable for agents and easier to validate.

5. **Adding `scope` as free-text instead of enum.** Rejected because `"all" | "files" | "symbols" | "tests" | "docs"` covers the needed use cases without ambiguity.

---

## Validation

This is a documentation-only change. No code was modified.

```bash
$ git diff --stat
 docs/design/mcp_4_tool_interface.md | 782 ++++++++++++++++++++
 1 file changed, 782 insertions(+)

$ git status --short
?? docs/design/mcp_4_tool_interface.md
```

No doc lint checks are configured for markdown files in this repository.
The file is valid Markdown.

---

## 61.1 — Final Report

**File created:**
- `docs/design/mcp_4_tool_interface.md`

**Target tool schemas defined:**
- `rsm_search` — broad discovery with scope/kind/role filters, cursor pagination, compact results
- `rsm_find_related` — anchor-based expansion with 9 relation groups, strength scoring, cursor pagination
- `rsm_prepare_context` — direct rename of `rsm_build_context_pack`, adds `active_repo` and `warnings`
- `rsm_get_context_page` — unchanged, stable offset-based pagination over context packs

**Key design decisions:**
- Shared error model: fatal errors (6 codes) vs recoverable uncertainties (4 codes) vs warnings (7 codes)
- Shared `active_repo` block in all repo-scoped responses
- Cursor-based pagination (`cursor_{base64(json)}`) for `rsm_search` and `rsm_find_related`
- Result IDs: `search_{hex}` for search, `pack_{hex}` for context packs
- `rsm_prepare_context` is a thin rename, not a rewrite
- Anchor priority: `entity_id` > `result_id` > `qualified_name` > `path`
- 9 pre-defined relation groups for `rsm_find_related`
- Old tools kept as deprecated aliases (Phase A/B), hidden later (Phase C)

**Open questions:**
- Summary string in `rsm_search`: include or omit?
- Batch multi-anchor in `rsm_find_related`: support or single only?
- `include_rendered` on `rsm_prepare_context`: keep or remove?
- Multi-hop `graph_neighbors` in v1: support or reserve?
- Search result ID stability across queries: stable or per-query?

**Recommended next step:**
61.2 — Existing MCP compatibility strategy (register new tools alongside old, update agent instructions)

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
- 61.1 complete ✓
