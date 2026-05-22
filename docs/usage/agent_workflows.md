# Agent workflows

This page explains how coding agents should use RSM without turning generated artifacts into a second documentation set.

For exact commands, use [`docs/usage/cli.md`](cli.md). For the short agent-facing command card, use `.ai/AGENT_COMMANDS.md`.

## Source of truth

Code, docs, tests, and Git history are authoritative. RSM outputs are derived, compact, and sometimes stale. Verify important claims against cited source ranges before editing.

## Task workflow

1. Build or refresh the local index when needed.
2. Generate a task-specific context pack before opening broad source files.
3. Inspect the cited files, symbols, and relations.
4. Treat inferred relations/components as navigation hints, not facts.
5. Re-index after structural changes.

## Large-repository orientation

Use a repo map for broad structure and `.ai/` snapshots only when they are current. Load the smallest artifact that answers the task:

- `repo_map.md` for structure
- `symbols.yaml` for entity IDs and source ranges
- `relations.yaml` for dependency/export/test links
- `components.yaml` and `invariants.yaml` only when needed

Do not load every `.ai/` file by default.

## Public API tasks

Public API work should start from context packs and cited `__init__.py` exports. `confirmed PublicAPI` means exported in source; it does not mean long-term API stability.

## Debugging and ranking diagnostics

Use the debug profile and ranking explanations only when normal context selection looks surprising. Debug output is intentionally larger and should not be the default for routine edits.

## Documentation tasks

For documentation changes, use context packs to identify relevant doc sections, then verify against the linked source docs. Keep README, `docs/`, `AGENTS.md`, and `.ai/` roles distinct.

## Evaluation interpretation

Token savings are approximate and directional. Smaller context is valuable only when benchmark gold file/symbol coverage is preserved. Internal benchmark results should not be presented as broad superiority claims.

## See also

- [`docs/usage/cli.md`](cli.md) — human command reference
- [`docs/usage/ai_directory.md`](ai_directory.md) — `.ai/` artifact policy
- [`docs/concepts/compression_profiles.md`](../concepts/compression_profiles.md) — profile details
- [`AGENTS.md`](../../AGENTS.md) — contributor/agent guardrails
