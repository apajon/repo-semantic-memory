# MCP runtime usage

The MCP prototype lets an MCP-capable client start RSM as a local stdio process and ask it for repository context during an agent/client session.

It is intentionally small in phase 1: read-only tools, explicit repo/db paths, no Docker, no daemon, no cloud, no HTTP server, and no auto-indexing.

This is a minimal local stdio MCP-compatible JSON-RPC prototype. It is not yet externally conformance-tested against a real MCP client.

`rsm mcp serve` exposes the existing pure RSM handlers through a local stdio JSON-RPC loop that follows the
[Model Context Protocol](https://modelcontextprotocol.io/) stdio transport shape. It is launched by an MCP client (an agent or IDE) for the lifetime of that client's session and exits when the client closes its stdin.

The runtime does not index your repository, does not modify your repository,
does not modify the SQLite index, does not execute arbitrary shell commands,
does not run tests, and does not apply patches. It is a thin transport over the
read-only handlers documented in
[`docs/design/mcp_server.md`](../design/mcp_server.md). The
`rsm_get_git_summary` tool may invoke a fixed, read-only `git` subprocess
internally via the existing extractor; that is bounded local Git inspection
with hardcoded arguments, not arbitrary command execution.

## Prerequisites

Build the local index first. The MCP server only reads from it.

```bash
# Option A: explicit DB path (original workflow, unchanged)
uv run rsm index /path/to/target-repo --db /path/to/target-repo/.rsm/index.sqlite

# Option B: index directly into the RSM Index Store and register in one step (recommended)
uv run rsm index /path/to/target-repo --register

# Option C: register an existing DB into the store without re-indexing
uv run rsm store register /path/to/target-repo --index
```

Option B (`rsm index --register` without `--db`) writes the DB to the RSM Index Store canonical
path and does **not** write anything to the target repository.

If the database is missing or out of date, regenerate it with `rsm index`
before launching the MCP server. The server will report missing/stale state
but does **not** rebuild it. See
[`docs/design/index_staleness.md`](../design/index_staleness.md) for the
status states, the `rsm_status` payload contract, and the policy for
stale / `schema_mismatch` / `unknown` indexes.

## Starting the server

```bash
# With explicit --db (original, always works)
uv run rsm mcp serve \
  --repo /absolute/path/to/target-repo \
  --db /absolute/path/to/target-repo/.rsm/index.sqlite

# Without --db (requires prior rsm store register or rsm index --register)
uv run rsm mcp serve \
  --repo /absolute/path/to/target-repo
```

`--repo` is required. `--db` is optional:

- When `--db` is provided: the existing validation rules apply (must be an existing file;
  when inside `--repo`, it must resolve within the repo tree).
- When `--db` is absent: the RSM Index Store registry is consulted. If no entry is found the
  command exits with code `2` and a clear `error:` line on stderr.

Invalid inputs always exit with code `2` and a clear `error:` line on stderr.

## From-source MCP client configuration

This is the supported configuration during local dogfooding. PyPI installation
is not required.

**With explicit `--db` (original workflow, unchanged):**

```json
{
  "mcpServers": {
    "repo-semantic-memory": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/repo-semantic-memory",
        "rsm",
        "mcp",
        "serve",
        "--repo",
        "/absolute/path/to/target-repo",
        "--db",
        "/absolute/path/to/target-repo/.rsm/index.sqlite"
      ]
    }
  }
}
```

**With RSM Index Store (register once, no `--db` in config):**

```bash
# One-time setup: index directly into the RSM Index Store.
uv run rsm index /absolute/path/to/target-repo --register
```

```json
{
  "mcpServers": {
    "repo-semantic-memory": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/repo-semantic-memory",
        "rsm",
        "mcp",
        "serve",
        "--repo",
        "/absolute/path/to/target-repo"
      ]
    }
  }
}
```

## Exposed tools (read-only)

| Tool                          | Wraps                                                 |
| ----------------------------- | ----------------------------------------------------- |
| `rsm_status`                  | local store metadata + version info                   |
| `rsm_search_symbols`          | `handle_search_symbols`                               |
| `rsm_explain_entity`          | `handle_explain_entity`                               |
| `rsm_build_context_pack`      | `handle_build_context_pack`                           |
| `rsm_get_context_page`        | session-local result store (no recompute)             |
| `rsm_query_graph`             | `handle_query_graph`                                  |
| `rsm_validate_patch_context`  | `handle_validate_patch_context`                       |
| `rsm_get_git_summary`         | `handle_get_git_summary`                              |

Each tool preserves the existing handler's bounds (result size caps, graph
depth/entity caps, context-pack budget caps, citations, and uncertainty
records).

## Deferred tools

The following are intentionally **not** exposed in phase 1:

- `rsm_index`
- `rsm_export_ai`
- `rsm_export_jsonl`
- `rsm_import_jsonl`
- any invariant write tool
- arbitrary command execution
- test execution
- patch application
- filesystem browsing tools

## Dependency decision

The phase 1 server is implemented directly on top of the Python standard
library (`json`, `sys`, `pathlib`). It speaks newline-delimited JSON-RPC 2.0
on stdio, which is the MCP stdio transport. The official `mcp` Python SDK was
considered but not adopted because:

- RSM has a zero-runtime-dependency policy; the SDK pulls in `pydantic`,
  `anyio`, and related runtime dependencies that are out of scope for a
  minimal read-only prototype.
- The phase 1 surface (`initialize`, `tools/list`, `tools/call`, `ping`,
  `shutdown`) is small enough to implement and audit by hand.
- Keeping the implementation in one focused module makes the safety boundary
  (read-only, no arbitrary shell command execution, no network) easy to review.

This decision is revisited if/when the runtime grows beyond the phase 1
read-only surface.

## Safety summary

- No arbitrary shell command execution.
- No network access.
- No mutation of repository or database state in phase 1.
- No auto-indexing.
- Explicit `--repo`/`--db` validation.
- DB path must be inside the repository root by default.
- Existing handler output and path bounds are preserved.

If a tool call fails for a recoverable reason (unknown entity ID, missing
changed path, etc.) the server returns a JSON-RPC success result with
`isError: true` and a short text message rather than a transport-level error.

## What remains untested

Phase 1 ships unit tests covering:

- CLI subcommand presence and help output.
- `--repo`/`--db` path validation, including DB-outside-repo rejection.
- Tool registry surface (exact names, deferred tool exclusion).
- Wrapper behavior for each exposed tool (delegates to the existing handler).
- JSON-RPC dispatch for `initialize`, `tools/list`, `tools/call`, malformed
  JSON, and unknown methods, exercised with in-memory `stdin`/`stdout` streams.

End-to-end protocol conformance against an external MCP client is **not** part
of phase 1. The plan is to validate against a real MCP client (and against
`lifecore_ros2`) as part of a later phase, before promoting the runtime out
of prototype status.

## Reading MCP tool output safely

MCP tool results include machine-friendly fields for agents. Prefer these fields before summarizing:

- `path`
- `start_line`
- `end_line`
- `selected_files`
- `selected_entities`
- `selected_relations`
- `citations`
- `agent_instructions`

Agents should not infer paths, symbols, or classes that are not listed in the tool output.

### Prompt example

```
Use RSM MCP and print `selected_files`, `selected_entities`, and `selected_relations` exactly as returned before summarizing.
```

## Compact-by-default context packs and progressive disclosure

`rsm_build_context_pack` returns a **brief first-page preview** by default. The full Markdown/YAML rendering, the full nested `payload`, citations, and items beyond the brief caps are not emitted unless the caller explicitly opts in or pages over the session-local result set with `rsm_get_context_page`. This is a deliberate MCP-prototype evolution: large tool outputs are often spilled by MCP clients into temporary resource files that an agent then has to fetch again, which is wasteful and bad as a default workflow. The CLI `rsm pack` command is unchanged and still emits the full pack.

### Default MCP response shape

A default `rsm_build_context_pack` MCP call returns roughly:

- `task` — the requested task string.
- `truncated` — whether the budget cap or pack size forced truncation.
- `budget` — `requested_chars`, `used_chars`, `truncated`.
- `detail_level` — echoes the resolved preview profile (`"brief"` by default).
- `selected_files` — repo-relative file paths the agent should read (brief: up to 5).
- `selected_entities` — bounded list of flattened entries with `entity_id`, `kind`, `name`, `qualified_name`, `path`, `start_line`, `end_line` (brief: up to 5).
- `selected_relations` — bounded list of `{kind, source_entity_id, target_entity_id}` entries (brief: up to 3).
- `citations` — bounded list of source citations (brief: empty by default; full list paged via `rsm_get_context_page`).
- `uncertainties` — machine-readable uncertainty envelopes.
- `agent_instructions` — verbatim guidance to print before summarizing.
- `omitted_sections` — names of bulky sections omitted from the response (e.g. `rendered`, `payload`, `ranking_breakdowns`).
- `how_to_get_more` — concrete follow-up calls to retrieve the omitted material.
- `result_set_id` — opaque session-scoped ID (`pack_<10 hex>`) usable with `rsm_get_context_page` to page over additional items without recomputing.
- `counts` — per-stream item counts (`files`, `entities`, `relations`, `citations`, `ranking_breakdowns`) stored in the session-local result set. Always reflects the full stream size, even when the preview is empty.
- `next` — per-stream availability hints. Each entry advertises a stream where more items are available than the preview shows, e.g. `{"citations": {"stream": "citations", "available": 12, "shown": 0, "tool": "rsm_get_context_page"}}`.

`rendered` and `payload` are still present as keys, but are empty (`""` and `{}`) by default, so existing consumers that check for key presence keep working.

In brief mode, the verbose full-list compatibility fields `selected_entity_ids` and `selected_relation_keys` are intentionally returned as empty arrays (`[]`). The full data is still reachable through `result_set_id` + `rsm_get_context_page`, and `counts.entities` / `counts.relations` continue to report the full totals. `detail_level="compact"` keeps these lists populated for agents that rely on the post-46.1/46.3 one-shot shape; `include_payload=true` continues to expose the full nested payload.

### Preview profiles and per-stream caps

| `detail_level` | `max_files` | `max_entities` | `max_relations` | `max_citations` |
| -------------- | ----------- | -------------- | --------------- | --------------- |
| `brief` (default) | 5         | 5              | 3               | 0               |
| `compact`      | unbounded   | 15             | 10              | 12              |

Brief is the default because the result set is always built and registered for paging; an agent that needs more items should call `rsm_get_context_page` rather than asking for a heavier first response. `compact` preserves the post-46.1/46.3 one-shot preview shape for agents that want a larger first answer.

### Opt-in flags

Pass these in `arguments` to opt into heavier output:

| Argument                       | Default   | Effect                                                                 |
| ------------------------------ | --------- | ---------------------------------------------------------------------- |
| `detail_level`                 | `"brief"` | `"brief"` (small preview) or `"compact"` (larger one-shot preview).    |
| `include_rendered`             | `false`   | Include Markdown (or YAML when `format=yaml`) rendering of the pack.   |
| `include_payload`              | `false`   | Include the full nested context-pack payload dict.                     |
| `include_ranking_breakdowns`   | `false`   | Include `ranking_breakdowns` under `payload` (or alone if no payload). |
| `max_files`                    | profile   | Override the per-profile file preview cap.                             |
| `max_entities`                 | profile   | Override the per-profile entity preview cap.                           |
| `max_relations`                | profile   | Override the per-profile relation preview cap.                         |
| `max_citations`                | profile   | Override the per-profile citation preview cap.                         |

Explicit `max_*` values take precedence over the profile defaults and are clamped to a safety cap (200). Negative values are rejected as tool-call errors. Even when included, output remains bounded by the existing budget and profile behavior. Some MCP clients store long tool outputs as temporary content resources rather than inlining them; that is expected for `include_rendered=true` debug runs and acceptable, but should not be the default workflow.

### Recommended progressive workflow

1. Call `rsm_build_context_pack` with defaults to get a brief preview plus an opaque `result_set_id`, per-stream `counts`, and a `next` map of streams that have more items available.
2. Inspect `selected_files`, `selected_entities`, and `selected_relations`.
3. Call `rsm_explain_entity` with a specific `entity_id` for focused details.
4. Call `rsm_get_context_page` with the `result_set_id` from step 1 to page over additional `files`, `entities`, `relations`, `citations`, or `ranking_breakdowns` without recomputing the pack. The brief default omits `citations`; they are always retrievable this way when the pack produced any.
5. Pass `detail_level="compact"` if you want a larger one-shot preview without paging.
6. Only call `rsm_build_context_pack` again with `include_rendered=true` if a full Markdown pack is actually needed (e.g. debugging the ranking output).

Ranking behavior, selected entities, and selected relations are **not** changed by these MCP defaults; only the response shape is.

## Progressive context retrieval (`rsm_get_context_page`)

`rsm_build_context_pack` registers its compact streams (`files`, `entities`, `relations`, `citations`, and optional `ranking_breakdowns`) in a small **in-memory session-local result store**. The build response carries an opaque `result_set_id` (format: `pack_<10 hex chars>`) and a `counts` object listing how many items each stream has. Agents page over those streams by calling `rsm_get_context_page` with the same `result_set_id`.

Key properties:

- **Read-only and bounded.** No disk writes, no background timers. The store keeps at most 8 result sets and at most 256 KB per result set; oldest entries are evicted on insertion.
- **No recompute.** `rsm_get_context_page` only ever returns slices of the already-stored streams. It does not re-run ranking, selection, or budget evaluation.
- **Session-scoped IDs.** `result_set_id` is stable only within the current MCP server process. It is not reproducible across sessions and must not be persisted by the client.
- **Short per-entry IDs.** Each stored entry has a short stable ID inside its result set: `f1, f2, …` for files, `e1, e2, …` for entities, `r1, r2, …` for relations, `c1, c2, …` for citations, `b1, b2, …` for ranking breakdowns.

### `rsm_get_context_page` arguments

| Argument         | Required | Default | Effect                                                                                |
| ---------------- | -------- | ------- | ------------------------------------------------------------------------------------- |
| `result_set_id`  | yes      | —       | The opaque ID returned by a previous `rsm_build_context_pack` call in the same session.|
| `stream`         | yes      | —       | One of `files`, `entities`, `relations`, `citations`, `ranking_breakdowns`.            |
| `offset`         | no       | `0`     | Zero-based start offset within the stream.                                            |
| `limit`          | no       | `5`     | Maximum entries to return. Hard upper bound: `20`.                                    |

### `rsm_get_context_page` response

```jsonc
{
  "result_set_id": "pack_4f3a91c2b8",
  "stream": "entities",
  "offset": 0,
  "limit": 5,
  "total": 12,
  "next_offset": 5,
  "items": [
    {"id": "e1", "entity_id": "python:function:...", "name": "...", "path": "...", "start_line": 1, "end_line": 10},
    ...
  ],
  "uncertainties": []
}
```

`next_offset` is `null` when the stream is exhausted. `items` is empty (and `next_offset` is `null`) when `offset` is past the end.

### Error handling

- **Unknown or expired `result_set_id`** is a *recoverable tool-level outcome*: the response includes a `result_set_unknown` entry under `uncertainties` with `recoverable: true`. The suggested action is to call `rsm_build_context_pack` again to mint a fresh result set. This is **not** surfaced as a JSON-RPC protocol error.
- **Malformed arguments** (missing `result_set_id`/`stream`, unknown `stream` value, out-of-range `offset`/`limit`) are normal MCP tool-call errors: the response carries `isError: true` and a short message, leaving the JSON-RPC envelope intact.

