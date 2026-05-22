# Roadmap

This roadmap is directional and should not be read as a committed release promise.

## Implemented foundation

- Project/package scaffolding
- Typed CLI entry point
- Tag-driven package version plus explicit schema/context-pack compatibility constants
- CI baseline with formatting, linting, type checks, and tests
- Deterministic repository indexing
- Python AST and Markdown outline extraction
- Public API export and test relationship extraction
- Repo-map and context-pack generation
- Ranking explanations, BM25 lexical scoring, graph relation selection, and compression profiles
- Benchmark/eval commands with token-savings metrics
- `.ai` export and JSONL import/export
- Pure MCP-style handlers/contracts without runtime server

## Near-term priorities

- Continue improving retrieval precision and ranking explanations.
- Expand internal benchmark coverage before making broad quality claims.
- Keep evidence and uncertainty explicit across generated artifacts.
- Keep runtime dependencies narrow and local-first.

## Deferred

- Runtime MCP server/transport
- Vector database or embedding-first architecture
- Neo4j/graph database backend
- Web UI/dashboard
- LLM-generated claims as source of truth
