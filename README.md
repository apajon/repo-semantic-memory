# repo-semantic-memory

[![CI](https://github.com/apajon/repo-semantic-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/apajon/repo-semantic-memory/actions/workflows/ci.yml)
[![Release](https://github.com/apajon/repo-semantic-memory/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/apajon/repo-semantic-memory/actions/workflows/release.yml)

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Package manager: uv](https://img.shields.io/badge/package%20manager-uv-blue)

![Status: experimental pre-1.0](https://img.shields.io/badge/status-experimental%20pre--1.0-orange)
[![Latest Release](https://img.shields.io/github/v/release/apajon/repo-semantic-memory)](https://github.com/apajon/repo-semantic-memory/releases/latest)
![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)

**Give your coding agent the right repo context before it edits code.**

`repo-semantic-memory` (`rsm`) is a local tool that indexes a repository and prepares focused context for coding agents.

Instead of asking an agent to explore a codebase from scratch, RSM helps it start from the files, tests, docs, and related context that matter for the task.

```text
Index the repo -> search for task context -> prepare a ContextPack -> give it to your agent
```

[Quickstart](docs/quickstart.md) · [CLI](docs/usage/cli.md) · [Examples](docs/usage/examples.md) · [MCP](docs/usage/mcp.md) · [Project Brief](docs/usage/project_brief.md) · [Limitations](docs/known_limitations.md) · [Roadmap](docs/design/roadmap.md) · [Benchmarks](docs/eval/benchmarks.md)

---

## Quickstart

Install dependencies:

```bash
uv sync --all-groups
```

Index the current repository:

```bash
uv run rsm index . --db .rsm/index.sqlite
```

Prepare context for a task:

```bash
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 8000 \
  --profile agent_standard
```

Generate a project brief:

```bash
uv run rsm project-brief --db .rsm/index.sqlite --force
```

Default output:

```text
.rsm/PROJECT_CONTEXT.md
```

### Use RSM through MCP in VS Code

For an editor/agent workflow, expose the same index through the MCP server:

```bash
uv run rsm mcp serve --repo . --db .rsm/index.sqlite
```

Example `mcp.json` configuration for a single repository/index:

```json
{
  "servers": {
    "repo-semantic-memory": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/repo-semantic-memory",
        "rsm",
        "mcp",
        "serve",
        "--repo",
        "/path/to/your/repository",
        "--db",
        "/path/to/your/repository/.rsm/index.sqlite"
      ]
    }
  }
}
```

A VS Code MCP config usually points to that command through `uv` and the repository path. See [MCP usage](docs/usage/mcp.md) for the exact editor configuration and troubleshooting notes.

### Use an index store

For day-to-day work across multiple repositories, use an RSM store instead of passing one database path manually every time:

```bash
uv run rsm store add . --db .rsm/index.sqlite
uv run rsm store list
```

The store lets RSM remember available repository indexes and select one when using store mode.

### Use MCP with the store

Start MCP in store mode when you want the agent to choose from registered indexes:

```bash
uv run rsm mcp serve --store
```

Example `mcp.json` configuration for VS Code-style MCP clients:

```json
{
  "servers": {
    "repo-semantic-memory-store": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/repo-semantic-memory",
        "rsm",
        "mcp",
        "serve",
        "--store"
      ],
      "env": {
        "RSM_HOME": "/path/to/.rsm_store"
      }
    }
  }
}
```

In store mode, the agent can use:

```text
rsm_store_list_indexes
rsm_store_select_index
rsm_store_current_index
rsm_search
rsm_find_related
rsm_prepare_context
rsm_get_context_page
```

This is useful when you switch between projects or want a single MCP server to expose several indexed repositories.

See the [Quickstart](docs/quickstart.md), [CLI usage](docs/usage/cli.md), and [MCP usage](docs/usage/mcp.md) docs for the full command flow.

## Why I built this

I built RSM because I kept running into the same problem when using coding agents on real repositories.

Before making a useful change, the agent often had to re-read large parts of the codebase, open full files, rediscover the project structure, and piece together how files interacted. That used a lot of context, took time, and still did not always give the agent the right view of the task.

RSM is my attempt to make that first step cheaper and more reliable.

It builds a local index of the repository and uses it to prepare focused context for a specific development task.

## What problem does it solve?

Coding agents are usually better at editing code than at deciding what to read first.

On a real project, the important context is often split across:

- implementation files
- tests
- docs and design notes
- examples
- related modules
- past architectural decisions

RSM helps collect that context before the agent starts editing.

It is especially useful when you are returning to a project after a pause, working in a larger repo, or trying to avoid wasting context on irrelevant files.

## What RSM does

RSM can help you:

- index a local repository
- search for task-relevant files, symbols, tests, and docs
- find related files or entities
- prepare a compact ContextPack for an agent
- generate a project brief for future sessions
- expose the same workflow through MCP-compatible tools
- run benchmarks to measure retrieval quality

A typical task might be:

```text
I need to change lifecycle cleanup behavior.
Find the implementation, tests, docs, and nearby context my agent should read first.
```

RSM does not make the change. It prepares the context so your coding agent can start from a better place.

## Core workflow

1. **Index** a repository.
2. **Search** for task-relevant context.
3. **Inspect related files or symbols.**
4. **Prepare a ContextPack** for the task.
5. **Give that ContextPack to your coding agent.**
6. **Optionally generate a project brief** for future sessions.
7. **Optionally use MCP** to expose the workflow directly to agent tools.

## Project brief

A project brief is a short Markdown summary generated from an existing RSM index.

It helps an agent understand the repository before it starts calling tools or editing files.

Run:

```bash
uv run rsm project-brief --db .rsm/index.sqlite --force
```

The brief includes:

- repository identity
- freshness/readiness status
- main code areas
- important tests and docs
- known caveats
- suggested agent workflow

See [Project Brief usage](docs/usage/project_brief.md).

## MCP support

RSM includes a local read-only MCP-compatible runtime for agent workflows.

Default task tools:

| Tool | Purpose |
|---|---|
| `rsm_search` | Find relevant indexed files, symbols, docs, and tests. |
| `rsm_find_related` | Expand around a known file, symbol, or qualified name. |
| `rsm_prepare_context` | Build a task-centered ContextPack. |
| `rsm_get_context_page` | Page through a larger ContextPack result. |

Store-mode tools:

| Tool | Purpose |
|---|---|
| `rsm_store_list_indexes` | List registered repository indexes. |
| `rsm_store_select_index` | Select the active repository index. |
| `rsm_store_current_index` | Show the selected index and readiness state. |

Example:

```bash
uv run rsm mcp serve --repo /path/to/repo --db /path/to/index.sqlite
```

RSM MCP tools are read-only. They do not modify your repository and do not auto-index in the background.

See [MCP usage](docs/usage/mcp.md).

## Benchmarks and dogfooding

RSM is developed with benchmark cases and real-repository dogfooding.

That means retrieval changes are checked against task examples instead of only judged by manual impressions.

Useful benchmark commands include:

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
uv run rsm eval bench --dataset benchmarks/ci_benchmark_cases.yaml --json
```

See [Benchmarks](docs/eval/benchmarks.md) and the [`lifecore_ros2` case study](docs/case_studies/lifecore_ros2.md).

## What RSM is not

RSM is not:

- a coding agent
- a Copilot, Cursor, or Claude Code replacement
- a general-purpose search SaaS
- a vector database
- a GUI
- a full code graph platform
- an automatic background indexer
- a source of truth that replaces the repository itself

RSM produces local, source-cited context. You should still verify important decisions against the actual files.

## Current strengths

RSM is currently most useful for:

- Python-first repositories
- documentation-heavy repositories
- agents that need focused context before editing
- local workflows where repository data should stay on your machine
- benchmark-driven improvement of retrieval quality
- returning to a project after a long pause

## Current limitations

RSM is experimental pre-1.0 software.

Current limitations include:

- Python and Markdown/documentation support are strongest today.
- Non-Python language support is limited.
- ROS interface files such as `.msg`, `.srv`, and `.action` are not indexed yet.
- Search and ranking are useful but not perfect.
- ContextPacks are starting points, not proof.
- Some relations are inferred heuristically.
- MCP support is local and read-only.
- RSM does not auto-index, auto-refresh, watch the filesystem, or modify source code.

The goal is to be useful and honest, not magical.

## Roadmap

Near-term public-readiness work focuses on:

- validating the quickstart
- improving CLI examples
- documenting known limitations clearly
- running release-readiness checks
- preparing a public announcement

Deferred technical work includes:

- non-Python and interface-file indexing
- search and ranking refinement
- `find_related` refinement
- ContextPack balance and noise improvements
- optional deterministic snippets/chunks if benchmarks justify them
- packaging and MCP documentation hardening

See the [Roadmap](docs/design/roadmap.md).

## Documentation

- [Documentation index](docs/README.md)
- [Quickstart](docs/quickstart.md)
- [CLI usage](docs/usage/cli.md)
- [MCP usage](docs/usage/mcp.md)
- [Project brief](docs/usage/project_brief.md)
- [Agent workflows](docs/usage/agent_workflows.md)
- [Benchmarks](docs/eval/benchmarks.md)
- [`lifecore_ros2` case study](docs/case_studies/lifecore_ros2.md)
- [Agent instructions](AGENTS.md)

## Status

RSM is experimental pre-1.0 software.

It is suitable for local dogfooding, agent-context experiments, and benchmark-backed development on Python-first repositories. Public APIs, database details, and ContextPack formats may change before 1.0.

## License

Apache-2.0.
