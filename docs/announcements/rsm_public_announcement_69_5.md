# RSM Public Announcement Drafts 69.5

Status: Draft — not yet published.

---

## 1. GitHub / Repository Announcement

# Announcing repo-semantic-memory

`repo-semantic-memory` (`rsm`) is a local tool that indexes a repository and prepares focused context for coding agents.

```text
Index the repo -> search for task context -> prepare a ContextPack -> give it to your agent
```

## Why I built this

I kept running into the same problem when using coding agents on real repositories.

Before making a useful change, the agent often re-read large parts of the codebase, opened full files, rediscovered project structure, and pieced together how files interacted. That used a lot of context, took time, and still did not always give the agent the right view of the task.

RSM is my attempt to make that first step cheaper and more reliable. It builds a local index of the repository and uses it to prepare focused context for a specific development task — so your agent starts from the right files instead of exploring from scratch.

## What it does today

RSM indexes Python and Markdown files in your repository and lets you:

- **Search** for task-relevant files, symbols, tests, and docs.
- **Find related entities** — tests, imports, exports, callers, and callees — starting from a known file or symbol.
- **Prepare ContextPacks** — task-specific, budget-bounded context packages with source citations.
- **Generate project briefs** — compact Markdown summaries that an agent can read before calling any RSM tools.
- **Expose the workflow through MCP** — a local read-only MCP server gives coding agents direct access to search, find-related, and context pack tools.

Everything is deterministic: same index, same query, same result. No LLM calls, no network access, no randomized ordering.

RSM is strongest today for Python and documentation-heavy repositories.

## How to try it

Install dependencies, build an index, and prepare your first context pack:

```bash
uv sync --all-groups
uv run rsm index . --db .rsm/index.sqlite
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 8000 \
  --profile agent_standard
```

Generate a project brief that your agent can use for orientation:

```bash
uv run rsm project-brief --db .rsm/index.sqlite --force
```

Use RSM through MCP in VS Code or Claude Code:

```bash
uv run rsm mcp serve --repo /path/to/repo --db /path/to/index.sqlite
```

## Current limitations

RSM is experimental pre-1.0 software. It is useful today, but it is not a complete code intelligence platform.

- Strongest for Python and Markdown. Non-Python files are indexed as file-level entities only (no symbol extraction).
- No embeddings or vector search. RSM uses BM25 lexical scoring by design.
- No GUI, no automatic background indexing, no watch mode. You run `rsm index` explicitly.
- ContextPacks are retrieval aids, not correctness guarantees. Verify important claims against the actual source files.
- No `.msg`/`.srv`/`.action` indexing yet (relevant for ROS 2 users).

For the full list, see [Known Limitations](https://github.com/apajon/repo-semantic-memory/blob/main/docs/known_limitations.md).

These limitations do not block current use for Python codebase exploration, documentation-heavy work, or local agent workflows.

## What is next

The [roadmap](https://github.com/apajon/repo-semantic-memory/blob/main/docs/design/roadmap.md) covers the near-term backlog:

- **68.x**: Non-Python / interface-file indexing (`.msg`, `.srv`, `.action`, and others).
- **63.x**: Search refinement.
- **64.x**: `find_related` refinement.
- **65.x**: ContextPack refinement.

Tracks are not committed release promises. Priorities are driven by benchmarks, dogfooding on real repositories, and real agent workflow failures.

[README](https://github.com/apajon/repo-semantic-memory) · [Quickstart](https://github.com/apajon/repo-semantic-memory/blob/main/docs/quickstart.md) · [Examples](https://github.com/apajon/repo-semantic-memory/blob/main/docs/usage/examples.md) · [MCP](https://github.com/apajon/repo-semantic-memory/blob/main/docs/usage/mcp.md) · [Limitations](https://github.com/apajon/repo-semantic-memory/blob/main/docs/known_limitations.md) · [Roadmap](https://github.com/apajon/repo-semantic-memory/blob/main/docs/design/roadmap.md)

---

## 2. Short Social Post

I built `repo-semantic-memory` because coding agents waste too much time reading entire files and rediscovering project structure before they can make a useful change.

RSM indexes your local repository (Python + Markdown), retrieves task-relevant files, tests, and docs, and prepares a focused ContextPack to give to your agent before it starts editing.

It is local, deterministic, and read-only. No LLM calls, no network access. Pre-1.0 and experimental — honest about what it does not do yet.

If you work with Python repos and coding agents, give it a try:

```bash
uv sync --all-groups
uv run rsm index . --db .rsm/index.sqlite
uv run rsm pack --db .rsm/index.sqlite --task "your task here" --budget 8000
```

Link: [repo-semantic-memory on GitHub](https://github.com/apajon/repo-semantic-memory)

---

## 3. ROS Discourse Draft

> **Note:** RSM is not a ROS-specific project. This draft is for the ROS community because RSM was dogfooded on `lifecore_ros2` and may be useful to ROS developers working with coding agents on larger Python/documentation-heavy repositories.
>
> **Suggested category:** General / Software Engineering
> **Suggested tags:** `tools`, `python`, `developer-experience`

### repo-semantic-memory: focused repo context for coding agents

I built `repo-semantic-memory` (`rsm`) while working on `lifecore_ros2` — a Python lifecycle framework for ROS 2 nodes.

The problem was simple: every time I asked a coding agent to make a change, it spent a lot of time re-reading files, rediscovering the project structure, and piecing together how modules interacted — before it could do anything useful.

RSM indexes a local repository and prepares focused ContextPacks for specific tasks. Instead of "explore the whole repo," the agent gets the files, tests, docs, and related symbols that matter for the task — with source citations and a character budget.

It works through CLI commands or an MCP server (VS Code, Claude Code, etc.).

### What it does for ROS 2 developers

- Indexes Python packages and Markdown docs.
- Finds task-relevant files, tests, and docs across the workspace.
- Generates project briefs that an agent can read before editing.
- Exposes search, find-related, and context pack tools through MCP.

### Honest limitations

- **No `.msg`/`.srv`/`.action` indexing yet.** This is a planned feature (see roadmap) but not implemented. If your task depends on interface files, RSM will not surface them today.
- RSM is experimental pre-1.0. It is useful but not a complete solution.
- It works best for Python and documentation-heavy repos.

### Try it

```bash
uv sync --all-groups
uv run rsm index . --db .rsm/index.sqlite
uv run rsm pack --db .rsm/index.sqlite --task "validate lifecycle cleanup" --budget 8000
uv run rsm project-brief --db .rsm/index.sqlite --force
```

[GitHub repo](https://github.com/apajon/repo-semantic-memory) · [Known limitations](https://github.com/apajon/repo-semantic-memory/blob/main/docs/known_limitations.md) · [Roadmap](https://github.com/apajon/repo-semantic-memory/blob/main/docs/design/roadmap.md)

---

## 4. Tagline Options

Short taglines for README, social bios, or project descriptions:

1. Give coding agents the right repo context before they edit code.
2. Local repository memory for coding-agent workflows.
3. Focused ContextPacks for coding agents.
4. Index your repo. Prepare context. Give it to your agent.
5. Stop letting coding agents read your entire repo. Give them a ContextPack.
6. Deterministic, source-cited context for coding agents.
7. What if your coding agent started from the right files?
8. RSM: index, search, pack — give your agent the context it needs.

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

- [ ] Review wording — ensure no overclaiming, no hype language.
- [ ] Verify all links resolve correctly against the current `main` branch.
- [ ] Ensure the release validation (69.4) passed cleanly.
- [ ] Check that the quickstart flow works from a fresh clone.
- [ ] Confirm the roadmap and limitations docs are up to date.
- [ ] Decide which channels to post to (GitHub Discussions, ROS Discourse, social).
- [ ] Do not post until the maintainer explicitly approves.
