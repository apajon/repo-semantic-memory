# Task context packs

A context pack is a task-specific, source-cited selection of repository context under an explicit budget.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "<task>" --budget 8000 --profile agent_standard
```

Context packs combine lexical scoring, path-role signals, semantic component hints, BM25-style ranking, and graph relation selection. They are deterministic for the same inputs.

Use `--explain-ranking` or `--profile agent_debug` when diagnosing why specific entities were selected.

## Caveats

- Budgets are character-based; token estimates are approximate.
- Selected context is intentionally compact and not exhaustive.
- Inferred relations and components require source verification.
- Smaller context is only better when relevant files/symbols remain covered.
