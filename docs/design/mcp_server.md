# MCP handlers and contracts

RSM currently includes pure deterministic MCP-style handlers and typed contracts over local core logic. These are local building blocks, not a runtime server.

## Current status

- Contracts describe planned tool envelopes and request/response shapes.
- Pure handlers can call existing local index/context-pack logic.
- No transport, daemon, network listener, or runtime MCP server is shipped.
- No LLM, embedding, vector database, or remote API dependency is introduced.

## Intended tool surface

The planned surface includes local, bounded tools such as symbol search, entity explanation, context-pack building, graph querying, `.ai` export, patch-context validation, and Git summary.

Every semantic response should preserve evidence/citations where available and mark uncertainty when evidence is incomplete.

## Runtime split

Runtime/server concerns are tracked separately in [MCP runtime](mcp_runtime.md). Keeping contracts separate from runtime transport avoids freezing a server API before the local deterministic behavior and security model are stable.
