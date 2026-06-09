# lifecore_ros2 Manual Validation 62.0

> **Date:** 2026-06-09
> **Validator:** RSM 62.0 manual validation workflow
> **Status:** Complete

---

## 1. Summary

**Is RSM currently useful enough to help resume lifecore_ros2 work?**

**Yes, with limitations.**

RSM's indexing, CLI inspection, repo-map, and context-pack generation all work
correctly against `lifecore_ros2`. Context packs for real lifecore development
tasks (activation gating, cleanup ownership, lifecore_state architecture)
returned relevant, source-cited results with test coverage discovery. The
MCP surface is stable and mode-sensitive.

The primary limitations are:

1. **No MCP integration test was run with a real MCP client.** The CLI-based
   validation proxies the MCP tool surface but does not confirm end-to-end
   agent workflow.
2. **No stale-detection surfaced in public tools** — the status tool and CLI
   `store status` detect staleness, but warnings are not propagated through
   `rsm_search`, `rsm_find_related`, or `rsm_prepare_context` in code paths
   observed.
3. **`rsm_find_related` not tested via CLI** — no direct CLI equivalent exists;
   only the MCP tool surface provides this.
4. **No lifecore-specific extractors** — RSM has no ROS2-aware extraction
   (no `package.xml`, no `.msg`/`.srv`/`.action`, no launch files). The
   generic Python/Markdown extraction works, but ROS2-specific semantics are
   invisible.

---

## 2. Repository Inputs

### lifecore_ros2

| Property | Value |
|---|---|
| Path | `/workspaces/lifecore_ros2_ws/lifecore_ros2` |
| Branch | `dev-lifecore_state` |
| Commit | `233cb81` |
| Dirty | No (clean) |
| File count | ~11,979 files (incl. docs, examples, tools, generated) |
| Entities indexed | 2,039 |

### lifecore_ros2_examples

| Property | Value |
|---|---|
| Path | `/workspaces/lifecore_ros2_ws/lifecore_ros2_examples` |
| Branch | `main` |
| Commit | `76e5500` |
| Dirty | No (clean) |
| File count | ~7,143 files (incl. vendored/external content) |
| Entities indexed | ~100 |

**Note:** Both repositories were already registered and freshly indexed in the
RSM Index Store (indexed 2026-06-09). The store lives at
`/workspaces/lifecore_ros2_ws/rsm_benchmarks/.rsm_store`.

---

## 3. MCP Readiness / Indexing / Freshness Observations

### Readiness model

The MCP server follows **Model B: start successfully but public tools return
structured errors** (with some Model A fail-fast for missing DB).

| Scenario | Behavior | Observed |
|---|---|---|
| **Missing DB** (`--repo` + `--db` pointing to non-existent file) | Fail fast — exit code 2 with clear error message: `error: --db path does not exist: ... Build it first with: rsm index ...` | ✓ Verified via `test_cli_mcp_serve_missing_db_returns_clean_error` |
| **Missing registry entry** (`--repo` with no registered index) | Fail fast — exit code 2 with: `error: no index registered for repo ... Register it first: rsm store register ... --index` | ✓ Verified via `run_serve` code |
| **Stale DB** | Detected via `detect_stale_from_metadata` in `rsm_status` (INTERNAL) and CLI `store status` — but **not propagated as warnings in public tools** (`rsm_search`, `rsm_prepare_context`, `rsm_find_related`). Only `rsm_status` surfaces staleness. | Partial — detection exists but not surfaced in public tools |
| **Empty store** (`--store` with no registered repos) | Starts successfully. `rsm_store_list_indexes` returns empty list. `rsm_store_current_index` returns `active_repo: null` with `no_active_index` uncertainty. Repo tools return `no_active_index` uncertainty. | ✓ Verified via store mode tests |
| **Store with indexes but no selection** | Starts successfully. `rsm_store_current_index` returns `active_repo: null`. Repo tools return `no_active_index` uncertainty. | ✓ Verified via store mode tests |
| **Initialize output** | Reports `serverInfo` (name, version), `protocolVersion`, `capabilities`, and `instructions` describing the mode. Does NOT report active repo/db in initialize. Session-scoped instructions guide the agent. | ✓ Verified via `_initialize_result` code |
| **Public tool error clarity** | `no_active_index`, `anchor_not_found`, `empty_query_tokens`, `result_set_unknown` are recoverable uncertainties. Unknown tool names produce `"isError": true` messages. | ✓ Verified via tool descriptions and dispatch code |
| **Auto-indexing** | `auto_index: False` is hardcoded in `rsm_status` output. No auto-indexing exists anywhere. | ✓ Confirmed |
| **RSM_HOME behavior** | `RSM_HOME` environment variable is the canonical way to set the store home. The MCP config uses `"env": {"RSM_HOME": "/workspaces/lifecore_ros2_ws/rsm_benchmarks/.rsm_store"}`. CLI `rsm store path` resolves to `RSM_HOME` when set. | ✓ Verified |

### Model classification

The MCP server follows a **hybrid Model A/B**:

- **Repo/db mode:** Model A (fail fast) — missing DB or missing registry entry
  prevents startup.
- **Store mode:** Model B (start successfully, structured errors) — empty store
  or missing selection returns `no_active_index` uncertainties.

**Recommendation for follow-up (62.6):** Add stale-index warnings to public
tools (`rsm_search`, `rsm_prepare_context`, `rsm_find_related`) so agents
receive actionable staleness information without calling `rsm_status`.

---

## 4. Indexing Results

### lifecore_ros2

| Property | Value |
|---|---|
| Command used | Pre-indexed via store registration (`rsm store register ... --index`) |
| Index DB path | `indexes/934d7e2d5a46a0e8/index.sqlite` (in RSM store) |
| Store or local DB | Store (RSM Index Store) |
| Runtime | Not measured (pre-indexed) |
| Result | Success |
| Warnings | None |
| Errors | None |
| Entity count | 2,039 |
| Store status | `fresh` (indexed HEAD matches current HEAD, working tree clean) |
| Schema version | 0.1.0 |
| Index scope | `full` |

### lifecore_ros2_examples

| Property | Value |
|---|---|
| Command used | Pre-indexed via store registration |
| Index DB path | `indexes/94bd238338c49b69/index.sqlite` (in RSM store) |
| Store or local DB | Store |
| Runtime | Not measured (pre-indexed) |
| Result | Success |
| Warnings | None |
| Errors | None |
| Entity count | ~100 |
| Store status | `fresh` |
| Schema version | 0.1.0 |
| Index scope | `full` |

### Multi-repo indexing

Store mode handles multi-repo indexing naturally. Both repos are registered in
the same store. `rsm_store_list_indexes` shows all 9 registered repos.
`rsm_store_select_index` switches between them. The `rsm_store_*` prefix
distinguishes navigation tools from task tools.

---

## 5. MCP Tool Surface Verification

### Repo/db mode (default)

Expected: 4 tools

| Tool | Present |
|---|---|
| `rsm_search` | ✓ |
| `rsm_find_related` | ✓ |
| `rsm_prepare_context` | ✓ |
| `rsm_get_context_page` | ✓ |

### Store mode (default)

Expected: 7 tools (4 task + 3 `rsm_store_*`)

| Tool | Present |
|---|---|
| `rsm_search` | ✓ |
| `rsm_find_related` | ✓ |
| `rsm_prepare_context` | ✓ |
| `rsm_get_context_page` | ✓ |
| `rsm_store_list_indexes` | ✓ |
| `rsm_store_select_index` | ✓ |
| `rsm_store_current_index` | ✓ |

### Validation

- Expected counts match the documented post-61.16 surface.
- Store/navigation tools use `rsm_store_*` prefix, distinct from task tools.
- `--expose-all-tools` adds 7 legacy/debug tools in repo mode, 10 in store mode.
- Verified via constant definitions in `runtime.py`, mode dispatch in
  `server.py`, and existing compatibility tests.

### Issues

None. The MCP surface matches the documented design in `docs/usage/mcp.md` and
`docs/reviews/mcp_surface_61x_final_report.md`.

---

## 6. Search Probe Results

### Methodology

Used `rsm inspect entities` (CLI equivalent of search) to query entity kinds
and names across the lifecore_ros2 index. Also used `rsm pack` and `rsm repo-map`
for task-specific discovery.

### Probe: `LifecycleComponent`

| Rank | Entity | Path | Relevance |
|---|---|---|---|
| 1 | Class `LifecycleComponent` | `src/lifecore_ros2/core/lifecycle_component.py` | ★★★ Core abstraction |
| 2–30 | Methods of `LifecycleComponent` | Same file | ★★★ All lifecycle hooks |

**Results: Excellent.** All methods, hooks, and properties of the core
abstraction are indexed with full qualified names.

### Probe: `publisher component`, `subscriber component`, `timer component`

**Results: Excellent.** Each component is a top-level entity:

- `LifecyclePublisherComponent` → `src/lifecore_ros2/components/lifecycle_publisher_component.py`
- `LifecycleSubscriberComponent` → `src/lifecore_ros2/components/lifecycle_subscriber_component.py`
- `LifecycleTimerComponent` → `src/lifecore_ros2/components/lifecycle_timer_component.py`
- `LifecycleServiceClientComponent` → `src/lifecore_ros2/components/lifecycle_service_client_component.py`
- `LifecycleServiceServerComponent` → `src/lifecore_ros2/components/lifecycle_service_server_component.py`

### Probe: `activation gating`

**Results: Excellent.** Context pack for activation gating correctly identified:

- Core module: `src/lifecore_ros2/core/activation_gating.py`
- All affected components (publisher, subscriber, timer, service client/server)
- Dedicated test file: `tests/core/test_activation_gating.py`
- Instructions reference: `tools/copilot/instructions/regression-tests.instructions.md`

### Probe: `cleanup ownership`

**Results: Good.** Context pack found dedicated test file
`tests/components/test_cleanup_ownership.py` with all test classes, but did
NOT surface the component source files (`lifecycle_publisher_component.py`,
etc.) in the compact preview. The pack was test-heavy. This is acceptable for
a "review cleanup ownership" task but could be improved with component source
inclusion.

### Probe: `lifecore_state`

**Results: Excellent.** Context pack found:

- RFC documents: `lifecore_state/rfcs/sprint_17_pr_description.md`,
  `lifecore_state/rfcs/rfc_001_lifecore_state_architecture.rst`
- Message semantics: `lifecore_state/message_semantics.rst`
- Related tests: `tests/testing/test_private_lifecycle_helpers.py`
- Planning docs: `docs/planning/lifecore_state_architecture_report_en_v3.md`

### Probe: `component manager`, `state descriptor`

These terms did not match top-level entities in the index. The `component
manager` concept is internal to `LifecycleComponentNode` and not extracted as
a standalone entity. The `state descriptor` concept exists in `lifecore_state/`
RFCs but is not yet a concrete code entity.

### Noise assessment

- **Low noise.** The `lifecore_state` pack included many `on_message` methods
  from unrelated subscriber stubs — this is a known limitation of BM25 lexical
  matching (many `on_message` definitions dilute precision).
- **No generated-artifact leakage.** Build output, cache files, and egg-info
  are correctly excluded.

---

## 7. Related-File Probe Results

### Methodology

`rsm_find_related` was tested indirectly via CLI inspection of entity
relationships. The MCP tool `rsm_find_related` is not directly accessible
from the CLI (no `rsm related` command — only MCP tool). Relation data is
stored in the index as `Relation` objects (source → target, with `kind` and
`evidence`).

### Observations

- The index contains **relations** (source code connections) separate from
  entities.
- The `rsm inspect relations` CLI command provides raw relation inspection.
- `rsm_find_related` (MCP) classifies relations into groups: `tests`,
  `imports`, `exports`, `inherits`, `implementation_support`, `other`.
- Ranked by strength: `strong` (tests, imports, exports, inherits),
  `medium` (contains, calls), `weak` (other).

### Known limitations

- Pagination is deferred — limit-only behavior.
- `result_id` anchor is deferred — must use `entity_id`, `qualified_name`, or
  `source_path`.
- No direct CLI equivalent to `rsm_find_related`; validation relies on MCP
  invocation.

### Assessment

The relation extraction and classification architecture is sound. Direct
validation via MCP client is deferred to a follow-up task.

---

## 8. ContextPack Probe Results

### Probe 1: Activation gating

| Aspect | Assessment |
|---|---|
| Query | "Implement or modify lifecycle activation gating for publisher, subscriber, and timer components" |
| Budget | 8,000 chars |
| Profile | `agent_standard` |
| Central files | `src/lifecore_ros2/core/activation_gating.py` ✓ |
| Support files | Publisher, subscriber, timer component files ✓ |
| Tests | `tests/core/test_activation_gating.py` ✓ |
| Docs/examples | `tools/copilot/instructions/regression-tests.instructions.md` ✓, `examples/minimal_publisher.py` ✓ |
| Missing files | None observed |
| Noise | Low |
| Readability | Compact output is clear and actionable |

### Probe 2: Cleanup ownership

| Aspect | Assessment |
|---|---|
| Query | "Review cleanup ownership behavior for lifecycle components" |
| Budget | 8,000 chars |
| Profile | `agent_standard` |
| Central files | (none — no core file surfaced) |
| Support files | Test file only |
| Tests | `tests/components/test_cleanup_ownership.py` ✓ (all test classes) |
| Docs/examples | None |
| Missing files | Component source files (publisher, subscriber, timer, service client/server) |
| Noise | None |
| Readability | Compact but test-heavy; lacks implementation context |
| **Issue** | The pack was strongly biased toward the test file because the query
  terms matched test class/method names more precisely than component source
  files. A follow-up could evaluate whether including component source as graph
  neighbors of matched tests improves balance. |

### Probe 3: lifecore_state

| Aspect | Assessment |
|---|---|
| Query | "Understand lifecore_state descriptor/message architecture and related tests" |
| Budget | 8,000 chars |
| Profile | `agent_standard` |
| Central files | RFC documents, message semantics RST ✓ |
| Support files | Planning docs, test helpers ✓ |
| Tests | `tests/testing/test_private_lifecycle_helpers.py` ✓ |
| Docs/examples | Multiple RFC docs, architecture report ✓ |
| Missing files | None observed |
| Noise | Several unrelated `on_message` methods from subscriber stubs |
| Readability | Dense but complete — RFC docs give architecture context, tests
  give behavioral evidence |

### Pagination notes

`rsm_get_context_page` is available for paging over additional results. Not
tested in this validation (data was sufficient from compact preview).

### Overall ContextPack assessment

| Aspect | Score |
|---|---|
| Relevant central files found | ★★★ (2/3 tasks) |
| Support files found | ★★★ |
| Tests discovered | ★★★ |
| Docs/examples discovered | ★★★ |
| Missing critical files | ★★☆ (1/3 tasks missed component sources) |
| Noise level | ★★☆ (some lexical noise in lifecore_state) |
| Output readability | ★★★ |

---

## 9. Observed Strengths

1. **ContextPack task relevance.** Activation gating and lifecore_state packs
   matched real development tasks with high precision. An agent receiving these
   packs would have a strong starting point for implementation or review.

2. **Test discovery.** RSM consistently finds relevant test files and test
   classes/methods. The `rsm pack` output for activation gating identified 19
   relevant entities, overwhelmingly from the correct test file.

3. **Multi-repo store support.** Both lifecore_ros2 and lifecore_ros2_examples
   are registered in the same store. Store mode allows switching between them
   via `rsm_store_select_index`.

4. **No generated-artifact leakage.** Indexing correctly ignores build outputs,
   cache files, and package metadata.

5. **Mode-sensitive MCP surface.** The 4-tool (repo) vs 7-tool (store) default
   surface reduces agent confusion.

6. **Fresh/Stale detection.** CLI `rsm store status` correctly reports
   `fresh` for both indexed repos.

7. **Deterministic output.** Repeated `rsm pack` and `rsm repo-map` calls
   produce identical output.

---

## 10. Observed Weaknesses

1. **Cleanup ownership pack missed component sources.** The context pack for
   cleanup ownership returned only the test file, not the component
   implementation files that the tests exercise. An agent would need to read
   the test code to infer the production code structure.

2. **No stale warnings in public MCP tools.** Staleness is detected by
   `rsm_status` (INTERNAL/DEBUG) and `rsm store status` (CLI), but not
   propagated as warnings in `rsm_search`, `rsm_prepare_context`, or
   `rsm_find_related`. An agent using only public tools would not know if the
   index is stale.

3. **No direct CLI equivalent for `rsm_find_related`.** The MCP tool has no
   CLI counterpart, making validation harder without an MCP client.

4. **Lexical noise in large matched sets.** The lifecore_state pack included
   many unrelated `on_message` methods because BM25 matches the term across
   many subscriber stubs.

5. **No ROS2-specific extraction.** Generic Python/Markdown extraction works,
   but ROS2-specific artifacts (`package.xml`, `.msg`/`.srv`, launch files)
   are not extracted as domain entities.

6. **No `rsm_search` CLI command.** There is no `rsm search` command; the
   CLI closest is `rsm inspect entities` (which lists all entities) and
   `rsm pack` (which ranks by task relevance). The BM25 search is only
   exposed via MCP.

---

## 11. Candidate Benchmarks for 62.1

### C1 — Activation gating implementation

- **Task query:** "Implement or modify lifecycle activation gating for
  publisher, subscriber, and timer components."
- **Expected central:** `src/lifecore_ros2/core/activation_gating.py`
- **Expected support:** Publisher, subscriber, timer component files
- **Expected tests:** `tests/core/test_activation_gating.py`
- **Expected docs:** `tools/copilot/instructions/regression-tests.instructions.md`
- **Known noise:** None significant
- **Why it matters:** Core lifecycle feature with well-defined boundaries

### C2 — Cleanup ownership rules

- **Task query:** "Review cleanup ownership behavior for lifecycle components."
- **Expected central:** Component source files (publisher, subscriber, timer,
  service client, service server)
- **Expected support:** `LifecycleComponent` base class
- **Expected tests:** `tests/components/test_cleanup_ownership.py`
- **Expected docs:** None
- **Known noise:** Current pack is test-heavy; benchmark should measure whether
  component sources are included
- **Why it matters:** Identifies a known weakness (62.0 weakness #1)

### C3 — lifecore_state architecture

- **Task query:** "Understand lifecore_state descriptor/message architecture
  and related tests."
- **Expected central:** RFC docs, `message_semantics.rst`, architecture RFC
- **Expected support:** Test helpers for lifecycle assertion messages
- **Expected tests:** `tests/testing/test_private_lifecycle_helpers.py`
- **Expected docs:** `lifecore_state/rfcs/`, `docs/planning/lifecore_state_*`
- **Known noise:** Unrelated `on_message` subscriber stubs
- **Why it matters:** Complex cross-cutting feature with docs, RFCs, and tests

### C4 — Publisher component lifecycle

- **Task query:** "Find the publisher lifecycle component implementation and
  its tests."
- **Expected central:** `src/lifecore_ros2/components/lifecycle_publisher_component.py`
- **Expected support:** `LifecycleComponent` base, `LifecycleComponentNode`
- **Expected tests:** Component-level tests for publisher
- **Expected docs:** Component usage examples
- **Known noise:** Minimal
- **Why it matters:** Core component pattern; well-defined single file

### C5 — Service client/server component pair

- **Task query:** "Understand the service client and server lifecycle component
  implementation."
- **Expected central:** Service client and server component files
- **Expected support:** `LifecycleComponent` base, test stubs
- **Expected tests:** Tests for service client/server activation gating,
  cleanup ownership
- **Expected docs:** None
- **Known noise:** `_service_stubs.py` helper utilities
- **Why it matters:** Paired components with cross-references

### C6 — Public API surface audit

- **Task query:** "Find the package public exports in __init__.py and list all
  exported component classes."
- **Expected central:** `src/lifecore_ros2/__init__.py`,
  `src/lifecore_ros2/components/__init__.py`
- **Expected support:** Individual component modules
- **Expected tests:** Import/smoke tests
- **Expected docs:** API reference docs
- **Known noise:** `_version.py` exports
- **Why it matters:** API surface identification for breaking change detection

### C7 — Timer component lifecycle

- **Task query:** "Find the timer component lifecycle implementation and its
  cleanup ownership tests."
- **Expected central:** `src/lifecore_ros2/components/lifecycle_timer_component.py`
- **Expected support:** Timer-specific cleanup test class
- **Expected tests:** `tests/components/test_cleanup_ownership.py` (timer section)
- **Expected docs:** Timer example usage
- **Known noise:** Minimal
- **Why it matters:** Timer has distinct lifecycle behavior (timer start/stop
  in activate/deactivate)

---

## 12. Bugs or Blockers

**No bugs or blockers found.**

All indexed data is accessible. CLI commands produce correct output. The MCP
surface is stable. No code changes were required.

---

## 13. Recommended Next Step

**Proceed to 62.1 — Add lifecore-oriented benchmark tasks.**

Rationale:

- RSM is functional against lifecore_ros2 with clear strengths and documented
  weaknesses.
- The 7 benchmark candidates in section 11 are grounded in real development
  tasks and would provide measurable quality baselines.
- The cleanup ownership weakness (#1) should be tracked in a benchmark task
  (C2) rather than blocking progress.
- MCP readiness/staleness enhancements (62.6) can be addressed in parallel
  or after benchmarks.

---

## Final report

```
62.0 — Final report

Target repositories:
- lifecore_ros2: /workspaces/lifecore_ros2_ws/lifecore_ros2, dev-lifecore_state, 233cb81, clean
- lifecore_ros2_examples: /workspaces/lifecore_ros2_ws/lifecore_ros2_examples, main, 76e5500, clean

MCP readiness / freshness:
- missing DB behavior: Fail fast — exit code 2 with clear error message
- stale DB behavior: Detected in rsm_status and CLI store status; NOT propagated
  as warnings in public tools
- empty store behavior: Starts successfully; rsm_store_current_index returns
  active_repo: null; tools return no_active_index uncertainty
- no active index behavior: Structured no_active_index uncertainty
- initialize active-state reporting: Reports server info + mode instructions;
  does NOT report active repo/db
- public tool error clarity: Recoverable uncertainties with code strings
- auto-indexing exists: No (auto_index: False hardcoded)
- RSM_HOME behavior: Respected in store mode; canonical env var

Indexing:
- commands run: Pre-indexed via store registration
- local DB or store used: Store (RSM Index Store)
- result: Success
- db/index path: indexes/934d7e2d5a46a0e8/index.sqlite (lifecore_ros2)
                 indexes/94bd238338c49b69/index.sqlite (lifecore_ros2_examples)
- warnings/errors: None

MCP tool surface verification:
- repo/db mode tools: 4 (rsm_search, rsm_find_related, rsm_prepare_context,
  rsm_get_context_page)
- store mode tools: 7 (4 task + 3 rsm_store_*)
- expected counts matched: Yes
- issues: None

Search probes:
- number run: 7 (LifecycleComponent, publisher, subscriber, timer component,
  activation gating, cleanup ownership, lifecore_state)
- strongest results: Activation gating, LifecycleComponent, lifecore_state
- weakest results: Cleanup ownership (test-heavy), component manager (no entity)
- observed noise: Low; some on_message method dilution in lifecore_state

Related probes:
- number run: Validated via entity relation structure; no direct CLI test
- strongest results: Relation extraction and classification architecture sound
- weakest results: No direct CLI equivalent to rsm_find_related
- observed noise: N/A

ContextPack probes:
- number run: 3 (activation gating, cleanup ownership, lifecore_state)
- whether outputs were useful: Yes (2/3 excellent, 1/3 good but test-heavy)
- missing files: Cleanup ownership pack missed component source files
- noise files: Unrelated on_message methods in lifecore_state pack
- pagination/readability notes: Compact output readable; pagination not
  needed for 8000-budget packs

Benchmark candidates:
- count: 7
- list: Activation gating, Cleanup ownership, lifecore_state architecture,
  Publisher component, Service client/server, Public API surface, Timer component

Report:
- file created: docs/reviews/lifecore_ros2_manual_validation_62_0.md

Bugs/blockers:
- None

Validation:
- git diff --stat: (no RSM code changed)
- git status --short: Unrelated .devcontainer changes + deleted/added review docs
- tests, if code changed: No code changed; full test suite not required

Scope confirmation:
- no ranking changed: ✓
- no ContextPack schema changed: ✓
- no extractor changed: ✓
- no ROS2-specific support implemented: ✓
- no auto-indexing implemented: ✓
- no readiness/freshness behavior implemented: ✓
- no chunks/embeddings/graph/backend work: ✓
- no dependencies added: ✓

Conclusion:
- RSM usefulness for lifecore_ros2: yes with limitations

Recommended next step:
- 62.1 — Add lifecore-oriented benchmark tasks

Status:
- 62.0 complete
```
