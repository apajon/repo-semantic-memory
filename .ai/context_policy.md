# Context Policy

This file describes how coding agents should use `.ai/` semantic memory files.

## Source of truth

Code, docs, tests, and git history are authoritative. `.ai/` files are derived snapshots and may be stale.

## Loading order

1. Load `INDEX.yaml` to confirm generation timestamp and versions.
2. Load `repo_map.md` for structural orientation.
3. Load `symbols.yaml` only to resolve entity IDs and source locations.
4. Load `relations.yaml` only when tracing structural dependencies.
5. Load `components.yaml` or `invariants.yaml` only when relevant.

Do not load all `.ai/` files at once unless the task explicitly requires it.

## Budget guidance

Prefer `rsm pack` for task-specific work:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "<task>" --budget 8000 --profile agent_standard
```

Use `agent_brief` for tight budgets and `agent_debug` with `--explain-ranking` for ranking diagnostics. See `docs/concepts/compression_profiles.md` for full profile details.

## Staleness

Check `INDEX.yaml` → `generated_at` against recent repository changes. Regenerate after structural changes:

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

## Interpretation rules

- Verify important claims against cited source.
- Treat inferred relations/components as heuristic.
- `confirmed PublicAPI` means exported in source, not stable API.
- Token estimates are approximate and directional.
