# AGENT_COMMANDS - RSM command guide for coding agents

## Purpose

This static guide gives coding agents a compact command and workflow reference for
RSM-assisted repository work. Source code, docs, tests, and Git history remain
authoritative; `.ai/` files are derived artifacts and may be stale.

## Core workflow

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm pack --db .rsm/index.sqlite --task "<task description>" --budget 8000 --profile agent_standard
```

Read the context pack first, then inspect cited files, symbols, and relations. Avoid speculative full-file reads when the pack gives narrower citations.

If the repository is registered in the RSM Index Store (see below), `--db` can be omitted from all reader commands:

```bash
uv run rsm index . --register
uv run rsm pack --task "<task description>" --budget 8000 --profile agent_standard
```

## Orientation workflow

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
# or, if registered in the Index Store:
uv run rsm repo-map --budget 4000 --profile agent_standard
```

Use a repo map for broad structure before deep inspection. For committed or generated `.ai/` snapshots, load only the files needed for the task.

## Debug ranking

```bash
uv run rsm pack --db .rsm/index.sqlite --task "..." --budget 12000 --profile agent_debug --explain-ranking
```

Use debug ranking when selected context looks surprising. Debug output is larger and should not be the default for routine edits.

## Evaluation

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

Treat benchmark results as internal and directional. Token savings matter only when relevant gold file and symbol coverage is preserved.

## `.ai/` file usage

- `INDEX.yaml`: generation time, versions, and counts; check this first for staleness.
- `repo_map.md`: compact structural overview.
- `symbols.yaml`: entity IDs, names, kinds, and source ranges.
- `relations.yaml`: structural links such as imports, exports, containment, and tests.
- `components.yaml`: semantic component labels when present; inferred labels require verification.
- `invariants.yaml`: invariant records when present.
- `context_policy.md`: loading order, budget guidance, and interpretation rules.

Do not load all `.ai/` files by default. Start with the smallest artifact that answers the task.

## RSM Index Store

Register a repo once to skip `--db` for all reader commands:

```bash
uv run rsm index . --register        # index to the store's canonical path
uv run rsm store status .            # check freshness
```

DB resolution order for `pack`, `repo-map`, `inspect`, `components`, `invariants`, `eval`, `export-ai`, `export-jsonl`:

1. Explicit `--db` argument — always wins.
2. RSM Index Store entry for the current working directory.
3. `.rsm/index.sqlite` — legacy fallback.

## Regeneration / staleness

Regenerate after structural changes such as new modules, renamed files, moved packages, changed exports, or large refactors:

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

Check `INDEX.yaml` `generated_at` against recent repository changes before relying on snapshots.

## Do not

- Do not treat `.ai/` files as source truth.
- Do not trust inferred components or relations as confirmed claims.
- Do not use stale snapshots without checking `INDEX.yaml`.
- Do not ignore citations when editing code.
- Do not claim `confirmed PublicAPI` means API stability.
- Do not claim broad superiority from internal benchmark results.
- Do not commit volatile generated `.ai/` snapshots unless a PR explicitly chooses to version them.

## Human documentation link

Use `docs/README.md` for the human documentation index and deeper explanations.
