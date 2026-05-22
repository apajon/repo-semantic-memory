# AGENTS.md

## Purpose

This repository hosts `rsm`, a deterministic repository context compiler for coding agents.

Use RSM to index repository structure, generate source-cited repo maps and context packs, export `.ai/` agent artifacts, and evaluate retrieval/context quality under a fixed budget.

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

## Versioning policy (pre-1.0)

- Stay in `0.x` until public API/schema/context-pack format are explicitly stable.
- `fix:` patch, `feat:` minor, `feat!` or `BREAKING CHANGE` affects major semantics.
- Keep schema/context-pack version contracts explicit and intentional.
- See [`docs/release/versioning.md`](docs/release/versioning.md).

## Guardrails

- Keep outputs deterministic and scriptable.
- Keep semantic claims tied to evidence or clearly marked uncertain.
- Avoid overclaiming benchmark scope or quality.
- Do not add runtime features when performing documentation-only changes.
