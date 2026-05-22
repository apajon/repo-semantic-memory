# .ai/ - Agent Semantic Memory

## Purpose

This directory contains agent-facing semantic memory artifacts for RSM. These files are
derived from the repository index and may be stale. They are not the primary human
documentation source; code, docs, tests, and Git history remain authoritative.

## Files

| File | Description |
|---|---|
| `INDEX.yaml` | Versions, source DB path, generation timestamp, entity/relation counts |
| `AGENT_COMMANDS.md` | Compact command and workflow guide for coding agents |
| `repo_map.md` | Compact structural map of the repository |
| `symbols.yaml` | Stable entity IDs, kinds, names, and source locations |
| `relations.yaml` | Directed structural relations between entities |
| `components.yaml` | ECS-style semantic component labels, if present |
| `invariants.yaml` | Invariant records, if present |
| `context_policy.md` | Loading order, budget guidance, and interpretation rules |

## Git behavior

In this repository, volatile generated snapshots are gitignored. Static templates may be committed:

- `.ai/AGENT_COMMANDS.md`
- `.ai/README.md`
- `.ai/context_policy.md`

The local `.rsm/` index must not be committed.

## Human docs

Use `docs/README.md` for the human documentation index.
