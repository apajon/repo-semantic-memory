# repo-semantic-memory

Coding agents work better when they know where to look.

`repo-semantic-memory` (`rsm`) builds compact, source-cited repository context for coding agents. It can generate broad repo maps for orientation, task-shaped context packs for focused work, and `.ai/` snapshots for agent workflows.

The goal is not to replace reading source. The goal is to give an agent a better starting point: relevant files, symbols, exports, tests, structural relations, citations, and uncertainty, all derived from local repository evidence.

RSM is an experimental pre-1.0, Python-first repository context compiler. It runs locally and avoids LLM calls, embeddings, vector databases, hosted services, and web UIs.

RSM also includes a minimal local stdio MCP-compatible JSON-RPC prototype for read-only dogfooding. It is not yet externally conformance-tested.

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
uv run rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml --json
```

See [`docs/eval/benchmarks.md`](docs/eval/benchmarks.md) for benchmark workflows.

For more detail, start with [`docs/README.md`](docs/README.md) and [`docs/quickstart.md`](docs/quickstart.md).

## What it currently covers

RSM is organized around one practical workflow: index the repository once, then ask for compact context tailored to a task.

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
- benchmark harness with CI and manual external datasets
- `.ai/` export
- JSONL import/export
- minimal local stdio MCP-compatible JSON-RPC prototype for read-only local dogfooding, not yet externally conformance-tested

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
- Context packs are starting points, not proof. Important claims should be verified against cited source.
- Some relations and components are inferred heuristically.
- `confirmed PublicAPI` means explicitly exported in source, not a stable API guarantee.
- Token estimates use approximate deterministic accounting (`chars / 4`) and are directional.
- Internal benchmark results are small, repository-specific, and not broad superiority claims.
- The MCP prototype is read-only and not yet externally conformance-tested.

## License

Apache-2.0.
