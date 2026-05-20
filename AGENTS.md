# AGENTS.md

## Purpose

This repository hosts `rsm`, a deterministic repository context compiler for coding agents.

Use RSM to index repository structure, generate source-cited context packs, export `.ai/` agent artifacts, and evaluate retrieval/context quality under a fixed budget.

## Canonical commands

```bash
# Index the repository
uv run rsm index . --db .rsm/index.sqlite

# Generate a compact repository map
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard

# Generate a task-specific context pack
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000 --profile agent_standard

# Export .ai artifacts
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force

# Evaluate retrieval
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json

# Compare repo-map baseline vs context-pack baseline
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

## Generated artifacts and source of truth

- Source of truth remains code, docs, tests, and git history.
- `.rsm/` stores local SQLite working state and is local-only.
- `.ai/` stores compiled semantic artifacts for agents and may be stale.
- Regenerate `.ai/` after re-indexing when structural changes occur.

## `.rsm/` vs `.ai/`

- `.rsm/index.sqlite`: local index database, gitignored.
- Volatile `.ai` snapshots are gitignored in this repo (`INDEX.yaml`, `symbols.yaml`, `relations.yaml`, `components.yaml`, `repo_map.md`, `invariants.yaml`).
- Static `.ai` templates are intentionally tracked (`AGENT_COMMANDS.md`, `README.md`, `context_policy.md`).

## Profiles

`rsm repo-map` and `rsm pack` support deterministic profiles:

- `agent_brief`
- `agent_standard`
- `agent_debug`
- `human_review`
- `ci_summary`
- `full`

Use tighter profiles for small budgets and `agent_debug` for ranking diagnostics.

## Evidence and interpretation rules

- Do not treat inferred relations/components as confirmed facts.
- Verify important claims against cited source ranges.
- `confirmed PublicAPI` means explicitly exported in source, not an API stability promise.
- Token-savings values are approximate (`chars / 4`) and directional.
- Benchmark claims must be scoped to the current internal benchmark.

## Versioning policy (pre-1.0)

- Stay in `0.x` until public API/schema/context-pack format are explicitly stable.
- `fix:` patch, `feat:` minor, `feat!` or `BREAKING CHANGE` affects major semantics.
- Keep schema/context-pack version contracts explicit and intentional.

## Guardrails

- Keep outputs deterministic and scriptable.
- Keep semantic claims tied to evidence or clearly marked uncertain.
- Avoid overclaiming benchmark scope or quality.
