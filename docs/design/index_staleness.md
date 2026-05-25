# Index staleness detection design

This document specifies how RSM detects and reports whether the index it is
about to use is fresh, stale, missing, schema-mismatched, or unknown — without
auto-indexing by default.

It builds on the RSM Index Store introduced in Prompt 48 / 48.1
(`RSM_HOME`, central `registry.json`, `indexes/<repo_id>/index.sqlite`,
`rsm store` command group, `rsm index --register`, optional `--db` on
`rsm mcp serve`). See [`docs/usage/cli.md`](../usage/cli.md#rsm-index-store)
and [`docs/usage/mcp.md`](../usage/mcp.md) for the user-facing surface.

The goal of this prompt is **design only**. Implementation will follow in a
later prompt, with the exception of trivially small additions explicitly
called out in [§10](#10-implementation-staging).

## Non-goals

This design does **not**:

- Auto-index by default. Detection only reports; the user runs `rsm index`.
- Add a file watcher, daemon, or background service.
- Mutate the target repository.
- Change ranking, selection, or indexing semantics.
- Make any network call or remote Git call.
- Break existing explicit `--db` workflows.
- Assume the RSM Index Store is in use; explicit `--db` stays a first-class
  mode.
- Hide stale indexes from MCP clients. Stale must be a visible status, never
  silently auto-fixed.

## 1. Status states

`index_status` is one of:

| State              | Meaning                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| `fresh`            | Indexed Git HEAD matches current HEAD **and** the working tree has no relevant changes.                 |
| `missing`          | No index DB found for the selected mode (see [§1.1](#11-missing-substates)).                            |
| `stale`            | Indexed Git HEAD differs from current HEAD.                                                             |
| `maybe_stale`      | Working tree has modified/untracked relevant files, or relevant files are newer than `indexed_at`.      |
| `schema_mismatch`  | Index `schema_version` or `context_pack_version` does not match the runtime.                            |
| `unknown`          | No Git metadata, no index metadata, or insufficient metadata to classify.                               |

Precedence (highest wins, evaluated top-down):

1. `schema_mismatch`
2. `missing`
3. `stale`
4. `maybe_stale`
5. `unknown`
6. `fresh`

Rationale: a schema mismatch is unsafe regardless of staleness; a missing
file makes other checks moot; a HEAD difference is more decisive than a
dirty working tree; `unknown` is preferred over `fresh` when metadata is
incomplete (no silent false positives).

### 1.1 Missing substates

`missing` covers four distinct situations the user needs to disambiguate:

| Substate                       | Trigger                                                                              |
| ------------------------------ | ------------------------------------------------------------------------------------ |
| `missing.unregistered`         | Index Store mode, repo not in `registry.json`.                                       |
| `missing.registered_no_db`     | Index Store mode, repo registered but DB file does not exist.                        |
| `missing.explicit_db`          | Explicit `--db` mode, the provided path does not exist.                              |
| `missing.metadata_incomplete`  | DB exists, but required metadata rows are absent. Reported as `unknown`, not stale.  |

The first three are surfaced as the top-level `index_status: "missing"` with
a distinct `suggested_action`. The fourth maps to `unknown` because we have
a DB but cannot reason about it. These substates are *internal* to the
detector; the top-level status string remains one of the values in §1 so
clients keep a small enum.

## 2. Metadata model

### 2.1 Required per-index metadata

Per-index metadata is the source of truth for everything except the live
Git HEAD comparison. The detector reads:

```jsonc
{
  "indexed_at": "2026-05-25T00:10:16+00:00",
  "repo_root": "/absolute/path/to/repo",
  "repo_id": "a1b2c3d4e5f6a7b8",
  "git_head": "abc123...",         // HEAD at index time, or null
  "git_dirty": false,               // working tree dirty at index time, or null
  "schema_version": "...",
  "context_pack_version": "...",
  "package_version": "...",
  "entity_count": 0,
  "relation_count": 0,
  "indexed_paths_fingerprint": null // optional, see §2.3
}
```

`git_head` and `git_dirty` may be `null` when the repo is not a Git working
tree or when `git` was unavailable at index time. That is not an error;
it downgrades the result to `unknown` rather than `fresh`.

### 2.2 Where metadata lives

`SQLiteStore` already has a `metadata` key/value table that today carries
`schema_version`, `package_version`, `extractor_names`, `repository_root`,
and `timestamp` (see `src/repo_semantic_memory/store/sqlite_store.py`).
The remaining fields (`git_head`, `git_dirty`, `entity_count`,
`relation_count`, `context_pack_version`, `indexed_paths_fingerprint`) are
added as additional rows in the same `metadata` table, with stable string
values:

- `git_head` — full SHA string, or empty string when unavailable.
- `git_dirty` — `"true" | "false" | ""` (empty = unknown at index time).
- `indexed_at` — ISO 8601 UTC; replaces the current `timestamp` row
  semantically (kept under the new key; the old `timestamp` row stays for
  backward compatibility for one minor version).
- `entity_count`, `relation_count` — decimal strings.
- `context_pack_version` — string from `version.py`.
- `indexed_paths_fingerprint` — optional hex digest, see §2.3.

**Why SQLite and not a sidecar:**

- Works identically for explicit-repo-local DBs and for store-managed DBs.
- Survives `cp index.sqlite somewhere/else.sqlite`. A sidecar JSON does not.
- Atomic with the existing transactional persist path; no second write to
  reason about.
- The detector already has to open the SQLite to confirm it is a valid RSM
  DB; reading one extra metadata table costs nothing.

The Index Store `registry.json` keeps only `registered_at` and
`last_indexed_at`. It deliberately does **not** duplicate Git metadata,
because the source of truth for "what was this index built against" must
travel with the DB file.

### 2.3 `indexed_paths_fingerprint` (optional)

A deterministic SHA-256 over the sorted list of `(repo-relative path,
size, mtime)` for indexed source/doc files, captured at index time. It is
optional because:

- For most repos, `git_head` + working-tree-dirty + per-file mtime checks
  are sufficient.
- The fingerprint is an additional safety net for `--no-git` repos and
  for detecting changes to *tracked* files that did not move HEAD (e.g.
  the user re-checked-out the same commit but local mtimes changed).

When absent, the detector falls back to `git_head` and per-file mtime
checks only.

## 3. Detection inputs

All inputs are **local only**. No remote Git calls. No network.

| Input                           | Source                                                                           |
| ------------------------------- | -------------------------------------------------------------------------------- |
| Current Git HEAD                | `git rev-parse HEAD` via the existing bounded `_run_git` in `git_history.py`.    |
| Working tree dirty bit          | `git status --porcelain` via the existing extractor.                             |
| `git_head`, `git_dirty` at index time | Index `metadata` table.                                                    |
| `schema_version`                | Index `metadata` vs `version.SCHEMA_VERSION`.                                    |
| `context_pack_version`          | Index `metadata` vs `version.CONTEXT_PACK_VERSION`.                              |
| `indexed_at`                    | Index `metadata`.                                                                |
| Relevant file mtimes (optional) | `Path.stat()` on indexed paths, used to refine `maybe_stale`.                    |
| `indexed_paths_fingerprint`     | Index `metadata`, when present.                                                  |

"Relevant" files = files matching the same path-roles filter the indexer
used (source, test, doc; never `generated_artifact`). The detector calls
the existing `path_roles` helpers to keep this consistent with indexing.

The detector never re-parses sources, never re-indexes, and never touches
the DB except to read.

## 4. Detection policy

Default policy (phase 1):

1. Resolve the active index path (explicit `--db`, else Index Store lookup).
2. If no path resolves → `missing` (substate per §1.1).
3. Open the DB read-only; read the metadata table.
4. If `schema_version` or `context_pack_version` does not match runtime
   → `schema_mismatch`. Stop.
5. If `git_head` from metadata is missing, or the repo is not a Git working
   tree, and no `indexed_paths_fingerprint` is available → `unknown`.
6. If indexed `git_head` ≠ current `git_head` → `stale`.
7. If working tree is dirty (relevant files modified or untracked), **or**
   any relevant file `mtime > indexed_at`, **or** a fingerprint comparison
   diverges → `maybe_stale`.
8. Otherwise → `fresh`.

Steps 6–7 short-circuit; we do not "promote" `maybe_stale` to `stale`.

**Never auto-rebuild.** The detector returns a status and a
`suggested_action`. Running `rsm index` is always the user's choice.

Future optional policies (mentioned for design completeness only,
**not implemented**):

- `rsm mcp serve --auto-index missing` — opt-in build on first start.
- `rsm mcp serve --auto-index stale` — opt-in rebuild on HEAD divergence.
- `rsm index --incremental` — only re-extract files whose mtime changed
  since `indexed_at`.
- `rsm index --watch` — explicit, foreground, user-initiated watch mode.

These are out of scope for this prompt and must remain off-by-default if
implemented later.

## 5. MCP status output (`rsm_status`)

`rsm_status` currently returns repo/db/index counts and version info
(see `_tool_status` in `src/repo_semantic_memory/mcp/runtime.py`). The
design extends — not replaces — that payload with a stable
`index_status` block. Existing keys (`repo_root`, `db_path`, `db_exists`,
`package_version`, `schema_version`, `context_pack_version`, `read_only`,
`auto_index`, `tools`, `index_metadata`, `entity_count`, `relation_count`)
stay unchanged so existing clients keep working.

### 5.1 Added fields

```jsonc
{
  // ... existing rsm_status fields ...
  "index_status": "fresh",
  "indexed_at": "2026-05-25T00:10:16+00:00",
  "indexed_git_head": "abc123...",
  "current_git_head": "abc123...",
  "working_tree_dirty": false,
  "suggested_action": null,
  "index_mode": "store" | "explicit_db",
  "index_status_reason": "head_match_and_clean_tree"
}
```

- `index_status` — one of the values in §1.
- `indexed_git_head` — from the index metadata; `null` when absent.
- `current_git_head` — from a live bounded `git rev-parse HEAD`; `null`
  if not a Git repo.
- `working_tree_dirty` — `true | false | null` from a live bounded
  `git status --porcelain`.
- `indexed_at` — promoted to the top level for convenience even though it
  also appears in `index_metadata`.
- `suggested_action` — short human/CLI-runnable command string, or `null`
  when `index_status == "fresh"`. See §5.2.
- `index_mode` — which mode resolved the DB: `"explicit_db"` (user passed
  `--db`) or `"store"` (Index Store lookup succeeded). When the DB is
  missing in store mode, `index_mode` is still `"store"`.
- `index_status_reason` — short stable enum string ("head_match_and_clean_tree",
  "head_diff", "dirty_tree", "mtime_after_indexed_at", "schema_version_mismatch",
  "registry_missing_entry", "registered_db_missing", "explicit_db_missing",
  "no_git_metadata", "metadata_incomplete") used by tests and tooling.

### 5.2 `suggested_action` examples

Stale (Index Store mode):

```jsonc
{
  "index_status": "stale",
  "indexed_git_head": "abc123",
  "current_git_head": "def456",
  "working_tree_dirty": false,
  "suggested_action": "rsm index /path/to/repo --register"
}
```

Missing in Index Store mode, repo not registered:

```jsonc
{
  "index_status": "missing",
  "suggested_action": "rsm store register /path/to/repo --index"
}
```

Missing in Index Store mode, repo registered but DB gone:

```jsonc
{
  "index_status": "missing",
  "suggested_action": "rsm index /path/to/repo --register"
}
```

Missing in explicit `--db` mode:

```jsonc
{
  "index_status": "missing",
  "suggested_action": "rsm index /path/to/repo --db /path/to/index.sqlite"
}
```

Schema mismatch:

```jsonc
{
  "index_status": "schema_mismatch",
  "schema_version": "<runtime>",
  "indexed_schema_version": "<db>",
  "suggested_action": "rsm index /path/to/repo --register   # rebuild with current schema"
}
```

`suggested_action` is always a single line, free of shell metacharacters
from user input (the repo path is the user's own input), and always
respects which mode the user is in. We never suggest `--register` in
explicit `--db` mode unless the user already opted into the store, and we
never suggest a store command in explicit `--db` mode.

### 5.3 Other MCP handler impact

No other MCP tool changes its return shape. Tools continue to operate on
whatever index they were started with, regardless of `index_status`. The
status is purely informational; the *caller* (the agent) decides whether
to act on a stale or missing status by surfacing the suggested action.

## 6. CLI status command

### 6.1 Command shape

Add a small `rsm store status [REPO]` subcommand. Rationale for picking
`rsm store status` over `rsm status` or `rsm indexes status`:

- It groups with the other `rsm store ...` subcommands already documented
  in [`docs/usage/cli.md`](../usage/cli.md#store-commands).
- It is the smallest coherent addition: no new top-level verb, no
  collision with `rsm git summary` or `rsm components list`.
- It works in both modes: with a `--db` flag it inspects an explicit DB;
  without one it consults the Index Store.

The command takes a single optional positional `REPO` (defaulting to
`.`), plus the same `--db` and `--json` flags as the rest of the CLI:

```bash
uv run rsm store status                    # cwd, store-resolved
uv run rsm store status /path/to/repo      # explicit repo, store-resolved
uv run rsm store status /path/to/repo --db /path/to/index.sqlite
uv run rsm store status /path/to/repo --json
```

### 6.2 Human output

```text
Repo: /path/to/repo
Index: /home/user/.local/share/repo-semantic-memory/indexes/a1b2c3d4e5f6a7b8/index.sqlite
Mode: store
Status: stale
Indexed at: 2026-05-20T18:14:02+00:00
Indexed HEAD: abc123
Current HEAD: def456
Working tree dirty: no
Schema version: 7 (runtime: 7)
Context pack version: 3 (runtime: 3)
Entities: 1842
Relations: 4731
Suggested action: rsm index /path/to/repo --register
```

For `fresh`, the `Suggested action` line is omitted. For `missing`, the
DB line shows `Index: <none>` and HEAD/working-tree/schema lines are
omitted; only `Suggested action` is printed.

### 6.3 JSON output

```jsonc
{
  "repo": "/path/to/repo",
  "db": "/path/to/index.sqlite",
  "index_mode": "store",
  "index_status": "stale",
  "indexed_at": "2026-05-20T18:14:02+00:00",
  "indexed_git_head": "abc123",
  "current_git_head": "def456",
  "working_tree_dirty": false,
  "schema_version": "7",
  "indexed_schema_version": "7",
  "context_pack_version": "3",
  "indexed_context_pack_version": "3",
  "entity_count": 1842,
  "relation_count": 4731,
  "suggested_action": "rsm index /path/to/repo --register",
  "index_status_reason": "head_diff"
}
```

Keys are stable; missing values are `null`, not absent, so consumers can
write straight `obj["indexed_git_head"]` access. JSON output ordering is
not guaranteed; consumers MUST parse, not pattern-match.

### 6.4 Exit codes

| Status                                    | Exit |
| ----------------------------------------- | ---- |
| `fresh`                                   | `0`  |
| `maybe_stale`, `stale`, `unknown`         | `0`  |
| `missing` in any substate                 | `0`  |
| `schema_mismatch`                         | `0`  |
| Invalid arguments (bad repo, bad `--db`)  | `2`  |

`rsm store status` is informational; it never returns a non-zero exit for
a stale or missing index. Scripts that want to gate on freshness can read
the JSON and check `index_status == "fresh"` themselves. This keeps the
command safe in CI, agent loops, and `&&`-chained scripts.

## 7. Error and warning policy

| Situation                                              | Where surfaced       | Behavior                                                                         |
| ------------------------------------------------------ | -------------------- | -------------------------------------------------------------------------------- |
| `rsm mcp serve` with missing DB                        | startup              | Hard error, exit 2, stderr `error:` line. **Unchanged from Prompt 48.1.**         |
| `rsm mcp serve` with stale DB                          | `rsm_status`         | Server starts; status reports `stale` with a `suggested_action`.                  |
| `rsm mcp serve` with `schema_mismatch` (DB unreadable by runtime) | startup | **Hard error, exit 2**, stderr `error:` line. The current `SQLiteStore.initialize()` already raises on any `schema_version` divergence; that behavior is kept as the safe default. |
| `rsm mcp serve` with `schema_mismatch` (DB still readable, contextual metadata only) | `rsm_status` | The implementation *may* choose to start and surface `index_status: "schema_mismatch"` via `rsm_status` with a suggested rebuild action. The hard-error default remains acceptable. |
| `rsm mcp serve` with `unknown` status                  | `rsm_status`         | Server starts; status reports `unknown`.                                          |
| `rsm store status` for missing/stale/etc.              | CLI                  | Print status, exit 0.                                                             |
| `rsm store status` for invalid arguments               | CLI                  | Exit 2, stderr `error:` line.                                                     |
| `rsm pack`/`rsm repo-map` against stale DB             | CLI                  | Run normally. Print a single-line `warning:` to stderr identifying the stale status and suggested action. Do not fail. |
| `rsm pack`/`rsm repo-map` against `schema_mismatch` DB (unreadable) | CLI | **Hard error** (already raised by `SQLiteStore.initialize()`). No change. |
| `rsm pack`/`rsm repo-map` against `schema_mismatch` DB (contextual only) | CLI | Print a `warning:` to stderr; continue if the DB is safely readable. Hard error remains the acceptable default. |

### `schema_mismatch` error vs. warning distinction

The detector distinguishes two flavours of `schema_mismatch`:

1. **DB unreadable / structurally incompatible.** `SQLiteStore.initialize()`
   raises a `ValueError` because the stored `schema_version` does not match
   the runtime. This is a **hard error** in all contexts (`rsm mcp serve`,
   `rsm pack`, `rsm repo-map`, `rsm store status`). The safe default is to
   refuse to operate on an index whose entity/relation encoding may be
   incompatible.

2. **DB readable, contextual metadata divergence only.** If a future
   migration policy allows the runtime to open a DB that has an older
   `schema_version` (e.g. a forward-compatible additive change), the
   implementation *may* choose to start and report
   `index_status: "schema_mismatch"` via `rsm_status` / `rsm store status`
   instead of hard-erroring. The suggested action is always a rebuild.
   **The hard-error default remains acceptable;** this soft path is opt-in
   at the implementation level and requires an explicit compatibility
   annotation in `SQLiteStore`.

Until an explicit soft-compatibility path is implemented, all
`schema_mismatch` conditions are treated as hard errors. This keeps the
safety boundary simple and auditable.

The warning emitted by `rsm pack` / `rsm repo-map` against a *stale* DB is the smallest
behavioral nudge we add outside `rsm store status`. It is deliberately not
a fatal error so existing scripts keep working.

## 8. Behavior by mode

| Scenario                                              | `index_status`            | `index_mode`     | `suggested_action`                                              |
| ----------------------------------------------------- | ------------------------- | ---------------- | --------------------------------------------------------------- |
| Explicit `--db`, DB exists, HEAD matches, clean tree  | `fresh`                   | `explicit_db`    | `null`                                                          |
| Explicit `--db`, DB does not exist                    | `missing`                 | `explicit_db`    | `rsm index <repo> --db <path>`                                  |
| Explicit `--db`, DB exists, HEAD differs              | `stale`                   | `explicit_db`    | `rsm index <repo> --db <path>`                                  |
| Index Store, repo not in registry                     | `missing`                 | `store`          | `rsm store register <repo> --index`                             |
| Index Store, registered, DB file missing              | `missing`                 | `store`          | `rsm index <repo> --register`                                   |
| Index Store, registered, fresh                        | `fresh`                   | `store`          | `null`                                                          |
| Index Store, registered, stale                        | `stale`                   | `store`          | `rsm index <repo> --register`                                   |
| Any mode, schema mismatch                             | `schema_mismatch`         | per resolution   | `rsm index <repo> --register` or `--db <path>`                  |
| Any mode, not a Git repo, no fingerprint              | `unknown`                 | per resolution   | `null`                                                          |

The detector picks the suggestion that matches `index_mode`. It never
suggests opting into the store from an explicit-`--db` invocation, and it
never suggests an explicit DB path from a store-resolved invocation.

## 9. Validation plan

When this design is implemented, validation will be:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
```

Plus a focused test matrix per `index_status` × `index_mode`. Detection
must be deterministic: same inputs → same outputs, sorted keys in JSON.

## 10. Implementation staging

This prompt ships **design only**. The minimal-and-safe pieces that may
land alongside it are:

- Documentation: this file, plus links from `docs/usage/cli.md` and
  `docs/usage/mcp.md`.

Everything else — the metadata-table additions, the detector module,
`rsm store status`, the warning line on `rsm pack` / `rsm repo-map`, and
the extended `rsm_status` payload — lands in dedicated follow-up prompts
where each can be reviewed in isolation.

## 11. Open questions

- Should `indexed_paths_fingerprint` be required for `--no-git` repos,
  or stay strictly optional? Current design: optional, fall back to
  `unknown` when neither Git nor fingerprint is available.
- Do we want to expose a stable machine-readable `index_status_reason`
  enum? Current design: yes, see §5.1. The exact string set is finalized
  during implementation.
- Should `rsm store status` accept `--all` to print status for every
  registered repo at once? Likely yes, but deferred until the
  single-repo path is shipped.
