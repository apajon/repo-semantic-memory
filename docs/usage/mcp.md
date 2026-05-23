# MCP runtime usage

> **Status — phase 1 prototype.** Minimal local stdio MCP-compatible JSON-RPC
> prototype, not yet externally conformance-tested. Read-only. No Docker, no
> daemon, no HTTP, no cloud, no auto-indexing.

`rsm mcp serve` exposes the existing pure RSM handlers through a minimal
local stdio JSON-RPC loop that follows the
[Model Context Protocol](https://modelcontextprotocol.io/) stdio transport
shape. It is launched by an MCP client (an agent or IDE) for the lifetime of
that client's session and exits when the client closes its stdin. Conformance
against external MCP clients has not yet been validated, so this is best
described as an MCP-compatible prototype rather than a fully compliant MCP
server.

The runtime does not index your repository, does not modify your repository,
does not modify the SQLite index, does not execute arbitrary shell commands,
does not run tests, and does not apply patches. It is a thin transport over the
read-only handlers documented in
[`docs/design/mcp_server.md`](../design/mcp_server.md). The
`rsm_get_git_summary` tool may invoke a fixed, read-only `git` subprocess
internally via the existing extractor; that is bounded local Git inspection
with hardcoded arguments, not arbitrary command execution.

## Prerequisites

Build the local index first. The MCP server only reads from it.

```bash
uv run rsm index /path/to/target-repo --db /path/to/target-repo/.rsm/index.sqlite
```

If the database is missing or out of date, regenerate it with `rsm index`
before launching the MCP server. The server will report missing/stale state
but does **not** rebuild it.

## Starting the server

```bash
uv run rsm mcp serve \
  --repo /absolute/path/to/target-repo \
  --db /absolute/path/to/target-repo/.rsm/index.sqlite
```

`--repo` and `--db` are required. The server validates them at startup:

- `--repo` must exist and be a directory.
- `--db` must exist and be a regular file (no auto-creation).
- `--db` must resolve to a path inside `--repo`.
- Invalid inputs exit with code `2` and a clear `error:` line on stderr.

## From-source MCP client configuration

This is the supported configuration during local dogfooding. PyPI installation
is not required.

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

## Exposed tools (read-only)

| Tool                          | Wraps                                                 |
| ----------------------------- | ----------------------------------------------------- |
| `rsm_status`                  | local store metadata + version info                   |
| `rsm_search_symbols`          | `handle_search_symbols`                               |
| `rsm_explain_entity`          | `handle_explain_entity`                               |
| `rsm_build_context_pack`      | `handle_build_context_pack`                           |
| `rsm_query_graph`             | `handle_query_graph`                                  |
| `rsm_validate_patch_context`  | `handle_validate_patch_context`                       |
| `rsm_get_git_summary`         | `handle_get_git_summary`                              |

Each tool preserves the existing handler's bounds (result size caps, graph
depth/entity caps, context-pack budget caps, citations, and uncertainty
records).

## Deferred tools

The following are intentionally **not** exposed in phase 1:

- `rsm_index`
- `rsm_export_ai`
- `rsm_export_jsonl`
- `rsm_import_jsonl`
- any invariant write tool
- arbitrary command execution
- test execution
- patch application
- filesystem browsing tools

## Dependency decision

The phase 1 server is implemented directly on top of the Python standard
library (`json`, `sys`, `pathlib`). It speaks newline-delimited JSON-RPC 2.0
on stdio, which is the MCP stdio transport. The official `mcp` Python SDK was
considered but not adopted because:

- RSM has a zero-runtime-dependency policy; the SDK pulls in `pydantic`,
  `anyio`, and related runtime dependencies that are out of scope for a
  minimal read-only prototype.
- The phase 1 surface (`initialize`, `tools/list`, `tools/call`, `ping`,
  `shutdown`) is small enough to implement and audit by hand.
- Keeping the implementation in one focused module makes the safety boundary
  (read-only, no arbitrary shell command execution, no network) easy to review.

This decision is revisited if/when the runtime grows beyond the phase 1
read-only surface.

## Safety summary

- No arbitrary shell command execution.
- No network access.
- No mutation of repository or database state in phase 1.
- No auto-indexing.
- Explicit `--repo`/`--db` validation.
- DB path must be inside the repository root by default.
- Existing handler output and path bounds are preserved.

If a tool call fails for a recoverable reason (unknown entity ID, missing
changed path, etc.) the server returns a JSON-RPC success result with
`isError: true` and a short text message rather than a transport-level error.

## What remains untested

Phase 1 ships unit tests covering:

- CLI subcommand presence and help output.
- `--repo`/`--db` path validation, including DB-outside-repo rejection.
- Tool registry surface (exact names, deferred tool exclusion).
- Wrapper behavior for each exposed tool (delegates to the existing handler).
- JSON-RPC dispatch for `initialize`, `tools/list`, `tools/call`, malformed
  JSON, and unknown methods, exercised with in-memory `stdin`/`stdout` streams.

End-to-end protocol conformance against an external MCP client is **not** part
of phase 1. The plan is to validate against a real MCP client (and against
`lifecore_ros2`) as part of a later phase, before promoting the runtime out
of prototype status.
