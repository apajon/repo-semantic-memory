# GitHub Copilot Instructions — repo-semantic-memory

You are working on `repo-semantic-memory`, a tool that builds a compact semantic memory layer for software repositories.

The project goal is not to create another documentation generator, Obsidian vault, or generic vector database.

The project is a semantic compiler for repositories.

It extracts structured knowledge from:
- source code
- docs
- tests
- git history
- project conventions

It produces:
- symbol indexes
- structural graphs
- ECS-style semantic components
- claims and invariants with evidence
- token-budgeted context packs for coding agents
- benchmark reports comparing context quality and agent usefulness

Core design rules:
- Source code, docs, tests, and git history remain the source of truth.
- Every semantic claim must have evidence, or be marked as uncertain.
- Prefer deterministic extraction before LLM-generated summaries.
- Prefer small focused modules over monolithic files.
- Target 150-300 LOC per module.
- Hard limit: avoid files above 400 LOC unless explicitly justified.
- One module should have one clear responsibility.
- No large utility dumping-ground modules.
- No hidden global state.
- No agent-facing claim without provenance.
- No premature Neo4j, vector DB, web UI, or LLM dependency in the MVP.

Preferred stack:
- Python 3.12+
- uv
- pytest
- ruff
- mypy-ready typing where practical
- stdlib `ast` for Python extraction in early phases
- SQLite for local storage in early phases
- YAML/JSONL export for interoperability

Architecture layers:
1. Raw repository inputs
2. Symbol index
3. Structural graph
4. ECS-style semantic components
5. Claims, contracts, invariants
6. Evidence and temporal validity
7. Context pack builder
8. Benchmark harness
9. MCP server later

Do not implement future phases unless requested.

When modifying code:
- keep APIs explicit
- write tests for each new extractor/model component
- preserve deterministic output ordering
- use stable IDs
- keep CLI behavior boring and scriptable
- document uncertainty rather than guessing

At the end of each task, report:
- files changed
- commands run
- remaining uncertainty
- suggested next task

ChatGPT or Codex will review the deliverables.
