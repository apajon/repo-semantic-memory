# AGENTS

## Purpose

This repository hosts the `rsm` semantic compiler foundation.

## Agent workflow

1. Read source files, docs, and tests before changing behavior.
2. Keep modules focused and deterministic.
3. Add or update tests for any behavior change.
4. Run formatting, linting, type-checking, and tests before finalizing.
5. Keep semantic claims tied to explicit evidence or mark uncertainty.

## Guardrails

- Do not add repository scanning, AST extraction, SQLite, vector DB, Neo4j, MCP server, or web UI in this phase.
- Keep APIs explicit and scriptable.
- Keep CLI output stable for automation.

## Commit conventions for releases

- `fix:` triggers a patch release.
- `feat:` triggers a minor release.
- `feat!:` or a `BREAKING CHANGE:` footer triggers a major release.
- `docs:`, `test:`, `chore:`, and `ci:` should not normally trigger a release.

## Pre-1.0 versioning policy

- The project is in initial development and must remain in the `0.x` range.
- Do not release `1.0.0` until the public API, schema versioning contract, and context-pack format are explicitly declared stable.
- Keep `SCHEMA_VERSION` and `CONTEXT_PACK_VERSION` manually managed; release automation must not bump them automatically.

## Using RSM to develop RSM

When working on this repository, use RSM itself to navigate and understand the codebase:

```bash
# Re-index after structural changes
uv run rsm index . --db .rsm/index.sqlite

# Regenerate .ai/ if this project commits snapshots
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force

# Pack context for a specific development task
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000
```

See `.ai/AGENT_COMMANDS.md` for the full command guide and canonical workflows.

Before editing source, run `rsm pack` to identify the relevant symbols and cited files.
Do not read full source modules before checking the context pack output.



```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm export-ai --db .rsm/index.sqlite --out .ai
```

Use `--force` to regenerate after re-indexing:

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

Generated files under `.ai/` are compiled semantic artifacts. Projects may choose
to commit them as a shared snapshot (similar to generated protobufs) or keep them
local-only. The `.rsm/` index (SQLite) must never be committed — it is git-ignored.

Source of truth always remains code, docs, tests, and git history. Generated `.ai/`
files may be stale; regenerate after significant structural changes.
