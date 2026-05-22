# repo-semantic-memory

`repo-semantic-memory` (`rsm`) is an **experimental pre-1.0** deterministic repository context compiler for coding agents.

It indexes source code, docs, tests, and optional local Git metadata, then emits compact, source-cited artifacts such as repo maps, task context packs, JSONL graph exports, and `.ai/` snapshots. RSM is local-first and intentionally avoids LLM calls, embeddings, vector databases, web UIs, and runtime servers in the MVP.

RSM is not a documentation generator, Obsidian vault, generic vector database, or broad “AI knowledge graph platform.” The repository remains the source of truth.

## Quick start

```bash
uv sync --all-groups
uv run rsm index . --db .rsm/index.sqlite
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
uv run rsm pack --db .rsm/index.sqlite --task "find where context pack ranking happens" --budget 8000 --profile agent_standard
```

Optional exports and evaluation:

```bash
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

For more detail, start with [`docs/README.md`](docs/README.md) and [`docs/quickstart.md`](docs/quickstart.md).

## What it currently covers

- deterministic repository indexing
- Python AST extraction
- Markdown outline extraction
- public API export extraction from `__init__.py`
- test relationship extraction
- repo-map and context-pack generation
- ranking breakdowns, BM25 lexical scoring, and graph relation selection
- deterministic compression profiles
- approximate token-savings metrics
- benchmark/eval commands
- `.ai/` export
- JSONL import/export
- pure MCP-style handlers and contracts, with no runtime MCP server yet

## Documentation map

- [`docs/README.md`](docs/README.md) — documentation index by reader intent
- [`docs/quickstart.md`](docs/quickstart.md) — setup and first commands
- [`docs/concepts/`](docs/concepts/) — semantic index, repo maps, context packs, compression profiles, claims/invariants
- [`docs/usage/`](docs/usage/) — CLI, agent workflows, `.ai/`, JSONL interchange
- [`docs/eval/`](docs/eval/) — benchmarks and token-savings interpretation
- [`docs/design/`](docs/design/) — data model, MCP design, future CLI output summarizer, roadmap/review notes
- [`docs/release/versioning.md`](docs/release/versioning.md) — pre-1.0 versioning and release policy
- [`docs/case_studies/lifecore_ros2.md`](docs/case_studies/lifecore_ros2.md) — real-repo validation case study

Agent/contributor operations live in [`AGENTS.md`](AGENTS.md). Static `.ai/` templates are agent-facing artifacts, not primary human docs.

## Limitations

- Experimental pre-1.0 project; APIs, schemas, and context-pack formats may evolve.
- All semantic claims should be verified against cited source evidence.
- Some relations and components are inferred heuristically.
- `confirmed PublicAPI` means explicitly exported in source, not a stable API guarantee.
- Token estimates use approximate deterministic accounting (`chars / 4`) and are directional.
- Internal benchmark results are small, repository-specific, and not broad superiority claims.
- MCP handlers/contracts exist for local deterministic logic, but no runtime MCP server is shipped yet.

## License

Apache-2.0.
