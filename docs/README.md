# RSM documentation

This documentation explains how to use RSM as a local context compiler for coding-agent workflows.

Start with the quickstart if you want to run commands. Read the concepts if you want to understand what repo maps, context packs, citations, relations, and uncertainty mean. Use the design docs if you want to inspect how the system is built or contribute to it.

## Start here

- **I want to try RSM:** read [Quickstart](quickstart.md).
- **I want to understand the main idea:** read [Context packs](concepts/context_packs.md) and [Repo maps](concepts/repo_maps.md).
- **I want to use the CLI:** read [CLI usage](usage/cli.md).
- **I want to use the MCP prototype:** read [MCP usage](usage/mcp.md).
- **I want to understand evaluation:** read [Benchmarks](eval/benchmarks.md).
- **I want to understand release/versioning:** read [Versioning](release/versioning.md).
- **I want to see examples:** read [CLI Examples](usage/examples.md).
- **I want to know what RSM does not do:** read [Known Limitations](../known_limitations.md).
- **I want to see what is planned:** read [Roadmap](design/roadmap.md).

## Limitations and roadmap

- [Known Limitations](../known_limitations.md) — what RSM supports well, what it does not, and what that means.
- [Roadmap](design/roadmap.md) — current focus and near-term backlog.

## Concepts

- [Semantic index](concepts/semantic_index.md) — entities, relations, evidence, and deterministic extraction.
- [Repo maps](concepts/repo_maps.md) — compact structural repository summaries.
- [Context packs](concepts/context_packs.md) — task-specific, source-cited context under a budget.
- [Compression profiles](concepts/compression_profiles.md) — deterministic context-noise filtering profiles.
- [Claims and invariants](concepts/claims_invariants.md) — evidence rules and current scope.

## Usage

- [CLI](usage/cli.md) — local commands for indexing, packing, export, import, eval, and checks.
- [Agent workflows](usage/agent_workflows.md) — task-oriented agent usage patterns.
- [.ai directory](usage/ai_directory.md) — generated/static artifact policy and staleness rules.
- [JSONL interchange](usage/jsonl_interchange.md) — export/import role and caveats.
- [MCP runtime usage](usage/mcp.md) — `rsm mcp serve` read-only stdio MCP server.

## Evaluation

- [Benchmarks](eval/benchmarks.md) — internal dataset scope and interpretation limits.
- [Token savings](eval/token_savings.md) — approximate token metrics and when savings are meaningful.

## Design notes

- [Data model](design/data_model.md) — schema/version contracts, entity and relation semantics.
- [MCP handlers and contracts](design/mcp_server.md) — current pure local handler surface and contract status.
- [MCP runtime](design/mcp_runtime.md) — phase 1 stdio prototype design and security boundaries (MCP-compatible JSON-RPC, not yet externally conformance-tested; see [usage/mcp.md](usage/mcp.md)).
- [CLI output summarizer](design/cli_output_summarizer.md) — future design only.
- [Architecture overview](design/architecture.md) — layered semantic compiler model.
- [Roadmap](design/roadmap.md) and [MVP review](design/mvp_review.md) — historical planning/review notes.

## Release/versioning

- [Versioning](release/versioning.md) — hatch-vcs dynamic package versioning, schema/context-pack contracts, and protected-main release policy.

## Case studies

- [lifecore_ros2](case_studies/lifecore_ros2.md) — one real-repository validation case study.

## Global caveats

RSM is experimental and pre-1.0. It is local-first, deterministic, source-cited, and does
not use LLM calls, embeddings, or vector databases in the MVP. Benchmark results are
internal and directional; token estimates are approximate; `confirmed PublicAPI` means
exported in source, not a compatibility promise. MCP-style handlers/contracts exist;
a minimal local stdio MCP-compatible JSON-RPC prototype (`rsm mcp serve`) is
available for local dogfooding (see [usage/mcp.md](usage/mcp.md)). External MCP
client conformance has not yet been tested.
