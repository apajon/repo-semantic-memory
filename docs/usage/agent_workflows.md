# Agent Workflows

This document describes how coding agents should use `repo-semantic-memory` (RSM)
to navigate repositories efficiently.

> **Note**: The canonical quick-reference guide is `.ai/AGENT_COMMANDS.md`.
> This document provides additional rationale and context.

---

## Source of truth

Code, docs, tests, and git history are always authoritative.
`.ai/` files are derived snapshots. They may be stale after structural changes.
Always verify claims against the cited source locations before editing.

---

## Setup

Index the repository once after cloning, and again after significant structural changes:

```bash
uv run rsm index . --db .rsm/index.sqlite
```

Generate the `.ai/` snapshot (if the project commits it):

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

---

## Canonical workflows

### 1. New task

Before reading any source files, run a context pack to identify what is relevant:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "<describe the task>" --budget 8000
```

The pack output cites source files and symbols. Read only those. Do not open
full modules speculatively.

### 2. Large repo orientation

When first encountering an unfamiliar repository:

1. Load `.ai/INDEX.yaml` — confirm generation timestamp and version.
2. Load `.ai/repo_map.md` — structural overview at low token cost.
3. Load `.ai/symbols.yaml` — only when resolving a specific entity by name or ID.
4. Load `.ai/relations.yaml` — only when tracing import/inheritance/test dependencies.

Do not load all `.ai/` files at once. Load only what the task needs.

### 3. Public API task

When working on exported symbols or public interfaces:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "public API for <module>" --budget 8000
```

Then inspect:
- `__init__.py` exports cited in the pack output.
- Public import tests listed in `relations.yaml` (kind: `tests`, `exports`).

### 4. Debug regression

When investigating a failing test or unexpected behaviour:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "<failing test or symptom>" --budget 8000
```

If the ranking seems wrong, add `--profile agent_debug` and `--explain-ranking`
to see the scoring breakdown.

### 5. Documentation task

When updating or writing documentation:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "<doc section topic>" --budget 8000
```

Inspect only the doc sections cited in the pack output. Do not read full
documentation files before checking cited sections.

### 6. After code structure change

After renaming files, adding modules, or changing exports:

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

Verify `INDEX.yaml` → `generated_at` is current before relying on any `.ai/` file.

---

## Compression profiles

`rsm repo-map` and `rsm pack` accept a `--profile` flag:

| Profile | Use when |
|---|---|
| `agent_brief` | Token budget is tight; narrow, well-defined tasks |
| `agent_standard` | Default; balanced for most coding tasks |
| `agent_debug` | Diagnosing pack ranking or unexpected output |
| `human_review` | PR review or design review workflows |
| `ci_summary` | CI pipeline; strict noise suppression |
| `full` | Maximum verbosity for deep analysis |

Example:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 4000 --profile agent_brief
```

---

## Token-savings caveat

A smaller context pack is only better if it preserves coverage of the relevant
files and symbols for the task. Use `rsm eval compare` to measure:

```bash
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000
```

Do not claim token savings are quality improvements unless coverage is preserved.

---

## What NOT to do

- Do not treat `.ai/` files as source truth.
- Do not read full source files before checking the context pack.
- Do not trust `inferred` components as confirmed claims.
- Do not use stale `.ai/` without checking the timestamp.
- Do not ignore citations when editing code.
- Do not claim token savings are quality unless coverage is preserved.

---

## See also

- `.ai/AGENT_COMMANDS.md` — quick-reference command guide (generated)
- `.ai/context_policy.md` — loading policy and profile details (generated)
- `AGENTS.md` — agent guardrails and commit conventions
- `docs/design/architecture.md` — system architecture
