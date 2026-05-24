# MCP progressive context retrieval

Status: design proposal (no implementation in this change).

This document proposes a progressive retrieval model for RSM's MCP context-pack
tool. It builds on the compact-by-default behavior introduced in Prompt 46.1
(see [`docs/usage/mcp.md`](../usage/mcp.md) and
[`docs/design/mcp_runtime.md`](mcp_runtime.md)). It does not change CLI
`rsm pack`, ranking, or selection semantics.

## Motivation

Prompt 46.1 made `rsm_build_context_pack` compact by default:

- no full rendered Markdown by default
- no full nested payload by default
- bounded selected entities, relations, and citations
- opt-in flags for rendered, payload, and ranking breakdowns
- CLI `rsm pack` unchanged

Local smoke tests after Prompt 46.1 still showed responses around 14 KB even
in compact mode, because the response inlines `selected_files`,
`selected_entities`, `selected_relations`, and `citations` together. That is
small compared to a full rendered pack, but still:

- Wider than many MCP chat surfaces want to render inline.
- Large enough that some MCP clients spill the response to a temporary
  content file, which the agent then has to re-read as a follow-up step.
- Often more than the agent actually needs on the first turn: the agent
  typically wants a short overview, then drills into one file or entity.

The remaining problem is shape, not just size. A single tool call still tries
to deliver a complete answer. A progressive retrieval model fits MCP and
agent workflows better.

## Goals

- Make the first MCP response very small: small enough to render inline in
  any reasonable MCP chat surface.
- Let the agent ask for more pages or details only when needed.
- Preserve read-only behavior.
- Preserve deterministic ranking and selection.
- Keep CLI `rsm pack` unchanged (full pack, scriptable, no session model).
- Keep the existing `include_rendered` / `include_payload` /
  `include_ranking_breakdowns` opt-in flags available as a debug escape
  hatch.

## Non-goals

- Changing ranking, selection, or budget caps.
- Adding any write tools.
- Writing MCP outputs to disk.
- Adding disk persistence for result sets.
- Adding HTTP, daemon, cloud, or Docker.
- Claiming full MCP conformance.
- Adding a separate `rsm_brief_retrieval` tool at this stage.
- Coupling progressive retrieval to embeddings, LLMs, or a vector store.

## Why progressive retrieval fits MCP

MCP tools are request/response over a session-scoped stdio process. That maps
well to a paging model:

1. The first call returns a brief, scannable page with short IDs.
2. Subsequent calls request specific pages or specific entries by ID.
3. The full Markdown rendering remains available as an explicit debug call.

This matches how agents actually consume context: a small overview is enough
to plan, and only a few items need details.

## Conceptual model: result sets

`rsm_build_context_pack` already builds a deterministic `ContextPack` in
memory. The progressive model treats that in-memory pack as a *result set*
that can be paged over the lifetime of the current MCP session.

Key properties:

- A result set is created by a single `rsm_build_context_pack` call.
- It is identified by an opaque `result_set_id` returned in the response.
- It lives only in the current MCP server process memory.
- It is never written to disk.
- It is bounded in number, evicted on a small LRU cap (see "State bounds").
- It expires when the MCP session ends, when the cap evicts it, or when the
  client calls a release operation (future, optional).

The result set is a thin view over the existing deterministic
`ContextPack`. It does not rerank, refilter, or recompute anything; it only
exposes already-computed slices in a paged shape.

### `result_set_id` format

- Format: `pack_<short-hash>` where `<short-hash>` is a 10–12 character
  base32 or hex digest derived deterministically from
  `(task, profile, budget_chars, index fingerprint, monotonic counter)`.
- The fingerprint component is derived from the existing index metadata
  (entity/relation counts, schema version) already exposed by `rsm_status`.
- The monotonic counter prevents collisions when the same task is rebuilt
  with the same parameters in one session.
- IDs are opaque to clients; clients must treat them as strings.
- IDs are only valid in the MCP session that minted them. Sending an unknown
  ID returns a clear `result_set_unknown` uncertainty rather than a transport
  error.

Example: `pack_4f3a91c2b8`.

### Page model

Each `result_set_id` exposes several deterministic ordered streams:

- `files` — repo-relative file paths (today `selected_files`).
- `entities` — flattened entity entries (today compact `selected_entities`).
- `relations` — flattened relation entries (today compact
  `selected_relations`).
- `citations` — bounded source citations.

A page request takes:

- `result_set_id`
- `stream` ∈ `{files, entities, relations, citations}`
- `offset` (default `0`)
- `limit` (default small; e.g. `5`)

The response always includes:

- the requested slice
- `total` (size of the stream)
- `next_offset` (or `null` if exhausted)
- short stable per-entry IDs (see below)

Ordering is the deterministic ordering already produced by the pack; the
progressive model never reorders.

### Short per-entry IDs

To keep follow-up calls small and human-readable, each entry gets a short
stable ID inside the result set:

- `f1`, `f2`, … for files
- `e1`, `e2`, … for entities (also accept the underlying `entity_id` for
  cross-call stability)
- `r1`, `r2`, … for relations
- `c1`, `c2`, … for citations

Short IDs are stable within a single result set. They are not stable across
result sets. Agents that need stability across calls should pass the
underlying `entity_id` (already globally stable in the index).

## First-page response shape

The first response from `rsm_build_context_pack` becomes a brief page:

```jsonc
{
  "task": "...",
  "result_set_id": "pack_4f3a91c2b8",
  "budget": { "requested_chars": 8000, "used_chars": 0, "truncated": false },
  "truncated": false,
  "counts": {
    "files": 12,
    "entities": 30,
    "relations": 18,
    "citations": 14
  },
  "preview": {
    "files":     [ { "id": "f1", "path": "src/.../foo.py" }, ... ],
    "entities":  [ { "id": "e1", "entity_id": "python:function:...", "name": "...", "path": "...", "start_line": 1, "end_line": 10 }, ... ],
    "relations": [ { "id": "r1", "kind": "tests", "source_entity_id": "...", "target_entity_id": "..." }, ... ],
    "citations": [ { "id": "c1", "subject_id": "...", "path": "...", "start_line": 1, "end_line": 10 }, ... ]
  },
  "uncertainties": [],
  "agent_instructions": [
    "Use only paths listed in this response.",
    "Do not infer missing paths, symbols, or class names.",
    "Call rsm_explain_entity for details about a selected entity.",
    "Call rsm_context_page for more files/entities/relations from this result set."
  ],
  "omitted_sections": ["rendered", "payload", "ranking_breakdowns"],
  "how_to_get_more": [
    "Call rsm_context_page with result_set_id and stream=entities to page entities.",
    "Call rsm_explain_entity with an entity_id for focused details.",
    "Call rsm_build_context_pack with include_rendered=true for the full Markdown pack."
  ]
}
```

Defaults aim for ≤ 3–4 entries per preview stream so the first response stays
on the order of 2–4 KB in typical repositories.

## Follow-up tool: `rsm_context_page` (future, optional)

A small read-only tool that pages an existing result set. Sketch:

- Input: `result_set_id`, `stream`, `offset?`, `limit?`.
- Output: ordered slice, `total`, `next_offset`, short IDs.
- Bounds: same per-stream caps as the existing compact response (e.g.
  `max_entities=15`, `max_relations=10`, `max_citations=12`).

This tool is **not** added in this design pass. The current task is design
only. If implemented later, it should reuse `handle_build_context_pack`'s
existing deterministic outputs without re-running the pack.

## Why session-local in-memory only

Disk persistence would re-introduce most of the problems progressive
retrieval is trying to avoid (and add new ones):

- It would require a cache directory, eviction policy, schema, and possibly
  invalidation against the underlying index.
- It would broaden the safety surface from "read the existing index" to
  "read and write a new on-disk cache".
- It would make result sets outlive the agent session in unexpected ways.

By restricting state to the MCP server process:

- The cache vanishes when the session ends; no leftover files.
- No new disk writes, matching the existing read-only safety model.
- No new failure modes from corrupted or stale on-disk caches.

The MCP runtime is launched per session by the client; this matches the
expected lifetime of a result set.

## State bounds

To keep the in-memory cache safe and predictable:

- Maximum result sets per session: small constant (e.g. `8`).
- Eviction policy: LRU.
- Eviction is silent for the caller; expired IDs return
  `result_set_unknown` as an uncertainty with a clear message and a
  suggested action (rebuild the pack).
- Maximum size per result set: bounded by the existing context-pack budget
  cap (`_MAX_CONTEXT_BUDGET`).
- No background timers; eviction happens lazily on tool calls.

A future implementation should keep the cache implementation small: a
plain ordered dict guarded by a single lock is enough.

## Safety preservation

The progressive model preserves the existing phase 1 safety boundary:

- Read-only: result sets are derived from an already-built index; no
  database writes.
- Bounded: per-stream caps and an LRU cap on the cache.
- Deterministic: ordering and content come from the existing context pack.
- No new shell, network, or filesystem write surfaces.
- No background processes; the session ends with the MCP stdio process.
- Errors stay recoverable: unknown `result_set_id` is reported via an
  uncertainty entry, not a transport-level failure.

## Compatibility with CLI `rsm pack`

CLI `rsm pack` is unchanged:

- It still emits the full pack as Markdown / YAML.
- It does not allocate result sets.
- It does not depend on the MCP runtime.

The MCP tool's existing opt-in flags also remain:

- `include_rendered=true` returns the full rendered Markdown/YAML in a
  single response (debug path).
- `include_payload=true` returns the full nested payload (debug path).
- `include_ranking_breakdowns=true` returns ranking details.

These flags continue to be the documented escape hatch for one-shot full
output when an agent has decided it actually needs everything.

## Migration / rollout plan (proposal)

This document is design-only. A safe rollout would be:

1. Land this design doc (current change).
2. Add a minimal in-memory result-set registry inside the MCP runtime
   keyed by `result_set_id`, behind feature gating so the default
   compact response is unchanged until clients are ready.
3. Have `rsm_build_context_pack` emit a `result_set_id` and `counts`
   alongside the current compact preview lists, while still returning
   the same bounded preview content (so existing agents keep working).
4. Add a `rsm_context_page` tool that consults the registry.
5. Add stdio tests covering: ID minting, paging, unknown ID handling,
   eviction, and the unchanged default preview shape.
6. Validate against `rsm` and `lifecore_ros2` before promoting the
   model out of prototype status.

Each step is independently revertible and adds no disk-resident state.

## Open questions

- Should the `result_set_id` also be returned by `rsm_search_symbols`
  and `rsm_query_graph` for symmetric paging? Probably yes, but out of
  scope for this design.
- Should `rsm_explain_entity` accept a short ID like `e1` scoped to the
  most recent result set, or only the underlying `entity_id`? The
  current proposal sticks to the underlying `entity_id` to avoid
  hidden "last result set" state.
- Should we ever emit a `release_result_set` tool? Likely not for phase 1;
  LRU eviction is enough.

## Summary

Compact-by-default helped, but a single response is still trying to deliver
the whole answer. Progressive retrieval splits that into a brief first page
plus deterministic follow-up paging over an in-memory result set,
identified by an opaque `result_set_id`. State stays read-only, in-memory,
session-scoped, and bounded. CLI `rsm pack` and ranking semantics are
untouched.
