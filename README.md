# repo-semantic-memory

`repo-semantic-memory` is an experimental repository context compiler for coding agents.

It indexes a software repository and produces compact, deterministic, source-cited knowledge artifacts that help agents understand codebases without reading entire files or dumping excessive context.

The project is currently pre-1.0 and under active design.

## What this is

`repo-semantic-memory` is designed to help coding agents answer questions like:

- Which files and symbols are relevant to this task?
- What classes, functions, methods, imports, and relations exist in this repository?
- Can we generate a compact repo map instead of pasting whole files?
- Can we benchmark whether retrieval finds the expected files and symbols?
- Can future context packs be measured against a generic repo map?

The long-term goal is to build a semantic memory layer for repositories, including:

- symbol indexes
- structural relations
- compact repo maps
- task-specific context packs
- evidence-backed semantic components
- claims and invariants
- benchmark reports
- optional MCP integration

## What this is not

This project is not:

- an Obsidian vault generator
- a generic vector database
- a documentation generator
- an IDE replacement
- a language server replacement
- a code completion model
- an LLM wrapper

The first priority is deterministic repository analysis, compact context generation, and measurable retrieval quality.

## Current status

Experimental MVP.

Implemented:

- Python 3.12+ package using `uv`
- CLI entrypoint: `rsm`
- deterministic version contracts
- filesystem scanning
- Python AST symbol extraction
- SQLite local index
- compact repo map generation
- task-specific context pack generation
- local retrieval benchmark harness

Not implemented yet:

- repo-map vs context-pack benchmark comparison
- ECS-style semantic components
- claims and invariants
- `.ai/` export
- JSONL import/export
- git temporal memory
- MCP server
- embeddings
- LLM summarization

## Installation

Clone the repository:

```bash
git clone https://github.com/<owner>/repo-semantic-memory.git
cd repo-semantic-memory
```

Install dependencies:
```bash
uv sync --all-groups
```
Run the CLI:
```bash
uv run rsm --help
uv run rsm version
```

## Quick start

Index a repository into SQLite:
```bash
uv run rsm index /path/to/repo --db .rsm/index.sqlite
```
Inspect indexed entities:
```bash
uv run rsm inspect entities --db .rsm/index.sqlite
```
Inspect indexed relations:
```bash
uv run rsm inspect relations --db .rsm/index.sqlite
```
Generate a compact repo map:
```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000
```
Generate a task-specific context pack in Markdown:
```bash
uv run rsm pack \
  --task "Update DerivedThing imports in src/python_symbols.py" \
  --db .rsm/index.sqlite \
  --budget 4000
```
Generate a task-specific context pack in YAML-compatible structured output:
```bash
uv run rsm pack \
  --task "Update DerivedThing imports in src/python_symbols.py" \
  --db .rsm/index.sqlite \
  --budget 4000 \
  --format yaml
```
Or generate a repo map directly from a path without leaving persistent artifacts:
```bash
uv run rsm repo-map --path /path/to/repo --budget 4000
```
Run a retrieval benchmark:
```bash
uv run rsm eval retrieval \
  --db .rsm/index.sqlite \
  --dataset benchmarks/tasks.yaml
```
Generate JSON output:
```bash
uv run rsm eval retrieval \
  --db .rsm/index.sqlite \
  --dataset benchmarks/tasks.yaml \
  --json
```
Generate a Markdown report:
```bash
uv run rsm eval retrieval \
  --db .rsm/index.sqlite \
  --dataset benchmarks/tasks.yaml \
  --markdown-report retrieval_report.md
```


## CLI overview
```bash
rsm version
rsm scan <path>
rsm index-python <path> --json
rsm index <path> --db .rsm/index.sqlite
rsm inspect entities --db .rsm/index.sqlite [--json]
rsm inspect relations --db .rsm/index.sqlite [--json]
rsm repo-map --db .rsm/index.sqlite --budget 4000
rsm repo-map --path <path> --budget 4000
rsm pack --task "..." --db .rsm/index.sqlite --budget 4000 [--format markdown|yaml]
rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml
```


## Data model

The MVP data model is intentionally small.

Core objects:

StableId

SourceRange

Evidence

Entity

Relation


Supported entity kinds:

repository
package
module
class
function
method
field
test
doc
concept
invariant

Supported relation kinds:

contains
imports
inherits
calls
uses
tests
documents
owns
requires
violates

Relations are currently logical edges keyed by:

(source_id, target_id, kind)

Repeated occurrences of the same logical relation are collapsed. This is deliberate for the MVP. A later schema may add occurrence-level relation IDs if line-level multiplicity becomes important.

## Python extraction

The Python AST extractor currently extracts:

modules

classes

functions

methods

imports

inheritance declarations

source ranges

simple metadata such as docstring presence, decorators, signatures, and async flags


Limitations:

no full type inference

no import resolution

no inheritance target resolution

no call graph extraction yet

no nested function modeling guarantee

no LLM summarization


Unresolved inheritance targets are represented explicitly and must not be treated as resolved graph facts.

## Repo map

The repo map is a compact Markdown representation of indexed symbols.

It includes:

modules

classes

methods

functions

compact imports

source citations


Example:

# Repo map

## src/pkg/module.py

- module `pkg.module` src/pkg/module.py:1-120
- class `pkg.module.MyClass` src/pkg/module.py:10-42
  - method `run` src/pkg/module.py:20-35
- function `pkg.module.helper` src/pkg/module.py:45-51

Imports:
- `typing` static
- `pathlib.Path` static

The --budget option is currently an approximate character budget, not a tokenizer-based token budget.

## Context pack

The context pack is a compact task-specific output generated from indexed entities and relations.

Selection behavior in the MVP:

- lexical matching across entity names, qualified names, source paths, stable IDs, and string-like metadata
- direct graph-neighbor expansion from selected entities
- deterministic ranking and deterministic tie-break by stable ID
- conservative handling of unresolved import/inheritance edges with explicit uncertainty
- no source bodies and no full docstring content in output

`--format yaml` emits a JSON-formatted payload that is YAML 1.2-compatible.

Budget semantics:

- budget is character-based (not tokenizer-based)
- budget is applied during context-pack construction and final Markdown rendering
- selected files are deduplicated, deterministic, and bounded by the budget-constrained selected entities

## Retrieval benchmarks

Retrieval benchmarks are local and deterministic.

Dataset example:

tasks:
  - id: example_001
    category: code_localization
    prompt: "Where is inactive publish gating enforced?"
    gold:
      files:
        - src/example.py
      symbols:
        - example.Symbol
      invariants:
        - inactive_outgoing_calls_forbidden

Gold files should be repository-relative POSIX paths.

Gold symbols are intended to match indexed entity names, qualified names, or IDs depending on benchmark configuration.

Current metrics:

file recall@k

symbol recall@k

file MRR

symbol MRR

approximate context character estimate

gold file coverage

gold symbol coverage


Gold invariants may appear in datasets for future compatibility, but invariant retrieval is not implemented yet.

## Design principles

1. Source remains the source of truth.

Code, docs, tests, and git history are authoritative. Generated memory artifacts must be traceable back to source evidence.


2. Deterministic extraction first.

Prefer AST, filesystem, and static analysis before LLM-generated summaries.


3. Compact context over large dumps.

The project optimizes for concise, cited, task-relevant context.


4. Evidence over vibes.

Semantic claims must eventually carry source evidence or be marked uncertain.


5. Measure before adding complexity.

Repo maps, context packs, ECS components, invariants, embeddings, and MCP integrations should be benchmarked against simpler baselines.



## Versioning

This project uses semantic versioning through python-semantic-release.

The project is still in 0.x development.

Important version contracts:

package version

schema version

context-pack version


These are separate.

The package version may change through semantic-release. Schema and context-pack versions must only change when their persisted compatibility contracts change.

During 0.x development:

fix: bumps patch

feat: bumps minor

breaking changes do not imply 1.0.0

1.0.0 must not be released until the public API, schema, and context-pack format are explicitly declared stable


## Development

Install all dependencies:
```bash
uv sync --all-groups
```
Run checks:
```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
```
Format code:
```bash
uv run ruff format .
```


## Devcontainer

A minimal devcontainer is provided for reproducible development.

Open the repository in VS Code or a compatible environment and rebuild the container. The devcontainer installs uv and runs:
```bash
uv sync --all-groups
```
## Roadmap

Near-term:

task-specific context pack builder

repo-map vs context-pack baseline comparison

ECS-style semantic component layer

claims and invariants

.ai/ export

JSONL import/export


Later:

git temporal memory

MCP server

richer graph traversal

language-server or Tree-sitter integration

optional vector retrieval

public benchmark datasets


## Research and design notes

See:

docs/roadmap.md

docs/design/architecture.md

docs/design/data_model.md

docs/benchmarks/benchmark_plan.md


If present, the initial research report is stored under:

docs/research/


## License

Apache License 2.0
