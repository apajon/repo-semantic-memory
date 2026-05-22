# Targeted public announcement draft

## 1) Short positioning

`repo-semantic-memory` (`rsm`) is an experimental pre-1.0, deterministic repository context compiler for coding agents. It produces source-cited context packs from repository evidence, runs local-first, and supports benchmarkable evaluation.

## 2) What it does

- indexes Python repositories
- extracts symbols, Markdown sections, exports, and test relationships
- builds repo maps and task-specific context packs
- exports `.ai/` artifacts
- evaluates context quality and approximate token savings
- includes MCP-style local handlers/contracts, but no MCP runtime server yet

## 3) What it does not do

- not a vector DB
- not an LLM agent
- not a generic knowledge graph platform
- not a replacement for reading source
- not stable 1.0
- not currently an MCP server runtime

## 4) Suggested GitHub repository description

Deterministic, local-first repository context compiler for coding agents: source-cited repo maps/context packs, `.ai/` exports, and benchmark tooling. Experimental pre-1.0.

## 5) Suggested short GitHub README tagline

Deterministic, source-cited repository context packs for coding agents (local-first, experimental pre-1.0).

## 6) Suggested LinkedIn post

I’m sharing `repo-semantic-memory` (`rsm`), an experimental pre-1.0 tool for deterministic repository context compilation.

It indexes Python repositories, extracts structural signals (symbols, docs sections, exports, and test relationships), and builds source-cited repo maps and task-specific context packs. It also exports `.ai/` artifacts and includes an evaluation path for context quality and approximate token savings.

Design constraints are explicit: local-first operation, deterministic outputs, and evidence-linked claims. It includes MCP-style local handlers/contracts, but there is no MCP runtime server in the current scope.

Repository: https://github.com/apajon/repo-semantic-memory

## 7) Suggested short Discord/ROS-adjacent message

Sharing `repo-semantic-memory` (`rsm`): a deterministic, local-first context compiler for coding-agent workflows on Python repos. It generates source-cited repo maps/context packs and `.ai/` artifacts, with internal benchmark tooling for directional context-quality and token-savings checks. It includes MCP-style handlers/contracts, but no MCP runtime server yet.

## 8) Suggested caveats block

> **Caveats (please keep with any announcement):**
> - Benchmark results are internal and directional.
> - There is no broad superiority claim versus other approaches.
> - Token-savings numbers are approximate (`chars / 4`) and directional.
> - `confirmed PublicAPI` means a symbol is explicitly exported, not that it is a stable API promise.
> - `lifecore_ros2` validation is dogfooding evidence, not general proof.
> - MCP handlers/contracts exist, but no runtime MCP server is shipped yet.
