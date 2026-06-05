# Ranking v2 Benchmark Migration — 59.X Status

> **Date:** 2026-06-05
> **Source:** `docs/reviews/ranking_v2_regression_eval.md` (58.6 report)
> **Branch:** `feat/benchmark-harness-59`

## What was migrated

The four manual tasks from the 58.6/58.7 Ranking v2 regression evaluation have been
converted into structured, schema-validated benchmark cases using the 59.0 harness.

Each case preserves the original 58.6 query text, expected central/support/test files,
forbidden noise files, and score summary in the `notes` field.

| 58.6 Task | Case ID | Fixture | Mode | 58.6 Score |
|-----------|---------|---------|------|-----------|
| Django URL resolution | `django_url_resolution` | `django` | `manual_external` | 3/5 |
| Ansible plugin loading | `ansible_loader_discovery` | `ansible` | `manual_external` | 3/5 |
| HTTPX public API | `httpx_public_client_api` | `httpx` | `manual_external` | 4/5 |
| Typer command registration | `typer_command_registration` | `typer` | `manual_external` | 3/5 |

## CI benchmark cases (local fixtures)

Six additional cases were created against the `ranking_repo` checked-in fixture to
exercise the harness deterministically in CI without external repositories.

| Case ID | Fixture | Tests |
|---------|---------|-------|
| `ci_lifecycle_component_impl` | `ranking_repo` | Central file retrieval |
| `ci_state_component_impl` | `ranking_repo` | Central + support via imports |
| `ci_public_api_imports_and_exports` | `ranking_repo` | Public API + support via exports |
| `ci_lifecycle_tests` | `ranking_repo` | Test file retrieval |
| `ci_generated_artifact_forbidden` | `ranking_repo` | Generated doc suppression |
| `ci_example_not_selected_for_impl` | `ranking_repo` | Example path exclusion |

## Dataset files

| File | Schema | Content |
|------|--------|---------|
| `benchmarks/tasks.yaml` | Legacy `RetrievalTask` | Internal retrieval eval (unchanged) |
| `benchmarks/ci_benchmark_cases.yaml` | 59.0 `BenchmarkCase` | 6 CI cases (`ci_fixture`) |
| `benchmarks/manual_external_benchmark_cases.yaml` | 59.0 `BenchmarkCase` | 4 manual cases (`manual_external`) |
| `benchmarks/public_repos.yaml` | Pilot manifest | Repo URLs, pins, path env vars |

## How to run CI benchmarks

```bash
# Index the ranking fixture
rsm index tests/fixtures/ranking_repo --db .rsm/ci_index.sqlite

# Text output
rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml --db .rsm/ci_index.sqlite

# JSON output
rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml --db .rsm/ci_index.sqlite --json

# Markdown report
rsm eval bench \
  --dataset benchmarks/ci_benchmark_cases.yaml \
  --db .rsm/ci_index.sqlite \
  --markdown-report /tmp/rsm-ci-bench.md
```

## How to run manual benchmarks

Prerequisites: local checkout and pre-built RSM index for each target repository.
Pin the revision from `benchmarks/public_repos.yaml`.

```bash
# Clone and index (example: Typer)
git clone https://github.com/fastapi/typer /tmp/typer-bench
cd /tmp/typer-bench && git checkout 8c70d4987284a37ca6c418297af0210dc01ed5ac
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
  --markdown-report /tmp/rsm-typer-bench.md
```

## Mapping to original 58.6 review tasks

Every expected and forbidden file in the manual cases traces back to an explicit
row in the 58.6 report. See the report tables for provenance:

| 58.6 Report Table | Mapped To |
|-------------------|-----------|
| "Selected central files" | `expected.central_files` |
| "Missing central files" | `expected.central_files` (post-58.7 expected) |
| "Selected support files" | `expected.support_files` |
| "Selected test files" | `expected.test_files` |
| "Remaining noise" | `expected.forbidden_files` |
| Score summary | `notes` field |

## Intentionally out of scope

The 59.x benchmark harness explicitly excludes:

- Ranking retuning or behavior changes
- Chunks and embeddings
- Semble backend integration
- CodeGraph backend integration
- Context graph export
- Automatic cloning or downloading of external repos
- Network access during CI
- External repo CI dependency

## 59.x benchmark harness completed

Available:

- Schema-validated benchmark cases (59.0 schema)
- Deterministic metrics (central/support/tests/noise/overall)
- CLI execution (`rsm eval bench`)
- CI fixture dataset (6 cases, `ci_fixture`)
- Manual external dataset (4 cases, `manual_external`)
- JSON output (`--json`)
- Markdown report output (`--markdown-report`)
- Mode filtering (`--mode ci|manual`)
- Case filtering (`--case ID`)

Not included:

- Ranking retune
- Chunks
- Embeddings
- Semble backend
- CodeGraph backend
- Context graph export
