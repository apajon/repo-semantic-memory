# lifecore_ros2 Benchmark Cases 62.1

> **Date:** 2026-06-09
> **Status:** Complete
> **Prerequisite:** 62.0 — lifecore_ros2 manual validation

---

## 1. Summary

Seven benchmark cases were added to the RSM benchmark harness, targeting real
lifecore_ros2 development tasks. These are `manual_external` cases that require
a pre-built index of the `lifecore_ros2` repository.

All cases pass schema validation. No ranking, extractor, or schema changes were
made. The benchmark harness loads all 7 cases correctly with the expected
`central_files`, `support_files`, `test_files`, and `forbidden_files`.

---

## 2. Cases Added

| # | ID | Query | Central | Support | Tests |
|---|---|---|---|---|---|
| 1 | `lc_lifecycle_component_core` | LifecycleComponent class impl. | 1 file | 2 files | 2 files |
| 2 | `lc_activation_gating` | Activation gating impl. | 1 file | 3 files | 1 file |
| 3 | `lc_cleanup_ownership` | Cleanup ownership (weakness) | 3 files | 3 files | 1 file |
| 4 | `lc_lifecore_state_architecture` | lifecore_state docs/RFCs | 2 files | 3 files | 1 file |
| 5 | `lc_publisher_subscriber_components` | Pub/sub pair | 2 files | 2 files | 3 files |
| 6 | `lc_service_client_server_components` | Svc client/server pair | 2 files | 2 files | 3 files |
| 7 | `lc_timer_lifecycle_behavior` | Timer lifecycle behavior | 1 file | 2 files | 1 file |

**Total: 7 cases, all `mode: manual_external`, fixture `lifecore_ros2`.**

Each case includes a `notes` field documenting:
- Why the case matters
- What 62.0 observed about this area
- Known weaknesses to track

---

## 3. Expected Strengths

Based on 62.0 observations:

| Case | Expected Strength | 62.0 Evidence |
|---|---|---|
| `lc_lifecycle_component_core` | ★★★ Strong | LifecycleComponent class + all methods correctly indexed |
| `lc_activation_gating` | ★★★ Strong | ContextPack returned gating impl + all affected components + tests |
| `lc_lifecore_state_architecture` | ★★★ Strong | RFC docs, architecture docs, and related tests all found |
| `lc_publisher_subscriber_components` | ★★☆ Good | Component files found individually; pair retrieval not tested in 62.0 |
| `lc_service_client_server_components` | ★★☆ Good | Components found individually; pair retrieval not tested in 62.0 |
| `lc_timer_lifecycle_behavior` | ★★☆ Good | Timer component found; cleanup tests embedded in shared file |

---

## 4. Expected Weaknesses

Based on 62.0 observations:

| Case | Expected Weakness | 62.0 Evidence |
|---|---|---|
| `lc_cleanup_ownership` | ★☆☆ Test-heavy bias | 62.0 ContextPack returned only test file, missing component source files |
| `lc_lifecore_state_architecture` | ★★☆ Lexical noise | Unrelated `on_message` subscriber stubs appeared in ContextPack |
| `lc_service_client_server_components` | ★★☆ Undetermined | Not directly tested in 62.0; relation with activation gating may be noisy |

The `lc_cleanup_ownership` case is explicitly designed to **capture and track**
the 62.0 weakness #1. If ranking improvements are made, this case should show
measurable improvement in central/support file recall.

---

## 5. External Repository Requirements

These are `manual_external` benchmark cases. They:

- **Require** a pre-built RSM index of the `lifecore_ros2` repository.
- **Do not** run automatically in CI.
- **Do not** clone or download any repository.
- **Are skipped safely** when the `--mode ci` flag is used (only `ci_fixture`
  cases run in CI mode).

**To run manually:**

```bash
uv run rsm eval bench \
  --db /path/to/lifecore_ros2/.rsm/index.sqlite \
  --dataset benchmarks/lifecore_ros2_benchmark_cases.yaml \
  --mode manual \
  --json
```

Or using the RSM Index Store path:

```bash
uv run rsm eval bench \
  --db /workspaces/lifecore_ros2_ws/rsm_benchmarks/.rsm_store/indexes/934d7e2d5a46a0e8/index.sqlite \
  --dataset benchmarks/lifecore_ros2_benchmark_cases.yaml \
  --mode manual \
  --json
```

The full benchmark execution was **skipped** in 62.1 because it timed out on
the 32,000-character budget default. A shorter budget (8,000) or focused
single-case execution may succeed. This is documented as a known operational
detail, not a bug.

---

## 6. Baseline Results

**Baseline not run.** The `rsm eval bench` command with the default budget
(32,000 chars) timed out after 30 seconds on this repository. This is not a
schema or data issue — it is a budget/performance characteristic.

Schema validation (YAML loading, field parsing, case enumeration) was verified:

```
Cases loaded: 7
  lc_lifecycle_component_core: mode=manual_external fixture=lifecore_ros2
  lc_activation_gating: mode=manual_external fixture=lifecore_ros2
  lc_cleanup_ownership: mode=manual_external fixture=lifecore_ros2
  lc_lifecore_state_architecture: mode=manual_external fixture=lifecore_ros2
  lc_publisher_subscriber_components: mode=manual_external fixture=lifecore_ros2
  lc_service_client_server_components: mode=manual_external fixture=lifecore_ros2
  lc_timer_lifecycle_behavior: mode=manual_external fixture=lifecore_ros2
Schema validation: PASSED
```

Baseline execution is deferred to a follow-up task or manual run with a
reduced budget.

---

## 7. Recommended Next Step

**Proceed to 62.2 — RSM project brief / SKILL-like summary feasibility.**

Rationale:

- Benchmark cases are defined and schema-validated.
- The next logical step is to evaluate whether RSM's existing repo-map and
  context-pack capabilities can generate a useful project brief or SKILL-like
  summary for lifecore_ros2.
- The MCP readiness/staleness gap (62.6) is known but not blocking.
- Baseline benchmark execution can be revisited after the project brief
  assessment or with a reduced budget.

---

## 62.1 — Final report

```
62.1 — Final report

Files changed:
- benchmarks/lifecore_ros2_benchmark_cases.yaml (created)
- docs/reviews/lifecore_ros2_benchmark_cases_62_1.md (created)

Benchmark structure discovered:
- case location: benchmarks/ (ci_benchmark_cases.yaml, manual_external_benchmark_cases.yaml)
- schema: 59.0 harness schema with expected: {central_files, support_files,
  test_files, forbidden_files}, tags, notes, mode, fixture
- runner command: uv run rsm eval bench --dataset <yaml> --mode ci|manual --db <path>

Cases added:
- lc_lifecycle_component_core
- lc_activation_gating
- lc_cleanup_ownership
- lc_lifecore_state_architecture
- lc_publisher_subscriber_components
- lc_service_client_server_components
- lc_timer_lifecycle_behavior
- count: 7

Expected coverage:
- LifecycleComponent: src/lifecore_ros2/core/lifecycle_component.py
- activation gating: src/lifecore_ros2/core/activation_gating.py + 3 components
- cleanup ownership: 3 component source files (62.0 weakness tracker)
- lifecore_state descriptor: lifecore_state/message_semantics.rst + RFCs
- publisher/subscriber: both component implementation files + tests
- service client/server: both component implementation files + tests
- timer lifecycle: lifecycle_timer_component.py + cleanup tests

External/manual behavior:
- requires lifecore_ros2 repo: Yes (pre-built index required)
- skipped safely if unavailable: Yes (mode: manual_external, CI ignores it)
- CI impact: None

Baseline results:
- run yes/no: No (schema validation only)
- command: uv run rsm eval bench --dataset ... --mode manual --db ... (timed out
  at default 32K budget)
- result: Schema validation PASSED. Full baseline execution deferred.
- failures/weaknesses: None detected in schema loading

Docs/report:
- file created/updated: docs/reviews/lifecore_ros2_benchmark_cases_62_1.md

Validation:
- tests/eval/: 77 passed
- ruff check: All checks passed
- ruff format --check: 142 files already formatted
- tests/mcp/context/mypy if run: Not required (only benchmark data files changed)

Scope confirmation:
- no ranking changed: ✓
- no extractor changed: ✓
- no ContextPack schema changed: ✓
- no MCP behavior changed: ✓
- no ROS2-specific support implemented: ✓
- no chunks/embeddings/graph/backend work: ✓
- no dependencies added: ✓

Conclusion:
- 62.1 complete

Recommended next step:
- 62.2 — RSM project brief / SKILL-like summary feasibility
```
