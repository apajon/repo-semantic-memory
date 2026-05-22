# repo-semantic-memory MVP critical review

Date: 2026-05-19

Historical note: this review is preserved as a point-in-time design/release-readiness assessment; current docs and benchmark counts may have changed.
Scope: current MVP state after 16.2 hardening and lifecore_ros2 validation pass.

## Executive summary

The MVP is technically coherent, deterministic, and testable. Core extraction/indexing/export flows are stable, and context-pack retrieval currently outperforms repo-map baseline on the seed benchmark (2 wins, 1 inconclusive, 0 losses). Hardening around generated-artifact filtering and source-first ranking materially improved quality.

However, the project is not yet ready for a broad public announcement. The biggest remaining gaps are ranking breadth/precision in public API and cleanup ownership tasks, limited benchmark scope (3 tasks, single category), and ECS taxonomy ambiguity (lifecycle hooks mixed into integration labels). The repo is ready for broader targeted testing with early adopters, but public launch messaging should remain “experimental semantic compiler foundation,” not “AI knowledge graph platform.”

## Current implemented capabilities

- Deterministic filesystem extraction with artifact filtering (`docs/_build`, `dist`, `build`, `*.egg-info`, caches).
- Deterministic Python AST extraction (modules/classes/functions/methods, imports, inherits, ranges, metadata).
- SQLite index with explicit schema lock and deterministic ordering.
- Compact repo-map generation with source-role ordering and citations.
- Task-scoped lexical context-pack builder with budgeting, neighbor expansion, citations, uncertainty notes.
- Retrieval benchmark runner and repo-map vs lexical context-pack comparison.
- ECS-style derived semantic components (non-persisted).
- `.ai/` export and JSONL import/export.
- Claims/invariants YAML exchange (external, non-persisted in SQLite).
- Minimal Git metadata (`rsm git summary`, optional `index --with-git`).
- MCP typed placeholders (contracts only, runtime deferred).

## Strengths

1. **Determinism discipline is strong**
   - Stable IDs, sorted entity/relation persistence, deterministic rendering, deterministic benchmark outputs.
2. **Evidence and uncertainty framing is explicit**
   - Unresolved imports/inheritance are preserved as unresolved, with uncertainty surfaced in context packs.
3. **Hardening delivered measurable retrieval gains**
   - `eval compare` aggregate: lexical context pack wins 2/3 tasks; repo-map wins 0/3.
4. **Interchange surfaces are pragmatic**
   - SQLite for local runtime, JSONL for machine portability, `.ai/` for portable snapshots.
5. **Deferred-complexity decisions are mostly correct**
   - MCP runtime deferred; claims/invariants persistence deferred; no premature vector DB/graph DB dependency.

## Weaknesses

1. **Repo-map baseline still underperforms severely on retrieval tasks**
   - In current compare run, repo-map gold file/symbol coverage is 0.0 average.
2. **Public API context remains overly broad in real-world style tasks**
   - Includes test/CI/docs agent-instruction noise in public-API-flavored prompts.
3. **Cleanup/ownership retrieval still misses concrete implementation files in some scenarios**
   - Improved but incomplete for component-level files (publisher/subscriber/timer/service client/server style targets).
4. **ECS taxonomy remains blurry**
   - Lifecycle hook semantics are represented under integration-like component types, reducing semantic precision.
5. **Benchmark dataset is too small and narrow**
   - 3 tasks, all code-localization, no mutation planning, invariant lookup, or cross-package disambiguation tasks.

## Model quality review

- **Entity stability:** Good. StableId normalization and source-path-based IDs are deterministic.
- **ID determinism:** Good overall; relation IDs are implicit via `(source,target,kind)` keying.
- **Source ranges:** Good enough for MVP; AST range extraction with column normalization is consistent.
- **Relation clarity:** Clear types; unresolved imports/inherits are marked in metadata.
- **Version contracts:** Correct separation of package/schema/context-pack versions.
- **Relation occurrence collapse:** Acceptable for MVP, but now a clear debt for richer evidence/explanations.

## Extraction quality review

- **Filesystem extraction:** Good deterministic behavior and improved generated-artifact filtering.
- **Python AST extraction:** Useful and stable for structural indexing; unresolved-target strategy is explicit and safe.
- **Imports/inheritance utility:** Useful despite unresolved targets; uncertainty is preserved.
- **Generated artifact filters:** Safer than before, but still lexical/path-pattern based (risk of false positives/negatives).
- **Git metadata:** Useful as temporal context; correctly scoped and explicitly non-semantic.
- **Unsupported:** No type inference, import resolution, inheritance target resolution, call graph, non-Python language extraction.

## Evidence quality review

- Entity and relation citations are present and deterministic.
- Derived/inferred semantics (ECS) are marked inferred with heuristic notes.
- Uncertainty is represented but remains mostly string-level in context packs (not yet fully structured across all surfaces).
- Claims/invariants are evidence-capable in model, but default flow produces empty payload unless externally authored.

## Storage and interchange quality review

- **SQLite schema:** Minimal and extensible enough for MVP.
- **Schema versioning:** Clear and enforced; no hidden auto-migration behavior.
- **Query determinism:** Good due to sorted persistence and sorted reads.
- **Migration debt:** Controlled but accumulating (no migration path yet).
- **JSONL roundtrip:** Stable and strict, with explicit format version and import validation.
- **`.ai/` export:** Compact and useful as snapshot artifact.
- **Should `.ai/` be committed?** Optional policy is reasonable. For this project stage: keep local by default; commit only for explicit shared snapshots and review handoff points.

## Repo-map and context-pack quality review

- Output remains compact and cited.
- Hardening effectively reduced generated-doc/build pollution.
- Source-first ordering improved for validated cases (notably `src/lifecore_ros2`), but generic non-`src/` source-root classification is still an open gap for multi-package repositories.
- Remaining source-root coverage to harden includes roots like `lifecore_state/`, ROS 2 package roots (`package.xml`), Python package roots declared via `pyproject.toml`/`setup.py`/`setup.cfg`, and top-level package `__init__.py` layouts.
- Budget handling is sane and deterministic (char-based, explicit truncation marker).
- Context packs are currently more useful than repo-map for coding-agent retrieval tasks.
- Remaining ranking problems from lifecore-style validation:
  - public API over-selection (tests/docs/CI/copilot docs leakage)
  - cleanup/ownership under-selection of concrete component implementations.

## Benchmark readiness review

Current seed dataset result (run at 2026-05-19 on commit `6be7f9e39b39ede4eb54d34233013a7612170fa6`):

- Retrieval aggregate:
  - file recall@1/3/5: 0.667
  - file recall@10: 1.0
  - symbol recall@10: 0.278
- Compare aggregate:
  - lexical context pack wins: 2
  - repo-map wins: 0
  - inconclusive: 1

Assessment:

- Deterministic measurement exists and is useful.
- Recall can be measured and baseline comparison works.
- Dataset is currently too small and biased toward code-localization internals.
- Need broader tasks before strong quality claims.

Benchmark cases to add next:

1. Public API extraction precision task (avoid test/docs/CI leakage).
2. Cleanup/ownership retrieval for concrete ROS-like components.
3. Cross-package source-root disambiguation in multi-package repos.
4. Invariant/claim retrieval readiness (even if externally authored payload).
5. “Patch-context sufficiency” task to align with future MCP `validate_patch_context`.

## ECS/components/invariants readiness review

- Components are useful today as ranking hints and lightweight labels, not just decorative.
- They are correctly treated as derived, inferred signals (non-persisted).
- Inferred vs confirmed separation exists in model/status, but confirmed pipeline is not yet present.
- Claims/invariants: YAML exchange is sufficient for now.
- Persistence decision: keep external for now; add DB persistence only after benchmarked use-cases justify it.

## Related work notes

### Graphify-like repository knowledge graph tools

- **What they do well:** rich graph traversal, multi-hop analysis, schema-rich graph operations.
- **What to borrow now:** graph query ergonomics, explicit relation provenance patterns, subgraph explainability conventions.
- **What to defer:** graph database/runtime dependency, heavy ontology expansion, distributed graph infra.

### qmd-like local document/search tools

- **What they do well:** fast local text/document retrieval and lightweight workflows.
- **What to borrow now:** frictionless local UX, deterministic local outputs, simple query surfaces.
- **What to defer:** document-centric framing that dilutes code-structure-first semantics.

### RTK-like token/output compression tools

- **What they do well:** compact context shaping and budget-sensitive output packaging.
- **What to borrow now:** stricter budget accounting, selection transparency, compact representation patterns.
- **What to defer:** opaque compression that drops provenance or weakens symbol-level traceability.

## Graphify/qmd/RTK positioning

`repo-semantic-memory` should be positioned as a **deterministic semantic compiler for repositories**:

- Not a generic knowledge graph platform (Graphify-like full graph runtime).
- Not a general local notes/search/document tool (qmd-like).
- Not only a token compressor (RTK-like).

Differentiator: deterministic extraction + provenance + benchmarked context utility for coding agents.

## Ideas to borrow

1. Graph traversal explainability formats (Graphify-like).
2. Lightweight local command ergonomics (qmd-like).
3. Budget diagnostics and compact context accounting (RTK-like).
4. Better retrieval evaluation diversity and reproducibility templates from all three categories.

## Ideas to defer

1. Graph DB backend and query engine replacement.
2. Remote/networked MCP runtime.
3. Vector DB / embedding-first architecture.
4. LLM-generated semantic claims as primary truth layer.
5. Rich UI/dashboard work before benchmark maturity.

## Concrete refactor recommendations (no architecture rewrite)

1. **Factor ranking signals into explicit score groups** in context-pack builder (lexical, path-role, task-hint, component-hint) to improve auditability.
2. **Promote structured uncertainty objects** earlier in pack internals (not only strings) to align with MCP contract direction.
3. **Isolate generated-artifact policy constants** into a shared policy module used by filesystem + pack ranking.
4. **Create explicit lifecycle-hook semantic component type** (derived) to reduce taxonomy blur.
5. **Add evaluation helper for “noise ratio by path role”** to quantify public API leakage.

## High-priority fixes

1. Tighten public API ranking to suppress tests/docs/CI/copilot instructions unless explicitly requested.
2. Improve cleanup/ownership ranking for concrete implementation files (publisher/subscriber/timer/service patterns).
3. Expand benchmark dataset beyond 3 internal localization tasks.
4. Add measurable regression guard for source-root inference in multi-package repositories.
5. Add explicit metric/report section for false-positive context noise.

## Low-priority future ideas

1. Optional relation-occurrence table for line-level multiplicity.
2. Optional tokenizer-aware budgeting mode (while keeping char budget default).
3. Controlled enrichment for resolved imports/inheritance (deterministic only).
4. Additional language extractors once Python baseline benchmark goals are met.
5. Read-only MCP runtime after tool contract hardening and security review.

## Things not to implement yet

- Full MCP server runtime/transport.
- Vector DB or embedding pipeline.
- Neo4j/graph DB dependency.
- Web UI/dashboard.
- LLM-first summarization/claim generation.
- Automatic persistence layer for claims/invariants without benchmarked need.

## MCP readiness review

- Placeholder contracts are useful and scoped correctly.
- Runtime deferral is correct.
- Main risks of implementing too early:
  - freezing unstable query contracts,
  - exposing premature security surface,
  - shifting effort away from retrieval-quality fundamentals.
- First MCP tools to implement later (in order):
  1. `search_symbols`
  2. `build_context_pack`
  3. `explain_entity`
  4. `query_graph`
  5. `validate_patch_context`

## Release/versioning quality review

- Semantic-release is correctly configured for zero-version mode (`allow_zero_version = true`, `major_on_zero = false`).
- Package/schema/context-pack versions are separated.
- Pre-1.0 constraints are documented and aligned with current policy.
- Apache-2.0 is reflected in project metadata and generated artifact templates.

## Architecture risks review

- No major hidden global state found.
- Module sizing is mostly controlled; large files exist in CLI and some builders but remain understandable.
- Main risk is **heuristic concentration** (ranking + components) rather than monolith explosion.
- No premature external dependency creep detected.
- Generated artifacts handling remains a process risk (must keep local artifacts intentionally managed).

## Public-readiness review

- README is generally honest about scope and limitations.
- Deterministic constraints and uncertainty handling are clearly stated.
- Examples/commands are reproducible.
- Source-of-truth vs generated-artifact distinction is explicit.

Verdict:

- **Repo ready for broader testing?** Yes, for targeted early adopters.
- **Ready for broad public announcement?** Not yet; complete priority fixes and benchmark expansion first.

## Suggested next milestone

**Milestone: Retrieval Precision Hardening v0.7**

Exit criteria:

1. Generic source-root classifier is implemented and validated across multi-package layouts (including non-`src/` roots).
2. Ranking output includes explainable score-breakdown reporting per selected entity.
3. Field-weighted BM25 lexical retrieval is added as the primary ranking baseline.
4. Deterministic graph-neighborhood selection is stabilized and benchmarked for predictable expansion behavior.
5. Context noise and token-savings metrics are reported; benchmark dataset expansion (8–12 diverse tasks) is completed using those metrics.

## Public announcement verdict

- **Now:** defer broad announcement.
- **After next milestone:** proceed with a scoped technical announcement focused on deterministic semantic compilation and measured context quality.

## Suggested public pitch

“`repo-semantic-memory` is a deterministic semantic compiler for software repositories. It turns code, docs, tests, and Git history into compact, source-cited context artifacts and benchmarkable retrieval outputs for coding agents—without relying on opaque LLM summaries as source of truth.”

## Suggested platforms for sharing

1. GitHub README + Releases (primary canonical channel).
2. GitHub Discussions (design/benchmark transparency).
3. Python-focused communities (packaging + tooling audience).
4. Agent tooling communities (MCP-adjacent audiences) after retrieval milestone completion.
5. Technical blog post with benchmark methodology and limits.

## Top 5 risks

1. Ranking noise in public API tasks reduces trust in context packs.
2. Small benchmark dataset creates overconfidence and blind spots.
3. ECS taxonomy ambiguity causes semantic drift in downstream usage.
4. Relation occurrence collapse may limit future explainability for repeated edges.
5. Artifact-management drift (`.ai/` snapshots and local generated outputs) can confuse source-of-truth boundaries.

## Top 5 next actions

1. Implement a generic source-root classifier for multi-package repositories (including non-`src/` roots).
2. Add explainable ranking breakdown output (lexical/path-role/task-hint/component contributions).
3. Introduce field-weighted BM25 retrieval for ranking stability and precision.
4. Stabilize a deterministic graph-neighborhood selector for context expansion.
5. Add context-noise and token-savings metrics, then expand benchmark tasks using those metrics.
