# Case study: lifecore_ros2

Date: 2026-05-22
Target repo: [apajon/lifecore_ros2](https://github.com/apajon/lifecore_ros2)
Validation type: local static dogfooding run

## Scope

This report summarizes a fresh RSM run against `lifecore_ros2`, a Python ROS2 lifecycle-component library. It intentionally keeps only compact facts from the generated repo-map and context packs.

Constraints:

- Static source extraction only; no runtime ROS introspection.
- No LLM calls, embeddings, or external semantic services.
- The source repository was cloned locally at `../lifecore_ros2` and indexed once before all derived outputs were generated.
- Context-pack claims are interpreted with their explicit status: `confirmed` for source-backed exports, `inferred` for heuristic relations/components.
- This is dogfooding evidence for RSM behavior, not a controlled benchmark.

## Commands used

The following commands were run from the `repo-semantic-memory` repository root:

```bash
uv run rsm index ../lifecore_ros2 --db .rsm/lifecore_ros2.sqlite

uv run rsm repo-map \
  --db .rsm/lifecore_ros2.sqlite \
  --budget 8000 \
  --profile agent_standard > /tmp/lifecore_repo_map.md

uv run rsm pack \
  --task "Find public API exported by the package" \
  --db .rsm/lifecore_ros2.sqlite \
  --budget 8000 \
  --profile agent_standard \
  --format yaml \
  --explain-ranking > /tmp/lifecore_public_api_pack.yaml

uv run rsm pack \
  --task "Find where activation gating is implemented" \
  --db .rsm/lifecore_ros2.sqlite \
  --budget 8000 \
  --profile agent_standard \
  --format yaml \
  --explain-ranking > /tmp/lifecore_activation_impl_pack.yaml

uv run rsm pack \
  --task "Find regression tests for activation gating behavior" \
  --db .rsm/lifecore_ros2.sqlite \
  --budget 8000 \
  --profile agent_standard \
  --format yaml \
  --explain-ranking > /tmp/lifecore_activation_regression_pack.yaml

uv run rsm pack \
  --task "Find lifecycle component ownership and cleanup rules" \
  --db .rsm/lifecore_ros2.sqlite \
  --budget 8000 \
  --profile agent_standard \
  --format yaml \
  --explain-ranking > /tmp/lifecore_cleanup_pack.yaml
```

No raw repo-map or context-pack output is reproduced here.

## Compact findings

- RSM version for this run: `0.23.4.dev1+g71a59888b`.
- Index size for `lifecore_ros2`: 1923 entities and 3256 relations.
- Repo-map generation completed at budget 8000 with `agent_standard`; the full repo-map is not pasted in this report.
- Public API pack retained the expected relation signal: 1 `exports` relation.
  - It selected 22 entities and 2 semantic components.
  - `PublicAPI` was present once with `status: confirmed`.
  - One uncertainty was reported for an unresolved export target: `ComponentDependencyError`.
- Activation implementation pack retained the expected implementation relation signal: 1 `contains` relation.
  - It selected 21 entities.
  - It included `ExternalIntegration`, `LifecycleManaged`, `TestTarget`, and `TestFile` components, all inferred.
- Activation regression pack retained the expected test relation signal: 1 `tests` relation.
  - It selected 21 entities.
  - The retained `tests` relation is inferred by the test-relationship extractor.
- Cleanup ownership pack retained the expected relationship signal: 1 `tests` relation and no `contains` relation in the selected relation budget.
  - It selected 19 entities.
  - It included 8 inferred `LifecycleManaged` components.
- Generated artifact leakage check passed for all generated outputs.
  - No generated build docs, coverage output, package metadata, local index paths, or volatile `.ai` snapshot files appeared in the repo-map or context-pack outputs.

## Before/after lessons

- Generated-artifact filtering keeps the indexed context focused on source, tests, docs, and tracked project files instead of build or coverage byproducts.
- Source-first ranking helps implementation prompts surface code such as activation-gating logic before lower-value prose matches.
- Explain-ranking relation budgeting now keeps the important compact relation signals visible: `exports` for public API, `contains` for implementation, and `tests` for regression or cleanup questions.
- The lifecore_ros2 run is a useful smoke test because it exercises package exports, lifecycle-style classes, test-to-source heuristics, and documentation/tooling paths in one repository.

## Known limitations

- All four context packs were budgeted outputs; selected entities and relations are not exhaustive.
- `confirmed PublicAPI` only means statically exported through package surfaces; it does not imply long-term API stability.
- `tests`, `LifecycleManaged`, and integration-like components in these packs are inferred heuristically, not proven by type analysis or runtime inspection.
- RSM does not resolve all imports or export targets yet; unresolved targets are surfaced as uncertainties.
- RSM does not build a Python call graph, infer ROS node topology, or introspect ROS messages/services/actions at runtime.
- This is one local run against one repository, so the results should not be generalized as benchmark evidence.

## Public wording guidance

Use narrow wording:

- Safe: “RSM indexed lifecore_ros2 and retained compact relation signals for public exports, activation-gating implementation, regression tests, and cleanup ownership.”
- Safe: “The run surfaced inferred lifecycle and test relationships with explicit status labels.”

Avoid overclaims:

- Do not claim RSM understands ROS2 lifecycle semantics at runtime.
- Do not claim `confirmed PublicAPI` means stable public API.
- Do not claim this case study proves RSM is better than other retrieval systems.
- Do not quote token savings or benchmark wins from this report; this run was not a benchmark comparison.
