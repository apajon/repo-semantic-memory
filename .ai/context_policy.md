# Context Policy

## Source of truth

Code, docs, tests, and Git history are authoritative. `.ai/` files are derived snapshots and may be stale. Verify important claims against cited source ranges before editing.

## Loading order

1. Load `INDEX.yaml` to confirm generation timestamp and versions.
2. Load `repo_map.md` for broad structural orientation.
3. Load `symbols.yaml` only when resolving entity IDs or source locations.
4. Load `relations.yaml` only when tracing dependencies, exports, containment, or test links.
5. Load `components.yaml` or `invariants.yaml` only when the task needs semantic labels or invariants.

Do not load all `.ai/` files at once unless the task explicitly requires it.

## Budget guidance

Prefer task-specific context packs for edits and debugging:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "<task>" --budget 8000 --profile agent_standard
```

Use repo maps for broad orientation and context packs for task-specific work. Keep loaded artifacts as small as possible for the current task.

## Compression profiles

- `agent_brief`: smallest output for tight budgets and narrow tasks.
- `agent_standard`: default balanced profile for most coding-agent work.
- `agent_debug`: larger diagnostic output with ranking detail.
- `human_review`: balanced output for PR or design review.
- `ci_summary`: compact CI-oriented output with strict noise suppression.
- `full`: maximum detail while still avoiding source body dumps.

See `docs/concepts/compression_profiles.md` for full profile details.

## Staleness

Check `INDEX.yaml` `generated_at` against recent repository changes. Regenerate after structural changes:

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm export-ai --db .rsm/index.sqlite --out .ai --force
```

## Interpretation rules

- Treat `.ai/` files as derived context, not source truth.
- Treat inferred relations and components as heuristic until verified.
- `confirmed PublicAPI` means exported in source, not stable API.
- Token estimates are approximate and directional.
- Internal benchmark results are not broad superiority claims.
- MCP handlers/contracts may exist, but no runtime MCP server is shipped yet.
