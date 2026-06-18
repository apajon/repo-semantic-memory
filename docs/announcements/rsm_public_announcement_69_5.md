# RSM Public Announcement Drafts 69.5

Status: Draft — not yet published.

---

## 1. GitHub / Repository Announcement

# Announcing repo-semantic-memory

I built `repo-semantic-memory` (`rsm`) because I kept running into the same frustration with coding agents.

They can be useful, but on a real repository they often start by doing the same expensive work again and again: reading large files, rediscovering the project structure, opening tests, guessing where behavior lives, and slowly building enough context before they can make a useful change.

That costs time. It also consumes a lot of context.

RSM is my attempt to make that first step more explicit.

It builds a local index of a repository and exposes a small set of tools that help a coding agent ask better questions before editing code:

```text
What files matter for this task?
What tests are related?
What docs explain this area?
What context should I read before changing anything?
```

You can use RSM from the CLI, but the most useful workflow is through MCP: a compatible coding agent can call RSM directly from the editor workflow to search the repo, find related context, and prepare a focused ContextPack.

```text
Index the repo -> configure MCP -> agent asks RSM -> edit with better context
```

## What RSM does

RSM is a local repository context layer for coding agents.

Today, it can:

- index Python code and Markdown documentation
- search for files, symbols, tests, and docs related to a task
- expand from a known file or symbol to nearby context
- prepare source-cited ContextPacks with a character budget
- generate a compact project brief for agent orientation
- expose the workflow through a local read-only MCP server

The MCP side is important.

Instead of asking an agent to explore the repository from scratch, you can give it access to RSM tools:

- `rsm_search`
- `rsm_find_related`
- `rsm_prepare_context`
- `rsm_get_context_page`

For multi-repo or multi-index workflows, RSM also has a store mode so one MCP server can expose several registered repository indexes.

The server is local and read-only. It does not edit files, and it does not auto-index in the background. You explicitly build or refresh the index with `rsm index`.

RSM is designed to be deterministic: given the same index and query, it should produce stable, repeatable results. Retrieval does not use LLM calls, does not require embeddings, and does not depend on a hosted service.

## Why this matters

A coding agent does not only need instructions. It needs the right context.

Without that context, it may over-read, miss important tests, change the wrong abstraction, or spend half of the conversation reconstructing repository structure.

RSM is not trying to replace the agent.

It is trying to give the agent a better starting point.

## How to try it

Install dependencies and build an index:

```bash
uv sync --all-groups
uv run rsm index . --db .rsm/index.sqlite
```

Expose the index through MCP:

```bash
uv run rsm mcp serve --repo /path/to/repo --db /path/to/index.sqlite
```

Then use the RSM tools from a compatible MCP client.

You can also prepare context manually from the CLI:

```bash
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 8000 \
  --profile agent_standard
```

Generate a project brief for orientation:

```bash
uv run rsm project-brief --db .rsm/index.sqlite --force
```

## Current limitations

RSM is experimental pre-1.0 software.

It is useful today, but it is not a complete code intelligence platform.

Current limitations:

- Python and Markdown/documentation-heavy repositories are the strongest use case today.
- Non-Python files are indexed more shallowly.
- No embeddings or vector search are used by default.
- No GUI, no automatic background indexing, and no watch mode.
- The MCP server is local and read-only. It exposes retrieval tools but does not edit files.
- ContextPacks are retrieval aids, not correctness guarantees. Important claims should still be checked against the source.
- No `.msg`, `.srv`, or `.action` indexing yet, which matters for ROS 2 users.

For the full list, see [Known Limitations](https://github.com/apajon/repo-semantic-memory/blob/main/docs/known_limitations.md).

These limitations do not block current use for Python codebase exploration, documentation-heavy work, or local agent workflows.

## What is next

The [roadmap](https://github.com/apajon/repo-semantic-memory/blob/main/docs/design/roadmap.md) covers the near-term backlog:

- **68.x**: Non-Python / interface-file indexing, including `.msg`, `.srv`, `.action`, and similar files.
- **63.x**: Search refinement.
- **64.x**: `find_related` refinement.
- **65.x**: ContextPack refinement.

These tracks are not release promises. Priorities are driven by benchmarks, dogfooding on real repositories, and real agent workflow failures.

[README](https://github.com/apajon/repo-semantic-memory) · [Quickstart](https://github.com/apajon/repo-semantic-memory/blob/main/docs/quickstart.md) · [Examples](https://github.com/apajon/repo-semantic-memory/blob/main/docs/usage/examples.md) · [MCP](https://github.com/apajon/repo-semantic-memory/blob/main/docs/usage/mcp.md) · [Limitations](https://github.com/apajon/repo-semantic-memory/blob/main/docs/known_limitations.md) · [Roadmap](https://github.com/apajon/repo-semantic-memory/blob/main/docs/design/roadmap.md)

---

## 2. Short Social Post

I built `repo-semantic-memory` because I kept seeing the same pattern with coding agents: before making a useful change, they often had to rediscover the repository from scratch.

RSM gives them a better starting point.

It indexes a local repo and exposes search, related-context, and ContextPack tools through a local read-only MCP server. A compatible coding agent can ask RSM which files, tests, docs, and symbols matter for a task before it starts editing.

CLI workflows are also available for indexing, manual ContextPack generation, project briefs, and evaluation.

It is pre-1.0 and experimental. Python and documentation-heavy repos work best today. Non-Python support is still shallow, and `.msg` / `.srv` / `.action` files are not indexed yet.

Basic flow:

```bash
uv sync --all-groups
uv run rsm index . --db .rsm/index.sqlite
uv run rsm mcp serve --repo /path/to/repo --db /path/to/index.sqlite
```

Link: [repo-semantic-memory on GitHub](https://github.com/apajon/repo-semantic-memory)

---

## 3. ROS Discourse Draft

> **Note:** RSM is not a ROS-specific project. I am sharing it here because I dogfooded it while working on `lifecore_ros2`, and it may be useful to ROS developers using coding agents on larger Python/documentation-heavy repositories.
>
> **Suggested category:** General / Software Engineering
> **Suggested tags:** `tools`, `python`, `developer-experience`, `mcp`

### repo-semantic-memory: local repository context for coding agents

I built `repo-semantic-memory` (`rsm`) while working on `lifecore_ros2`, a Python lifecycle framework for ROS 2 nodes.

The problem was not that the coding agent could not edit code. The problem was that it first had to rediscover the repository: where the behavior lived, which tests mattered, which docs explained the design, and which files were related.

That context-building step became repetitive and expensive.

RSM is an attempt to make that step explicit.

It indexes a local repository and helps prepare task-focused context before the agent starts editing. The main workflow is through MCP: RSM ships with a local read-only MCP server, so compatible agents can call tools like:

- `rsm_search`
- `rsm_find_related`
- `rsm_prepare_context`
- `rsm_get_context_page`

In practice, the agent can ask RSM for task-relevant files, tests, docs, and related context directly from the editor workflow.

CLI commands are also available for indexing, manual ContextPack generation, project briefs, and evaluation.

### What it can help with

For ROS 2 developers working mostly in Python, RSM can help:

- find task-relevant implementation files, tests, and docs
- prepare focused context before using a coding agent
- generate a short project brief for an agent to read before editing
- expose repository search and ContextPack tools through MCP-compatible clients

Store mode can also expose multiple registered repository indexes from one MCP server.

### Honest limitations

RSM is experimental pre-1.0 software.

The most important ROS-related limitation is that it does **not** index `.msg`, `.srv`, or `.action` files yet. That is on the roadmap, but not implemented today. If your task depends heavily on interface files, RSM will miss part of the picture.

It currently works best for Python and documentation-heavy repositories.

The MCP server is local and read-only. It does not edit files and does not auto-index in the background.

### Try it

Build an index:

```bash
uv sync --all-groups
uv run rsm index . --db .rsm/index.sqlite
```

Expose it through MCP:

```bash
uv run rsm mcp serve --repo /path/to/repo --db /path/to/index.sqlite
```

Or prepare a ContextPack manually:

```bash
uv run rsm pack --db .rsm/index.sqlite --task "validate lifecycle cleanup" --budget 8000
uv run rsm project-brief --db .rsm/index.sqlite --force
```

[GitHub repo](https://github.com/apajon/repo-semantic-memory) · [Known limitations](https://github.com/apajon/repo-semantic-memory/blob/main/docs/known_limitations.md) · [Roadmap](https://github.com/apajon/repo-semantic-memory/blob/main/docs/design/roadmap.md)

---

## 4. Tagline Options

Short taglines for README, social bios, or project descriptions:

1. Give coding agents the right repo context before they edit code.
2. A local MCP context server for coding agents.
3. Help your coding agent start from the right files.
4. Index your repo. Expose it through MCP. Let your agent ask for context.
5. Local repository context for coding-agent workflows.
6. Focused, source-cited ContextPacks for coding agents.
7. Stop making coding agents rediscover your repo from scratch.
8. What if your coding agent started from the right files?
9. Task-centered repository retrieval for MCP agent workflows.
10. RSM: local repo context before the agent edits.

---

## 5. Links to Include

For any announcement post, include these links:

| Resource | Path |
|---|---|
| README | `https://github.com/apajon/repo-semantic-memory` |
| Quickstart | `https://github.com/apajon/repo-semantic-memory/blob/main/docs/quickstart.md` |
| CLI Examples | `https://github.com/apajon/repo-semantic-memory/blob/main/docs/usage/examples.md` |
| MCP docs | `https://github.com/apajon/repo-semantic-memory/blob/main/docs/usage/mcp.md` |
| Project brief | `https://github.com/apajon/repo-semantic-memory/blob/main/docs/usage/project_brief.md` |
| Known Limitations | `https://github.com/apajon/repo-semantic-memory/blob/main/docs/known_limitations.md` |
| Roadmap | `https://github.com/apajon/repo-semantic-memory/blob/main/docs/design/roadmap.md` |

---

## 6. Notes Before Posting

- [ ] Review wording one last time.
- [ ] Verify all links resolve correctly against the current `main` branch.
- [ ] Ensure the release validation (69.4) passed cleanly.
- [ ] Check that the quickstart flow works from a fresh clone.
- [ ] Confirm the roadmap and limitations docs are up to date.
- [ ] Decide which channels to post to: GitHub Discussions, GitHub Release, ROS Discourse, social.
- [ ] Do not post until the maintainer explicitly approves.
