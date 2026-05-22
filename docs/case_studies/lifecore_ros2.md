# Case study: lifecore_ros2

Date: 2026-05-22
RSM version: 0.23.3
Target repo: [apajon/lifecore_ros2](https://github.com/apajon/lifecore_ros2)
Validation type: local dogfooding, static source only

---

## Scope

This case study records the results of running RSM against `lifecore_ros2`, a ROS2
lifecycle-component library written in Python. All results were regenerated locally
from the current repo state. No assumptions were carried forward from memory.

Validation constraints:

- local source-only, no LLM calls, no embeddings
- no runtime imports, no runtime ROS introspection
- static AST extraction only
- `confirmed PublicAPI` means explicitly exported via `__init__.py`; it is not an
  API stability promise
- token estimates are approximate (`chars / 4`)
- this is dogfooding evidence for the RSM toolchain, not a scientific benchmark

---

## Commands used

```bash
# RSM version
uv run python -c "import repo_semantic_memory; print(repo_semantic_memory.__version__)"
# 0.23.3

# Index
uv run rsm index ../lifecore_ros2 --db .rsm/lifecore_ros2.sqlite

# Repo-map
uv run rsm repo-map \
  --db .rsm/lifecore_ros2.sqlite \
  --budget 8000 \
  --profile agent_standard \
  > /tmp/lifecore_repo_map.md

# Context packs (all with --explain-ranking)
uv run rsm pack \
  --task "Find public API exported by the package" \
  --db .rsm/lifecore_ros2.sqlite --budget 8000 --profile agent_standard \
  --format yaml --explain-ranking \
  > /tmp/lifecore_public_api_pack.yaml

uv run rsm pack \
  --task "Find where activation gating is implemented" \
  --db .rsm/lifecore_ros2.sqlite --budget 8000 --profile agent_standard \
  --format yaml --explain-ranking \
  > /tmp/lifecore_activation_impl_pack.yaml

uv run rsm pack \
  --task "Find regression tests for activation gating behavior" \
  --db .rsm/lifecore_ros2.sqlite --budget 8000 --profile agent_standard \
  --format yaml --explain-ranking \
  > /tmp/lifecore_activation_regression_pack.yaml

uv run rsm pack \
  --task "Find lifecycle component ownership and cleanup rules" \
  --db .rsm/lifecore_ros2.sqlite --budget 8000 --profile agent_standard \
  --format yaml --explain-ranking \
  > /tmp/lifecore_cleanup_pack.yaml
```

---

## Index findings

```
entities=1923  relations=3256
```

The index covers modules, classes, functions, methods, docs, and config files.
Relations include `contains`, `imports`, `inherits`, `exports`, `tests`, and others
inferred by the test-relationships extractor.

---

## Repo-map summary

Generated at budget 8000, profile `agent_standard`.
Top-ranked entries: `src/lifecore_ros2/__init__.py`, the components sub-package
`__init__.py`, and the `lifecycle_parameter_component.py` module. Budget was
reached before exhausting all symbols; a `[truncated: budget reached]` marker
appears for lower-priority files.

---

## Context-pack findings

### Task: Find public API exported by the package

| Metric                  | Value |
|-------------------------|-------|
| Entities selected        | 22    |
| Relations selected       | 1 (`exports`) |
| Semantic components      | 2 (`PublicAPI ×1`, `TestTarget ×1`) |
| Source citations         | 23    |
| Suggested files          | 12    |
| Truncated                | yes   |
| Uncertainties            | 1     |

The single `exports` relation comes from `src/lifecore_ros2/__init__.py`.
The `PublicAPI` component on `lifecore_ros2` (module) is `status: confirmed`,
meaning RSM found an explicit `__all__` or `__init__.py` export, not a heuristic
guess.

Top suggested files: `src/lifecore_ros2/__init__.py`,
`src/lifecore_ros2/components/__init__.py`,
`src/lifecore_ros2/core/__init__.py`,
`src/lifecore_ros2/testing/__init__.py`.

One uncertainty was surfaced: an unresolved export target
(`ComponentDependencyError` from `.core`) whose declaration was not found in the
indexed entities. RSM surfaces this rather than silently dropping it.

**Noise observed:** several doc-path and `.github/instructions` files ranked
highly on lexical grounds (`"api"` token hit on path name). The `agent_standard`
profile applies a `-5.0 penalty` for docs/prose when the task hint is
`public_api`, but some doc-type files still entered the selected set because the
budget was large relative to the purely source-matching candidates.

### Task: Find where activation gating is implemented

| Metric                  | Value |
|-------------------------|-------|
| Entities selected        | 21    |
| Relations selected       | 1 (`contains`) |
| Semantic components      | 22 (`ExternalIntegration ×6`, `TestTarget ×13`, `TestFile ×1`, `LifecycleManaged ×2`) |
| Source citations         | 22    |
| Suggested files          | 9     |
| Truncated                | yes   |

Top entities: `lifecore_ros2.core.activation_gating` (module),
`tests.core.test_activation_gating` (module),
`lifecore_ros2.core.activation_gating.require_active` (function),
`lifecore_ros2.testing.assertions.assert_activation_gated` (function).

Top suggested files: `src/lifecore_ros2/core/activation_gating.py`,
`tests/core/test_activation_gating.py`,
`src/lifecore_ros2/testing/assertions.py`,
`src/lifecore_ros2/core/lifecycle_component.py`.

The `contains` relation links the `activation_gating` module to the
`require_active` function directly. The ranking correctly surfaced the
implementation module as the primary target and its corresponding test
module alongside it.

### Task: Find regression tests for activation gating behavior

| Metric                  | Value |
|-------------------------|-------|
| Entities selected        | 21    |
| Relations selected       | 1 (`tests`, `status: inferred`, heuristic: `file_path`) |
| Semantic components      | 28 (`TestTarget ×18`, `ExternalIntegration ×7`, `LifecycleManaged ×2`, `TestFile ×1`) |
| Source citations         | 22    |
| Suggested files          | 7     |
| Truncated                | yes   |

The `tests` relation (`confidence: 0.85`, extractor: `test_relationships`)
links `tests/core/test_activation_gating.py` to
`src/lifecore_ros2/core/activation_gating.py` via file-path heuristic.

Top entities include `TestPublisherActivationGating`,
`TestSubscriberActivationGating`, and a Copilot regression-test instruction
doc that ranked lexically on `"activation"` + `"gating"`.

Top suggested files: `tests/core/test_activation_gating.py`,
`tools/copilot/instructions/regression-tests.instructions.md`,
`tests/components/test_watchdog_component.py`,
`src/lifecore_ros2/core/activation_gating.py`.

The instruction doc appearing in suggestions is a true positive for agent
context (it documents the regression-test policy), though it is not
implementation code.

### Task: Find lifecycle component ownership and cleanup rules

| Metric                  | Value |
|-------------------------|-------|
| Entities selected        | 19    |
| Relations selected       | 1 (`tests`, `status: inferred`, heuristic: `direct_import`) |
| Semantic components      | 13 (`LifecycleManaged ×8`, `ROSLikeIntegration ×4`, `TestFile ×1`) |
| Source citations         | 20    |
| Suggested files          | 9     |
| Truncated                | yes   |

Top entities: `tests.components.test_cleanup_ownership` (module),
`lifecore_ros2.core.lifecycle_component.LifecycleComponent` (class),
`LifecycleComponent._on_cleanup` and `on_cleanup` (methods).

The `tests` relation links `test_cleanup_ownership.py` to the
`lifecore_ros2.components` package via `direct_import` heuristic.

Top suggested files: `tests/components/test_cleanup_ownership.py`,
`src/lifecore_ros2/core/lifecycle_component.py`,
`src/lifecore_ros2/components/lifecycle_parameter_component.py`,
`src/lifecore_ros2/components/lifecycle_watchdog_component.py`.

The eight `LifecycleManaged` components are all `status: inferred`; they were
assigned by the ECS extractor based on lifecycle-hook heuristics, not declared
in source.

---

## Artifact leakage check

None of the generated context packs include paths or identifiers from the
`repo-semantic-memory` indexer working directory (e.g., `.rsm/lifecore_ros2.sqlite`
or other RSM repo paths). Outputs are scoped to the indexed target repo only.

---

## Quality checks

```
uv run ruff format --check .   →  95 files already formatted
uv run ruff check .            →  All checks passed!
uv run mypy src                →  Success: no issues found in 52 source files
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest  →  385 passed in 1.97s
```

---

## Lessons from prompts 34.1 / 34.2 / 34.3

These three incremental hardening passes directly improved what this case study
can demonstrate:

**34.1 — Generated-artifact filtering:**
Before 34.1, generated build directories (`dist/`, `*.egg-info/`, `docs/_build/`)
were indexed and polluted entity counts and context packs with non-source symbols.
After: artifact detection is centralized in `path_roles.py`
(`is_generated_artifact_path()`), and generated-path entities are excluded from
packs by default. The lifecore_ros2 index (1923 entities, 3256 relations) reflects
clean source-only coverage.

**34.2 — Source-first ranking:**
Before 34.2, doc-path and config entities with incidental lexical hits could
dominate context-pack slots. After: the ranker boosts source path roles and
applies targeted penalties for docs/prose/tool paths when the task hint signals
implementation or public-API intent. The activation-gating packs correctly rank
the `activation_gating.py` module and `require_active` function above unrelated
doc files.

**34.3 — Relation budgeting in explain-ranking mode:**
Before 34.3, budget caps on related-symbol counts could filter out `exports`,
`tests`, and source `contains` relations before the agent saw them. After:
relations are task-priority ordered before the profile cap is applied, so the one
critical relation per pack (`exports`, `contains`, `tests`) is not dropped.

---

## Known limitations

1. **Truncated packs.** All four packs hit the 8000-token budget before exhausting
   candidates. Higher budgets or tighter scoping would include more context.

2. **Unresolved `exports` targets.** `ComponentDependencyError` from `.core` is
   exported in `__init__.py` but its class definition was not indexed (possibly
   because the symbol name does not appear at module top-level). RSM surfaces this
   as an uncertainty; it does not silently drop it.

3. **Inferred `tests` and `LifecycleManaged` components.** All `tests` relations
   and `LifecycleManaged`/`ROSLikeIntegration` components carry `status: inferred`.
   Heuristic confidence is noted (0.85 for file-path-matched tests), but these are
   not confirmed structural claims.

4. **Doc and tool noise in public-API task.** When the task wording contains
   `"api"`, docs and Copilot instruction files with `"api"` in their path rank on
   lexical score. Profile penalties dampen but do not eliminate them under a large
   budget.

5. **No call graph, type inference, or import resolution.** RSM performs static
   structural indexing only. Cross-module call flows (e.g., which node calls
   `require_active` at runtime) are not captured.

6. **No ROS-specific extraction.** ROS message types, action servers, service
   interfaces, and node graph topology are outside RSM's current scope.

7. **Single-target validation scope.** This case study covers one Python ROS2
   library. Results are not generalizable to other languages or project structures.

---

## Public wording guidance

When referencing this case study:

- Say: *"RSM indexed lifecore_ros2 and surfaced activation-gating implementation
  files and regression tests via static extraction."*
- Do not say: *"RSM understands ROS2 lifecycle semantics"* — it does not import
  or introspect ROS at runtime.
- Do not say: *"`confirmed PublicAPI` means the API is stable"* — it means the
  symbol was explicitly exported in `__init__.py`.
- Do not say: *"token savings are precise"* — estimates use `chars / 4` and are
  directional only.
- Do not say: *"this proves RSM is better than alternatives"* — this is internal
  dogfooding against one known repo, not a controlled study.
