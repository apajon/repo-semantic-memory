# Repo maps

A repo map is a compact, deterministic overview of repository structure.

Use `repo-map` for orientation:

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
```

Repo maps prioritize source-oriented structure, stable entity names, and citations under a character budget. They are useful before exploring an unfamiliar repository, but they are not task-specific and may omit details needed for a particular edit.

For task work, generate a context pack after the repo map.
