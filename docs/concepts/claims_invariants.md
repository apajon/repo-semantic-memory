# Claims and invariants

RSM is designed around evidence-backed semantic claims, contracts, and invariants, but the MVP keeps this layer intentionally narrow.

## Current scope

- Claims/invariants can be represented through YAML/JSONL-style interchange surfaces.
- Default indexing does not invent broad semantic claims.
- Agent-facing claims must be cited or marked uncertain.
- Source code, docs, tests, and Git history remain the source of truth.

## Interpretation rules

- Treat inferred components as heuristic hints.
- Treat confirmed components as confirmed only for the specific evidence they cite.
- `confirmed PublicAPI` means explicitly exported in source, not a long-term stability promise.
- Do not use benchmark or case-study text as proof of broad repository understanding.
