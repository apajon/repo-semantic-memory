# repo-semantic-memory

`repo-semantic-memory` (`rsm`) is an **experimental (pre-1.0)** deterministic repository context compiler for coding agents.

It indexes a repository and produces compact, source-cited artifacts (repo maps, task context packs, JSONL graph exports, `.ai/` snapshots) that are local-first and benchmarkable.

This project is intentionally positioned as a repository context compiler, **not** a broad "AI knowledge graph platform".

## Positioning

RSM focuses on:

- deterministic extraction and ranking
- source-cited artifacts tied to code/docs/tests/git metadata
- benchmarkable retrieval and compression behavior
- local-first outputs that can be inspected in plain text

Source of truth always remains the repository itself (code, docs, tests, git history).

## Current status

- MVP is functional
- benchmark dataset has expanded (still small by category)
- token-savings metrics are reported (approximate)
- `.ai/` export exists
- JSONL import/export exists
- ranking explainability exists (`--explain-ranking`)
- deterministic compression profiles exist
- Markdown section extraction exists
- public API export resolver exists
- test relationship extraction exists
- pure MCP handlers may exist depending on merge state

## Quick start

```bash
# install deps
uv sync --all-groups

# build local index
uv run rsm index . --db .rsm/index.sqlite

# compact repository map
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard

# task-specific context pack
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 4000 \
  --profile agent_standard

# deterministic .ai/ artifact export
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force

# JSONL graph portability
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite

# benchmark retrieval
uv run rsm eval retrieval \
  --db .rsm/index.sqlite \
  --dataset benchmarks/tasks.yaml \
  --json

# compare repo-map baseline vs lexical context pack baseline
uv run rsm eval compare \
  --db .rsm/index.sqlite \
  --dataset benchmarks/tasks.yaml \
  --budget 4000 \
  --json
```

## Public API export semantics

RSM extracts Python exports from `__init__.py` via static AST analysis and uses that evidence to mark `PublicAPI` components as `confirmed`.

Important caveat:

- `confirmed PublicAPI` means **explicitly exported in source** (for example via `__all__`/export patterns)
- it does **not** mean a long-term stability guarantee for users of that API

## Test relationship extraction

RSM infers `tests` relations between test entities and implementation entities using deterministic heuristics (for example direct imports and path/symbol signals). These are emitted as inferred relations with metadata and confidence labels.

## Markdown section extraction

RSM indexes Markdown headings as section entities (`doc_section`) with source ranges and stable IDs, then adds `contains` relations between documents and sections (including nested heading structure).

## Compression profiles

`rsm repo-map` and `rsm pack` support deterministic profiles:

- `agent_brief`
- `agent_standard` (default)
- `agent_debug`
- `human_review`
- `ci_summary`
- `full`

Profiles control detail level and noise suppression while preserving deterministic ordering.

## Benchmarks and token-savings caveats

Use local benchmark commands:

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

When discussing results:

- say **"on the current internal benchmark"**
- benchmark categories are still small; results are directional
- token estimate is approximate and deterministic (`estimated_tokens = chars / 4`)
- token savings are only meaningful when gold coverage is preserved
- do not claim scientific superiority

## Illustrative examples (generated, small, non-authoritative)

### 1) Context pack snippet

```markdown
# Context pack
Task: Find explicit public API exports for lifecore_ros2 and related tests

## Selected symbols
- tests.fixtures.ranking_repo.src.lifecore_ros2
- tests.fixtures.ranking_repo.src.lifecore_ros2.components.lifecycle_component.LifecycleComponent

## Suggested files to inspect
- tests/fixtures/ranking_repo/src/lifecore_ros2/__init__.py
- tests/fixtures/ranking_repo/src/lifecore_ros2/components/lifecycle_component.py
```

### 2) Repo-map snippet

```markdown
# Repo map
## src/repo_semantic_memory/cli.py
- module repo_semantic_memory.cli
- function repo_semantic_memory.cli.build_parser
- function repo_semantic_memory.cli.main
```

### 3) Benchmark report snippet

```markdown
# Baseline comparison report
- dataset: benchmarks/tasks.yaml
- tasks: 12
- wins: repo_map=0, lexical_context_pack=11, inconclusive=1
```

### 4) Token-savings example (approximate)

```text
average_estimated_tokens_saved: 442.58
average_compression_ratio: 0.5566
coverage_preserved_tasks: file=12, symbol=12
```

### 5) `.ai/` export listing example

```text
.ai/
  AGENT_COMMANDS.md
  README.md
  context_policy.md
  INDEX.yaml
  symbols.yaml
  relations.yaml
  components.yaml
  repo_map.md
```

### 6) lifecore_ros2 case-study excerpt (fixture-based)

```text
task: package_public_api_exports
category: public_api_localization
fixture files include:
- tests/fixtures/ranking_repo/src/lifecore_ros2/__init__.py
- tests/fixtures/ranking_repo/src/lifecore_ros2/components/lifecycle_component.py
```

All examples above are illustrative snapshots and may become stale after re-indexing.

## `.rsm/` and `.ai/` tracking policy

- `.rsm/` (SQLite index) is local working state and must remain ignored
- volatile `.ai/` snapshots are ignored by default:
  - `.ai/INDEX.yaml`
  - `.ai/symbols.yaml`
  - `.ai/relations.yaml`
  - `.ai/components.yaml`
  - `.ai/repo_map.md`
  - `.ai/invariants.yaml`
- static `.ai` guide/policy templates are intentionally tracked:
  - `.ai/AGENT_COMMANDS.md`
  - `.ai/README.md`
  - `.ai/context_policy.md`

Generated outputs should not be committed accidentally unless a PR intentionally versions them.

## Related work and scope boundaries

Adjacent categories include:

- broad repository knowledge graph tools
- local document/search and code navigation tools
- token/output compression tools for LLM workflows

RSM’s differentiator is the combination of:

- deterministic extraction and ranking
- explicit source citations and uncertainty signaling
- benchmarked context artifacts
- local-first operation and inspectable outputs

RSM does not claim global superiority over other tools or scientific generalization beyond current internal benchmark coverage.

## Limitations

- pre-1.0: API/format ergonomics may evolve
- benchmark categories are still small and not comprehensive
- token metrics are approximate (`chars / 4`), not tokenizer-accurate
- some relations/components are inferred and require source verification
- extracted context is compact by design and may omit useful details for some tasks

## Versioning and license

- package versioning uses python-semantic-release
- project remains in `0.x` (no accidental `1.0.0` path intended)
- `SCHEMA_VERSION` and `CONTEXT_PACK_VERSION` are managed explicitly for compatibility
- license is Apache-2.0 across project metadata and repository license files

## Development checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest
```
