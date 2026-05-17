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
