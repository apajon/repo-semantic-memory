# Compression profiles

This document defines deterministic context compression for `repo-semantic-memory`.

## Scope

Compression profiles apply to:

- `rsm repo-map --profile ...`
- `rsm pack --profile ...`

They are declarative and deterministic. They do not introduce LLM calls, embeddings, MCP runtime behavior, schema changes, or terminal hooks.

## Noise categories

The system treats the following as low-signal context by default:

1. generated artifacts
2. repeated imports
3. standard library imports
4. unresolved external imports
5. duplicate logical relations
6. low-signal metadata
7. long component lists
8. test fixture boilerplate
9. build/cache/docs artifacts
10. oversized doc sections
11. low-rank tooling/config context when task does not request it

## Preservation categories

Compression must preserve task-critical context:

1. direct task matches
2. source citations
3. selected gold items during eval
4. explicit public exports
5. confirmed claims
6. active invariants
7. high-confidence test relations
8. high-score graph neighbors
9. selected implementation symbols

## Profile definitions

Profiles are defined in `src/repo_semantic_memory/context/compression.py`.

### `agent_brief`

- max imports/module: `6`
- max components/entity: `2`
- unresolved imports: excluded
- ranking breakdown: excluded
- low-confidence inferred components: excluded
- relation verbosity: compact
- citation verbosity: minimal
- max related symbols: `20`
- max uncertainties: `6`
- compact score reasons: excluded

### `agent_standard` (default)

- max imports/module: `12`
- max components/entity: `4`
- unresolved imports: included
- ranking breakdown: excluded
- low-confidence inferred components: excluded
- relation verbosity: standard
- citation verbosity: standard
- max related symbols: `40`
- max uncertainties: `12`
- compact score reasons: excluded

### `agent_debug`

- max imports/module: `20`
- max components/entity: `6`
- unresolved imports: included
- ranking breakdown: included
- low-confidence inferred components: included
- relation verbosity: verbose
- citation verbosity: full
- max related symbols: `80`
- max uncertainties: `30`
- compact score reasons: included

### `human_review`

- max imports/module: `16`
- max components/entity: `4`
- unresolved imports: included
- ranking breakdown: excluded
- low-confidence inferred components: excluded
- relation verbosity: standard
- citation verbosity: standard
- max related symbols: `50`
- max uncertainties: `15`
- compact score reasons: excluded

### `ci_summary`

- max imports/module: `8`
- max components/entity: `3`
- unresolved imports: excluded
- ranking breakdown: excluded
- low-confidence inferred components: excluded
- relation verbosity: compact
- citation verbosity: minimal
- max related symbols: `24`
- max uncertainties: `8`
- compact score reasons: excluded

### `full`

- max imports/module: unlimited
- max components/entity: unlimited
- unresolved imports: included
- ranking breakdown: included
- low-confidence inferred components: included
- relation verbosity: verbose
- citation verbosity: full
- max related symbols: unlimited
- max uncertainties: unlimited
- compact score reasons: included

## Determinism guarantees

- Profile resolution is name-based with a fixed registry.
- Relation/component/citation trimming is stable and order-preserving.
- Invalid profile names fail with a clear error listing valid profiles.
- Source bodies remain excluded; only structural summaries and citations are emitted.
