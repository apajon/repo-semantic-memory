# repo-semantic-memory

`repo-semantic-memory` (`rsm`) is a semantic compiler foundation for software repositories.

It is designed to produce deterministic, evidence-backed semantic artifacts over time, including symbol indexes, structural relationships, semantic components, claims, and context packs for coding agents.

This initial scaffold provides a typed Python CLI, explicit artifact versioning, CI checks, and development tooling with `uv`.

## Quick start

```bash
uv sync --all-groups
uv run rsm --help
uv run rsm version
```

## Development checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```

## Release automation

Releases are automated with `python-semantic-release` on pushes to `main`. The release job runs the same quality checks as CI and then executes `uv run semantic-release version` with tag format `v{version}`.

The project is currently pre-1.0 and must remain in the `0.x` range. Do not release `1.0.0` until the public API, schema contract, and context-pack format are declared stable.

Only `project.version` and `PACKAGE_VERSION` are updated automatically; schema and context-pack versions are managed independently and must remain manually controlled.
