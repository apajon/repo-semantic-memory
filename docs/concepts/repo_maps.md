# Repo maps

A repo map is a compact, deterministic overview of repository structure.

Use `repo-map` for orientation:

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
```

Repo maps are for broad orientation: they help a reader quickly see major source paths, stable
entity names, and source-cited structure before diving into task work.

## Output shape

`repo-map` emits budgeted Markdown. The budget is approximate and character-based, so the map is
kept intentionally compact and may omit lower-priority detail when the repository is large.

Repo maps prioritize source-oriented structure and citations over prose. They are useful before
exploring an unfamiliar repository, but they are not tailored to a specific edit or question.

## Repo maps vs. context packs

A repo map answers "what is here?" across the repository. A
[context pack](context_packs.md) answers "what matters for this task?" for one prompt under a
similar budget.

Use a repo map first for orientation, then generate a context pack when you need task-specific
entities, relations, uncertainty notes, and ranking-driven selection.
