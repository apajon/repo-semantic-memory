# Case study: lifecore_ros2

Date: 2026-05-22
Target repo: [apajon/lifecore_ros2](https://github.com/apajon/lifecore_ros2)
Validation type: local static dogfooding run

## Scope

This report summarizes one fresh RSM run against `lifecore_ros2`, a Python ROS2
lifecycle-component library. It focuses on what RSM gives a coding agent beyond
a broad repo-map, grep search, or README scan: task-specific context,
source-backed entities, structural relations, and generated-artifact suppression.

Constraints:

- Static source extraction only; no runtime ROS introspection.
- No LLM calls, embeddings, or external semantic services.
- The source repository was cloned locally and indexed once before all derived outputs were generated.
- Context-pack claims are interpreted with their explicit status: `confirmed` for source-backed exports, `inferred` for heuristic relations/components.
- This is dogfooding evidence for RSM behavior, not scientific proof or a controlled benchmark.

## Revision context

- RSM branch used for generation: `copilot/create-docs-case-studies-lifecore-ros2`.
- RSM short commit used for generation: `71a5988`.
- RSM version for generated outputs: `0.23.4.dev1+g71a59888b`.
- `lifecore_ros2` branch: `main`.
- `lifecore_ros2` short commit: `ea220f1`.
- `lifecore_ros2` working tree status during validation: clean.

This case study intentionally uses `lifecore_ros2` `main`, the release/PyPI-facing branch. It should not be compared directly with earlier Prompt 35 hardening-validation counts from `dev-lifecore_state`.

## Commands used

The run used one local index, one repo-map, and four task-specific context packs with
an 8000-character budget and the `agent_standard` profile. The context packs used
`--format yaml` and `--explain-ranking` for these tasks:

- “Find public API exported by the package”.
- “Find where activation gating is implemented”.
- “Find regression tests for activation gating behavior”.
- “Find lifecycle component ownership and cleanup rules”.

No raw repo-map, terminal transcript, or context-pack output is reproduced here.

## What RSM adds beyond a repo map

A repo-map is useful for broad orientation: it helps an agent see the main files,
modules, and rough project shape. A context-pack is useful for task-specific
work: it changes what is selected and ranked based on the prompt.

The useful behavior in this run was not just finding files with matching words.
RSM selected different context for different tasks: exports for a public API
question, implementation symbols for an implementation question, and tests for
a regression question. It also preserved compact structural relations such as
`exports`, `contains`, and `tests`, so an agent receives navigational structure
rather than only file names or prose matches.

That matters because grep or a README scan can find shared words like
“activation”, “lifecycle”, or “public API”, but they do not label whether a
match is an exported package surface, an implementation symbol, or a regression
test. RSM's value here is narrower: it gives a source-cited, task-shaped
starting point that an agent can verify against the repository.

## Task-centered findings

Index size for the `lifecore_ros2` run: 1923 entities and 3256 relations.

### 1. Public API surface

- Question: “Find public API exported by the package”.
- Why this is hard: docs, tools, and README text can mention public API without being the exported package surface.
- What RSM surfaced: package `__init__.py` context, exported symbols, 1 retained `exports` relation, and 1 `PublicAPI` component with `status: confirmed`.
- Why it matters: an agent gets a source-backed API surface instead of prose-only matches. One unresolved export target, `ComponentDependencyError`, was reported as an uncertainty rather than silently guessed.

### 2. Activation gating implementation

- Question: “Find where activation gating is implemented”.
- Why this is hard: tests and docs share activation vocabulary with implementation code.
- What RSM surfaced: source implementation context, an implementation symbol, and 1 retained `contains` relation.
- Why it matters: an agent gets an implementation entry point plus nearby verification context, rather than starting from every text match for “activation”.

### 3. Activation gating regression behavior

- Question: “Find regression tests for activation gating behavior”.
- What RSM surfaced: test file/class context and 1 retained `tests` relation.
- Why it matters: a regression-focused task correctly prioritizes tests and keeps the source/test relationship visible for follow-up verification.

### 4. Cleanup / ownership lifecycle

- Question: “Find lifecycle component ownership and cleanup rules”.
- What RSM surfaced: lifecycle implementation context, cleanup-related methods, ownership tests, and 1 useful retained `tests` relation. No `contains` relation fit within the selected relation budget for this pack.
- Why it matters: an agent gets both implementation and behavior evidence, which is more useful for cleanup rules than a flat list of files mentioning lifecycle terms.

## Artifact leakage check

Generated-artifact leakage checks passed for all generated outputs. The repo-map
and context packs did not include forbidden build-output, coverage-output,
package-metadata, local-index, shell-prompt, raw-pack, or volatile
agent-snapshot markers.

## Quality checks

- The forbidden-output grep check returned no matches after this cleanup.
- Ruff format check passed.
- Ruff lint check passed.
- Mypy passed for `src`.
- Pytest passed with plugin autoload disabled.
- Final git status showed only the intended case-study documentation change before commit.

## Lessons from hardening

- Generated-artifact filtering keeps indexed context focused on source, tests, docs, and tracked project files instead of build or coverage byproducts.
- Source-first ranking helps implementation prompts surface code before lower-value prose matches.
- Explain-ranking relation budgeting keeps compact relation signals visible: `exports` for public API, `contains` for implementation, and `tests` for regression or cleanup questions.
- The useful claim is narrower: RSM can provide a small, source-backed, task-shaped context pack with explicit relation evidence.

## Known limitations

- All four context packs were budgeted outputs; selected entities and relations are not exhaustive.
- Ranking is heuristic and should be verified against cited source.
- `confirmed PublicAPI` only means statically exported through package surfaces; it does not imply long-term API stability.
- `tests`, `LifecycleManaged`, and integration-like components in these packs are inferred heuristically, not proven by type analysis or runtime inspection.
- RSM does not resolve all imports or export targets yet; unresolved targets are surfaced as uncertainties.
- RSM does not build a Python call graph, infer ROS node topology, or introspect ROS messages/services/actions at runtime.
- Token estimates are approximate and directional.
- This is one local run against one repository, so the results should not be generalized as benchmark evidence.

## Public wording guidance

Use narrow wording:

- Safe: “RSM indexed lifecore_ros2 and retained compact relation signals for public exports, activation-gating implementation, regression tests, and cleanup ownership.”
- Safe: “The run shows task-specific context selection: exports for an API question, implementation context for an implementation question, and tests for a regression question.”
- Safe: “The run surfaced inferred lifecycle and test relationships with explicit status labels.”

Avoid overclaims:

- Do not claim RSM understands ROS2 lifecycle semantics at runtime.
- Do not claim `confirmed PublicAPI` means stable public API.
- Do not claim this case study proves RSM is better than grep, README scanning, or other retrieval systems.
- Do not claim this case study proves universal coding-agent context coverage.
- Do not quote token savings or benchmark wins from this report; this run was not a benchmark comparison.

RSM’s useful behavior in this run was not just finding matching files; it produced task-shaped, source-cited context with structural relations such as `exports`, `contains`, and `tests`.
