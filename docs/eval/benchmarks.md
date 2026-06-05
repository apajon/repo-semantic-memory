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

## 59.0 Benchmark harness datasets

The 59.0 benchmark harness supports two dataset schemas:

### CI benchmark cases (`benchmarks/ci_benchmark_cases.yaml`)

Local deterministic cases running against checked-in fixtures (`tests/fixtures/ranking_repo/`).
These run with `--mode ci` (the default) and require no external repositories.

```bash
rsm index tests/fixtures/ranking_repo --db .rsm/ci_index.sqlite
rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml --db .rsm/ci_index.sqlite
```

### Manual external benchmark cases (`benchmarks/manual_external_benchmark_cases.yaml`)

Opt-in cases migrated from the Ranking v2 regression evaluation (58.6 report).
These target public repositories — Django, Ansible, HTTPX, Typer — and use `mode: manual_external`.

**Manual external benchmarks are opt-in.** External repos are:
- **Not cloned automatically.** You must check out each repo at the pinned revision
  listed in `benchmarks/public_repos.yaml`.
- **Not required for CI.** `--mode ci` (the default) silently skips all
  `manual_external` cases.
- **Not indexed automatically.** You must run `rsm index` once per external repo.

#### Manual execution walkthrough

Prerequisites: a local checkout and a pre-built RSM index for each repository.

```bash
# Clone once (example: Typer at pinned revision)
git clone https://github.com/fastapi/typer /tmp/typer-bench
cd /tmp/typer-bench && git checkout 8c70d4987284a37ca6c418297af0210dc01ed5ac

# Index once
rsm index /tmp/typer-bench --db /tmp/rsm-typer.sqlite

# Run a single case
rsm eval bench \
  --dataset benchmarks/manual_external_benchmark_cases.yaml \
  --mode manual \
  --case typer_command_registration \
  --db /tmp/rsm-typer.sqlite

# Run all manual cases for one repo
rsm eval bench \
  --dataset benchmarks/manual_external_benchmark_cases.yaml \
  --mode manual \
  --db /tmp/rsm-typer.sqlite

# JSON output
rsm eval bench \
  --dataset benchmarks/manual_external_benchmark_cases.yaml \
  --mode manual \
  --db /tmp/rsm-typer.sqlite \
  --json

# Markdown report
rsm eval bench \
  --dataset benchmarks/manual_external_benchmark_cases.yaml \
  --mode manual \
  --db /tmp/rsm-typer.sqlite \
  --markdown-report /tmp/bench-report.md
```

#### Filtering by mode

- `--mode ci` (default): runs only `ci_fixture` cases, skips `manual_external`.
- `--mode manual`: runs only `manual_external` cases, skips `ci_fixture`.

If no cases match the selected mode, the command exits with code 2 and a clear
message on stderr. This is expected when running `--mode manual` against a CI-only
dataset or vice versa.

#### Dataset migration provenance

Every case in `manual_external_benchmark_cases.yaml` is tagged `58.6_migration`.
Expected and forbidden files trace back to explicit rows in
`docs/reviews/ranking_v2_regression_eval.md`. The `notes` field on each case
preserves the original 58.6 score summary and root-cause diagnosis.
