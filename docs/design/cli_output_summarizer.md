# CLI output summarizer design

This document captures a future design for summarizing validation output in
`repo-semantic-memory`. It is design-only: it does not add a runtime command,
shell integration, MCP handler, dependency, or command execution behavior.

## Why this exists

Coding agents often spend too much context on long command outputs before they
can identify the small set of facts that matter for the task. Validation logs
are noisy, but they also contain useful semantic signals:

- failed tests
- error locations
- changed files
- benchmark regressions
- `mypy` and `ruff` issues

RSM can eventually summarize these artifacts as compact, repo-aware context.
The summarizer should treat command output as another local artifact to parse,
normalize, cite, and optionally enrich with indexed repository structure.

This should not turn RSM into RTK, a terminal proxy, or a command execution
wrapper. The goal is deterministic noise filtering and optional semantic
enrichment, not command interception.

## What RSM should not do

The future summarizer must not introduce:

- shell hooks
- transparent command rewriting
- command execution
- terminal proxy behavior
- telemetry
- automatic network uploads
- hidden mutation of repository state
- automatic patching

It should only summarize explicit stdin or file input provided by the caller.

## Supported future inputs

The first supported input formats should be validation and repository-state
artifacts that are already common in RSM workflows:

- `pytest` output
- `ruff` output
- `mypy` output
- `git diff`
- `git status`
- coverage reports
- benchmark compare JSON
- benchmark retrieval JSON

Each parser should fail clearly when input is malformed, truncated in a way that
prevents confident parsing, or from an unsupported version/format.

## Intended future outputs

Summaries should be compact, deterministic, and optimized for agent triage.
Possible output sections include:

- failed tests only
- changed files
- error locations
- symbols implicated by errors
- related entities from the index
- suggested context-pack queries
- benchmark regression summary
- token-savings regression summary
- generated-artifact leakage summary

The summary should preserve enough source pointers for the agent to decide what
to inspect next, while avoiding full source body leakage or a claim that the
summary replaces the original log in ambiguous debugging cases.

## Possible future commands

The future CLI surface could be explicit and stdin-driven:

```bash
rsm summarize-output pytest < pytest.log
rsm summarize-output ruff < ruff.log
rsm summarize-output mypy < mypy.log
rsm summarize-output git-diff < diff.patch
rsm summarize-output git-status < status.txt
rsm summarize-output benchmark < compare.json
```

The command names are provisional. They should not be added until parser
contracts, output schemas, and quality tests exist.

## Optional future integration

If `--db` is provided, the summarizer could enrich parsed events with indexed
repository context:

- map error paths and line ranges to indexed symbols
- attach related entities from the structural graph
- suggest `rsm pack --task ...` commands
- detect changed files missing from a context pack
- detect benchmark regressions by category
- detect generated artifact leakage
- detect token-savings regression
- detect loss of gold coverage in benchmark reports

Enrichment should remain optional. A parser should still produce a useful
summary without an index database.

## Safety model

The safety boundary is intentionally narrow:

- stdin/file input only
- no command execution
- no shell wrapping
- no hidden calls to `pytest`, `ruff`, `mypy`, or `git`
- no network
- deterministic parsing
- clear parser failure modes
- no automatic repository mutation
- no automatic patch generation
- no claim that summarized output replaces reading the original log when
  debugging is ambiguous

Parser output should state when it is incomplete, uncertain, or based on an
unrecognized format. Any repo-aware claim must either be backed by index
evidence or marked as uncertain.

## Deferred implementation

Runtime implementation should be deferred until:

- the public-readiness pass is complete
- MCP handlers are stable
- benchmark output shape is stable
- command-output examples are collected
- failure modes are known
- output schemas are designed
- summary quality can be tested against real logs

Deferring runtime work avoids freezing a CLI contract before RSM knows which
log shapes, benchmark schemas, and agent workflows need first-class support. It
also keeps the current MVP focused on deterministic indexing, context packs,
benchmarks, and explicit evidence.

## Suggested future architecture

A future implementation could use this pipeline:

```text
stdin/file log
→ parser
→ normalized event model
→ optional repo index enrichment
→ compact deterministic summary
→ optional context-pack suggestion
```

Possible future module layout:

```text
src/repo_semantic_memory/outputs/
  parsers/
    pytest.py
    ruff.py
    mypy.py
    git_diff.py
    git_status.py
    benchmark.py
  summary.py
  models.py
```

The parser layer should only transform raw input into normalized events. Repo
index enrichment, output rendering, and context-pack suggestions should stay in
separate modules so the parser contracts remain testable and deterministic.

### Potential normalized event model

A future event model could capture validation facts without preserving entire
logs:

```python
ValidationEvent(
    source="pytest",
    severity="error",
    path="tests/test_example.py",
    line=42,
    symbol="test_example",
    message="AssertionError: ...",
)
```

The final model should use explicit enums or constrained strings for source and
severity, stable path normalization, optional line/column ranges, optional
symbol IDs when index enrichment is available, and uncertainty notes when a
parser infers rather than directly observes a field.

## Benchmarking future summarizer quality

The future summarizer should be tested before it is exposed as a runtime CLI
feature. Suggested quality checks:

- fixture logs for each supported input source
- deterministic golden summaries
- changed-file detection accuracy
- failed-test extraction accuracy
- no false command execution
- no source body leakage
- compactness under a character budget
- correct suggested context-pack query

Benchmark fixtures should include clean runs, single failures, multiple
failures, truncated logs, malformed input, generated artifact paths, benchmark
regressions, token-savings regressions, and loss of gold coverage. Golden
outputs should verify stable ordering and clear uncertainty reporting.

## Relationship to RTK

RTK-like tools optimize command output for agents by filtering noisy terminal
streams into compact summaries. RSM should borrow the concept of noise filtering
and token-aware summaries, especially for validation output that would otherwise
consume large context windows.

RSM should not become a shell proxy or transparent command wrapper. Its
differentiator would be repo-aware enrichment from its semantic index: mapping
log events to symbols, related entities, context-pack queries, benchmark
coverage, generated-artifact leakage, and evidence-backed repository context.

