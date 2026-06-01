# RSM Indexing Performance Plan (Prompt 57)

Status: analysis and planning only. This document does **not** change behavior. It
profiles the current indexing architecture, identifies likely bottlenecks on very
large repositories (Home Assistant Core), and splits the remediation work into
staged `57.x` implementation prompts for a later implementation model.

Scope guardrails honored here: no chunk indexing, no embeddings, no ranking
changes, no context-pack changes, no Semble integration, no required network
access, no hidden auto-indexing.

---

## 1. Executive summary

RSM full indexing walks the repository **four separate times** and reads most
files **two-to-four times**, then runs a **global test-relationship pass that is
worst-case O(entities × test-entities)**. On a small repo this is invisible; on a
repo the size of Home Assistant Core (tens of thousands of Python files, a very
large `homeassistant/components/**` and matching `tests/components/**`) these
costs compound into a real performance cliff. There is **no way to scope or
down-shift** indexing today: every `rsm index` run is a full, deep extraction of
the entire tree with no `--include/--exclude`, no `--scope`, and no `--mode`.

**Verdict: there is a performance cliff, and it is architectural, not incidental.**
The single most damaging property is the combination of (a) no default scoping for
huge component trees and (b) a quadratic-leaning global test pass that consumes the
full entity set. Before optimizing anything, we must **measure**: the first
implementation prompt must be an observational phase profiler that confirms which
phase dominates on Home Assistant Core. Optimization (57.6) is explicitly gated on
that evidence.

Recommended sequencing: ship instrumentation first (57.1, 57.2), then the two
features that let users avoid the cliff entirely on big repos (scoped indexing
57.3/57.4 and fast mode 57.5), then evidence-driven optimization (57.6), then docs
(57.7).

---

## 2. Current indexing pipeline

Entry point: `_run_index_command` in `src/repo_semantic_memory/cli.py:739`.
The full (non-incremental) path executes these phases in order.

| # | Phase | Code | What it does |
|---|-------|------|--------------|
| 1 | File discovery + path filtering | `extract_filesystem_entities` (`extractors/filesystem.py:49`) | `os.walk` of the whole tree; per file: `should_index_repo_path`, `_is_binary_looking` (reads 8 KB), `_classify_kind`, `_build_entity` → `_line_count` (reads whole file) |
| 2 | Drop module file-entities | `_drop_python_module_file_entities` (`cli.py`) | Removes `module` file entities so the AST extractor can re-emit richer ones |
| 3 | Markdown extraction | `extract_markdown_outline_path` (`extractors/markdown_outline.py:46`) | **Second `os.walk`**; re-reads and parses every `.md`/`.markdown` |
| 4 | Python AST parsing | `index_python_path` (`extractors/python_ast.py:128`) | **Third `os.walk`** (`_iter_python_files`); re-reads + `ast.parse` every `.py`; emits module/class/function/method entities and `contains`/`imports`/`inherits` relations |
| 5 | Exports extraction | `index_python_exports` (`extractors/python_exports.py:133`) | **Fourth `os.walk`** (`_iter_init_files`); re-reads + `ast.parse` every `__init__.py`; emits `exports` relations |
| 6 | Merge | `_merge_entities` (`cli.py`) | Combines filesystem + markdown + python entities |
| 7 | Test relationship computation | `extract_test_relationships` (`extractors/test_relationships.py:114`) | Global pass over **all** entities/relations; builds source indexes then matches every test entity (see §3 for complexity) |
| 8 | Git summary (always) | `get_git_repository_summary` (`extractors/git_history.py:56`) | One bounded `git` subprocess for HEAD/dirty staleness metadata |
| 9 | Git per-entity metadata (opt-in `--with-git`) | `attach_git_metadata_to_entities` (`memory/temporal.py:33`) → `collect_git_file_metadata` | One git call per unique file path; only when `--with-git` is passed |
| 10 | Metadata build | `build_default_extraction_metadata` (`store/sqlite_store.py:433`) | Builds extractor-name / version metadata |
| 11 | SQLite write | `SQLiteStore.persist_index` (`store/sqlite_store.py:92`) | One transaction; `executemany` upsert of entities then relations |
| 12 | Staleness metadata write | `write_extra_metadata` (`store/sqlite_store.py:271`) | Writes `indexed_at`, `git_head`, `git_dirty`, counts, `last_index_mode="full"` |
| 13 | Index Store registry update (opt-in `--register`) | `IndexRegistry.register` (`store_home/`) | Records repo → db mapping |

The incremental path (`indexing/executor.py`, `store/sqlite_store.py:117`) reuses
the same extractors per changed file and re-runs the **global** test pass whenever
`tests` relations are invalidated.

---

## 3. Phase-by-phase complexity analysis

For each phase: cost class, repeated walks, repeated reads, global recomputation,
batched writes, parallelizability, and fast-mode skippability.

### Phase 1 — File discovery + path filtering (`extract_filesystem_entities`)
- Cost: O(files) for the walk; but **2 reads per file** (`_is_binary_looking`
  reads 8 KB; `_line_count` at `filesystem.py:101` reads the **entire** file).
- Walks tree: 1× (this is walk #1 of 4).
- `should_index_repo_path` re-resolves `repo_root` and re-derives the relative
  path per file (`filesystem.py:127`); cheap but redundant with the walk.
- Global recomputation: none. Row-by-row writes: n/a. Parallelizable: yes
  (per-file, embarrassingly parallel). Fast-mode skippable: no — file records are
  the minimum output, but `_line_count`'s full read can be skipped/streamed.

### Phase 3 — Markdown extraction (`extract_markdown_outline_path`)
- Cost: O(markdown files × file size). Walk #2. Re-reads every `.md`.
- Global recomputation: none. Parallelizable: yes. Fast-mode: keep headings only
  (already heading-only), but could be skipped or reduced; cheap on most repos.

### Phase 4 — Python AST parsing (`index_python_path`)
- Cost: O(python files × file size) for `read_text` + O(nodes) for `ast.parse`.
  AST parsing is the most CPU-expensive per-file operation. Walk #3.
- Re-reads each `.py` even though Phase 1 already opened it.
- `SyntaxError` files are silently skipped (`python_ast.py:162`).
- Global recomputation: none (per-file). Writes: n/a. Parallelizable: **yes, and
  this is the highest-value parallelization target** (CPU-bound, independent per
  file; a `ProcessPoolExecutor` would scale with cores). Fast-mode: emit only
  top-level classes/functions + imports, skip method bodies/decorator/signature
  metadata.

### Phase 5 — Exports extraction (`index_python_exports`)
- Cost: O(`__init__.py` files). Walk #4. Re-reads + re-parses every `__init__.py`
  that Phase 4 already parsed.
- Global recomputation: none. Parallelizable: yes. Fast-mode: keep (imports/exports
  are cheap and high-value), or fold into Phase 4 to avoid the re-parse.

### Phase 7 — Test relationship computation (`extract_test_relationships`)
- Builds `_SourceIndex` once: O(entities).
- Then iterates every test entity and matches:
  - `_import_based_relations`: O(imports per test) — cheap (dict lookups).
  - `_path_mapping_relations`: O(candidates by stem) — cheap.
  - `_class_name_relations`: exact match is cheap, but the **token-overlap
    fallback iterates all source classes** for each unmatched test class →
    O(test_classes × source_classes) (`test_relationships.py:286`).
  - `_function_name_relations`: **iterates `symbols_by_qname.values()` (all
    non-test symbols) for every test function** (`test_relationships.py:314`) →
    O(test_functions × all_symbols).
- Cost: worst-case **O(entities × test-entities)** — the only super-linear phase.
- Walks tree: no (operates in memory). Global recomputation: **yes, this is the
  global pass.** Parallelizable: partially (per-test matching), but the quadratic
  scans are the real problem. Fast-mode skippable: **yes** — drop deep test mapping
  in fast mode; keep only `direct_import` + `file_path` (both near-linear).

### Phase 11 — SQLite write (`persist_index`)
- Cost: O(entities + relations). Uses `executemany` → **batched, not row-by-row**
  (good). One transaction.
- Caveats: default journal mode and `synchronous` (no `PRAGMA journal_mode=WAL`,
  no `synchronous=NORMAL`, no `PRAGMA temp_store`); JSON is serialized per row via
  `json.dumps`. The incremental delete helpers use
  `json_extract(source_range_json,'$.path')` (`sqlite_store.py:253`) which is an
  **unindexed full-table scan** — only relevant to incremental, but worth noting.
- Parallelizable: no (single writer). Fast-mode: unchanged.

### Phases 8–9 — Git
- Phase 8 (summary): one subprocess, bounded — fine.
- Phase 9 (`--with-git`): `collect_git_file_metadata` over unique file paths; opt-in
  and off by default, so not a default-path bottleneck. Fast-mode: must remain off.

### Summary of structural waste
- **4 independent `os.walk` traversals** (phases 1, 3, 4, 5) where 1 would do.
- **Each Python file is opened ~3×** (binary sniff + line count in phase 1, then
  read in phase 4); each `__init__.py` ~4× (phases 1, 4, 5).
- **One super-linear phase** (phase 7) that also runs on every incremental update.

---

## 4. Large-repo failure mode: Home Assistant Core

Home Assistant Core characteristics and how each maps to a code path:

| HA Core property | Code path that scales badly |
|------------------|------------------------------|
| Tens of thousands of `homeassistant/components/**/*.py` | 4× `os.walk` (phases 1/3/4/5) + per-file AST `read_text`+`ast.parse` (phase 4, `python_ast.py:159`) |
| Matching `tests/components/**` test files | Inflates the test-entity set fed to phase 7's quadratic scans |
| Many integration subpackages, each with `__init__.py` | Phase 5 re-parses every `__init__.py` (`python_exports.py:161`) already parsed in phase 4 |
| Very large entity count (classes/functions/methods) | `symbols_by_qname` grows huge; `_function_name_relations` scans it per test function (`test_relationships.py:314`) |
| Very large relation count | Phase 11 serialization + write volume grows O(relations) |
| No default component scoping | `should_index_repo_path` only excludes caches/build dirs (`filesystem.py:15`), **not** `components/**`; everything is indexed |
| Full reads for line counts | `_line_count` reads every file fully (`filesystem.py:101`) on top of the AST read |

Net effect: even if every phase were perfectly linear, the **sheer file count**
(walked 4×, read 3×) plus the **quadratic phase 7** means HA Core indexing finishes
far slower than a competitor that does shallow or scoped extraction. This matches
the reported symptom: Copilot and Semble can start working before RSM finishes.

These are hypotheses tied to code paths, not benchmarks — which is exactly why
**57.1 (profiler) must land first** to confirm whether the dominant cost is the
walk, the AST parse, the test pass, or the SQLite write before any optimization.

---

## 5. Missing instrumentation

Current instrumentation is only coarse `time.monotonic()` deltas printed to stderr
per phase (`cli.py:771-931`). There is no structured, machine-readable profile and
no per-file/per-role breakdown. Missing metrics:

```
phase_name              elapsed_seconds         files_total
files_processed         files_skipped           files_per_second
entities_created        relations_created       entities_per_second
relations_per_second    bytes_processed         slowest_files
largest_files           counts_by_path_role     counts_by_extension
skip_reason_counts      sqlite_write_time       global_relation_time
```

None of these are emitted today; there is no way to answer "where did the time go
on HA Core?" without adding them.

---

## 6. Profiling design (first, observational only)

Constraints: **no behavior changes, no ranking/extraction changes, no new required
dependencies, stderr output, optional JSON report.** Use only the stdlib (`time`,
`json`, `dataclasses`, `os.stat` for sizes).

Design:
- A small `IndexProfiler` (new `indexing/profiler.py`) holding a list of
  `PhaseRecord` dataclasses (`phase_name`, `elapsed_seconds`, counters).
- `_run_index_command` wraps each existing phase with `profiler.phase(name)` and
  feeds it the already-computed counts (file counts, entity/relation deltas).
- Per-file size/time tracking is opt-in (the extractors would need to report
  per-file timing); the MVP can derive `bytes_processed` from `os.stat` during the
  existing walk and approximate `slowest_files`/`largest_files` from file sizes
  without changing extractor behavior.
- Output: a human summary to stderr (default) and, when `--profile-report PATH` is
  given, a deterministic JSON document with the §5 metrics.
- Gate everything behind a flag (e.g. `--profile`) so default output is unchanged.

This phase produces the evidence that decides whether 57.6 optimizes the walk, the
AST parse, or the test pass.

---

## 7. Scoped indexing design

### CLI surface
```
rsm index --include "<glob>" [--include ...]
rsm index --exclude "<glob>" [--exclude ...]
rsm index --scope <name>
rsm store register <repo> --index --include "<glob>" --exclude "<glob>"
```

### Semantics
- `--include`/`--exclude` accept repeatable POSIX globs evaluated against
  repo-relative paths. Excludes win over includes. Applied as an **additional
  filter inside `should_index_repo_path`** so all four current walks honor it
  consistently (single chokepoint already shared by filesystem/python/markdown via
  `_should_ignore_directory_name`/`_should_ignore_directory_path`).
- Pruning should happen at the **directory level during `os.walk`** (prune
  `dirnames[:]`) so excluded subtrees like `homeassistant/components/**` are never
  descended into — this is where the real speedup comes from, not just post-filter.

### Named scopes (`.rsm/index_scopes.yaml`)
```yaml
scopes:
  core:
    include:
      - "homeassistant/**/*.py"
      - "tests/**/*.py"
      - "*.md"
    exclude:
      - "homeassistant/components/**"
      - "tests/components/**"
      - ".git/**"
      - ".venv/**"
      - "__pycache__/**"
      - ".mypy_cache/**"
      - ".pytest_cache/**"
```
`--scope core` loads the named include/exclude lists from that file. Reading YAML
requires a parser; prefer reusing an existing dependency if one is already vendored
(the repo already ships `uv.lock`-managed deps) — otherwise fall back to a minimal
loader to honor the "no new required dependency" constraint. Confirm during 57.3.

### Risks
- **Scoped DB no longer represents the full repo.** Relations to excluded files are
  absent (e.g. an indexed core module that imports a component class produces an
  unresolved/dangling relation target).
- **Test pass distortion:** excluding `tests/components/**` changes which `tests`
  relations exist; scoped results must not be confused with full results.
- **Visibility:** MCP/status and context packs must surface that the index is
  scoped (see §9) so agents don't assume completeness.

---

## 8. Fast index mode design

### CLI surface
```
rsm index --mode fast | standard | deep
```
Default remains `standard` (current behavior, optimized).

### Semantics to evaluate
- **fast**: file records + top-level Python classes/functions + imports + markdown
  headings. **Skip**: exports re-parse merge (or fold into AST pass), the global
  test pass beyond `direct_import`/`file_path`, per-entity git metadata, and
  `_line_count` full reads (approximate from byte scan). Targets the cliff: removes
  the quadratic phase 7 scans and reduces AST metadata.
- **standard**: today's default behavior, with the redundant-walk/read fixes from
  57.6 applied. No semantic loss vs. today.
- **deep**: all expensive relation/test/doc passes (superset of standard); the home
  for any future heavier extraction (still **not** chunks).

### Interaction with scoping
Fast mode and scoping are orthogonal and composable: scoping reduces *how many*
files are processed; fast mode reduces *how much work per file* and removes the
global quadratic pass. On HA Core, the recommended default for usability is
`--scope core --mode standard`, with `--mode fast` as the "just give me something
now" escape hatch.

---

## 9. Metadata / status implications

Persist (via `write_extra_metadata`, alongside the existing `last_index_mode`):
```
last_index_mode  = fast | standard | deep | incremental | full
index_scope      = full | scoped
scope_name       = <optional named scope>
include_patterns = <optional, serialized list>
exclude_patterns = <optional, serialized list>
```
- `last_index_mode` already exists (`cli.py:896`, `executor.py:154`); extend its
  value set rather than adding a parallel key.
- Surface all of these in:
  - CLI status / `IndexStatusReport` (`index_status.py:55`) — add fields and print
    a clear "index is SCOPED (scope=core)" / "mode=fast" line.
  - MCP status output and context-pack warnings — a scoped or fast index **must**
    warn so agents know support files/tests may be missing (do not hide stale or
    scoped status from users; this is an explicit non-goal violation otherwise).

---

## 10. Implementation prompt sequence 57.x

Ordering rationale: measure before optimizing; ship user-facing escape hatches
(scope, fast mode) before deep optimization; optimization (57.6) is **gated on
57.1/57.2 evidence**.

### 57.1 — Add indexing phase profiler
- **Goal:** Observational, opt-in phase timing + counters to stderr; no behavior
  change.
- **Files:** `indexing/profiler.py` (new), `cli.py` (`_run_index_command`),
  possibly `indexing/executor.py` for parity.
- **Steps:** add `IndexProfiler`/`PhaseRecord`; wrap each phase; feed existing
  counts; gate behind `--profile`; print a summary table.
- **Tests:** profiler unit tests (records, ordering, determinism); a CLI test that
  `--profile` adds stderr output and does not change stdout/DB.
- **Validation:** `ruff format --check .`, `ruff check .`, `mypy src`, `pytest`.
- **Risks:** accidental stdout/contract changes. **Rollback:** remove flag + module;
  no schema change so DBs unaffected.

### 57.2 — Add JSON profiling report and slow-file report
- **Goal:** `--profile-report PATH` emits a deterministic JSON with §5 metrics incl.
  `slowest_files`/`largest_files`/`counts_by_path_role`/`skip_reason_counts`.
- **Files:** `indexing/profiler.py`, `cli.py`; small helper to read file sizes from
  the existing walk.
- **Steps:** extend profiler to aggregate per-extension/per-role counts and sizes;
  serialize sorted JSON; document the schema.
- **Tests:** golden JSON shape test (sorted keys, stable ordering); empty-repo case.
- **Validation:** same four commands.
- **Risks:** non-determinism in ordering. **Rollback:** drop the flag; profiler from
  57.1 still works.

### 57.3 — Add include/exclude scoped indexing
- **Goal:** `--include`/`--exclude` globs that prune walks at directory level and
  filter files, honored by all four extractors via `should_index_repo_path`.
- **Files:** `extractors/filesystem.py` (filter + walk pruning),
  `extractors/python_ast.py`, `extractors/python_exports.py`,
  `extractors/markdown_outline.py` (pass through the same filter), `cli.py` (args),
  `indexing/executor.py` (incremental parity).
- **Steps:** thread an optional `PathFilter` (compiled globs) through the shared
  ignore checks; prune `dirnames[:]` for fully-excluded subtrees; ensure excludes
  beat includes.
- **Tests:** filter unit tests (include/exclude precedence, dir pruning); parity
  tests that scoped full vs. incremental agree; a HA-like fixture excluding a
  `components/**` subtree.
- **Validation:** same four commands.
- **Risks:** inconsistent filtering across the four walks; dangling relations to
  excluded files. **Rollback:** ignore the new args (default = index everything).

### 57.4 — Add scope metadata and status reporting
- **Goal:** Persist + surface `index_scope`, `scope_name`, `include_patterns`,
  `exclude_patterns`; load named scopes from `.rsm/index_scopes.yaml`; warn when
  scoped.
- **Files:** `store/sqlite_store.py` metadata callers in `cli.py`/`executor.py`,
  `index_status.py`, MCP status, context-pack warning surface; new scope-config
  loader.
- **Steps:** write metadata rows; extend `IndexStatusReport`; add a scoped-index
  warning to MCP/status and context packs; load `--scope` from YAML.
- **Tests:** metadata round-trip; status shows scope; MCP/status warning present;
  scope-config parsing.
- **Validation:** same four commands.
- **Risks:** hidden scope state (must be visible). **Rollback:** stop writing the new
  rows; status falls back to current output.

### 57.5 — Add fast index mode
- **Goal:** `--mode fast|standard|deep`; fast skips the quadratic test pass tail,
  exports re-parse, per-entity git, and full line-count reads.
- **Files:** `cli.py` (arg + phase gating), `extractors/test_relationships.py`
  (mode-limited heuristics), `extractors/python_ast.py` (lighter metadata),
  `store/sqlite_store.py` metadata (`last_index_mode`), `index_status.py`.
- **Steps:** add mode enum; gate phases 5/7/9 and metadata richness by mode; record
  `last_index_mode`.
- **Tests:** fast vs. standard entity/relation differences are intentional and
  asserted; deep == superset of standard; status reports mode.
- **Validation:** same four commands.
- **Risks:** users misreading fast results as complete (mitigated by 57.4 warnings).
  **Rollback:** default `standard` = today's behavior.

### 57.6 — Optimize redundant walks and SQLite writes (gated on 57.1/57.2)
- **Goal:** Only if the profiler confirms it: collapse the 4 walks into 1, read each
  file once, and tune SQLite (`WAL`, `synchronous=NORMAL`, single-pass JSON).
- **Files:** `extractors/filesystem.py` (single walk yielding candidates + sizes),
  `extractors/python_ast.py`/`python_exports.py`/`markdown_outline.py` (consume a
  shared file list instead of re-walking), `cli.py` (orchestrate one walk),
  `store/sqlite_store.py` (PRAGMAs; consider an index for the incremental
  `json_extract` delete), optional `ProcessPoolExecutor` for AST parsing.
- **Steps:** introduce a shared discovery result; refactor extractors to accept an
  explicit file list; add PRAGMAs in a backward-compatible way; benchmark before/after
  with the 57.2 report.
- **Tests:** parity (identical entities/relations vs. pre-refactor on fixtures);
  determinism preserved; SQLite PRAGMA changes don't alter results.
- **Validation:** same four commands + before/after profile report on a large fixture.
- **Risks:** highest-risk prompt (touches all extractors); ordering/determinism
  regressions; parallelism nondeterminism. **Rollback:** revert to per-extractor
  walks; keep profiler in place.

### 57.7 — Add Home Assistant Core recommended scope docs
- **Goal:** Document scoped/fast indexing and ship the recommended HA `core` scope.
- **Files:** `docs/usage/cli.md`, possibly a sample `.rsm/index_scopes.yaml`, link
  from `docs/design/incremental_indexing.md`.
- **Steps:** document `--include/--exclude/--scope/--mode`, the scope file format,
  the scoped-index warnings, and the HA Core example.
- **Tests:** none (docs); verify any documented commands match real flags.
- **Validation:** docs only — no lint/build/test impact.
- **Risks:** docs drifting from flags. **Rollback:** revert doc.

---

## 11. Validation strategy

For every code-bearing prompt (57.1–57.6):
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
```
For 57.6 additionally capture a before/after `--profile-report` on a large fixture
(or a real HA Core checkout) to prove the optimization moved the dominant phase.
57.7 is docs-only and needs no lint/build/test run.

Key parity guarantee across 57.3/57.5/57.6: for an unscoped `standard` index, the
produced entities/relations must be **identical** to today's output (the existing
parity tests in `tests/indexing/` are the safety net).

---

## 12. Risks and non-goals

### Non-goals (explicit, from the prompt)
- No chunk indexing, no embeddings, no Semble integration.
- No ranking changes, no context-pack output changes (only added scope/mode warnings).
- No required network access, no hidden auto-indexing.
- This prompt implements **nothing**; it only plans.

### Cross-cutting risks
- **Scoped/fast indexes are incomplete by design.** They must always be labeled as
  such in CLI status, MCP status, and context packs. Hiding this would mislead agents.
- **Determinism is a hard requirement.** Any parallelism (57.6 AST pool) must sort
  outputs to preserve the existing deterministic ordering used throughout the
  extractors and store.
- **Optimization without measurement is forbidden.** 57.6 must not start until
  57.1/57.2 evidence identifies the dominant phase on a large repo.
- **YAML dependency:** named scopes need a parser; confirm an existing dependency
  can be reused before adding one (honor the no-new-required-dependency constraint).
