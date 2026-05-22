# Architecture overview

`repo-semantic-memory` is structured as a layered semantic compiler for repositories.

1. Raw repository inputs
2. Symbol index
3. Structural graph
4. ECS-style semantic components
5. Claims/contracts/invariants
6. Evidence and temporal validity
7. Context pack builder
8. Benchmark harness
9. MCP integration later

The MVP favors deterministic extraction before generated summaries. It avoids LLM calls, embeddings, vector databases, web UI work, and runtime MCP server dependencies.

Implemented layers include deterministic repository indexing, Python AST extraction, Markdown outline extraction, public API export extraction, test relationship extraction, repo maps, context packs, evaluation commands, `.ai` export, JSONL interchange, and pure MCP-style handlers.
