# Versioning and release policy

RSM is experimental and pre-1.0. Public API, persisted schema, and serialized context-pack formats should be treated as evolving unless explicitly declared stable.

## Package version

The package version is tag-driven through hatch-vcs. Git tags and GitHub releases are the source
of truth for package versioning; there is no checked-in version file updated by release commits.

At runtime, `repo_semantic_memory.version` resolves the installed package version through
`importlib.metadata`, so the reported package version matches the installed distribution metadata.

## Compatibility contracts

`SCHEMA_VERSION` and `CONTEXT_PACK_VERSION` are separate compatibility contracts. They are not
inferred from the package version and should change only when the persisted schema or serialized
context-pack contract changes.

## Release workflow

`main` is protected. Release automation runs in tag-only semantic-release mode on protected main:
it creates/pushes tags and GitHub releases without version-bump commits or changelog commits.

The release workflow uses semantic-release with `--skip-build --no-commit --no-changelog --push
--vcs-release`, which fits hatch-vcs tag-driven versioning and keeps `main` commit-free for
release bumps.

## Pre-1.0 guardrails

- Stay in `0.x` until public API, schema, and context-pack formats are intentionally stable.
- `fix:` maps to patch semantics.
- `feat:` maps to minor semantics.
- `feat!` or `BREAKING CHANGE` marks major semantic impact, even while `0.x` policy may constrain release behavior.

See also [data model](../design/data_model.md) for schema/context-pack contract framing and the
root [README](../../README.md) for current MVP caveats.
