# Incremental indexing via Git diff (design)

This document specifies how RSM can update an existing index for only the
files that changed since the last successful indexing run, instead of
rebuilding the full index every time.

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

The goal of this prompt is **design only**. Nothing is implemented here.
Implementation will land in a dedicated follow-up prompt where it can be
reviewed in isolation and gated behind a feature flag until proven safe.

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

Example invocations (design intent — not yet implemented):

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
2. Every `Relation` carries the repo-relative source path of the file
   that produced the relation (the "producer file"). This is **already
   present** in today's relation evidence for most extractors but is
   not yet a hard schema-level guarantee. The implementation prompt
   must verify per-extractor and add an explicit `producer_path`
   accessor on `Relation` if needed. **This is the single non-trivial
   schema-touching change required to make incremental safe.**
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
incrementally and falls back to a full rebuild with a clear `warning:`.

## 4. Safety fallbacks

### 4.1 When `--incremental` falls back to full rebuild

The executor falls back, prints a single-line `warning:` to stderr, and
performs a full rebuild whenever any of the following holds:

| Condition                                                                              | Reason string                       |
| -------------------------------------------------------------------------------------- | ----------------------------------- |
| Target DB does not exist.                                                              | `incremental_db_missing`            |
| `metadata.git_head` is missing or empty.                                               | `incremental_no_indexed_head`       |
| Repo is not a Git working tree, or `git` is unavailable.                               | `incremental_git_unavailable`       |
| `metadata.schema_version` ≠ runtime `SCHEMA_VERSION`.                                  | `incremental_schema_mismatch`       |
| `metadata.context_pack_version` ≠ runtime `CONTEXT_PACK_VERSION`.                      | `incremental_context_pack_mismatch` |
| Indexed HEAD is not reachable from current HEAD (`merge-base --is-ancestor` failure).  | `incremental_history_unreachable`   |
| Previous index was built dirty (`metadata.git_dirty == "true"`).                       | `incremental_previous_dirty`        |
| Change set exceeds the safety threshold (default 50% of indexed files).                | `incremental_changeset_too_large`   |
| Any extractor in the active pipeline cannot attribute a relation to a producer path.   | `incremental_unattributable_relation` |
| Any uncaught exception during the per-file pass.                                       | `incremental_internal_error`        |

These reason strings are stable; they appear in stderr `warning:` lines
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

## 5. Metadata model (reuse, not extend)

Incremental indexing **does not** add new metadata rows. It writes the
same rows Prompt 49.1 already writes:

```jsonc
{
  "indexed_at": "<ISO8601 UTC of this run>",
  "git_head": "<current HEAD or ''>",
  "git_dirty": "true" | "false" | "",
  "entity_count": "<decimal>",
  "relation_count": "<decimal>",
  "context_pack_version": "<runtime>",
  "schema_version": "<runtime>"
}
```

A future prompt may add a small diagnostic row (e.g.
`last_index_mode = "incremental" | "full"`) **only if** the staleness
detector or the CLI status command needs to distinguish the two. The
default for this design is: no new row. The Index Store's
`registry.json` is likewise untouched; its `last_indexed_at` continues
to mean "last successful `rsm index` for this repo", regardless of
mode.

This is the explicit reason this prompt is design-only and not
implementation: we do **not** want to grow the metadata schema for a
mode that has not been validated end-to-end.

## 6. CLI / MCP surface

### 6.1 `rsm index`

- New flag: `--incremental` (boolean, default `false`).
- All existing flags compose unchanged.
- Output: identical summary line on success
  (`Indexed N entities, M relations ...`). When a fallback occurred,
  one extra `warning: incremental fallback: <reason>` line is printed
  to stderr **before** the summary.
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

If a future prompt adds `last_index_mode`, it would appear as an
additional top-level string in both outputs; absent until then.

## 7. Validation plan

When implementation lands, validation must include the following on top
of the standard suite (`uv run ruff format --check .`,
`uv run ruff check .`, `uv run mypy src`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest`):

1. **Determinism parity.** For a fixed repo state, the final DB
   produced by `rsm index --incremental` (starting from any reachable
   prior index) must be **byte-identical** to a fresh full rebuild,
   modulo `indexed_at` and any future `last_index_mode` row. This
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

Until these pass, `--incremental` is **not** advertised in user-facing
docs (`docs/usage/cli.md`, `README.md`) outside an "experimental"
callout.

## 8. Implementation staging

This prompt ships **design only**. The pieces below are sequenced for
later prompts, each small enough to review in isolation:

1. **Producer-path guarantee.** Audit every extractor and add an
   explicit `producer_path` accessor on `Relation` if any extractor
   currently produces a relation without an attributable source file.
   Tests cover every extractor. No CLI / MCP surface change.
2. **Change detector module.** New
   `src/repo_semantic_memory/incremental.py` (or similar) exposing a
   pure function `plan_incremental_update(repo_root, db_path) ->
   IncrementalPlan | FullRebuildRequired`. No DB writes; pure
   computation over inputs from §2.1. Heavily unit-tested.
3. **Executor.** Wire `plan_incremental_update` into `rsm index` behind
   the `--incremental` flag. Deletes + extractor scoping + dangling
   sweep + metadata refresh, all inside a single transaction.
4. **Docs.** Update `docs/usage/cli.md` and `README.md` once §7
   validation passes; remove the experimental callout.

Steps 2 and 3 are **gated** behind §7 validation. Step 1 is safe to land
on its own because it only tightens an existing extractor contract.

## 9. Open questions

- **Per-file extractor scoping.** Today's extractor pipeline takes a
  repo root and discovers files internally. Step 8.3 needs a clean way
  to constrain it to a path list without forking the pipeline.
  Candidate: pass an optional `paths_filter: set[Path] | None` through
  the existing entry points. Decision deferred to the implementation
  prompt; if the change is non-trivial, fall back to running each
  extractor on each changed file individually.
- **`last_index_mode` metadata row.** Whether to record incremental
  vs full mode in the metadata table. Default for this design: no.
  Revisit if §7 validation surfaces a need (e.g. easier debugging of
  drift bugs).
- **Safety threshold default.** §2.3 suggests "50% of indexed files".
  The exact constant is finalized during implementation against the
  benchmark repo; the design only requires *some* threshold.
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
Prompt 49.1 metadata model verbatim, never invents a second metadata
store, and falls back to a full rebuild whenever safety cannot be
proven. It is design-only in this prompt; implementation lands behind
an experimental flag in follow-up prompts, gated by the validation
matrix in §7.
