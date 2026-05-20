# AGENT_COMMANDS — RSM command guide for coding agents

> **WARNING**: Generated artifact. Source of truth is always code, docs, tests, and git history.
> Regenerate with: `rsm export-ai --db .rsm/index.sqlite --out .ai --force`

## Overview

These are the canonical RSM commands for coding agents. Load this file early in any
RSM-assisted task to avoid redundant full-file reads and context waste.

---

## When to run each command

### `rsm index`

Run after cloning or after significant structural changes (new modules, renamed files,
moved packages). This rebuilds the SQLite index from source.

```bash
uv run rsm index . --db .rsm/index.sqlite
```

Run with `--with-git` to attach last-commit dates to entities:

```bash
uv run rsm index . --db .rsm/index.sqlite --with-git
```

### `rsm repo-map`

Run to get a compact structural overview of the repository. Use as orientation before
editing unfamiliar code.

```bash
uv run rsm repo-map --db .rsm/index.sqlite
```

### `rsm pack`

Run to build a token-budgeted context pack for a specific task. Pass a task prompt to
focus the pack on relevant symbols and files.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "describe the task here" --budget 8000
```

Use `--explain-ranking` to see why entities were selected:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 8000 --explain-ranking
```

### `--profile agent_brief`

Use when token budget is very tight or the task is narrow. Suppresses unresolved
imports, low-confidence components, and ranking detail. Smallest output.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 4000 --profile agent_brief
```

### `--profile agent_debug`

Use when diagnosing unexpected pack output or ranking anomalies. Includes ranking
breakdown and compact score reasons. Larger output — use with a generous budget.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 12000 --profile agent_debug
```

---

## When to use each `.ai/` file

### `symbols.yaml`

Use to resolve entity IDs, source file paths, and line numbers before editing.
Prefer this over grepping for class/function names directly.

### `relations.yaml`

Use to understand structural dependencies: which modules import which, which classes
inherit from which, which functions are tested by which test files. Use before
refactoring to understand downstream impact.

### `components.yaml`

Use to identify semantic roles: PublicAPI, EntryPoint, TestTarget, TestFile, etc.
All components are `inferred` unless explicitly marked `confirmed`. Do not treat
inferred components as confirmed claims.

---

## When to regenerate `.ai/`

Regenerate after:
- indexing adds new symbols (new modules, classes, functions)
- files are renamed, moved, or deleted
- significant refactors that change structural relations
- public API changes (exports, `__init__.py` edits)

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

Check `INDEX.yaml` → `generated_at` against recent git commits to assess staleness.

---

## What NOT to do

- **Do not treat `.ai/` files as source truth.** They are derived snapshots.
  Always verify against the actual source files cited in symbols.yaml.

- **Do not read full source files before checking the context pack.**
  Run `rsm pack` first; it cites the relevant sections. Read only what is cited.

- **Do not trust inferred components as confirmed claims.**
  `components.yaml` entries with `status: inferred` are heuristic guesses.
  Confirm by reading the cited source.

- **Do not use stale `.ai/` without checking the timestamp.**
  Check `INDEX.yaml` → `generated_at`. If the repo has changed significantly
  since that timestamp, regenerate before relying on any `.ai/` file.

- **Do not ignore citations when editing code.**
  Every symbol in `symbols.yaml` has a `source:` citation. Use it.
  Do not guess file locations.

- **Do not claim token savings are quality unless coverage is preserved.**
  A smaller context pack is only better if it still covers the gold files and
  symbols for the task. Use `rsm eval compare` to measure coverage, not just size.

---

## Canonical workflows

### 1. New task

```
1. uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000
2. Inspect cited files and symbols in the pack output.
3. Edit only the cited source files.
```

Do not load full source files before running `rsm pack`.

### 2. Large repo orientation

```
1. Load .ai/INDEX.yaml — confirm generation timestamp and version.
2. Load .ai/repo_map.md — structural overview at low token cost.
3. Load .ai/symbols.yaml — only if resolving a specific entity.
4. Load .ai/relations.yaml — only if tracing dependencies.
```

Do not load all `.ai/` files at once.

### 3. Public API task

```
1. uv run rsm pack --db .rsm/index.sqlite --task "public API for <module>" --budget 8000
2. Inspect __init__.py exports cited in pack output.
3. Inspect public import tests if listed in relations.yaml.
```

### 4. Debug regression

```
1. uv run rsm pack --db .rsm/index.sqlite --task "<failing test or symptom>" --budget 8000
2. Inspect tests and related source cited in pack output.
3. Use --profile agent_debug if ranking seems off.
```

### 5. Documentation task

```
1. uv run rsm pack --db .rsm/index.sqlite --task "<doc topic>" --budget 8000
2. Inspect doc sections cited in pack output.
3. Do not read full doc files before checking cited sections.
```

### 6. After code structure change

```
1. uv run rsm index . --db .rsm/index.sqlite
2. uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
   (only if this project commits .ai/ snapshots)
3. Verify INDEX.yaml → generated_at is current.
```

---

## License

Apache-2.0 — generated by `repo-semantic-memory`
