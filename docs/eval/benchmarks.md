# Benchmarks

This benchmark remains a small internal dataset, but it is no longer only a smoke
test. The goal is to expose regressions in retrieval quality across multiple task
shapes without claiming broad scientific superiority.

## Current dataset scope

`benchmarks/tasks.yaml` is a YAML file shaped like:

```yaml
tasks:
  - id: unique_task_id
    category: implementation_localization
    prompt: "Find where compact repo map generation is implemented."
    gold:
      files:
        - src/repo_semantic_memory/context/repo_map.py
      symbols:
        - repo_semantic_memory.context.repo_map.build_repo_map_markdown
```

Each task has one prompt plus gold targets. Gold files are repository-relative paths; gold
symbols are indexed qualified names. Some tasks may later use additional fields such as
`invariants`, but files and symbols are the current core scoring targets.

The dataset currently covers these categories:

- `public_api_localization`
- `implementation_localization`
- `test_localization`
- `doc_localization`
- `generated_artifact_suppression`
- `graph_neighbor_selection`
- `compression_quality`
- `source_root_disambiguation`

The dataset currently includes realistic repository tasks for:

- context pack selection plus graph-neighbor expansion
- repo map generation
- SQLite persistence
- public package exports
- lifecycle cleanup and activation semantics
- benchmark documentation and benchmark runner internals
- JSONL export/import and `.ai` export
- generated-artifact suppression in public-API-oriented ranking
- source-root detection plus source-root regression tests
- compression profile selection and filtering

## Gold targets

Tasks may use these gold fields:

- `files` for repository-relative file localization
- `symbols` for indexed qualified names
- `invariants` when explicitly useful later

`doc_sections` and `relations` remain future extensions and are not scored in this
phase.

## Metrics

`rsm eval retrieval` reports retrieval-oriented metrics such as recall and MRR over the internal
gold targets, plus per-task and per-category breakdowns to localize regressions.

`rsm eval compare` reports shared-budget comparison metrics between baselines, including gold
file/symbol preservation and approximate token-savings style output when coverage is preserved.

## Report expectations

Retrieval and compare reports should stay deterministic and should show:

- aggregate metrics across the whole dataset
- per-category recall and MRR so regressions are easier to localize
- per-category compare summaries so wins/losses are visible by task type
- token-savings summaries when compare output is available
- generated-artifact false positives when selected non-gold files fall into known
  generated/build/cache paths

## Interpretation limits

Keep these limits explicit in every discussion of results:

- The dataset is small and repository-specific.
- Category counts are uneven, so per-category numbers are directional only.
- Results measure retrieval alignment against internal gold targets, not end-to-end
  coding-task success.
- Generated-artifact false positives only cover artifacts detectable by current path-role rules,
  so suppression numbers are incomplete by design.
- No LLM judging is used in this phase.
- No embeddings, vector DB, or runtime MCP server are involved in benchmark generation.

## Near-term benchmark candidates

Next dataset candidates after this expansion:

- explicit relation-level gold once relation retrieval is scored
- doc-section gold for longer design/spec documents
- invariant and claim lookup tasks backed by authored evidence
- cross-repository or public benchmark datasets once internal coverage stabilizes
- patch-context sufficiency tasks aligned with future coding-agent workflows
