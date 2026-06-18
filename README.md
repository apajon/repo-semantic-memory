# repo-semantic-memory

![RSN Banner](https://raw.githubusercontent.com/apajon/repo-semantic-memory/main/docs/_static/Logo_RSM_banner.png)

[![CI](https://github.com/apajon/repo-semantic-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/apajon/repo-semantic-memory/actions/workflows/ci.yml)
[![Release](https://github.com/apajon/repo-semantic-memory/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/apajon/repo-semantic-memory/actions/workflows/release.yml)

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Package manager: uv](https://img.shields.io/badge/package%20manager-uv-blue)

![Status: experimental pre-1.0](https://img.shields.io/badge/status-experimental%20pre--1.0-orange)
[![Latest Release](https://img.shields.io/github/v/release/apajon/repo-semantic-memory)](https://github.com/apajon/repo-semantic-memory/releases/latest)
![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)

**Give your coding agent the right repo context before it edits code.**

`repo-semantic-memory` (`rsm`) is a local repository context layer for coding agents.

You can use it from the CLI, but it is especially useful through MCP: compatible coding agents can call RSM to search your repository, find related files, and prepare focused ContextPacks before editing code.

```text
Index the repo -> configure MCP -> agent asks RSM -> start editing with context
```

[Quickstart](docs/quickstart.md) · [CLI](docs/usage/cli.md) · [Examples](docs/usage/examples.md) · [MCP](docs/usage/mcp.md) · [Project Brief](docs/usage/project_brief.md) · [Limitations](docs/known_limitations.md) · [Roadmap](docs/design/roadmap.md) · [Benchmarks](docs/eval/benchmarks.md)

---

## Quickstart

### CLI quickstart

Install dependencies, index, and prepare context:

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

### MCP quickstart (recommended for coding agents)

Index your repo, then start the MCP server so your agent can call RSM directly:

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm mcp serve --repo . --db .rsm/index.sqlite
```

Example `mcp.json` for VS Code:

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

Once connected, your agent can use:

| Tool | Purpose |
|---|---|
| `rsm_search` | Search for relevant files, symbols, docs, and tests |
| `rsm_find_related` | Expand around a known file, symbol, or qualified name |
| `rsm_prepare_context` | Build a task-centered ContextPack |
| `rsm_get_context_page` | Page through a larger ContextPack result |

### Store mode (multiple repositories)

Register multiple repositories so your agent can switch between them:

```bash
uv run rsm store register /path/to/repo1 --index
uv run rsm store register /path/to/repo2 --index
uv run rsm store list
```

The store lives at `~/.local/share/repo-semantic-memory` on Linux, `~/Library/Application Support/repo-semantic-memory` on macOS, or `%LOCALAPPDATA%\repo-semantic-memory` on Windows. Set `RSM_HOME` to override.

Start MCP in store mode — example `mcp.json`:

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

The agent can then call `rsm_store_list_indexes` and `rsm_store_select_index` to discover and activate indexes without a restart.

## Why I built this

I built RSM because I kept running into the same problem when using coding agents on real repositories.

Before making a useful change, the agent often had to re-read large parts of the codebase, open full files, rediscover the project structure, and piece together how files interacted. That used a lot of context, took time, and still did not always give the agent the right view of the task.

RSM is my attempt to make that first step cheaper and more reliable.

It builds a local index of the repository and exposes task-focused context through MCP and CLI, so an agent can start from relevant files, tests, docs, and symbols instead of exploring from scratch.

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
- expose repository search and ContextPack generation through a local read-only MCP server
- run benchmarks to measure retrieval quality

A typical task might be:

```text
I need to change lifecycle cleanup behavior.
Find the implementation, tests, docs, and nearby context my agent should read first.
```

RSM does not make the change. It prepares the context so your coding agent can start from a better place.

## Core workflows

RSM supports two main workflows.

### MCP workflow, recommended for coding agents

1. **Index** a repository.
2. **Start** the local MCP server.
3. **Let your agent call RSM tools** such as `rsm_search`, `rsm_find_related`, and `rsm_prepare_context`.
4. **Review the returned context** before editing important code.
5. **Refresh the index explicitly** when the repository changes.

### CLI workflow, useful for manual use and debugging

1. **Index** a repository.
2. **Search** for task-relevant context.
3. **Inspect related files or symbols.**
4. **Prepare a ContextPack** for the task.
5. **Give that ContextPack to your coding agent manually.**
6. **Optionally generate a project brief** for future sessions.

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

RSM includes a local read-only MCP server for agent workflows.

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

Near-term work focuses on:

- non-Python and interface-file indexing
- search and ranking refinement
- `find_related` refinement
- ContextPack balance and noise reduction
- MCP documentation and store-mode hardening
- optional deterministic snippets/chunks if benchmarks justify them

Deferred technical work includes:

- broader language-specific symbol extraction
- richer relation extraction
- optional semantic/chunk retrieval if benchmarks justify it
- graph export or external backend integrations
- packaging and release workflow hardening

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
