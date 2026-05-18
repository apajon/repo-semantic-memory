# repo-semantic-memory

`repo-semantic-memory` (`rsm`) is a semantic compiler foundation for software repositories.

It is designed to produce deterministic, evidence-backed semantic artifacts over time, including symbol indexes, structural relationships, semantic components, claims, and context packs for coding agents.

This initial scaffold provides a typed Python CLI, explicit artifact versioning, CI checks, and development tooling with `uv`.

## Extraction MVP behavior

- `rsm scan <path>` performs deterministic filesystem discovery.
- Python files are emitted as `module` entities.
- Stable IDs are based on repository-relative POSIX file paths (for example `file:src/pkg/app.py`).
- This MVP intentionally models files as modules; a future schema can split physical files from logical modules.
- `rsm index-python <path> --json` extracts Python AST entities (`module`, `class`, `function`, `method`) and structural relations (`contains`, `imports`, `inherits`).
- Python `qualified_name` values are logical symbol names (for example `python_symbols.DerivedThing`), while stable IDs keep repository-relative paths.

### Python AST MVP limitations

- Import resolution across files is not implemented.
- Inheritance resolution across files is not implemented. Unresolved bases use IDs like `unresolved:python:<BaseName>`.
- Nested functions are currently ignored.
- Decorators and signatures are static best-effort metadata.

## Repo map

- `rsm repo-map --db .rsm/index.sqlite --budget 4000` renders from an existing SQLite index.
- `rsm repo-map --path . --budget 4000` renders directly from a repository path without creating persistent artifacts in the target repository.
- `--budget` is currently an approximate **character** budget (not tokenizer-based token counting yet).
- Import lines are static extracted names and are labeled unresolved; cross-file import resolution is not implemented in this phase.

## Retrieval benchmark MVP

- `rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml` runs deterministic lexical retrieval evaluation.
- `--json` emits full machine-readable benchmark output.
- `--markdown-report out.md` writes a markdown report with aggregate and per-task details.
- Dataset files are YAML with top-level `tasks`, each containing `id`, `category`, `prompt`, and `gold` lists for `files`, `symbols`, and `invariants`.
- Gold `files` must be repository-relative POSIX paths and are matched against indexed `Entity.source_range.path`.
- Gold `symbols` are matched against indexed `Entity.qualified_name` in this MVP (matching against `name` or `id` is not implemented yet).
- Lexical ranking is deterministic and tie-breaks by entity stable ID.
- MRR is reciprocal rank of the first ranked item that matches any gold target.
- `context_character_estimate` is an approximate character-based estimate and is not tokenizer-based.
- Gold `invariants` can be present in datasets for forward compatibility, but invariant evaluation/coverage is not implemented in this MVP.

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
