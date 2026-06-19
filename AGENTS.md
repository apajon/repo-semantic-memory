# AGENTS.md

## Purpose

This repository hosts `rsm`, a deterministic repository context compiler for coding agents.

Use RSM to index repository structure, generate source-cited repo maps and context packs, export `.ai/` agent artifacts, and evaluate retrieval/context quality under a fixed budget.

## Architecture overview

RSM builds a semantic index over source code, docs, tests, and project conventions. Agents query this index for context packs, repo maps, and exported `.ai/` artifacts.

Key RSM layers (see [`docs/design/`](docs/design/) for details):
1. Raw repository inputs (code, docs, tests, git history)
2. Symbol index
3. Structural graph
4. Semantic components (ECS-style)
5. Claims, contracts, invariants
6. Evidence and temporal validity
7. Context pack builder
8. Benchmark harness

- **Source of truth**: code, docs, tests, git history.
- **Derived data**: `.rsm/` (SQLite index, caches), `.ai/` (compiled artifacts). Rebuild locally; never commit.
- **Config (versioned)**: `.rsm.yaml`, `.rsmignore`, docs explaining RSM usage, helper scripts.

## Canonical local commands

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000 --profile agent_standard
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

Development validation:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
```

See [`docs/usage/cli.md`](docs/usage/cli.md) for command details.

## Documentation roles

- `README.md`: short public entrypoint, quick start, capabilities, limitations, and links.
- `docs/`: human-facing explanations, usage, evaluation, design, release, and case-study docs.
- `AGENTS.md`: contributor/agent operational guide and guardrails.
- `.ai/`: generated/static agent-facing artifacts; not the primary human documentation source.

## Generated artifacts and source of truth

- Source of truth remains code, docs, tests, and git history.
- `.rsm/` stores local SQLite working state and must stay local-only.
- `.ai/` stores compiled semantic artifacts for agents and may be stale.
- Regenerate `.ai/` after re-indexing when structural changes occur.
- Volatile `.ai` snapshots are gitignored in this repo (`INDEX.yaml`, `symbols.yaml`, `relations.yaml`, `components.yaml`, `repo_map.md`, `invariants.yaml`).
- Static `.ai` templates are intentionally tracked (`AGENT_COMMANDS.md`, `README.md`, `context_policy.md`).

## Evidence and interpretation rules

- Do not treat inferred relations/components as confirmed facts.
- Verify important claims against cited source ranges.
- `confirmed PublicAPI` means explicitly exported in source, not an API stability promise.
- Token-savings values are approximate (`chars / 4`) and directional.
- Benchmark claims must be scoped to the current internal benchmark.
- MCP handlers/contracts are local deterministic building blocks; no runtime MCP server is shipped yet.

## Coding conventions

- Prefer small, reversible changes. Keep source-of-truth files explicit.
- Do not mix runtime cache logic with durable config.
- Keep APIs explicit; write tests for each new extractor or model component.
- Preserve deterministic output ordering; use stable IDs.
- Keep CLI behavior boring and scriptable.
- Document uncertainty rather than guessing.
- One module, one clear responsibility. Target 150–300 LOC per module; avoid files above 400 LOC unless explicitly justified.
- No hidden global state. No large utility dumping-ground modules.
- No agent-facing claim without provenance.
- No premature Neo4j, vector DB, web UI, or LLM dependency in the MVP.

## Forbidden changes

Agents must not modify:

- Secrets, `.env`, or credentials
- `.rsm/` (local SQLite index, caches, embeddings)
- Generated `.ai/` artifacts (`INDEX.yaml`, `symbols.yaml`, `relations.yaml`, `components.yaml`, `repo_map.md`, `invariants.yaml`)
- Unrelated architecture files
- GitHub workflow files unless the issue explicitly requires it

## Versioning policy (pre-1.0)

- Stay in `0.x` until public API/schema/context-pack format are explicitly stable.
- `fix:` patch, `feat:` minor, `feat!` or `BREAKING CHANGE` affects major semantics.
- Keep schema/context-pack version contracts explicit and intentional.
- See [`docs/release/versioning.md`](docs/release/versioning.md).

## Memory policy

- **RSM indexes** are derived data, rebuilt locally with `uv run rsm index`.
  - **Version**: `.rsm.yaml`, `.rsmignore`, docs explaining RSM usage, helper scripts.
  - **Do not version**: `.rsm/` (SQLite, caches, embeddings).
- **Vault** (`vault/`) stores long-term decisions: ADRs, architecture decisions, postmortems, important agentic workflow decisions.
  - Do not use the Vault for raw chat logs or noisy runtime traces.
- **`.ai/`** stores compiled agent-facing artifacts. Regenerate after re-indexing when structural changes occur.
  - Volatile snapshots are gitignored; static templates (`AGENT_COMMANDS.md`, `README.md`, `context_policy.md`) are tracked.
- **Source of truth** remains code, docs, tests, and git history — not derived artifacts.
