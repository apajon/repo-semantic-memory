# Versioning and release policy

RSM is experimental and pre-1.0. Public API, persisted schema, and serialized context-pack formats should be treated as evolving unless explicitly declared stable.

## Package version

The package version is tag-driven through hatch-vcs. Git tags and GitHub releases are the source of truth for package versioning.

## Compatibility contracts

`SCHEMA_VERSION` and `CONTEXT_PACK_VERSION` are explicit compatibility constants. They are not inferred from the package version and should change only when the persisted schema or context-pack contract changes.

## Release workflow

The protected-main release workflow is tag-only: release automation creates tags/releases without pushing version-bump commits or changelog commits to `main`.

## Pre-1.0 guardrails

- Stay in `0.x` until public API, schema, and context-pack formats are intentionally stable.
- `fix:` maps to patch semantics.
- `feat:` maps to minor semantics.
- `feat!` or `BREAKING CHANGE` marks major semantic impact, even while `0.x` policy may constrain release behavior.
