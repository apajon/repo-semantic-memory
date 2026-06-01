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
indexing.

**Recommended: let the store manage the DB location.** When `--register` is set and `--db` is
omitted, the DB is written directly to the RSM Index Store canonical path
(`<store_home>/indexes/<repo_id>/index.sqlite`). Nothing is written inside the target repository.

```bash
# Index to the RSM Index Store canonical path and register (recommended).
uv run rsm index /path/to/repo --register

# Index to an explicit path and register (alternative, explicit --db preserved).
uv run rsm index /path/to/repo --db /path/to/repo/.rsm/index.sqlite --register
```

Once registered, `rsm mcp serve` can omit `--db`:

```bash
uv run rsm mcp serve --repo /path/to/repo
```

When `--register` is not set and `--db` is omitted, the existing default of `.rsm/index.sqlite`
(relative to the current directory) is preserved. The store is purely additive.

See [`docs/design/index_staleness.md`](../design/index_staleness.md) for the
designed `rsm store status` command, the status state machine
(`fresh` / `missing` / `stale` / `maybe_stale` / `schema_mismatch` / `unknown`),
and the suggested-action rules for explicit-`--db` vs Index Store modes.

## Indexing progress output

`rsm index` and `rsm store register --index` print phase-by-phase progress to
**stderr** so large repositories do not appear hung.  All stdout output remains
machine-readable.

### Scan summary

Immediately after file discovery, a single line summarises what was found:

```text
indexing: discovered files: python=3912 markdown=428 other=154 total=4494
```

### Per-phase progress

For repositories with ≥ 100 files per phase, intermediate progress lines are
emitted on the first file and every 100 files:

```text
indexing: Markdown 1/428 files...
indexing: Markdown 100/428 files...
indexing: Python 1/3912 files...
indexing: Python 100/3912 files...
indexing: exports 1/142 files...
```

### Completion lines

Each phase prints a completion line with its count and elapsed time:

```text
indexing: Markdown complete: 428/428 files, elapsed=2.1s
indexing: Python complete: 3912/3912 files, elapsed=28.4s
indexing: exports complete: 142/142 files, elapsed=1.3s
indexing: test relationships complete: added=512 total_relations=8034, elapsed=4.2s
indexing: writing index complete: entities=12345 relations=8034, elapsed=3.1s
indexing: complete: entities=12345 relations=8034, elapsed=42.3s
```

The relation-computation banner also shows the entity and relation counts
available at that point:

```text
indexing: computing test relationships from entities=12345 relations=7522...
```

### Stdout remains clean

The final summary line on stdout (`entities=… relations=…`) is unaffected:

```text
entities=12345 relations=8034
```

## Indexing profiler

`rsm index --profile` prints a per-phase timing table to **stderr** after indexing
completes.  Profiling is observational only: indexing behavior, ranking, and DB
output are unchanged.

```bash
rsm index . --db .rsm/index.sqlite --profile
```

Sample stderr output:

```
indexing profile:
  phase                       elapsed    files   entities   relations
  ─────────────────────────────────────────────────────────────────────
  file_discovery               0.002s        8          8           -  (4865.3 files/s)
  markdown_extraction          0.001s        1          2           1  (1556.8 files/s)
  python_ast                   0.001s        2         11          12  (1898.6 files/s)
  exports_extraction           0.000s        -          -           -
  test_relationships           0.000s        -          -           -
  sqlite_persist               0.001s        -         18          13
  metadata_write               0.001s        -          -           -
  ─────────────────────────────────────────────────────────────────────
  total                        0.015s
```

### JSON profiling report

Pass `--profile-report PATH` to write a machine-readable JSON report.
`--profile-report` implies `--profile`; the stderr table is also emitted.

```bash
rsm index . --db .rsm/index.sqlite --profile-report /tmp/rsm-profile.json
```

Example JSON excerpt:

```json
{
  "schema_version": "0.1",
  "repo_root": "/abs/path/to/repo",
  "started_at": "2026-01-01T00:00:00+00:00",
  "completed_at": "2026-01-01T00:01:02+00:00",
  "total_elapsed_seconds": 62.3,
  "phases": [
    {
      "name": "python_ast",
      "elapsed_seconds": 42.1,
      "files": 3912,
      "entities": 18400,
      "relations": 7200,
      "files_per_second": 92.9,
      "entities_per_second": 436.8,
      "relations_per_second": 171.0
    }
  ],
  "summary": {
    "total_files": 4494,
    "total_entities": 21000,
    "total_relations": 9100
  },
  "diagnostics": {
    "phase_with_max_elapsed": "python_ast",
    "phase_elapsed_percent": {
      "file_discovery": 3.2,
      "python_ast": 67.6,
      "exports_extraction": 2.1,
      "test_relationships": 6.3,
      "sqlite_persist": 5.0,
      "metadata_write": 0.2
    }
  }
}
```

> **Note:** Profiling is observational. It does not optimize indexing, change
> indexing semantics, or modify DB content.

## Database resolution for reader commands

Reader commands can use an explicit `--db`, an entry in the RSM Index Store, or the legacy
repo-local `.rsm/index.sqlite`. They resolve the database path in this order:

1. **Explicit `--db`** — always wins; the Index Store is not consulted.
2. **RSM Index Store entry for the current working directory** — used when `--db` is omitted and
   the CWD is a registered repo root.
3. **`.rsm/index.sqlite`** — the legacy fallback used when neither of the above applies.

This applies to:

| Command | Notes |
|---|---|
| `rsm pack` | Task-specific context pack |
| `rsm repo-map` | Broad structural orientation |
| `rsm inspect entities` / `rsm inspect relations` | Raw entity/relation queries |
| `rsm components infer` / `rsm components list` | ECS-style semantic components |
| `rsm invariants export` / `rsm invariants import` | Claim/invariant documents |
| `rsm eval retrieval` / `rsm eval compare` | Evaluation benchmarks |
| `rsm export-ai` | `.ai/` artifact generation |
| `rsm export-jsonl` | JSONL interchange export |

### Typical workflow without `--db`

```bash
# Register the repo in the Index Store (once).
uv run rsm store register . --index

# Reader commands now resolve the DB automatically.
uv run rsm pack --task "Find where incremental indexing is implemented"
uv run rsm repo-map --budget 4000
uv run rsm eval retrieval --dataset benchmarks/tasks.yaml --json
```

### Force a specific database

```bash
rsm pack --db /path/to/index.sqlite --task "..."
rsm repo-map --db /path/to/index.sqlite --budget 4000
```

### Precedence when both a store entry and `.rsm/index.sqlite` exist

If a repo has a registered Index Store entry **and** a local `.rsm/index.sqlite`, the Index Store
entry wins (step 2 above) unless `--db` is explicit. To use the local file instead:

```bash
rsm pack --db .rsm/index.sqlite --task "..."
```

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
