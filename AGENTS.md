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
