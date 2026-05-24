# CLI usage

This page is the human command reference. `AGENTS.md` keeps contributor/agent operational guardrails, and `.ai/AGENT_COMMANDS.md` keeps the short agent-facing workflow guide.

## Core commands

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000 --profile agent_standard
```

- `rsm index` builds the SQLite-backed semantic index for later commands.
- `rsm repo-map` renders broad budgeted Markdown orientation from a DB or in-memory path scan.
- `rsm pack` renders a task-specific context pack; add `--explain-ranking` when diagnosing
  selection.

## RSM Index Store

The RSM Index Store is a central local directory that maps repository roots to their index files,
so `rsm mcp serve` can omit `--db` once a repo is registered.

### Store home resolution

The store home is resolved in this order:

1. `RSM_HOME` environment variable, if set and non-empty.
2. OS-specific default:
   - **Linux / Ubuntu**: `$XDG_DATA_HOME/repo-semantic-memory` or `~/.local/share/repo-semantic-memory`
   - **macOS**: `~/Library/Application Support/repo-semantic-memory`
   - **Windows**: `%LOCALAPPDATA%\repo-semantic-memory`

### Store commands

```bash
# Print the active store home directory.
uv run rsm store path

# List all registered repositories.
uv run rsm store list
uv run rsm store list --json

# Register a repository (without indexing yet).
uv run rsm store register /path/to/repo

# Register and immediately build the index.
uv run rsm store register /path/to/repo --index

# Print the registered DB path for a repository.
uv run rsm store db /path/to/repo

# Remove a repository from the registry (does not delete the index file).
uv run rsm store unregister /path/to/repo
```

### Register during indexing

Pass `--register` to `rsm index` to record the repo → DB mapping in the store immediately after
indexing:

```bash
# Index to the default local path and register.
uv run rsm index . --db .rsm/index.sqlite --register

# Index to an explicit path and register.
uv run rsm index /path/to/repo --db /custom/path/index.sqlite --register
```

Once registered, `rsm mcp serve` can omit `--db`:

```bash
uv run rsm mcp serve --repo /path/to/repo
```

The existing explicit `--db` workflow is unchanged; the store is purely additive.

## Export/import

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite
```

- `rsm export-ai` writes generated `.ai/` artifacts for agent consumption.
- `rsm export-jsonl` and `rsm import-jsonl` provide machine-facing interchange for entities,
  relations, and metadata.

See [`.ai/` directory](ai_directory.md) and [JSONL interchange](jsonl_interchange.md).

## Derived semantic helpers

```bash
uv run rsm components infer --db .rsm/index.sqlite
uv run rsm components list --db .rsm/index.sqlite
uv run rsm git summary .
uv run rsm invariants export --db .rsm/index.sqlite --out .rsm/invariants.yaml
uv run rsm invariants import --db .rsm/index.sqlite .rsm/invariants.yaml
```

- `rsm components infer` recomputes ECS-style semantic components from indexed entities and
  relations.
- `rsm components list` lists the current derived components.
- `rsm git summary` shows minimal local Git metadata; `rsm index --with-git` attaches similar
  metadata during indexing when available.
- `rsm invariants export/import` handles standalone claim/invariant YAML documents. The DB is
  checked for index availability and schema compatibility, but invariant data is not stored in
  SQLite yet.

## Evaluation

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

- `rsm eval retrieval` scores retrieval against internal gold files/symbols.
- `rsm eval compare` compares repo-map and context-pack style baselines under a shared budget.

See [benchmarks](../eval/benchmarks.md) and [token savings](../eval/token_savings.md).

## Development validation

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
```

## Profiles

`repo-map` and `pack` accept deterministic compression profiles:

- `agent_brief`
- `agent_standard` (default)
- `agent_debug`
- `human_review`
- `ci_summary`
- `full`

See [compression profiles](../concepts/compression_profiles.md) for details.


## Export/import

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite
```

- `rsm export-ai` writes generated `.ai/` artifacts for agent consumption.
- `rsm export-jsonl` and `rsm import-jsonl` provide machine-facing interchange for entities,
  relations, and metadata.

See [`.ai/` directory](ai_directory.md) and [JSONL interchange](jsonl_interchange.md).

## Derived semantic helpers

```bash
uv run rsm components infer --db .rsm/index.sqlite
uv run rsm components list --db .rsm/index.sqlite
uv run rsm git summary .
uv run rsm invariants export --db .rsm/index.sqlite --out .rsm/invariants.yaml
uv run rsm invariants import --db .rsm/index.sqlite .rsm/invariants.yaml
```

- `rsm components infer` recomputes ECS-style semantic components from indexed entities and
  relations.
- `rsm components list` lists the current derived components.
- `rsm git summary` shows minimal local Git metadata; `rsm index --with-git` attaches similar
  metadata during indexing when available.
- `rsm invariants export/import` handles standalone claim/invariant YAML documents. The DB is
  checked for index availability and schema compatibility, but invariant data is not stored in
  SQLite yet.

## Evaluation

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

- `rsm eval retrieval` scores retrieval against internal gold files/symbols.
- `rsm eval compare` compares repo-map and context-pack style baselines under a shared budget.

See [benchmarks](../eval/benchmarks.md) and [token savings](../eval/token_savings.md).

## Development validation

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
```

## Profiles

`repo-map` and `pack` accept deterministic compression profiles:

- `agent_brief`
- `agent_standard` (default)
- `agent_debug`
- `human_review`
- `ci_summary`
- `full`

See [compression profiles](../concepts/compression_profiles.md) for details.
