# RSM Post-PR [#59](https://github.com/apajon/repo-semantic-memory/pull/59) Synthesis Report

## Scope

PR #59 consolidates several major usability and correctness improvements around repository indexing:

- RSM Index Store
- index staleness detection
- incremental indexing via Git diff
- reader-command DB resolution
- local dogfooding of the full workflow

The result is a much more usable local-first workflow for CLI and MCP usage. RSM is no longer limited to manually passing one explicit `--db` path per repository and no longer requires full rebuilds for every indexing pass when incremental update is safe.

---

## 1. RSM Index Store

### Problem solved

Before this work, every MCP invocation and most CLI reader commands required a manually managed DB path:

```bash
rsm mcp serve --repo /path/to/repo --db /path/to/repo/.rsm/index.sqlite
```

This did not scale well across multiple repositories and made user configuration brittle.

### New model

RSM now supports a central local **RSM Index Store**.

Typical setup:

```bash
rsm store register /path/to/repo --index
rsm mcp serve --repo /path/to/repo
```

The `--db` argument is no longer required for MCP once the repository is registered.

### Store behavior

The Index Store resolves its home directory using:

```text
1. RSM_HOME environment variable
2. OS-specific default
```

OS defaults:

```text
Linux / Ubuntu:
  $XDG_DATA_HOME/repo-semantic-memory
  fallback: ~/.local/share/repo-semantic-memory

macOS:
  ~/Library/Application Support/repo-semantic-memory

Windows:
  %LOCALAPPDATA%\repo-semantic-memory
```

Store layout:

```text
<RSM_HOME>/
  registry.json
  indexes/
    <repo_id>/
      index.sqlite
```

### New CLI commands

```bash
rsm store path
rsm store list
rsm store list --json
rsm store register /path/to/repo
rsm store register /path/to/repo --index
rsm store unregister /path/to/repo
rsm store db /path/to/repo
rsm store status /path/to/repo
```

### Important policy

The Index Store does **not** auto-index by default.

Indexing remains explicit:

```bash
rsm store register /path/to/repo --index
```

or:

```bash
rsm index /path/to/repo --register
```

---

## 2. Reader-command DB resolution

### Problem found during dogfooding

After the Index Store was added, MCP could resolve a DB from the store, but reader commands such as:

```bash
rsm pack --task "..."
```

still failed without `--db`.

### Fix

A shared reader DB resolver was added.

Reader commands now resolve DB paths in this order:

```text
1. explicit --db
2. RSM Index Store entry for the current working directory
3. repo-local .rsm/index.sqlite
```

### Commands covered

The resolution applies to:

```text
rsm pack
rsm repo-map
rsm inspect entities
rsm inspect relations
rsm components infer
rsm components list
rsm invariants export
rsm invariants import
rsm eval retrieval
rsm eval compare
rsm export-ai
rsm export-jsonl
```

### Example workflow

```bash
rsm store register . --index
rsm pack --task "Find where incremental indexing is implemented"
rsm repo-map
```

To force a DB:

```bash
rsm pack --db /path/to/index.sqlite --task "..."
```

If both an Index Store entry and `.rsm/index.sqlite` exist, the Index Store wins unless `--db` is explicit.

---

## 3. Index staleness detection

### Problem solved

Before this work, RSM could read an index without clearly telling the user or agent whether the index was fresh, stale, dirty, missing, or incompatible.

### New status model

RSM now reports index status using stable states:

```text
fresh
missing
stale
maybe_stale
schema_mismatch
unknown
```

### Metadata written during indexing

Indexing writes lightweight metadata used for status detection and incremental planning, including:

```text
indexed_at
git_head
git_dirty
entity_count
relation_count
context_pack_version
last_index_mode
```

### MCP impact

`rsm_status` now reports fields such as:

```text
index_status
index_status_reason
indexed_at
indexed_git_head
current_git_head
working_tree_dirty
index_mode
suggested_action
```

This gives agents a way to detect stale or unsafe context before using a pack.

### CLI impact

`rsm store status` reports status in human and JSON form.

Example:

```bash
rsm store status .
rsm store status . --json
```

### Policy

RSM reports stale/missing/maybe-stale/schema mismatch status, but it does **not** rebuild automatically.

---

## 4. Incremental indexing

### Problem solved

Full rebuilds are simple and safe, but inconvenient when working iteratively.

The new incremental mode provides an opt-in way to update an existing index using Git signals.

### Command

```bash
rsm index /path/to/repo --incremental
```

With the Index Store:

```bash
rsm index /path/to/repo --register --incremental
```

### Policy

Incremental indexing is **explicit**.

Full rebuild remains the default.

If incremental indexing cannot prove safety, RSM falls back to a full rebuild.

Fallback is expected behavior, not an error.

### Change detection

Incremental planning uses local Git signals:

```text
git diff --name-status <indexed_head> HEAD
git status --porcelain
```

It detects:

```text
changed paths
deleted paths
renamed paths
working tree changes
unsafe conditions requiring full rebuild
```

### Safe fallback examples

Incremental mode falls back to full rebuild for cases such as:

```text
missing indexed Git head
schema/context-pack mismatch
previous index built from dirty tree
Git unavailable
Git history unreachable
diff/status failure
oversized change set
unsafe structural changes
```

### Metadata

`last_index_mode` is now consistent:

```text
full rebuild success       -> last_index_mode = full
incremental update success -> last_index_mode = incremental
fallback full rebuild      -> last_index_mode = full
```

---

## 5. Incremental indexing correctness cleanup

A senior audit identified and resolved the main correctness and maintainability issues before merge.

### Git copy handling

Problem:

```text
Cxxx old new
```

was previously at risk of being treated like a delete+add operation.

Correct behavior:

```text
Rxxx old new:
  old path -> deleted
  new path -> changed
  (old, new) -> renamed

Cxxx old new:
  new path -> changed
  old path is not deleted
  no renamed entry
```

This is now corrected.

### Incoming dangling relations

Problem:

Deleting a file could leave relations from unchanged files pointing at deleted entities.

Example:

```text
A.py relation -> B.Symbol
B.py deleted
```

RSM now removes incoming cross-file relations pointing at purged entity IDs before those entities are removed.

### Dangerous unused helper removed

An unused `_delete_dangling_relations` helper existed but could delete unresolved-ID relations such as placeholder `exports` / `imports`.

It was removed instead of renamed, reducing future footgun surface.

### Executor cleanup

Redundant `rename_old` / `rename_new` sets were removed from the executor.

The code now relies on the `IncrementalPlan` invariant:

```text
rename old paths are already in deleted_paths
rename new paths are already in changed_paths
```

---

## 6. Architecture boundaries

The senior audit found the layer separation clean.

### Planner

`indexing/incremental.py`:

```text
- parses Git signals
- determines changed/deleted/renamed paths
- decides fallback reasons
- produces IncrementalPlan
```

It does not mutate SQLite or run extractors.

### Executor

`indexing/executor.py`:

```text
- orchestrates extraction for changed paths
- calls SQLiteStore.apply_incremental_update
- writes metadata
- handles fallback path
```

It does not parse raw Git output.

### SQLite store

`store/sqlite_store.py`:

```text
- owns persistence mutation
- applies transactional updates
- purges entities/relations
- upserts extracted records
- updates metadata
```

It does not know Git semantics.

### CLI

`cli.py`:

```text
- wires commands
- resolves DB paths
- coordinates planner/executor/fallback
```

---

## 7. MCP policy remains safe

MCP remains read-only in this phase.

The MCP server can report index status through `rsm_status`.

It does not:

```text
auto-index
auto-refresh
run incremental indexing
write to target repositories
write to the Index Store on behalf of the client
```

Users must run indexing explicitly through the CLI.

---

## 8. Validation status

Reported validation after cleanup:

```text
647 tests passing
ruff clean
CodeQL: 0 alerts
```

Earlier validation also reported mypy clean during the broader PR work.

Recommended final local validation before merge:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
git status --short
```

Recommended dogfooding smoke:

```bash
TMP_RSM_HOME="$(mktemp -d)"

RSM_HOME="$TMP_RSM_HOME" uv run rsm index . --register
RSM_HOME="$TMP_RSM_HOME" uv run rsm store status .

RSM_HOME="$TMP_RSM_HOME" uv run rsm index . --register --incremental
RSM_HOME="$TMP_RSM_HOME" uv run rsm store status .

RSM_HOME="$TMP_RSM_HOME" uv run rsm pack \
  --task "Find where incremental indexing is implemented" \
  --budget 4000 \
  --profile agent_standard \
  > /tmp/rsm_incremental_pack.md

test -s /tmp/rsm_incremental_pack.md
```

---

## 9. Deferred items

The following were intentionally deferred.

### Promote `_run_git` to public API

Current issue:

```text
indexing.incremental imports _run_git from extractors.git_history
```

This crosses a package boundary using a private function.

Deferred cleanup:

```text
promote _run_git to public run_git(...)
```

Not blocking PR #59.

### SQLite expression index for path lookups

Current incremental update uses JSON path extraction for source paths.

Potential future optimization:

```sql
CREATE INDEX ... ON entities(json_extract(source_range_json, '$.path'))
```

This should be treated as a schema/performance task, not part of PR #59.

Not blocking PR #59.

### Public-repo benchmarks

Current dogfooding still relies mostly on:

```text
repo-semantic-memory
lifecore_ros2
```

A future benchmark suite should use public Python repositories with pinned commits and gold files/symbols.

Candidate repos:

```text
rich
typer
httpx
pytest
fastapi
black
pydantic
textual
django
ansible
```

---

## 10. Current recommended roadmap

After PR #59:

```text
51. Decide PyPI / no PyPI
52. Targeted announcement after MCP
53. Relation-cap diagnostic mode
54. Public-repo benchmark suite design
55. Next roadmap decision
```

However, before any serious public claims, RSM should eventually get:

```text
public-repo benchmark suite
pinned commits
gold files/symbols
reproducible reports
```

Dogfooding is useful, but it is not a general benchmark.

---

## 11. Merge recommendation

PR #59 is mergeable if final CI is green.

Merge criteria:

```text
ruff clean
mypy clean
pytest clean
dogfooding smoke OK
docs aligned with implementation
incremental remains opt-in
MCP remains read-only
```

Final verdict:

```text
PR #59 is a significant and valuable step.
It makes RSM much more usable for real local workflows by combining:
- Index Store
- status detection
- reader DB resolution
- incremental indexing
- safe fallback behavior
```
