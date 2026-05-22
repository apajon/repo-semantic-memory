# AGENT_COMMANDS — RSM command guide for coding agents

> Derived/static agent-facing guide. Source of truth is always code, docs, tests, and git history.
> Regenerate snapshots with: `uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force`.

## Core workflow

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000 --profile agent_standard
```

Read the pack output first, then inspect cited files and symbols. Do not load full source files or every `.ai/` artifact speculatively.

## Orientation workflow

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
```

For committed/generated `.ai/` snapshots, load only what the task needs:

1. `INDEX.yaml` for generation time and versions.
2. `repo_map.md` for broad structure.
3. `symbols.yaml` for entity IDs and source ranges.
4. `relations.yaml` for dependencies, exports, and test links.
5. `components.yaml` or `invariants.yaml` only when relevant.

## Debug ranking

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 12000 --profile agent_debug --explain-ranking
```

Use this when selected context looks surprising.

## Evaluation

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

Treat benchmark results as internal and directional. Token savings matter only when gold coverage is preserved.

## Do not

- Do not treat `.ai/` files as source truth.
- Do not trust inferred components as confirmed claims.
- Do not use stale snapshots without checking `INDEX.yaml`.
- Do not ignore citations when editing code.
- Do not claim `confirmed PublicAPI` means API stability.
- Do not claim broad superiority from internal benchmark results.

Human documentation index: `docs/README.md`.
