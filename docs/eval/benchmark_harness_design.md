# Benchmark Harness Design — 59.0

> **Status:** design-only, no implementation.
> **Date:** 2026-06-05.
> **Scope:** 59.0 design document for a repeatable, deterministic benchmark harness
> built on the existing RSM eval infrastructure.
>
> This document specifies the schema, metrics, runner contract, fixture strategy,
> CLI proposal, and migration plan. No production code, ranking behavior, or CLI
> implementation is changed in 59.0.

---

## 1. Benchmark case schema

### 1.1 Dataset file location

Benchmark datasets live under `benchmarks/`, consistent with the existing
`benchmarks/tasks.yaml` and `benchmarks/public_repos.yaml`. The format
described here is a **superset** of the current retrieval-task schema in
`src/repo_semantic_memory/eval/datasets.py` (`RetrievalTask` / `GoldTargets`).

The existing `benchmarks/tasks.yaml` remains the canonical CI dataset.
The harness adds new fields (`fixture`, `mode`, expanded `expected`,
`forbidden_files`, `tags`, `notes`) that the current `load_retrieval_dataset`
parser does not yet read. During 59.1+ implementation, the parser will be
extended to handle both the legacy and the enriched schema.

### 1.2 Required fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | Stable case identifier. Must be unique within a dataset. |
| `fixture` | `string` | yes | Fixture or repo label (e.g. `simple_repo`, `ranking_repo`, `httpx`). |
| `query` | `string` | yes | Natural-language task prompt fed to `build_context_pack`. |
| `expected.central_files` | `list[string]` | yes | Files expected to be selected as central hits. At least one entry. |
| `expected.support_files` | `list[string]` | yes | Files expected to be selected as support/adjacency. May be empty. |
| `expected.test_files` | `list[string]` | yes | Test files expected to be selected. May be empty. |
| `expected.forbidden_files` | `list[string]` | yes | Files that must NOT be selected (noise). May be empty. |
| `tags` | `list[string]` | yes | Categorization tags (e.g. `ranking_v2`, `regression`, `ci`). May be empty. |
| `notes` | `string` | yes | Rationale, expected behavior, provenance. Free-text. |
| `mode` | `enum` | yes | `ci_fixture` or `manual_external`. |

### 1.3 Design constraints

- **Paths are POSIX-style and repo-relative.** Backslash separators are rejected
  at parse time (same invariant as `_validate_gold_file_path` in the existing
  dataset parser).
- **Case IDs are stable.** An ID change is a breaking schema change.
- **Output ordering is deterministic.** All lists are sorted lexicographically
  at emission time.
- **`expected.central_files` is required.** A case without at least one central
  file is invalid.
- **Empty lists must be explicit.** `support_files: []`, not absent.
- **No network access for `mode: ci_fixture`.** All CI cases must resolve against
  local checked-in fixtures.
- **No automatic download of public repos.** `mode: manual_external` cases
  require explicit local paths or environment variables (already defined in
  `benchmarks/public_repos.yaml`).

### 1.4 YAML example

```yaml
tasks:
  - id: django_url_resolution
    fixture: django
    mode: manual_external
    query: >
      Find how Django resolves URL patterns into view execution, including
      resolver implementation files and relevant tests.
    expected:
      central_files:
        - django/urls/resolvers.py
        - django/urls/conf.py
        - django/core/handlers/base.py
      support_files:
        - django/urls/base.py
        - django/urls/exceptions.py
      test_files:
        - tests/urlpatterns/test_resolvers.py
      forbidden_files:
        - django/db/backends/base/features.py
        - django/contrib/staticfiles/utils.py
        - django/template/defaultfilters.py
        - django/core/files/storage/base.py
        - django/core/files/storage/memory.py
        - django/core/files/storage/filesystem.py
        - django/db/models/fields/files.py
        - django/utils/feedgenerator.py
        - django/templatetags/static.py
    tags:
      - ranking_v2
      - regression
      - public_repo_manual
      - 58.6_migration
    notes: >
      Migrated from docs/reviews/ranking_v2_regression_eval.md Task 1.
      Central files: resolvers.py (correct), conf.py and handlers/base.py (missing
      in 58.6, now expected). Support: base.py, exceptions.py. Tests:
      test_resolvers.py. Forbidden: 12+ .url method noise files from storage,
      feeds, templates, auth.
```

### 1.5 Relationship to existing `RetrievalTask`

The existing `src/repo_semantic_memory/eval/datasets.py` defines:

```python
@dataclass(frozen=True)
class RetrievalTask:
    id: str
    category: str
    prompt: str
    gold: GoldTargets

@dataclass(frozen=True)
class GoldTargets:
    files: tuple[str, ...]
    symbols: tuple[str, ...]
    invariants: tuple[str, ...]
```

The 59.0 schema **extends** this model:

- `category` → subsumed by `tags` (more flexible, multiple tags per case).
- `prompt` → renamed `query` for clarity.
- `gold.files` → split into `expected.central_files`, `expected.support_files`,
  `expected.test_files`.
- `forbidden_files` → new field, no equivalent in current schema.
- `fixture`, `mode`, `notes` → new fields.

Implementation (59.1+) must support **both** schemas: legacy tasks use a
compatibility path where all gold files are treated as `central_files` and
`forbidden_files` is empty.

---

## 2. Metrics

### 2.1 Core metrics

All metrics are computed per benchmark case, then aggregated across cases.

| Metric | Internal range | Calculation |
|--------|---------------|-------------|
| `central_file_found` | `0.0` or `1.0` | `1.0` if at least one expected central file is selected, else `0.0`. |
| `support_files_found` | `[0.0, 1.0]` | `count(selected ∩ expected.support_files) / len(expected.support_files)`. Returns `1.0` when `support_files` is empty (vacuous truth). |
| `tests_found` | `[0.0, 1.0]` | `count(selected ∩ expected.test_files) / len(expected.test_files)`. Returns `1.0` when `test_files` is empty. |
| `noise_reduced` | `[0.0, 1.0]` | `1.0 - min(1.0, count(selected ∩ expected.forbidden_files) / max(1, len(expected.forbidden_files)))`. Returns `1.0` when `forbidden_files` is empty. |
| `overall` | `[0.0, 1.0]` | Weighted aggregate (see §2.2). |

### 2.2 Weighted aggregate

```
overall = 0.35 * central_file_found
        + 0.25 * support_files_found
        + 0.20 * tests_found
        + 0.20 * noise_reduced
```

Weights are design-time constants. The `central_file_found` weight (0.35) is
highest because a missing central file makes the pack unusable regardless of
other scores. If evidence from real benchmark runs shows these weights produce
counterintuitive rankings, they may be adjusted in a future design revision.

### 2.3 58.6-compatible report projection

For human-readable reports that match the 58.6 / 58.7 review language, each
internal `[0.0, 1.0]` score is projected to a 1–5 scale:

| Internal score | Projected 1–5 |
|---------------|---------------|
| `[0.00, 0.20)` | 1 |
| `[0.20, 0.40)` | 2 |
| `[0.40, 0.60)` | 3 |
| `[0.60, 0.80)` | 4 |
| `[0.80, 1.00]` | 5 |

Report column names use the 58.6 vocabulary:

| Internal metric | Report column |
|-----------------|---------------|
| `central_file_found` | `central_file` |
| `support_files_found` | `support_files` |
| `tests_found` | `tests` |
| `noise_reduced` | `noise_reduced` |
| `overall` | `overall` |

Example report row (matching 58.6 style):

```
| Django URL resolution | 5/5 | 4/5 | 3/5 | 3/5 | 4/5 |
```

### 2.4 Machine-readable output

JSON output uses internal `[0.0, 1.0]` scores with full precision:

```json
{
  "case_id": "django_url_resolution",
  "central_file_found": 1.0,
  "support_files_found": 0.75,
  "tests_found": 0.6,
  "noise_reduced": 0.66,
  "overall": 0.73,
  "selected_files": ["django/urls/resolvers.py", "django/urls/conf.py", "..."],
  "missing_central": [],
  "missing_support": ["django/urls/exceptions.py"],
  "missing_tests": [],
  "forbidden_selected": ["django/core/files/storage/base.py"]
}
```

---

## 3. Runner contract

### 3.1 Entry point

```python
def run_benchmark(
    *,
    db_path: Path | str,
    dataset_path: Path | str,
    mode: Literal["ci", "manual"] = "ci",
    case_filter: tuple[str, ...] = (),
    budget_chars: int = 32000,
    profile: str = "agent_standard",
) -> BenchmarkResult:
```

### 3.2 Execution flow

```
1. Load dataset cases from dataset_path.
   - Validate schema (reject missing required fields, non-POSIX paths).
   - Filter by case_filter if non-empty.
   - Exclude manual_external cases when mode="ci".

2. For each case:
   a. Build context pack via build_context_pack(
          task=case.query,
          entities=entities,
          relations=relations,
          budget_chars=budget_chars,
          profile=profile,
      ).
   b. Extract selected files (see §3.3).
   c. Compare selected files against expected and forbidden sets.
   d. Compute per-case metrics (§2.1).

3. Compute aggregate metrics across all cases.

4. Emit human-readable report (stdout or --markdown-report).

5. Emit machine-readable JSON (if --json).
```

### 3.3 Selected file extraction

Files are extracted from the context pack in this priority order:

1. **`suggested_files_to_inspect`** — if the pack has this field and it is
   non-empty, use it directly. This is the preferred source because it
   represents the pack's own recommendation of which files to inspect.

2. **`selected_entities` source_path fallback** — if `suggested_files_to_inspect`
   is absent or empty, extract `source_range.path` from every entity in
   `selected_entities`.

3. **Deterministic deduplication** — deduplicate by `source_path`, keeping the
   first occurrence (preserving selection order). The result is a
   `tuple[str, ...]` of unique repo-relative POSIX paths.

### 3.4 Determinism guarantees

- All lists are sorted lexicographically before emission.
- Entity/relation ordering from the store is stable (sorted by `id.value`).
- Budget, profile, and all `build_context_pack` parameters are fixed per run.
- No random seeds, no network access, no wall-clock-dependent behavior.
- Two runs with the same `db_path`, `dataset_path`, and parameters produce
  identical JSON output.

### 3.5 Error handling

| Condition | Behavior |
|-----------|----------|
| Dataset file not found | Exit code 2, message to stderr. |
| Dataset contains no tasks | Exit code 2, message to stderr (same as existing `eval retrieval`). |
| Schema validation failure | Exit code 2, message to stderr with field path. |
| `mode=ci` but case has `mode: manual_external` | Skip case, count in `skipped_manual` summary. |
| `case_filter` matches no cases | Exit code 0, report with 0 tasks. |
| DB not found or unreadable | Exit code 2, message to stderr. |
| `central_files` empty in a case | Validation error at load time (exit 2). |

### 3.6 Result data model

```python
@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    fixture: str
    mode: str
    central_file_found: float
    support_files_found: float
    tests_found: float
    noise_reduced: float
    overall: float
    selected_files: tuple[str, ...]
    missing_central: tuple[str, ...]
    missing_support: tuple[str, ...]
    missing_tests: tuple[str, ...]
    forbidden_selected: tuple[str, ...]

@dataclass(frozen=True)
class BenchmarkResult:
    dataset_path: str
    db_path: str
    budget_chars: int
    profile: str
    run_mode: str  # "ci" or "manual"
    cases_run: int
    cases_skipped_manual: int
    outcomes: tuple[CaseOutcome, ...]
    aggregate: AggregateBenchmarkMetrics
```

---

## 4. Fixture strategy

### 4.1 CI mode (`--mode ci`, default)

CI benchmarks use **only local deterministic fixtures** checked into the
repository. No external repos, no network access, no environment variables
beyond what the test runner already provides.

Current available fixtures:

| Fixture label | Path | Contents |
|---------------|------|----------|
| `simple_repo` | `tests/fixtures/simple_repo/` | Small Python repo with `src/`, `config/`, `docs/`. Used by existing CLI tests. |
| `ranking_repo` | `tests/fixtures/ranking_repo/` | Multi-package repo with `src/lifecore_ros2/`, `lifecore_state/`, `docs/`, `examples/`, `tests/`. Used by ranking regression tests. |

CI cases are indexed on-the-fly with `rsm index --db <tmp_path>` or reuse a
pre-built in-memory entity pool (consistent with how
`tests/context/test_ranking_v2_regression.py` builds synthetic entities).

### 4.2 Manual mode (`--mode manual`)

Manual benchmarks use external public repos referenced in
`benchmarks/public_repos.yaml`. Each external repo declares a `checkout.path_env`
environment variable. The harness resolves the repo path from that variable;
if the variable is unset or the path does not exist, the case is skipped with
a clear message.

No automatic cloning. The user is responsible for:

```bash
git clone https://github.com/encode/httpx /path/to/httpx --branch <ref>
export RSM_BENCH_HTTPX_PATH=/path/to/httpx
rsm index /path/to/httpx --db .rsm/httpx.sqlite
rsm eval bench --dataset benchmarks/tasks.yaml --mode manual --db .rsm/httpx.sqlite
```

### 4.3 Mode gating in dataset

Cases with `mode: manual_external` are skipped when the runner is invoked with
`--mode ci`. This is enforced at the runner level, not the dataset level:
the dataset may contain both CI and manual cases, and the runner filters based
on the runtime mode flag.

---

## 5. CLI/API proposal

### 5.1 Recommended command

```
rsm eval bench --dataset <path> [options]
```

### 5.2 Rationale

The repo already has `rsm eval retrieval` and `rsm eval compare`. Placing the
benchmark harness under `rsm eval` keeps the CLI surface coherent:

```
rsm eval
  ├── retrieval    (existing)
  ├── compare      (existing)
  └── bench        (proposed, 59.1+)
```

A separate top-level `rsm bench` would fragment the eval namespace and imply
a different subsystem when the harness reuses the same index store, the same
context-pack builder, and the same eval metrics module.

### 5.3 Options

| Option | Required | Description |
|--------|----------|-------------|
| `--dataset` | yes | Path to YAML benchmark dataset. |
| `--db` | no | SQLite database path. When omitted, resolved from RSM Index Store registry. Same semantics as `eval retrieval --db`. |
| `--json` | no | Emit machine-readable JSON to stdout. |
| `--case` | no | Run only the named case(s). Repeatable. |
| `--mode` | no | `ci` (default) or `manual`. Controls whether `manual_external` cases are run. |
| `--markdown-report` | no | Write a Markdown report to this path. |
| `--budget` | no | Character budget for context packs. Default: `32000` (matching 58.6 evaluation parameters). |
| `--profile` | no | Compression profile. Default: `agent_standard`. |

### 5.4 Example invocations

```bash
# CI: local fixtures only
rsm eval bench --dataset benchmarks/tasks.yaml --db .rsm/index.sqlite

# CI: single case
rsm eval bench --dataset benchmarks/tasks.yaml --case django_url_resolution --mode ci

# CI: JSON output
rsm eval bench --dataset benchmarks/tasks.yaml --json

# Manual: external repos (requires pre-built DBs and env vars)
rsm eval bench --dataset benchmarks/tasks.yaml --mode manual --json

# Manual: with Markdown report
rsm eval bench --dataset benchmarks/tasks.yaml --mode manual --markdown-report docs/reviews/benchmark_report.md
```

### 5.5 CLI integration point

In `src/repo_semantic_memory/cli.py`, the new subcommand is added under the
existing `eval` subparser (line ~363):

```python
eval_bench_parser = eval_subparsers.add_parser(
    "bench",
    help="Run deterministic benchmark harness over context-pack selection quality.",
)
```

Implementation deferred to 59.1+.

---

## 6. Migration from Ranking v2 reports

### 6.1 Source documents

- `docs/reviews/ranking_v2_regression_eval.md` — four-task manual evaluation
  (Django, Ansible, HTTPX, Typer) with per-task scores, noise analysis, and
  root-cause diagnosis.
- `docs/reviews/ranking_v2_plan.md` — Ranking v2 design (prompts 58.0–58.7),
  failure taxonomy, and architecture.

### 6.2 Migration mapping

Each of the four tasks becomes one structured benchmark case. The mapping is
intentional and auditable: every expected and forbidden file traces back to a
specific table row in the 58.6 report.

#### Case 1: Django URL resolution

| Field | Value |
|-------|-------|
| `id` | `django_url_resolution` |
| `fixture` | `django` |
| `mode` | `manual_external` |
| `query` | `"Find how Django resolves URL patterns into view execution, including resolver implementation files and relevant tests."` |
| `expected.central_files` | `django/urls/resolvers.py`, `django/urls/conf.py`, `django/core/handlers/base.py` |
| `expected.support_files` | `django/urls/base.py`, `django/urls/exceptions.py`, `django/core/checks/urls.py` |
| `expected.test_files` | `tests/urlpatterns/test_resolvers.py` |
| `expected.forbidden_files` | 12 `.url` method noise files (see report §Task 1 "Remaining noise" table) |
| `tags` | `ranking_v2`, `regression`, `public_repo_manual`, `58.6_migration` |
| `notes` | "58.6: central 4/5 (resolvers.py correct; conf.py and handlers/base.py absent). support 3/5 (exceptions.py, base.py present; many noisy .url method files). tests 3/5. noise 2/5 (12+ .url entities). overall 3/5. 58.7 cleanup (7B–7E) partially addressed .url noise and compact preview caps." |

**Source in 58.6 report:** Task 1 tables "Selected central files", "Missing central files", "Selected test files", "Remaining noise", and score summary.

#### Case 2: Ansible plugin/module discovery

| Field | Value |
|-------|-------|
| `id` | `ansible_loader_discovery` |
| `fixture` | `ansible` |
| `mode` | `manual_external` |
| `query` | `"Find how Ansible discovers and loads modules/plugins, including loader implementation files and relevant tests."` |
| `expected.central_files` | `lib/ansible/plugins/loader.py`, `lib/ansible/utils/collection_loader/_collection_finder.py` |
| `expected.support_files` | `lib/ansible/_internal/_yaml/_loader.py`, `lib/ansible/module_utils/_internal/_ansiballz/_loader.py` |
| `expected.test_files` | `test/units/plugins/test_plugins.py` |
| `expected.forbidden_files` | `test/lib/ansible_test/_internal/cgroup.py`, `lib/ansible/playbook/block.py`, `lib/ansible/playbook/task.py`, `lib/ansible/playbook/role/__init__.py` |
| `tags` | `ranking_v2`, `regression`, `public_repo_manual`, `58.6_migration` |
| `notes` | "58.6: central 5/5 (loader.py and _collection_finder.py top-ranked). support 4/5 (internal loaders present; playbook set_loader marginal). tests 1/5 (test_plugins.py absent; cgroup FP only test-path entity). noise 3/5 (cgroup FP significant but isolated). overall 3/5. 58.7D added domain-stem fallback for test branch." |

**Source in 58.6 report:** Task 2 tables "Selected central files", "Missing central files", "Selected test files", "Remaining noise", and score summary.

#### Case 3: HTTPX public client API

| Field | Value |
|-------|-------|
| `id` | `httpx_public_client_api` |
| `fixture` | `httpx` |
| `mode` | `manual_external` |
| `query` | `"Find the public API for making HTTP requests with sync and async clients and where those clients are implemented."` |
| `expected.central_files` | `httpx/__init__.py`, `httpx/_api.py`, `httpx/_client.py` |
| `expected.support_files` | `httpx/_transports/default.py`, `httpx/_transports/base.py`, `httpx/_transports/__init__.py`, `httpx/_exceptions.py`, `httpx/_types.py` |
| `expected.test_files` | *(none indexed in 58.6; add if indexed later)* |
| `expected.forbidden_files` | `httpx/_main.py` |
| `tags` | `ranking_v2`, `regression`, `public_repo_manual`, `58.6_migration` |
| `notes` | "58.6: central 5/5 (all public-facing files present). support 5/5 (exceptions, types, transports, docs correct). tests 1/5 (no test files selected). noise 4/5 (only _main.py noise). overall 4/5 — best result of the four. 58.7C reduced docs/tutorial noise for implementation queries." |

**Source in 58.6 report:** Task 3 tables "Selected central files", "Missing central files" (none), "Selected test files" (none), "Remaining noise", and score summary.

#### Case 4: Typer command registration

| Field | Value |
|-------|-------|
| `id` | `typer_command_registration` |
| `fixture` | `typer` |
| `mode` | `manual_external` |
| `query` | `"Find how Typer turns @app.command() and @app.callback() declarations into executable Click commands, including the implementation files and core tests."` |
| `expected.central_files` | `typer/core.py`, `typer/main.py` |
| `expected.support_files` | `typer/_click/core.py` *(vendor; relevant but capped)* |
| `expected.test_files` | `tests/test_core.py` |
| `expected.forbidden_files` | `docs_src/commands/callback/tutorial002_py310.py`, `docs_src/commands/callback/tutorial003_py310.py`, `docs_src/commands/callback/tutorial004_py310.py`, `docs_src/commands/one_or_multiple/tutorial001_py310.py`, `docs_src/commands/one_or_multiple/tutorial002_py310.py`, `typer/cli.py` |
| `tags` | `ranking_v2`, `regression`, `public_repo_manual`, `58.6_migration` |
| `notes` | "58.6: central 4/5 (core.py and _click/core.py correct; main.py at rank 36). support 3/5 (cli.py marginal; vendor file dominates compact preview). tests 1/5 (no test files; Typer tests not indexed). noise 2/5 (5 docs_src/ tutorial files in top 40; vendor file crowds view). overall 3/5. 58.7C reduced docs_src/ noise; 58.7E capped per-file entities in compact preview." |

**Source in 58.6 report:** Task 4 tables "Selected central files", "Missing central files", "Selected test files" (none), "Remaining noise", and score summary.

### 6.3 Migration principles

1. **Every expected file traces to an explicit row in the 58.6 report.**
   No file is added to a case without provenance.
2. **Missing-central files from 58.6 become expected central files.**
   The harness measures whether post-58.7 ranking now retrieves them.
3. **Noise files from 58.6 "Remaining noise" tables become forbidden files.**
   The harness measures whether post-58.7 ranking now suppresses them.
4. **Notes copy the 58.6 score summary and root-cause diagnosis verbatim**
   for auditability.
5. **Tags include `58.6_migration`** so the provenance of every migrated case
   is machine-readable.

---

## 7. Non-goals

The following are **explicitly out of scope** for 59.0 and for the benchmark
harness in general:

| Non-goal | Rationale |
|----------|-----------|
| Chunks | Not yet part of RSM's retrieval model. |
| Embeddings | Not yet part of RSM's retrieval model. |
| Semble backend | Separate project; no integration surface defined. |
| CodeGraph backend | Separate project; no integration surface defined. |
| Backend abstraction | Premature; benchmark against current `build_context_pack` only. |
| Context graph export | Out of scope for selection-quality benchmarking. |
| GUI or web dashboard | CLI-only; machine-readable JSON is the integration surface. |
| Automatic external repo download | Manual-only by design; user controls repo checkout and indexing. |
| Scoring retune | The harness measures the current ranking; it does not change weights. |
| Ranking changes | 59.0 is measurement infrastructure, not ranking improvement. |
| LLM-based judging | All metrics are deterministic set operations. |

---

## 8. Implementation sequence

### 59.0 (current)
- [x] Design document (`docs/eval/benchmark_harness_design.md`).

### 59.1 (proposed next)
- Extend `src/repo_semantic_memory/eval/datasets.py` to parse the enriched
  benchmark schema (backward-compatible with existing `RetrievalTask`).
- Add `CaseOutcome` and `BenchmarkResult` dataclasses to
  `src/repo_semantic_memory/eval/runner.py`.
- Implement `run_benchmark()`.

### 59.2 (proposed)
- Add `rsm eval bench` subcommand to `src/repo_semantic_memory/cli.py`.
- Add CLI integration tests in `tests/test_cli.py`.

### 59.3 (proposed)
- Write the four migrated benchmark cases to `benchmarks/tasks.yaml` (or a
  separate `benchmarks/ranking_v2_regression.yaml`).
- Add schema validation tests in `tests/eval/`.

### 59.4+ (proposed)
- Run manual benchmarks against Django, Ansible, HTTPX, Typer.
- Compare 58.6 report scores against harness-computed scores.
- Tune weights if evidence shows counterintuitive rankings.
- Expand CI fixture cases.

---

## Appendix A: Schema validation rules

```
1. id: non-empty string, unique within dataset.
2. fixture: non-empty string.
3. query: non-empty string.
4. expected: mapping with exactly four keys:
   - central_files: list of strings, at least one element.
   - support_files: list of strings, may be empty.
   - test_files: list of strings, may be empty.
   - forbidden_files: list of strings, may be empty.
5. All file paths: POSIX separators only, no leading slash, no "./" prefix.
6. tags: list of strings, may be empty.
7. notes: non-empty string.
8. mode: one of "ci_fixture" or "manual_external".
```

## Appendix B: Determinism checklist

```
☐ Same db_path + same dataset_path → identical JSON output.
☐ Entity/relation ordering from SQLite is stable (ORDER BY id).
☐ File lists sorted lexicographically before comparison.
☐ Floating-point operations use deterministic order (no map/reduce parallelism).
☐ No wall-clock timestamps in output.
☐ No random seeds.
☐ No network access.
☐ No filesystem state beyond db_path and dataset_path.
```
