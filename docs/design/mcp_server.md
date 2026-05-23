# MCP handlers and contracts

RSM has MCP-style typed contracts and pure local handler functions, and now also
ships a minimal local stdio MCP-compatible JSON-RPC prototype.

The existing handlers are deterministic local building blocks over RSM's index,
graph, context-pack, and Git-summary logic. They are not a transport, daemon,
network listener, or long-running process by themselves. The phase-1 runtime
wraps these handlers instead of reimplementing indexing or query logic.

## Current status

- Contracts describe planned tool envelopes and request/response shapes.
- Pure handlers call existing local deterministic logic.
- Handler output should preserve evidence/citations where available and mark
  uncertainty when evidence is incomplete.
- A minimal local stdio MCP-compatible JSON-RPC prototype is available for
  read-only local dogfooding and is not yet externally conformance-tested.
- No transport, daemon, network listener, HTTP server, Docker image, cloud
  service, LLM, embedding, vector database, or remote API dependency is
  introduced.

## Phase 1 read-only surface

The planned phase 1 runtime surface is read-only:

- `rsm_status`
- `rsm_search_symbols`
- `rsm_explain_entity`
- `rsm_build_context_pack`
- `rsm_query_graph`
- `rsm_validate_patch_context`
- `rsm_get_git_summary`

Mutation-oriented tools such as indexing, exports/imports, invariant writes,
test execution, arbitrary command execution, and patch application are deferred.

## Runtime split

Runtime/server concerns are tracked separately in [MCP runtime](mcp_runtime.md).
Keeping contracts separate from runtime transport avoids freezing a server API
before the local deterministic behavior, path validation, staleness reporting,
and safety boundaries are stable.
