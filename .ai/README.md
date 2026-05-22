# .ai/ — Agent Semantic Memory

> These files are derived agent-facing artifacts and may be stale.
> Source of truth is always code, docs, tests, and git history.
> Regenerate with: `rsm export-ai --db .rsm/index.sqlite --out .ai --force`.

## Purpose

This directory contains compact semantic memory files for coding agents. It is not a replacement for human documentation under `docs/`.

## Files

| File | Description |
|---|---|
| `INDEX.yaml` | Versions, source DB path, generation timestamp, entity/relation counts |
| `AGENT_COMMANDS.md` | Short command guide and workflows for coding agents |
| `repo_map.md` | Compact structural map of the repository |
| `symbols.yaml` | Stable entity IDs, kinds, names, and source locations |
| `relations.yaml` | Directed structural relations between entities |
| `components.yaml` | ECS-style semantic component labels, if present |
| `invariants.yaml` | Invariant entities, if present |
| `context_policy.md` | How agents should load these files within context budgets |

## Git behavior

In this repository, volatile generated snapshots are gitignored. Static templates (`AGENT_COMMANDS.md`, `README.md`, `context_policy.md`) may be committed. `.rsm/` must not be committed.

## Human docs

Use `docs/README.md` for the human documentation index.
