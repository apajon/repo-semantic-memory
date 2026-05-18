# MCP Server Design (Deferred Runtime)

## Why MCP is useful

Static `.ai/` exports are useful for portable snapshots, but they can become stale between
index refreshes. A future Model Context Protocol (MCP) integration would let coding agents
query the local SQLite-backed semantic memory dynamically during a task while still keeping
code, docs, tests, and git history as the source of truth.

The MCP layer is intended to expose deterministic repository queries, not to introduce a new
analysis engine. It should sit on top of the existing index, repo-map, context-pack,
component, invariant, `.ai/`, JSONL, and optional Git summary capabilities.

## Why full MCP runtime is deferred

A full MCP server is intentionally deferred because the project is still stabilizing:

- tool contracts should follow the current deterministic data model
- runtime transport choices should not freeze too early
- security boundaries need review before agent-facing query execution is exposed
- the MVP should avoid a networked or long-lived server dependency
- existing CLI, `.ai/`, and JSONL surfaces already cover current offline workflows

This phase documents the contract and adds typed placeholders only. It does **not** add an
MCP runtime dependency, a server process, or any network behavior.

## Pre-stable placeholder status

The MCP dataclasses added in this step are design artifacts for an internal, pre-runtime phase.
They document intended request/response shapes, but they are **not** a declared stable public API
yet. Callers should treat them as provisional contracts that may evolve until a read-only MCP
runtime, serialization contract, and compatibility policy are explicitly documented.

`get_mcp_tool_contracts()` is similarly declarative only. It returns metadata describing planned
tool names and typed envelopes; it does **not** register executable handlers, start a transport,
perform repository queries, or imply that the runtime contract is frozen.

## Scope and non-goals

This future MCP layer must:

- read from local indexed data and existing deterministic builders
- return explicit evidence/citations with every semantic claim when available
- expose uncertainty instead of guessing
- enforce bounded output for agent context windows
- remain usable without network access

This future MCP layer must not:

- re-index repositories implicitly
- call remote APIs, including GitHub APIs
- depend on a vector database, web UI, or LLM runtime
- mutate repository content by default
- change schema or context-pack versions unless persisted formats change

## Expected tool surface

### `search_symbols`

Find entities by lexical query against indexed symbols.

**Inputs**
- `query`: non-empty search string
- `limit`: maximum number of matches
- `entity_kinds`: optional entity kind filter
- `include_relations`: whether to attach direct relation summaries

**Outputs**
- ordered symbol matches with stable entity IDs, kinds, qualified names, and source ranges
- optional direct-relation summaries when requested
- evidence/citations for returned entities
- uncertainty notes when the query is broad, empty after normalization, or truncated by limits

### `explain_entity`

Explain one entity using stored structure instead of free-form generation.

**Inputs**
- `entity_id`: stable entity ID
- `include_incoming_relations`: include incoming structural relations
- `include_outgoing_relations`: include outgoing structural relations
- `include_components`: include inferred ECS-style semantic component labels
- `include_claims`: include linked claims/invariants when present

**Outputs**
- the resolved entity payload
- related relations and semantic component labels
- evidence/citations for entity and relation facts
- uncertainty notes for missing entity IDs, incomplete evidence, or absent optional layers

### `build_context_pack`

Build a bounded, task-specific context pack from the current local index.

**Inputs**
- `task`: task prompt
- `budget_chars`: requested character budget
- `format`: `markdown` or `yaml`
- `include_semantic_components`: whether to include compact component labels

**Outputs**
- rendered context pack payload
- selected entity/relation IDs
- source citations and uncertainty notes
- budget usage details including truncation state

### `query_graph`

Run bounded structural graph queries over entities and relations.

**Inputs**
- `entity_ids`: seed entity IDs
- `relation_kinds`: optional relation-kind filter
- `max_hops`: bounded traversal depth
- `limit`: maximum number of entities/relations returned

**Outputs**
- deterministic subgraph rooted at the seed entities
- ordered entity and relation payloads
- citations for relations when evidence exists
- uncertainty notes when traversal hits limits or missing seeds

### `export_ai_memory`

Trigger the same `.ai/` export workflow already available locally.

**Inputs**
- `db_path`: local SQLite path
- `output_dir`: target `.ai/` directory
- `force`: overwrite behavior

**Outputs**
- exported file list and skipped file list
- entity/relation/component/invariant counts
- warnings if export targets already exist or no optional derived files were emitted

This tool is for local regeneration only. It should not replace committed `.ai/` artifacts as a
portable handoff format.

### `validate_patch_context`

Check whether a proposed patch has enough cited repository context before an agent acts on it.
This tool is about context coverage and touched-file justification, not patch correctness,
linting, testing, or semantic validation of the patch itself.

**Inputs**
- `task`: current task statement
- `changed_paths`: repository-relative paths touched by the patch
- `referenced_entity_ids`: optional entity IDs already in agent context
- `budget_chars`: optional target budget for suggested follow-up context

**Outputs**
- missing paths, entities, relations, or citations that should be loaded first
- touched files that still need explicit justification in the available context
- suggested context-pack or symbol queries to gather that context
- uncertainty notes when the repository index does not cover touched files
- a bounded remediation summary suitable for an agent loop

### `get_git_summary`

Expose the existing local Git summary as an optional MCP tool when Git metadata support is
available.

**Inputs**
- `path`: repository path to inspect

**Outputs**
- repository root, current branch, HEAD commit, dirty state, and availability reason
- no semantic claims beyond temporal repository status

This mirrors `rsm git summary` and remains local-only.

## Evidence and citations

MCP responses should return citations as structured records, not only inline strings. Each
citation should include enough data for an agent or UI to reopen the source deterministically:

- repository-relative POSIX path
- start/end line
- optional start/end columns
- subject kind (`entity`, `relation`, `claim`, `git_summary`)
- subject ID or stable relation key
- optional extractor name and confidence when available
- optional note for scope or limitations

If a tool returns a semantic fact without evidence, it must either:

- mark the fact as derived from deterministic local computation, or
- attach an uncertainty record explaining why direct evidence is absent

## Context budget enforcement

Budgets should remain explicit and character-based until a tokenizer-specific contract is added.
MCP tools that can emit large payloads (`build_context_pack`, `search_symbols`, `query_graph`,
and `validate_patch_context`) should:

- accept a caller-provided character budget or result limit
- report requested, used, and remaining budget
- report whether truncation occurred
- prefer stable ordering so truncation is repeatable
- avoid silently dropping citations when trimming output

## Uncertainty representation

Uncertainty should be first-class structured data, not prose hidden in summaries.
Each uncertainty item should include:

- `code`: stable machine-readable category
- `message`: human-readable explanation
- `subject_id`: optional affected entity/relation/tool subject
- `recoverable`: whether the caller can resolve it with another local query

Examples include missing entity IDs, truncated traversal, stale index suspicion, absent Git
repository data, or derived component labels without direct source evidence.

## Determinism requirements

The future MCP layer must remain deterministic for identical local inputs.
In practice this means:

- stable entity IDs and relation keys
- repository-relative POSIX paths
- sorted entities, relations, components, and file lists
- explicit output limits and truncation flags
- no hidden background refreshes or remote calls
- no LLM-generated summaries in tool responses

The transport layer may be interactive later, but the semantic results must stay boring and
scriptable.

## Network access constraints

The MCP layer must work entirely offline against local repository state:

- local SQLite index
- local working tree files
- local `.ai/` export path
- local Git repository information when present

It must not require internet access, hosted services, or remote code execution.

## MCP vs static `.ai/` export

`.ai/` export is a compiled snapshot meant for portability and commit-friendly sharing. MCP is a
live local query surface over the current index.

| Capability | `.ai/` export | MCP |
|---|---|---|
| Freshness | snapshot, may become stale | queries current local index |
| Distribution | easy to commit/share | local runtime interaction |
| Shape | fixed file set | task-driven tool responses |
| Budgeting | caller loads selected files | tool enforces bounded responses |
| Mutability | regenerated explicitly | queries without rewriting artifacts |

## MCP vs JSONL export

JSONL export is a machine-facing interchange format for entities/relations and metadata. MCP is
an interactive query contract layered on top of local indexed data.

| Capability | JSONL export | MCP |
|---|---|---|
| Primary goal | interchange/import-export | live bounded queries |
| Granularity | full datasets | task-specific slices |
| Consumer model | batch tooling | agent tools |
| Evidence handling | raw exported records | response-scoped citations and uncertainty |
| Context budgets | external concern | built into tool contracts |

## Security boundaries

Exposing repo queries to agents introduces security constraints even without a network server.
The future runtime should preserve these boundaries:

- no network access by default
- repository access must stay rooted to explicitly configured local paths
- tool inputs must not permit arbitrary filesystem traversal or reads outside the repository root
  unless explicit future configuration allows it
- no arbitrary command execution or shell execution from MCP query tools
- no implicit re-indexing or mutation without explicit future write-tool design
- Git exposure should remain summary-only unless more granular access is reviewed
- large result sets must be bounded to prevent context flooding or accidental data overexposure
- citations should reference repository-local evidence only

## Versioning impact

Keeping `SCHEMA_VERSION` and `CONTEXT_PACK_VERSION` unchanged in this step is correct because the
change is design-only. No persisted storage schema, `.ai/` artifact contract, JSONL interchange
format, or serialized context-pack payload was modified here.

## Placeholder code in this step

This repository now includes lightweight typed placeholders for the future MCP tool contracts in
`src/repo_semantic_memory/mcp/tools.py`. These placeholders define the expected request/response
shapes and shared metadata envelopes, but they do not start a server, register a transport, or
change any CLI behavior.
