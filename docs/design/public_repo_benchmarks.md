# Public repository benchmark suite

Status: design.

RSM is currently validated mostly through dogfooding on `repo-semantic-memory`
and `lifecore_ros2`. Those repositories are useful because they expose real RSM
workflows, but they are not enough evidence for broader retrieval-quality claims.
This design defines a staged public-repository benchmark strategy that keeps the
suite deterministic, source-cited, opt-in, and separate from normal unit tests.

## Goals

- Add well-known public Python repositories to retrieval validation.
- Exercise source-cited context packs, repo maps, graph ranking, index-store
  workflows, staleness detection, incremental indexing, and MCP retrieval against
  repositories RSM was not built on.
- Use pinned public repository refs and human-authored gold files/symbols.
- Keep benchmark execution local and explicit.
- Report quality as benchmark-specific retrieval evidence, not broad superiority.

## Non-goals

- Do not clone huge repositories blindly.
- Do not vendor public repositories into this repository.
- Do not add network-dependent CI.
- Do not benchmark private repositories.
- Do not use an LLM judge by default.
- Do not make public-repository benchmark execution mandatory in normal unit
  tests.
- Do not turn benchmark results into marketing claims or broad superiority
  statements.

## Staged strategy

### Stage 0: design and manifest only

Define the benchmark shape, candidate repositories, task categories, and dataset
format. No public repositories are cloned by default and no CI job runs the suite.

### Stage 1: manual Tier 1 pilot

Use a small manifest of pinned Tier 1 repositories. A maintainer explicitly clones
or updates each repository outside this repository, indexes it locally, and runs
retrieval tasks against the pinned ref. Results are stored as local reports unless
a later task explicitly defines committed report artifacts.

### Stage 2: repeatable local harness

Add opt-in commands that read the manifest, verify local checkout refs, run RSM
indexing/retrieval, and produce deterministic reports. The harness should fail
closed when a repo is missing, dirty, or at the wrong ref instead of fetching from
the network implicitly.

### Stage 3: curated expansion

After Tier 1 produces stable signal, add Tier 2 repositories with more framework,
typing, docs, and plugin complexity. Expand only when task gold can be maintained
with source citations.

### Stage 4: heavy-repository research

Evaluate Tier 3 repositories only after the harness handles large indexes, noisy
dependency structures, generated files, and runtime/CI complexity. Tier 3 results
should be treated as stress tests rather than first-line quality claims.

## Candidate repository tiers

### Tier 1: initial practical Python-first set

| Repository | GitHub URL | Why useful | Expected challenge | Size | Python-first | Indexing risk | Suggested task categories |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `rich` | <https://github.com/Textualize/rich> | Popular library with a clear public API, examples, docs, console rendering, and tests. | Distinguishing public API surfaces from renderer internals and docs/examples. | Medium | Yes | Low to medium | public API lookup, implementation location, docs/concepts, test/regression location, error handling |
| `typer` | <https://github.com/fastapi/typer> | Compact CLI framework with public decorators, command registration, docs, and examples. | Connecting user-facing CLI concepts to Click-backed implementation details. | Small | Yes | Low | public API lookup, implementation location, docs/concepts, configuration/build/release |
| `httpx` | <https://github.com/encode/httpx> | Widely used HTTP client with sync/async APIs, transports, timeouts, exceptions, and tests. | Mapping behavior across public clients, transports, configuration, and exception handling. | Medium | Yes | Medium | public API lookup, implementation location, test/regression location, error handling, cross-file architecture |
| `pytest` | <https://github.com/pytest-dev/pytest> | Mature test framework with plugin loading, configuration discovery, fixtures, and docs. | Large plugin/configuration surface and many historically layered internals. | Large | Yes | Medium to high | configuration/build/release, implementation location, docs/concepts, cross-file architecture, error handling |
| `fastapi` | <https://github.com/fastapi/fastapi> | Popular API framework with routing, dependency injection, OpenAPI generation, docs, and tests. | Connecting high-level docs and public APIs to implementation spread across routing, params, and dependency utilities. | Medium | Yes | Medium | public API lookup, implementation location, docs/concepts, test/regression location, cross-file architecture |
| `black` | <https://github.com/psf/black> | Formatter with CLI, parser/mode configuration, error handling, tests, and release metadata. | Separating formatting engine, grammar/parser behavior, CLI flags, and regression tests. | Medium | Yes | Medium | implementation location, test/regression location, configuration/build/release, error handling |

Tier 1 is intentionally Python-first and practical. These projects are known
enough to make benchmark tasks understandable, but they should still be small
enough to curate manually before automation exists.

### Tier 2: broader and harder

| Repository | GitHub URL | Why useful later | Why it should wait |
| --- | --- | --- | --- |
| `pydantic` | <https://github.com/pydantic/pydantic> | Exercises validation, typing, public API lookup, error handling, compiled-core boundaries, and docs. | Wait until Tier 1 works because v2 spans Python APIs plus `pydantic-core`, increasing cross-language and packaging complexity. |
| `textual` | <https://github.com/Textualize/textual> | Exercises framework architecture, widgets, app lifecycle, CSS-like styling, events, examples, and docs. | Wait because the framework is larger and more architecture-heavy than `rich`; gold tasks may require deeper domain knowledge. |
| `django` | <https://github.com/django/django> | Exercises a long-lived web framework with settings, apps, ORM, middleware, docs, and regression tests. | Wait because the repository is large, historically layered, and has broad subsystem boundaries that can dilute early signal. |
| `ansible` | <https://github.com/ansible/ansible> | Exercises plugin/module loading, CLI/configuration, collections, docs, and large-scale Python project structure. | Wait because the repository is large, has noisy plugin/module structure, and may stress source-root and generated-artifact filtering. |

Tier 2 should be added only after Tier 1 has stable manifest handling, task
curation rules, and report interpretation.

### Tier 3: heavy and later

| Repository | GitHub URL | Why not a first benchmark |
| --- | --- | --- |
| `pandas` | <https://github.com/pandas-dev/pandas> | Large repository with generated files, compiled extensions, C/Cython components, complex CI/runtime dependencies, and noisy dependency structure. It is valuable as a later stress test but too expensive for first-line benchmark design. |
| `scikit-learn` | <https://github.com/scikit-learn/scikit-learn> | Large repository with compiled extensions, generated artifacts, examples, documentation, and non-trivial runtime dependencies. Initial RSM benchmark signal could be dominated by build/layout complexity rather than retrieval quality. |
| `home-assistant` | <https://github.com/home-assistant/core> | Very large Python project with thousands of integrations, generated/noisy files, complex dependency structure, and runtime/CI assumptions. It is useful later for scale and noise testing but not for the first public benchmark suite. |

Tier 3 repositories should be explicitly labeled stress/scale benchmarks. They
should not block ordinary development and should not be run by default.

## Benchmark task categories

Each task should be a source-cited retrieval question with human-authored gold
files and, when practical, gold symbols. The prompt should be realistic for a
coding agent that needs a compact starting context.

### Public API lookup

Find the public surface a user should import or call.

- Find the public API for console output.
- Find the public API for defining a CLI command.

### Implementation location

Find where user-visible behavior is implemented.

- Find where CLI command registration is implemented.
- Find where timeout behavior is configured.

### Test/regression location

Find tests that cover a behavior or bug-prone path.

- Find tests covering parser error handling.
- Find tests covering configuration file discovery.

### Configuration/build/release

Find packaging, configuration, build, or release behavior.

- Find where project metadata and package entry points are configured.
- Find where release notes or version metadata are generated.

### Docs/concepts

Find documentation that explains a concept or extension point.

- Find the docs section explaining extension points.
- Find the docs explaining how users configure timeout behavior.

### Cross-file architecture

Find related components spread across multiple modules.

- Find where plugin loading is implemented.
- Find the main modules involved in request routing.

### Error handling

Find exception classes, error formatting, or failure behavior.

- Find where invalid user configuration errors are raised and formatted.
- Find tests and implementation for parser error handling.

## Dataset format

Public-repository benchmarks should use a separate manifest, likely:

```text
benchmarks/public_repos.yaml
```

The manifest should describe repositories, pinned refs, local checkout
expectations, and task files without vendoring repository contents.

Example shape:

```yaml
repositories:
  - name: rich
    url: https://github.com/Textualize/rich
    ref: "<pinned commit sha or release tag>"
    size_category: medium
    python_first: true
    indexing_risk: low-medium
    checkout:
      mode: external
      path_env: RSM_BENCH_RICH_PATH
    tasks:
      - id: rich_public_console_api
        category: public_api_lookup
        prompt: "Find the public API for console output."
        gold:
          files:
            - rich/console.py
            - rich/__init__.py
          symbols:
            - rich.console.Console
      - id: rich_parser_error_tests
        category: test_regression_location
        prompt: "Find tests covering parser error handling."
        gold:
          files:
            - tests/test_console.py
          symbols: []
```

Recommended top-level fields:

- `repositories`: list of benchmark repositories.
- `name`: short stable repository name used in reports.
- `url`: canonical public GitHub URL.
- `ref`: pinned commit SHA or release tag. Commit SHAs are preferred for
  reproducibility.
- `size_category`: `small`, `medium`, or `large`.
- `python_first`: boolean.
- `indexing_risk`: qualitative risk such as `low`, `medium`, `high`, or a
  combined value when the risk is between categories.
- `checkout.mode`: `external` for local checkouts managed outside this
  repository.
- `checkout.path_env`: environment variable that points to the local checkout.
- `tasks`: retrieval tasks for that repository.

Recommended task fields:

- `id`: stable unique task identifier, prefixed by repository name.
- `category`: one of the benchmark task categories.
- `prompt`: natural-language retrieval prompt.
- `gold.files`: repository-relative POSIX paths.
- `gold.symbols`: indexed qualified names when stable enough to curate.
- `gold.notes`: optional source-citation notes for maintainers; not part of
  scoring unless a future schema explicitly supports it.

The existing internal `benchmarks/tasks.yaml` shape can remain unchanged. Public
repository support can either extend the loader to understand `repositories` or
use a small adapter that flattens each repository's tasks into the existing
retrieval dataset model after verifying the local checkout and pinned ref.

## Execution policy

- Public repositories are never cloned during normal unit tests.
- CI should not depend on network access for these benchmarks.
- A local harness may verify that each external checkout exists and matches its
  pinned ref.
- Index output should be written to `.rsm/` in the external checkout or to the
  RSM Index Store, not committed to this repository.
- Benchmark reports should include repository name, pinned ref, RSM version,
  index metadata, task count, category breakdowns, and interpretation limits.
- Missing repositories should produce a skipped/blocked report, not a hidden
  network fetch.

## Scoring and interpretation

Initial scoring should remain deterministic:

- gold file recall
- gold symbol recall
- MRR or rank of first relevant gold target
- per-category breakdowns
- generated-artifact false positives where path-role rules can detect them

No LLM judge should be used by default. If optional qualitative review is added
later, it should be clearly labeled as non-default and separate from deterministic
metrics.

Results should be described as:

- "On this pinned public-repository benchmark set..."
- "For these task categories..."
- "Against these gold files/symbols..."

Results should not be described as:

- proof that RSM is broadly superior
- proof of end-to-end coding success
- representative of all Python repositories
- a marketing claim

## Acceptance criteria for adding a repository

A repository is ready for the public benchmark manifest when:

- it has a pinned public ref;
- it can be indexed locally without special network-dependent setup;
- generated/build/cache paths can be excluded or tolerated;
- at least three tasks have reviewed gold files;
- at least one task includes gold symbols when symbols are stable;
- task categories add coverage not already dominated by existing repositories;
- interpretation limits are documented in the report.

## First pilot recommendation

Start with three Tier 1 repositories before enabling all six:

1. `typer` for a small CLI-oriented project.
2. `rich` for public API, rendering, docs, and tests.
3. `httpx` for sync/async architecture, configuration, and error handling.

Once those produce stable local reports, add `fastapi`, `black`, and `pytest` to
increase framework, formatter, plugin/configuration, and larger-project coverage.
