# Task context packs

A context pack is a task-specific, source-cited selection of repository context under an explicit budget.

```bash
uv run rsm pack --db .rsm/index.sqlite --task "<task>" --budget 8000 --profile agent_standard
```

Context packs combine lexical scoring, path-role signals, semantic component hints, BM25-style
ranking, and graph relation selection. They are deterministic for the same inputs.

Import relations are weighted as heuristic structural signals. Local package imports and relative
imports can help surface nearby implementation modules, including test-to-source imports for
regression tasks. Standard-library imports and common third-party imports such as `numpy`, `pandas`,
or `pytest` are kept as graph facts when present, but contribute little or no ranking weight. Import
signals are tie-breakers and navigation hints; they do not prove behavior, and source citations
remain authoritative.

## What a pack contains

- **Selected entities**: the ranked files, modules, symbols, docs, or tests judged most relevant
  to the task prompt.
- **Selected relations**: compact structural edges around those entities, such as containment,
  tests, docs, imports, or exports, so the reader can see why nearby context matters.
- **Citations**: repository-relative file ranges that point back to the source of each important
  claim or summary.
- **Uncertainty**: inferred relations/components are kept separate from confirmed evidence and
  should be verified against the cited source.

## Profiles and ranking visibility

`pack` uses the same deterministic compression profiles as `repo-map`. Profiles change how much
detail survives trimming, not the underlying repository truth. Start with `agent_standard`; use
`agent_debug` or `full` when you need more ranking detail.

Use `--explain-ranking` to include deterministic ranking reasons and ordering breakdowns for the
selected entities. This is for diagnosis, not normal consumption. See
[compression profiles](compression_profiles.md).

## Budget behavior

`--budget` is an approximate character budget rather than a tokenizer-exact token count. RSM
tries to preserve the highest-value entities, relations, citations, and uncertainty notes first,
then trims lower-signal detail deterministically. Smaller output is only useful when relevant
files and symbols remain covered.

## How packs differ from repo maps

A [repo map](repo_maps.md) is a broad orientation artifact for an unfamiliar repository. A context
pack is narrower: it is built for one task prompt, includes task-ranked entities and relations,
and may omit unrelated parts of the tree even if they are globally important.

## Caveats

- Selected context is intentionally compact and not exhaustive.
- Inferred relations and components require source verification.
- Budget and token estimates are approximate and directional.
- RSM remains local-first and deterministic: no LLM calls, embeddings, vector DB, or MCP runtime
  server are involved here.
