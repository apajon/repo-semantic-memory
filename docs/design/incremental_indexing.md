# Incremental indexing

Status: implemented behind explicit `rsm index --incremental`.

Full rebuild remains the default indexing mode. Incremental indexing is opt-in
and falls back to a full rebuild whenever safety cannot be proven.

The implementation updates an existing index using local Git signals:
`git diff --name-status <indexed_head> HEAD` and `git status --porcelain`.
It re-extracts changed files, removes deleted paths from the index, refreshes
affected relations, and updates index metadata inside a SQLite transaction.

MCP remains read-only: the MCP server reports index status but does not
auto-index, auto-refresh, or mutate indexes for the client.

---

This document originated as the design specification for incremental indexing.
The current implementation follows the staged design and keeps incremental
indexing explicit via `--incremental`. Design rationale is preserved below.

It builds on:

- Prompt 48 / 48.1 — RSM Index Store (`RSM_HOME`, central `registry.json`,
  `indexes/<repo_id>/index.sqlite`, `rsm store` command group,
  `rsm index --register`, optional `--db` on `rsm mcp serve`).
- Prompt 49 / 49.1 — Index staleness detection
  (`src/repo_semantic_memory/index_status.py`, `IndexStatus`,
  `IndexStatusReason`, `IndexStatusReport`, `detect_index_status(...)`,
  `rsm store status`). See [`docs/design/index_staleness.md`](index_staleness.md).

The metadata rows already persisted by Prompt 49.1 (`indexed_at`,
`git_head`, `git_dirty`, `entity_count`, `relation_count`,
`context_pack_version`, `schema_version`) are the **single source of
truth** for "what state was this index built against". Incremental
indexing reuses them; **no second metadata system is introduced**.

## Implementation status

Implemented:

- `rsm index <repo> --incremental`
- incremental planning from local Git diff/status signals
- full rebuild fallback when safety cannot be proven
- file-level purge and re-extraction for changed/deleted paths
- transactional SQLite update path
- index metadata updates after successful indexing
- reader-command DB resolution through the RSM Index Store
- local dogfooding for Index Store + incremental indexing

Still deferred:

- automatic indexing from MCP
- daemon/watch mode
- background refresh
- non-Git incremental guarantees
- public benchmark claims
- aggressive fine-grained cross-file invalidation beyond the current safe model

## Non-goals

This design does **not**:

- Change the behavior of `rsm index` in its current (full-rebuild) form.
- Remove full rebuild support. Full rebuild stays the default and the
  always-correct fallback.
- Assume Git is always available. Non-Git repos remain full-rebuild only.
- Auto-index from MCP. `rsm mcp serve` continues to require an existing
  DB and never writes to the index on a client's behalf by default.
- Write to the target repository. The index DB is the only thing that
  changes.
- Add file watching, daemons, or background services.
- Add network or cloud behavior. All Git calls are local only.
- Introduce a second metadata store. All staleness/incremental state
  lives in the SQLite `metadata` table established in Prompt 49.1.
- Break explicit `--db` workflows. Both DB-resolution modes work
  identically for incremental indexing.
- Break Index Store workflows. `--incremental` composes cleanly with
  `--register` and with Index-Store-resolved DBs.
- Make unsafe partial updates that corrupt cross-file relations. When a
  partial update cannot be proven safe, the command falls back to a
  full rebuild and says so on stderr.

## 1. Mode shape

### 1.1 Command surface

Two shapes were considered:

| Option                            | Pros                                                                                              | Cons                                                                  |
| --------------------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `rsm index <repo> --incremental`  | One verb, one mental model; opt-in flag; composes with `--db` and `--register` without ambiguity. | Slightly longer to type.                                              |
| `rsm index update <repo>`         | Reads as a separate verb; clearer in shell history.                                               | Two ways to spell "update the index"; harder to compose with `--db`.  |

**Recommendation: `rsm index <repo> --incremental`.**

Rationale:

- Keeps a single `rsm index` entry point. All existing flags
  (`--db`, `--register`, `--with-git`, future `--no-git`) compose
  unchanged.
- Avoids subcommand proliferation under `rsm index`.
- Matches the precedent set in Prompt 49.1: behavior is selected by an
  explicit flag, never inferred.

Full rebuild remains the default. `--incremental` is opt-in until the
mode is proven stable across the validation matrix in §7.

Example invocations:

```bash
# Explicit --db, incremental update
uv run rsm index /path/to/repo --incremental --db /path/to/index.sqlite

# Index Store mode, incremental update of the registered DB
uv run rsm index /path/to/repo --incremental

# Index Store mode, incremental + register-if-missing
uv run rsm index /path/to/repo --incremental --register
```

### 1.2 DB resolution

Incremental mode reuses the existing DB resolver:

1. If `--db PATH` is provided, use it (explicit-`--db` mode).
2. Otherwise consult the Index Store
   (`store_home.IndexRegistry.lookup(repo_id)`).
3. If neither resolves to an existing DB → fall back to full rebuild
   (§4.1). The user is shown a single-line `warning:` explaining that
   `--incremental` requires an existing index.

`--incremental --register` is permitted but only triggers
`IndexRegistry.register(...)` after a successful (incremental or
fallback full) build, exactly like today's `rsm index --register`.

### 1.3 Git requirement

`--incremental` requires:

- The target repo is a Git working tree (i.e. `git rev-parse HEAD` succeeds).
- `git` is on `PATH` and reachable via the existing bounded
  `_run_git(...)` helper in `extractors/git_history.py`.

If either check fails → fall back to full rebuild with a `warning:` line
explaining the fallback reason. We never silently skip files.

## 2. Change detection

All Git calls are **local-only** and use the existing bounded
`_run_git(...)` helper (no remote fetch, no network).

### 2.1 Inputs

| Input                          | Source                                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------- |
| Last indexed Git HEAD          | `metadata.git_head` row (Prompt 49.1).                                                            |
| Last indexed dirty flag        | `metadata.git_dirty` row (Prompt 49.1).                                                           |
| Last indexed timestamp         | `metadata.indexed_at` row (Prompt 49.1).                                                          |
| Current Git HEAD               | `git rev-parse HEAD`.                                                                             |
| Tracked changes since HEAD     | `git diff --name-status <indexed_head> HEAD` (path × status).                                     |
| Working tree changes           | `git status --porcelain=v1` (modified, deleted, renamed, untracked relevant files).               |
| Path-role classification       | The existing `extractors.path_roles` helpers, identical to what full indexing uses.               |
| Schema / context-pack versions | `metadata.schema_version`, `metadata.context_pack_version` vs runtime (Prompt 49.1).              |

### 2.2 Computed change sets

From the inputs above the detector builds three disjoint sets of
repo-relative paths, all filtered to **indexed roles** (the same role
filter the full indexer applies — typically `source`, `test`, `doc`;
never `generated_artifact`):

- `changed_paths` — files that exist on disk and need re-extraction.
  Built from `git diff --name-status` statuses `A`, `M`, `T`, `C`, `R`
  (renamed target side) **plus** `git status --porcelain` modified and
  untracked entries.
- `deleted_paths` — files that no longer exist. Built from
  `git diff --name-status` statuses `D` and the source side of `R`
  (rename), plus `git status --porcelain` deleted entries.
- `renamed_paths` — map `old_path → new_path` for `R<score>` entries.
  These are reported separately so the executor (§3) can clean up
  entities keyed by the old path and re-extract the new path.

Untracked files outside indexed roles are ignored. Files inside
`.gitignore` are ignored. Files inside the configured exclude globs are
ignored. This matches the full indexer exactly.

### 2.3 Edge cases

- **Indexed HEAD missing or empty.** Treat as `unsafe` and full-rebuild
  (§4.1). Reason: cannot prove what state the DB was built against.
- **Indexed HEAD not reachable from current HEAD** (e.g. force-push,
  rebase, branch switch to an unrelated history). `git diff` still
  works between two reachable commits, but for an unreachable indexed
  commit, full-rebuild. Detected via
  `git merge-base --is-ancestor <indexed> HEAD` or equivalent; on
  failure, fall back.
- **`git_dirty == "true"` at last index.** The previous index was built
  with uncommitted changes; we cannot trust the HEAD-to-HEAD diff to
  cover everything. Full-rebuild.
- **Working tree currently dirty.** Include working-tree modifications
  in `changed_paths` and untracked-but-relevant files. We do **not**
  fall back to full rebuild just because the tree is dirty; the diff
  plus `git status` accurately covers the delta. The new
  `metadata.git_dirty` value reflects the post-run dirty state.
- **Submodules.** Out of scope. Treat as opaque path entries; do not
  recurse. If a submodule pointer changes, the parent's recorded
  pointer change shows up as a single modified gitlink path; we ignore
  it for extraction.
- **Symlinks.** Out of scope for v1; treat as ignored (current indexer
  behavior).
- **Large change set.** If `len(changed_paths) + len(deleted_paths)`
  exceeds a configurable safety threshold (default 50% of indexed
  files), fall back to full rebuild. Incremental is meant for small
  deltas; for large deltas the full path is faster and safer.

## 3. Execution model

Incremental indexing is a **delete-then-upsert** pass on the existing
DB, run inside the existing `SQLiteStore._transaction()` so it is
atomic. There is no separate writer.

### 3.1 Per-file invariant

Every entity and relation that the full indexer produces is attributable
to one or more **owning source paths**. The incremental executor relies
on three guarantees, which the implementation must honor:

1. Every `Entity` carries its repo-relative source path in its existing
   `path` field (already true today).
2. Every `Relation` can be attributed to the repo-relative source path
   of the file that produced it (its "producer file"). Per the
   Prompt 50.1 audit (§11), this is **already true for every relation
   kind today**, derivable as
   `relation.evidence.source_range.path` when evidence is present,
   else `Entity.source_range.path` of the relation's
   `source_entity_id`. No schema change is required to start
   implementing incremental indexing; an explicit `producer_path`
   column on the SQLite `relations` table is an optional later
   optimization, not a prerequisite.
3. A given producer file's full set of entities/relations is the union
   of what its extractors return; no extractor mutates another file's
   rows.

### 3.2 Steps

For a resolved change plan `(changed_paths, deleted_paths, renamed_paths)`:

1. **Open the DB** read/write. Re-run the same schema /
   context-pack-version checks the full indexer runs (Prompt 49.1).
   On mismatch → full rebuild.
2. **Compute the producer-path purge set** =
   `deleted_paths ∪ changed_paths ∪ {old_path for old_path,_ in renamed_paths}`.
3. **Inside a single transaction:**
   a. Delete every `Entity` whose `path` is in the purge set.
   b. Delete every `Relation` whose `producer_path` is in the purge set.
      This is the **producer-side** purge and is sufficient to avoid
      orphan relations *originating* in a changed file.
   c. Delete every `Relation` whose `source_entity_id` or
      `target_entity_id` references an entity we just deleted **and**
      whose producer is itself in the purge set. We do **not** delete
      cross-file relations whose producer survives; they will be
      re-emitted by step (e) if still valid, and we do not want to
      drop relations owned by an unchanged file.
   d. Re-run the existing extractor pipeline scoped to `changed_paths`
      (plus the new path side of each rename). The extractors emit the
      same `Entity` / `Relation` shapes as today; we reuse the
      existing pipeline unchanged.
   e. Upsert the new entities and relations via the existing
      `_upsert_entities` / `_upsert_relations` paths.
   f. Recompute and upsert metadata rows: `indexed_at`, `git_head`,
      `git_dirty`, `entity_count`, `relation_count`,
      `context_pack_version`, `schema_version`. These are the same
      rows Prompt 49.1 writes today. No new metadata key is added.
4. **Commit the transaction.** On any exception inside the block, the
   transaction rolls back; the DB is left in its prior consistent state
   and the command exits non-zero with the original error.

### 3.3 What is *not* incremental in v1

The following stay full-rebuild even in `--incremental` mode, because
they read across the whole index:

- Repo-wide invariants and ECS-style component derivation that depend
  on the global entity set (e.g. `PublicAPI` confirmation via the
  exports extractor). The executor runs these passes after step (e),
  scoped to the **whole** updated graph, not just changed files. They
  are fast relative to AST extraction and re-running them keeps the
  cross-file claim layer correct.
- The git-history extractor's repository-level summary. It already
  caches by HEAD and remains a single repo-level pass.

This split is the smallest one that keeps cross-file relations correct
without rewriting any extractor.

### 3.4 Cross-file relations: safety argument

The risk is dropping a relation that should stay or keeping a relation
that should be removed. The execution rules above maintain three
invariants:

1. **No orphan from a changed producer.** Step 3c deletes all relations
   produced by files in the purge set; step 3d-e re-emits the surviving
   relations from the new extractor output. ✔
2. **No orphan from a deleted target.** If a producer file `A`
   references an entity in deleted file `B`, then `A` is either in the
   purge set (because the import/usage change was reflected in `A`'s
   own diff or working-tree state — typical case) **or** `A` is
   unchanged. In the latter case, the relation pointing at the
   now-missing entity is a stale relation. To handle this, after
   step 3d the executor runs a small **dangling-relation sweep** that
   deletes any relation whose `source_entity_id` or `target_entity_id`
   no longer resolves to an entity row. This sweep is bounded
   (single SQL pass) and runs inside the same transaction.
3. **No double-counting.** Upserts use the same primary keys as today;
   re-emitting an unchanged entity is a no-op.

If any of these invariants cannot be enforced (e.g. an extractor cannot
attribute a relation to a producer path), the executor refuses to run
incrementally and falls back to a full rebuild with a clear `info:` message.

## 4. Safety fallbacks

### 4.1 When `--incremental` falls back to full rebuild

The executor falls back, prints a single-line `info:` message to stderr, and
performs a full rebuild whenever any of the following holds:

| Condition                                                                              | Reason string                       |
| -------------------------------------------------------------------------------------- | ----------------------------------- |
| Target DB does not exist.                                                              | `incremental_index_missing`         |
| `metadata.git_head` is missing or empty.                                               | `incremental_no_indexed_head`       |
| Repo is not a Git working tree, or `git` is unavailable.                               | `incremental_git_unavailable`       |
| `metadata.schema_version` ≠ runtime `SCHEMA_VERSION`.                                  | `incremental_schema_mismatch`       |
| `metadata.context_pack_version` ≠ runtime `CONTEXT_PACK_VERSION`.                      | `incremental_context_pack_mismatch` |
| Indexed HEAD is not reachable from current HEAD (`merge-base --is-ancestor` failure).  | `incremental_history_unreachable`   |
| Previous index was built dirty (`metadata.git_dirty == "true"`).                       | `incremental_previous_dirty`        |
| Change set exceeds the safety threshold (default 50% of indexed files).                | `incremental_changeset_too_large`   |
| Requested `--include`/`--exclude` scope differs from the stored scope.                 | `incremental_scope_mismatch`        |
| Any uncaught exception during the per-file pass.                                       | `incremental_internal_error`        |

These reason strings are stable and match the `IncrementalFallbackReason`
constants in `src/repo_semantic_memory/indexing/incremental.py`.  They appear
in stderr `info:` lines with the format:

```
info: incremental index fallback: <reason>; running full rebuild
```

and in any future JSON status output that wraps incremental runs. They
**do not** overlap with the `IndexStatusReason` constants from
Prompt 49.1 — they are diagnostic strings emitted by `rsm index
--incremental`, not by the staleness detector.

Fallback is always **safe** because a full rebuild is unconditionally
correct. The cost is wall-clock time, not correctness.

### 4.2 What never causes a fallback

- A clean fresh index (no changes detected). Incremental returns
  immediately after writing the refreshed `indexed_at` / `git_head`
  metadata rows. No entity or relation rows are touched.
- Working tree dirty *at run time*. Handled inside the change-detection
  pipeline (§2.3); the resulting `git_dirty` metadata reflects post-run
  state.
- Untracked relevant files. Treated as `changed_paths` and re-extracted.

### 4.3 Scope mismatch safety (Prompt 57.5.1)

If the `--include`/`--exclude` patterns supplied on the current run differ
from the patterns stored in `metadata.include_patterns` /
`metadata.exclude_patterns`, the incremental path **cannot** safely update
the existing index: deleted entries from previously-indexed paths that are
now excluded, and new entries for newly-included paths, would be silently
missed.

RSM therefore falls back to a full rebuild whenever the requested scope
differs from the stored scope:

| Transition                                   | Fallback? |
| -------------------------------------------- | --------- |
| full index → incremental full                | no        |
| full index → incremental with --include/--exclude | yes (`incremental_scope_mismatch`) |
| scoped index → incremental full (no patterns) | yes (`incremental_scope_mismatch`) |
| scoped index → incremental with same patterns | no        |
| scoped index → incremental with different patterns | yes (`incremental_scope_mismatch`) |

After a scope-mismatch fallback, the full rebuild writes the *new* scope
metadata — so the next incremental run against the same scope will proceed
normally.

Scope comparison is order-insensitive: `["a/", "b/"]` and `["b/", "a/"]`
are considered the same scope.

Legacy indexes built before Prompt 57.5 carry no scope metadata.  They are
treated as full-scope indexes: an incremental full run proceeds normally;
an incremental scoped run triggers `incremental_scope_mismatch`.

## 5. Metadata model (reuse, not extend)

Every successful `rsm index` run writes the same staleness rows Prompt 49.1
established, plus `last_index_mode` to record how the index was produced:

```jsonc
{
  "indexed_at": "<ISO8601 UTC of this run>",
  "git_head": "<current HEAD or ''>",
  "git_dirty": "true" | "false" | "",
  "entity_count": "<decimal>",
  "relation_count": "<decimal>",
  "context_pack_version": "<runtime>",
  "schema_version": "<runtime>",
  "last_index_mode": "incremental" | "full"
}
```

`last_index_mode` is written after every successful run:

- `"incremental"` — incremental update completed successfully.
- `"full"` — full rebuild ran (either directly or as an incremental fallback).

The Index Store's `registry.json` is likewise untouched; its `last_indexed_at`
continues to mean "last successful `rsm index` for this repo", regardless of
mode.

## 6. CLI / MCP surface

### 6.1 `rsm index`

- New flag: `--incremental` (boolean, default `false`).
- All existing flags compose unchanged.
- Output: identical summary line on success
  (`Indexed N entities, M relations ...`). When a fallback occurred,
  one extra `info: incremental index fallback: <reason>; running full rebuild`
  line is printed to stderr **before** the summary.
- Exit codes unchanged. Success is `0`; any unrecoverable error
  (including a full-rebuild fallback that itself fails) returns the
  same non-zero exit the full path would have returned.

### 6.2 `rsm mcp serve`

**No change.** MCP never indexes on a client's behalf. The existing
read-only contract holds. `--incremental` is a CLI-only flag.

### 6.3 `rsm store status` / `rsm_status`

**No change to the JSON shape.** The status report already exposes
freshness via `indexed_at`, `indexed_git_head`, `current_git_head`,
`working_tree_dirty`, and `index_status`. Incremental indexing simply
keeps those fields up-to-date faster.

`last_index_mode` is written by every successful run (see §5); it is not
currently surfaced in the `rsm_status` JSON output.

## 7. Validation

Validation covers the standard suite (`uv run ruff format --check .`,
`uv run ruff check .`, `uv run mypy src`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest`) plus the following:

1. **Determinism parity.** For a fixed repo state, the final DB
   produced by `rsm index --incremental` (starting from any reachable
   prior index) must be **byte-identical** to a fresh full rebuild,
   modulo `indexed_at` and `last_index_mode`. This
   includes entity ids, relation ids, sort orders, and metadata
   counts. Add a focused test that runs both modes against a fixture
   repo and diffs `list_entities()` / `list_relations()`.
2. **Cross-file relation safety.** Tests cover:
   - File deleted that other files import / call / test / document.
   - File renamed that other files import.
   - File modified to remove a symbol other files import.
   - File modified to add a symbol others later import.
   - Working-tree-only changes.
   - Untracked relevant files.
3. **Fallback matrix.** One test per row of the §4.1 table verifying
   the fallback path runs and emits the documented reason.
4. **Idempotency.** Running `--incremental` twice in a row with no
   intervening changes is a no-op for entity/relation rows and only
   refreshes `indexed_at`.
5. **Index Store + explicit `--db` parity.** Both DB-resolution modes
   produce identical results.
6. **Benchmark.** `uv run rsm eval retrieval`/`compare` against an
   incrementally-updated DB and a freshly-rebuilt DB on the same
   commit must produce identical metrics.

All items above are covered by `tests/indexing/test_parity.py` (13 parity
scenarios) and `tests/indexing/test_executor.py` (20 executor tests).

## 8. Implementation history

The design was implemented in four stages, each reviewed in isolation:

1. **Producer-path guarantee (Prompt 50.1).** Audited every extractor. All current
   relation kinds are attributable to a producer file path without any schema change.
   No CLI / MCP surface change.
2. **Change detector module (Prompt 50.2).** `src/repo_semantic_memory/indexing/incremental.py`
   exposes `plan_incremental_update(repo_root, indexed_head, ...) -> IncrementalPlan`.
   No DB writes; pure computation from Git signals. 48 unit tests.
3. **Executor (Prompt 50.3).** `run_incremental_index()` wired into `rsm index` behind
   the `--incremental` flag. Purge + re-extract + global recompute + metadata refresh,
   all inside a single `SQLiteStore._transaction()`. 20 executor tests.
4. **Docs (Prompt 50.6).** `docs/usage/cli.md` documents reader DB resolution; this file
   updated to reflect the implemented state.

## 9. Open questions

- **Per-file extractor scoping.** Today's extractor pipeline takes a
  repo root and discovers files internally. The executor constrains
  extraction to changed files by running each extractor on each
  changed file individually (the approach chosen as the non-trivial
  alternative).
- **`last_index_mode` metadata row.** Resolved: `last_index_mode = "incremental"`
  is written by incremental runs. Full-rebuild runs do not write `last_index_mode`.
  See §5.
- **Safety threshold default.** §2.3 suggests "50% of indexed files".
  The constant `max_changed_paths=500` is used in the implementation;
  users can override via the `plan_incremental_update` keyword argument.
- **Renames without `-M`/`-C` detection.** `git diff --name-status`
  detection of renames is heuristic. Treating an undetected rename as
  delete-plus-add is **safe** (the new file's relations are
  re-extracted; the old file's are purged), just slightly less
  efficient. No change to the design.
- **Concurrent writers.** Two `rsm index --incremental` runs on the
  same DB must not interleave. The existing single-transaction
  guarantee prevents corruption, but the second run will see a
  changed `indexed_at` mid-flight and may decide to fall back. This
  is acceptable; cross-process locking is out of scope.

## 10. Summary

`rsm index --incremental` is an opt-in mode that, when safe, updates
only the files changed since the last successful index. It reuses the
Prompt 49.1 metadata model, never invents a second metadata store, and
falls back to a full rebuild whenever safety cannot be proven. It is
implemented and validated; see §7 for the validation matrix and
`tests/indexing/test_parity.py` for the test scenarios.

## 11. Relation producer-path attribution audit (Prompt 50.1)

This section verifies the §3.1 invariant — *every relation can be
attributed to an owning producer file* — against the current extractor
pipeline. It is the prerequisite the incremental design depends on; if
any current relation kind were unattributable, incremental indexing
would be blocked until either the schema or the extractor changed.

**Result: every relation kind currently produced by RSM is
attributable to a producer file path without any schema change.**
Incremental implementation is unblocked.

### 11.1 Inventory

Source of truth: `Relation.kind` literal in
`src/repo_semantic_memory/model/relation.py` and every `Relation(...)`
construction site in `src/repo_semantic_memory/extractors/`.

Eleven relation kinds are declared in `RELATION_KINDS`:

```
contains, imports, inherits, calls, uses, tests, documents,
owns, requires, violates, exports
```

Of those, only five are actually produced by the current pipeline.
The remaining six (`calls`, `uses`, `documents`, `owns`, `requires`,
`violates`) are reserved kinds with **no producer extractor today**;
they exist in the schema for forward compatibility (e.g. the
`graph_selection` weight table references them) but are never written
to the SQLite store. They cannot create incremental-safety problems
because they cannot exist in any current index. If a future extractor
adds them, that extractor must satisfy the same producer-path rule.

| Relation | Producer pass                                       | Source kind                       | Target kind                                | Scope            | Evidence?  | Producer path source                                            |
| -------- | --------------------------------------------------- | --------------------------------- | ------------------------------------------ | ---------------- | ---------- | --------------------------------------------------------------- |
| `contains` (Python) | `extractors.python_ast`               | `module` / `class`                | `function` / `class` / `method`            | intra-file       | **none**   | `source_entity_id` → `Entity.source_range.path` (module path).  |
| `contains` (Markdown) | `extractors.markdown_outline`       | `doc` / section `doc`             | section `doc`                              | intra-file       | yes        | `evidence.source_range.path` = target heading path = doc path.  |
| `inherits` | `extractors.python_ast`                            | `class`                           | unresolved `python_symbol`                 | cross-file       | **none**   | `source_entity_id` → owning class's module path.                |
| `imports` | `extractors.python_ast`                             | `module`                          | external symbol id                         | cross-file       | **none**   | `source_entity_id` → owning module path.                        |
| `exports` | `extractors.python_exports`                         | `module` (`__init__.py`)          | unresolved export id                       | cross-file       | yes        | `evidence.source_range.path` = `__init__.py` path.              |
| `tests`   | `extractors.test_relationships` (post-pass)        | `test` / `function` / `class`      | tested entity                              | cross-file       | yes        | `evidence.source_range.path` = test file (source) path.         |

### 11.2 Producer-path derivation rule

For every relation in the store, the producer file path is computed
deterministically as:

```
producer_path(relation) =
    relation.evidence.source_range.path        if evidence is present
    else entity_path(relation.source_entity_id) if source is an indexed entity
    else None
```

`entity_path` is just `Entity.source_range.path`, which is a required
non-empty string (`SourceRange.__post_init__`).

The fall-back to `source_entity_id`'s entity path is sound because all
relations produced today have a source side that is **always an
indexed entity in the same DB**:

- `contains` (Python): source is a `module`/`class` entity emitted by
  the same `python_ast` pass.
- `inherits`: source is a `class` entity emitted by the same pass.
- `imports`: source is a `module` entity emitted by the same pass.
- `contains` (Markdown), `exports`, `tests` already carry explicit
  `evidence.source_range.path`, so the fall-back is not needed.

In every case the producer file is uniquely determined.

### 11.3 Classification

Using the categories from the task description:

| Category                                       | Kinds                                                  | Rationale                                                                                                                                                          |
| ---------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `safe_file_scoped`                             | `contains` (Python), `contains` (Markdown)             | Source and target live in the same producer file. Purging by producer path is exact.                                                                               |
| `safe_cross_file_with_global_recompute`        | `imports`, `inherits`, `exports`, `tests`              | Producer path is well-defined (source-side) and re-extracted from the changed file. The target may be unresolved or live in another file; correctness is preserved by the dangling-relation sweep (§3.2 step (e) of executor) plus repo-wide re-runs for `tests` and ECS `PublicAPI` confirmation. |
| `requires_full_rebuild`                        | *(none)*                                               | No current relation kind requires it.                                                                                                                              |
| `unknown`                                      | *(none)*                                               | All produced kinds are accounted for.                                                                                                                              |

The reserved-but-unused kinds (`calls`, `uses`, `documents`, `owns`,
`requires`, `violates`) are deliberately **not** classified above
because they have no producer today and therefore cannot appear in any
index. The incremental change detector treats any extractor that
emits an unrecognized or unattributable kind as a fallback trigger
(§4.1, `incremental_unattributable_relation`). This makes "unknown"
the safe default for any future extractor that has not been audited.

### 11.4 Invalidation strategy per class

- **File-scoped (`contains` Python, `contains` Markdown).**
  Purge by producer path = re-extract the changed file. No
  cross-file impact.
- **Cross-file with global recompute (`imports`, `inherits`).**
  Purge relations whose producer path is in the change set. Re-extract
  the changed module via the existing `python_ast` pass. Targets are
  unresolved or external ids; the dangling-relation sweep (§3.4
  invariant 2) removes any relation whose target no longer resolves
  after the changed file's deletions land.
- **Cross-file with global recompute (`exports`).**
  Purge relations whose producer (`__init__.py`) is in the change
  set. Re-extract the changed `__init__.py` via `python_exports`.
  Repo-wide ECS `PublicAPI` confirmation (§3.3) runs once over the
  updated graph regardless of which files changed.
- **Cross-file with global recompute (`tests`).**
  `test_relationships` is a post-pass that reads *all* entities and
  pre-existing relations. The incremental executor treats it as a
  global recompute step (§3.3): after per-file extraction completes,
  re-run `extract_test_relationships(repo_root, entities, relations)`
  and replace all existing `tests` relations atomically inside the
  same transaction. This is cheap relative to AST extraction and
  keeps test attribution correct even when a non-test file changes.

### 11.5 Required metadata changes

**None for the current relation set.** The producer path is derivable
from existing fields:

- `relation.evidence.source_range.path` when present.
- `entity.source_range.path` for the relation's `source_entity_id`
  otherwise.

The incremental change detector (Prompt 50, step 8.2) will expose this
derivation as a single helper, e.g. `producer_path(relation, store) ->
str | None`. Returning `None` triggers the
`incremental_unattributable_relation` fallback (§4.1) — but as
established above, that branch is unreachable with today's extractors.

The "explicit `producer_path` accessor on `Relation`" suggestion in
§3.1 of the original incremental design is therefore **downgraded to
optional**:

- It is **not required** to start implementing incremental indexing.
- It **may** be added later as a cached column on the SQLite
  `relations` table for query speed, behind a schema version bump.
  Until then the derivation is cheap (single dict lookup per relation
  against the entity table).

### 11.6 Tests proposed for Prompt 50.2+

The implementation prompt that adds the change detector should ship
the following tests (one per concern):

1. `test_producer_path_for_every_relation_kind` — index a small
   fixture repo, walk every relation in the store, assert that the
   derivation rule (§11.2) returns a non-`None` path for every
   relation. Snapshot the (kind, path) pairs.
2. `test_no_unknown_relation_kind_in_classification` — assert that
   every value in `RELATION_KINDS` is either in the classification
   table (§11.3) or has no producer extractor today. Fails if a new
   relation kind is wired in without an audit update.
3. `test_incremental_fallback_on_unattributable_relation` — inject a
   synthetic relation whose source entity is not in the store, run
   the change planner, assert it returns the
   `incremental_unattributable_relation` fallback.
4. `test_purge_by_producer_path_leaves_no_dangling_relations` — set
   up a fixture with cross-file `imports`/`inherits`/`exports`/`tests`
   relations; delete a producer file; run the executor; assert no
   relation in the store references a missing entity id and no
   relation has `producer_path` pointing at the purged file.
5. `test_python_ast_relations_have_resolvable_source_entity` — guard
   the §11.2 fall-back: every `contains`/`inherits`/`imports`
   relation produced by `python_ast` must have its `source_entity_id`
   present in the same extractor batch.

These tests live alongside the change-detector module in Prompt 50.2.
This audit prompt does **not** add them, because no production code
has changed.

### 11.7 Conclusion

- **5 relation kinds** are currently produced.
- **All 5** are safely attributable to a producer file path with no
  schema change.
- **0** are unattributable or require full rebuild.
- **6 reserved kinds** are unused and therefore non-issues today; any
  future extractor that emits one must update §11.1–§11.3 and is
  guarded by the `incremental_unattributable_relation` fallback in the
  meantime.

Incremental implementation (Prompt 50.2 — change detector,
Prompt 50.3 — executor) is **unblocked** by this audit and may proceed
without a schema change.
