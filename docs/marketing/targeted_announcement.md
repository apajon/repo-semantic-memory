# Targeted public announcement draft

## 1. Positioning

`repo-semantic-memory` (`rsm`) is an experimental pre-1.0 repository context compiler for coding agents.

It turns a local repository into deterministic, source-cited context artifacts: repo maps, task-specific context packs, `.ai/` snapshots, JSONL graph exports, and benchmark reports.

The goal is not to replace source reading. The goal is to give an agent a better starting point: compact, task-shaped context with cited files, symbols, relations, uncertainties, and explicit caveats.

RSM is local-first, deterministic, and evidence-oriented. It currently targets Python-first repositories and supporting documentation.

## 2. What it does

`rsm` currently supports:

- indexing Python-first repositories;
- extracting Python symbols from source files;
- extracting Markdown documentation sections;
- extracting explicit public API exports from package `__init__.py` files;
- inferring static test relationships between tests and source entities;
- building broad repo maps for repository orientation;
- building task-specific context packs for focused agent work;
- preserving structural relations such as `contains`, `exports`, `imports`, and `tests`;
- exporting `.ai/` artifacts for agent-facing snapshots;
- exporting and importing JSONL graph artifacts;
- evaluating retrieval/context quality against internal benchmark tasks;
- estimating approximate token savings with deterministic `chars / 4` accounting;
- exposing MCP-style local handlers/contracts, without shipping a runtime MCP server yet.

## 3. What it does not do

`rsm` is deliberately narrow at this stage.

It is not:

- an LLM agent;
- a vector database;
- an embeddings pipeline;
- a generic knowledge graph platform;
- a hosted service;
- a web UI;
- a replacement for reading source;
- a stable 1.0 API;
- a runtime MCP server yet;
- a runtime introspection system for ROS, Python, or application state.

It compiles structured repository context. It does not “understand” a codebase in the human sense, and it does not prove correctness.

## 4. Suggested GitHub repository description

Deterministic, local-first repository context compiler for coding agents: source-cited repo maps, task-specific context packs, `.ai/` exports, and benchmark tooling. Experimental pre-1.0.

## 5. Suggested short README tagline

Deterministic, source-cited repository context packs for coding agents.

Local-first. Python-first. Experimental pre-1.0.

## 6. Suggested longer README tagline

`repo-semantic-memory` compiles local repository structure into source-cited context packs for coding agents: files, symbols, relations, uncertainties, and benchmarkable retrieval outputs.

## 7. Suggested LinkedIn post

I’m sharing `repo-semantic-memory` (`rsm`), an experimental pre-1.0 tool for deterministic repository context compilation.

The idea is simple: before asking a coding agent to inspect an entire repository blindly, generate a compact, task-shaped context pack with cited files, symbols, structural relations, and explicit uncertainty.

`rsm` indexes Python-first repositories, extracts structural signals such as symbols, documentation sections, package exports, and test relationships, then builds source-cited repo maps and task-specific context packs. It also exports `.ai/` artifacts and includes internal evaluation commands for retrieval quality and approximate token-savings checks.

The design constraints are intentional:

- local-first;
- deterministic outputs;
- source-linked evidence;
- no LLM calls;
- no embeddings;
- no vector database;
- no hosted service.

It currently includes MCP-style local handlers/contracts, but no runtime MCP server yet. That is likely the next important integration step: a local stdio MCP server launched by the agent/client session.

Repository: https://github.com/apajon/repo-semantic-memory

## 8. Shorter LinkedIn post

I’m sharing `repo-semantic-memory` (`rsm`), an experimental local-first repository context compiler for coding agents.

It indexes Python-first repositories and produces source-cited repo maps, task-specific context packs, `.ai/` snapshots, and benchmark reports. The goal is to give an agent a compact, task-shaped starting point with cited files, symbols, and relations instead of sending it into a repository blind.

Current scope:

- deterministic local indexing;
- Python symbols, docs sections, exports, and test relationships;
- context packs with citations and uncertainty;
- internal retrieval/context evaluation;
- MCP-style handlers/contracts, but no runtime MCP server yet.

Repository: https://github.com/apajon/repo-semantic-memory

## 9. Suggested Discord / ROS-adjacent message

Sharing `repo-semantic-memory` (`rsm`): an experimental local-first context compiler for coding-agent workflows on Python-first repositories.

It generates source-cited repo maps, task-specific context packs, `.ai` artifacts, and internal benchmark reports. The useful part is not just file matching: context packs can preserve symbols, exports, test relationships, and structural relations such as `contains`, `exports`, and `tests`.

It is not a vector DB, not an LLM agent, and not a runtime MCP server yet. It currently has MCP-style handlers/contracts, with a local stdio MCP runtime planned as a likely next step.

Repo: https://github.com/apajon/repo-semantic-memory

## 10. Suggested GitHub release note blurb

This release stabilizes `repo-semantic-memory` as an experimental deterministic repository context compiler.

Highlights:

- source-cited repo maps and context packs;
- Python symbol extraction;
- Markdown section extraction;
- explicit package export extraction;
- static test relationship extraction;
- compression profiles;
- ranking explanations;
- internal retrieval/context evaluation;
- tag-driven package versioning via `hatch-vcs`;
- documentation cleanup and `lifecore_ros2` dogfooding case study.

Caveat: this is still pre-1.0. APIs, schemas, and context-pack formats may evolve.

## 11. Suggested caveats block

> **Caveats**
>
> - `repo-semantic-memory` is experimental pre-1.0.
> - Benchmark results are internal and directional.
> - There is no broad superiority claim over grep, repo maps, RAG, vector search, or other retrieval systems.
> - Token-savings numbers are approximate and use deterministic `chars / 4` accounting.
> - `confirmed PublicAPI` means a symbol is explicitly exported by source, not that it is a stable public API promise.
> - Inferred relations and components must be verified against cited source.
> - The `lifecore_ros2` case study is dogfooding evidence, not general proof.
> - MCP-style handlers/contracts exist, but no runtime MCP server is shipped yet.

## 12. Announcement strategy

### Share now, but narrowly

Reasonable now:

- GitHub repository description;
- README polishing;
- small LinkedIn post;
- direct sharing with technical peers;
- ROS-adjacent mention only if framed as “agent context tooling for Python/ROS repos,” not as a ROS tool.

Do not frame it as:

- production-ready;
- an MCP server;
- a replacement for RAG/vector DB;
- a solved agent-memory system;
- a ROS introspection tool.

### Wait for MCP before broader diffusion

A broader announcement will land better once RSM has:

- a local stdio MCP server;
- client-session-scoped startup;
- read-only tool surface;
- clear example client config;
- `rsm mcp serve --repo ... --db ...`;
- a short demo showing an agent requesting a context pack through MCP.

That will turn the message from:

> “Here is a CLI/context compiler agents can use.”

into:

> “Here is a local MCP server that gives coding agents source-cited repository context on demand.”

That second message is much easier for people to understand and try.

## 13. Recommended current public wording

Use this:

> `repo-semantic-memory` is an experimental, local-first repository context compiler for coding agents. It generates source-cited repo maps, task-specific context packs, `.ai/` artifacts, and benchmark reports from local repository evidence. It is not an LLM agent, not a vector DB, and not a runtime MCP server yet.

Avoid this:

> RSM solves coding-agent memory.

Avoid this:

> RSM is better than RAG.

Avoid this:

> RSM understands your codebase.

Avoid this:

> RSM is an MCP server.

## 14. Recommended next announcement milestone

The next stronger announcement should wait for:

```bash
rsm mcp serve --repo /path/to/repo --db /path/to/repo/.rsm/index.sqlite
```

with read-only tools such as:
- rsm_status;
- rsm_search_symbols;
- rsm_explain_entity;
- rsm_build_context_pack;
- rsm_query_graph;
- rsm_validate_patch_context;
rsm_get_git_summary.