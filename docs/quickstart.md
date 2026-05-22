# Quickstart

RSM is local-first. It reads the current repository and writes local artifacts; source code, docs, tests, and Git history remain authoritative.

## Install dependencies

```bash
uv sync --all-groups
```

## Build an index

```bash
uv run rsm index . --db .rsm/index.sqlite
```

`.rsm/index.sqlite` is local working state and should not be committed.

## Generate a repo map

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
```

Use this for broad orientation before deeper inspection.

## Generate a task context pack

```bash
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 8000 \
  --profile agent_standard
```

Use context packs to identify cited files and symbols for a specific task. Verify important claims against the cited source.

## Optional exports

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite
```

## Optional evaluation

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

Interpret benchmark results as internal and directional, not broad superiority claims.
