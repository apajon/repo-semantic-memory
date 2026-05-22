# `.ai/` directory

The `.ai/` directory is for agent-facing semantic memory artifacts. It is not the primary human documentation tree.

## File roles

- `.ai/README.md` — explains the directory and file roles to agents.
- `.ai/AGENT_COMMANDS.md` — short command/workflow guide for coding agents.
- `.ai/context_policy.md` — loading policy, staleness checks, and budget guidance.
- `.ai/INDEX.yaml`, `symbols.yaml`, `relations.yaml`, `components.yaml`, `invariants.yaml`, `repo_map.md` — volatile generated snapshots when exported.

## Tracking policy in this repository

`.rsm/` is always local-only. Volatile `.ai/` snapshots are gitignored in this repo. Static `.ai` templates may be committed:

- `.ai/AGENT_COMMANDS.md`
- `.ai/README.md`
- `.ai/context_policy.md`

Do not commit generated volatile `.ai` snapshots unless a PR explicitly decides to version a snapshot.

## Staleness policy

Treat `.ai/` artifacts as derived and possibly stale. Regenerate after structural changes:

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

Always verify important claims against cited source files.
