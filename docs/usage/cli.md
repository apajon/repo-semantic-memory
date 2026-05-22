# CLI usage

This page is the human command reference. `AGENTS.md` keeps contributor/agent operational guardrails, and `.ai/AGENT_COMMANDS.md` keeps the short agent-facing workflow guide.

## Core commands

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000 --profile agent_standard
```

## Export/import

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite
```

## Evaluation

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

## Development validation

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
```

## Profiles

`repo-map` and `pack` accept deterministic compression profiles:

- `agent_brief`
- `agent_standard` (default)
- `agent_debug`
- `human_review`
- `ci_summary`
- `full`

See [compression profiles](../concepts/compression_profiles.md) for details.
