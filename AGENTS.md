# AGENTS

## Purpose

This repository hosts `rsm`, a deterministic repository context compiler for coding agents.

## Canonical commands

```bash
# index
uv run rsm index . --db .rsm/index.sqlite

# repo map
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard

# context pack
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000 --profile agent_standard

# .ai export
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force

# eval retrieval
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json

# eval compare
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

## Generated artifacts and source of truth

- Source of truth: code, docs, tests, and git history.
- `.rsm/` stores local SQLite working state and is always local-only.
- `.ai/` stores compiled semantic artifacts for agents and may be stale.
- Regenerate `.ai/` after indexing when structural changes occur.

## `.rsm/` vs `.ai/`

- `.rsm/index.sqlite`: local index database, gitignored.
- `.ai/INDEX.yaml`, `.ai/symbols.yaml`, `.ai/relations.yaml`, `.ai/components.yaml`, `.ai/repo_map.md`: volatile generated snapshots, gitignored in this repo.
- `.ai/AGENT_COMMANDS.md`, `.ai/README.md`, `.ai/context_policy.md`: static tracked templates.

## Profiles

`rsm repo-map` and `rsm pack` support deterministic profiles:

- `agent_brief`
- `agent_standard`
- `agent_debug`
- `human_review`
- `ci_summary`
- `full`

Use tighter profiles for smaller context budgets and debug profile for ranking diagnostics.

## Evidence and interpretation rules

- Do not treat inferred relations/components as confirmed facts.
- Always verify important claims against cited source ranges.
- `confirmed PublicAPI` means explicitly exported in source; it is not a stability promise.
- Token-savings values are approximate (`chars / 4`) and directional.
- Benchmark claims must be scoped to the current internal benchmark.

## Versioning policy (pre-1.0)

- Stay in `0.x` until public API/schema/context-pack format are explicitly stable.
- `fix:` patch, `feat:` minor, `feat!` or `BREAKING CHANGE` triggers major semantics.
- Keep schema/context-pack version contracts explicit and intentional.

## Guardrails

- Keep outputs deterministic and scriptable.
- Keep semantic claims tied to evidence or marked uncertain.
- Avoid overclaiming benchmark scope or quality.
