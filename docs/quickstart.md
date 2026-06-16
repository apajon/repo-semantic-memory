# Quickstart

RSM is local-first. It reads the current repository and writes local artifacts; source code, docs, tests, and Git history remain authoritative.

This quickstart walks through the normal local workflow: install dependencies, build an index, inspect the repository, ask for task-specific context, optionally export `.ai/` artifacts, and run evaluation commands.

## Install dependencies

```bash
uv sync --all-groups
```

This creates the local environment used by the CLI and development checks. For a shorter
overview, see the root [README](../README.md); this page keeps the first-run command flow.

## Build an index

Indexing builds the local SQLite database that the other commands read.

```bash
uv run rsm index . --db .rsm/index.sqlite
```

`.rsm/index.sqlite` is local working state and should not be committed.

## Generate a repo map

A repo map gives broad orientation when you do not yet know where to look.

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
```

Use this for broad orientation before deeper inspection.

## Generate a task context pack

A context pack is task-specific: it selects files, symbols, relations, citations, and uncertainty for one prompt.

```bash
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 8000 \
  --profile agent_standard
```

Use context packs to identify cited files and symbols for a specific task. Verify important claims against the cited source.

## Optional exports

The `.ai/` export writes agent-facing snapshots derived from the local index.

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite
```

`.ai/` output is generated agent-facing material. Static `.ai` templates may be tracked, but
volatile generated snapshots should stay uncommitted in this repository. See
[`.ai/` directory](usage/ai_directory.md).

## Optional evaluation

Evaluation commands help compare retrieval/context behavior under fixed budgets.

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

Interpret benchmark results as internal and directional, not broad superiority claims.

## End-to-end example

Here is a complete first-use flow with expected output:

### 1. Install

```bash
uv sync --all-groups
```

### 2. Index

```bash
uv run rsm index . --db .rsm/index.sqlite
```

You should see progress lines and a final summary:

```text
indexing: complete: entities=3738 relations=6736, elapsed=7.5s
entities=3738 relations=6736
```

### 3. Explore (optional)

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
```

This prints a Markdown overview of modules and symbols.

### 4. Prepare context for a task

```bash
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 8000 \
  --profile agent_standard
```

The output includes selected symbols, suggested files, and source citations
for your task. Give this output to your coding agent before asking it to edit
code.

### 5. Generate a project brief

```bash
uv run rsm project-brief --db .rsm/index.sqlite --force
```

Writes `.rsm/PROJECT_CONTEXT.md`. Your agent can read this file to understand
the repository before calling any RSM tools.

For more examples with representative output, see [CLI Examples](usage/examples.md).

## Clean up local artifacts

`.rsm/` is local working state. Remove it when you want to rebuild from scratch:

```bash
rm -rf .rsm/
```

## Next reading

- [CLI examples](usage/examples.md) — concrete command examples with representative output
- [CLI usage](usage/cli.md) — full command reference
- [Repo maps](concepts/repo_maps.md) — broad orientation output
- [Context packs](concepts/context_packs.md) — task-specific output
- [Benchmarks](eval/benchmarks.md) — eval dataset scope and limitations
