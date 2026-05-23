# MCP runtime design

RSM ships a minimal phase 1 stdio MCP runtime (`rsm mcp serve`). See
[`docs/usage/mcp.md`](../usage/mcp.md) for the user-facing guide and from-source
client configuration.

Current RSM MCP support consists of MCP-style typed contracts, pure local
handler functions, and a thin stdio JSON-RPC server that wraps those handlers.
The runtime is deterministic, read-only, and reuses the existing index, graph,
context-pack, and Git-summary logic; it does not reimplement them.

## Target runtime model

The phase 1 runtime target is a local stdio MCP server:

- launched by the MCP client, not by the operating system
- bounded to the lifetime of the agent/client session
- configured with explicit `--repo` and `--db` paths
- read-only by default
- no OS-level daemon
- no login/startup service
- no Docker
- no cloud or hosted service
- no HTTP server in phase 1
- no always-on background process

Proposed installed command:

```bash
rsm mcp serve --repo /path/to/repo --db /path/to/repo/.rsm/index.sqlite
```

From source during local dogfooding:

```bash
uv run --directory /path/to/repo-semantic-memory \
  rsm mcp serve \
  --repo /path/to/target-repo \
  --db /path/to/target-repo/.rsm/index.sqlite
```

Generic MCP client configuration from source:

```json
{
  "mcpServers": {
    "repo-semantic-memory": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/repo-semantic-memory",
        "rsm",
        "mcp",
        "serve",
        "--repo",
        "/absolute/path/to/target-repo",
        "--db",
        "/absolute/path/to/target-repo/.rsm/index.sqlite"
      ]
    }
  }
}
```

PyPI installation is not required for initial local dogfooding.

## Phase 1 read-only tools

Phase 1 should expose read-only tools only:

- `rsm_status`
- `rsm_search_symbols`
- `rsm_explain_entity`
- `rsm_build_context_pack`
- `rsm_query_graph`
- `rsm_validate_patch_context`
- `rsm_get_git_summary`

These tools should call the existing deterministic handlers and preserve their
current limits, provenance, citations, uncertainty records, and deterministic
ordering.

## Deferred capabilities

The runtime should explicitly defer:

- `rsm_index`
- `rsm_export_ai`
- `rsm_export_jsonl`
- `rsm_import_jsonl`
- invariant write tools
- arbitrary command execution
- test execution
- patch application
- HTTP server
- daemon mode

## Safety model

The phase 1 server should enforce these safety decisions:

- no arbitrary shell command execution
- no network access
- no repository or database mutation
- repository and database paths must be explicit
- the DB path should be under the repository root by default
- result sizes must be bounded
- existing handler limits remain enforced
- missing DBs return clear errors
- stale DBs are reported, not rebuilt automatically

The server should not infer hidden global state, scan arbitrary working
directories, or silently switch repositories.

## Staleness model

The server should report index metadata when available, including enough detail
for a client to detect which repository and DB are being queried. It should not
auto-index by default.

If the DB is missing or stale, the server should return a clear diagnostic and
suggest rebuilding explicitly:

```bash
uv run rsm index /path/to/repo --db /path/to/repo/.rsm/index.sqlite
```

Staleness should be reported as state for the caller to act on, not corrected by
hidden writes during a read-only MCP request.

## Non-goals

The initial runtime is not:

- Docker-based
- cloud-hosted
- a hosted service
- an OS-level daemon
- a login/startup service
- an always-on background server
- an automatic repository mutation mechanism
- an MCP bridge/proxy
- dependent on PyPI packaging for local dogfooding

## Static `.ai/` vs MCP runtime

`.ai/` export is a portable snapshot. The future MCP runtime is a live local
query surface over an explicitly selected existing index. Both preserve the rule
that source code, docs, tests, and Git history remain authoritative.

## Implementation status

Phase 1 is implemented:

- `rsm mcp serve --repo ... --db ...` launches a read-only stdio JSON-RPC
  server that wraps the existing pure handlers.
- The transport is pure-stdlib newline-delimited JSON-RPC 2.0; the official
  `mcp` Python SDK is intentionally not used so that RSM keeps its
  zero-runtime-dependency policy and a small auditable safety boundary.
- The exposed tool registry exactly matches the phase 1 list above and is
  asserted in tests against the deferred-tools list.
- `--repo`/`--db` validation rejects missing repos, missing DBs, and DB paths
  outside the repository root, with clean stderr errors.

## Implementation plan

1. Wire a CLI route for `rsm mcp serve`.
2. Wrap the existing pure MCP-style handlers.
3. Expose read-only tool schemas for the phase 1 tool list.
4. Add explicit repository and database path validation.
5. Add smoke tests for startup, tool listing, missing DB errors, and bounded
   read-only tool calls.
6. Document from-source client configuration.
7. Validate on RSM itself and optionally on `lifecore_ros2`.
