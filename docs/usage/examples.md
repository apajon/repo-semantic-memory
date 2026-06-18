# RSM CLI Examples

Concrete command examples with representative output, organized by workflow step.

All examples assume dependencies are installed:

```bash
uv sync --all-groups
```

---

## 1. Basic Indexing

Build a local SQLite index of the current repository.

```bash
uv run rsm index . --db .rsm/index.sqlite
```

**What the output looks like:**

```text
indexing: scanning files...
indexing: discovered files: python=144 markdown=76 other=15 total=235
indexing: extracting Markdown...
indexing: Markdown complete: 76/76 files, elapsed=1.4s
indexing: parsing Python...
indexing: Python 1/144 files...
indexing: Python 100/144 files...
indexing: Python complete: 144/144 files, elapsed=2.4s
indexing: extracting exports...
indexing: exports complete: 19/19 files, elapsed=0.2s
indexing: computing test relationships from entities=3738 relations=6421...
indexing: test relationships complete: added=315 total_relations=6736, elapsed=0.1s
indexing: writing index...
indexing: writing index complete: entities=3738 relations=6736, elapsed=1.9s
indexing: complete: entities=3738 relations=6736, elapsed=7.5s
entities=3738 relations=6736
```

> The final line on stdout (`entities=… relations=…`) is machine-readable.
> Everything else goes to stderr.

**What this tells you:**

- The index found 235 files (144 Python, 76 Markdown, 15 other).
- It extracted 3,738 entities and 6,736 relations.
- The whole process took about 7.5 seconds on this repo.

---

## 2. Broad Discovery (Repo Map)

Use a repo map when you don't yet know where to look.

```bash
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
```

**What you get:**

A Markdown overview of modules, classes, and functions grouped by file.
This is broad orientation — it shows what exists, not what's relevant to a task.

```markdown
# Repo map

## src/repo_semantic_memory/__init__.py
- module `repo_semantic_memory` src/repo_semantic_memory/__init__.py:1

## src/repo_semantic_memory/cli.py
- module `repo_semantic_memory.cli` src/repo_semantic_memory/cli.py:1
- function `repo_semantic_memory.cli.build_parser` ...
- function `repo_semantic_memory.cli.main` ...
- function `repo_semantic_memory.cli._run_index_command` ...
...

## src/repo_semantic_memory/context/pack_builder.py
...
```

Use repo maps to get your bearings before narrowing down with a context pack.

---

## 3. Task-Specific Context (ContextPack)

Prepare focused context for a concrete task. This is the primary workflow.

```bash
uv run rsm pack \
  --db .rsm/index.sqlite \
  --task "find where context pack ranking happens" \
  --budget 8000 \
  --profile agent_standard
```

**What the output looks like (excerpt):**

```markdown
# Context pack

Task: find where context pack ranking happens

## Selected symbols
- `repo_semantic_memory.context.context_pack.ContextPack` src/repo_semantic_memory/context/context_pack.py:47-107
- `repo_semantic_memory.context.pack_builder.build_context_pack` src/repo_semantic_memory/context/pack_builder.py:155-496
- `repo_semantic_memory.context.pack_builder._ranking_reason_priority` src/repo_semantic_memory/context/pack_builder.py:1006-1007
- `tests.context.test_pack_builder.test_ranking_breakdown_is_deterministic` tests/context/test_pack_builder.py:642-660
- `tests.context.test_pack_builder.test_explain_ranking_retains_structural_relations` tests/context/test_pack_builder.py:743-778
...

## Suggested files to inspect
- `src/repo_semantic_memory/context/context_pack.py`
- `src/repo_semantic_memory/context/pack_builder.py`
- `src/repo_semantic_memory/context/render_markdown.py`
- `tests/context/test_pack_builder.py`
- `src/repo_semantic_memory/context/ranking.py`
- `tests/mcp/test_handlers.py`

## Source citations
- entity `python:src/repo_semantic_memory/context/context_pack.py:class:...ContextPack` ...
- entity `python:src/repo_semantic_memory/context/pack_builder.py:function:...build_context_pack` ...
...
```

**What this tells you:**

- **Selected symbols** are the entities most relevant to your task.
- **Suggested files** are the files you should read first.
- **Source citations** tie every symbol back to a specific file and line range.
- The output stays within the budget you set (here 8,000 characters).

> Give this output to your coding agent before asking it to make changes.
> The agent starts from the right files instead of exploring from scratch.

---

## 4. Project Brief

Generate a compact Markdown summary of the indexed repository.

```bash
uv run rsm project-brief --db .rsm/index.sqlite --force
```

**Output path:** `.rsm/PROJECT_CONTEXT.md` (alongside the index database).

**What the brief contains (excerpt):**

````markdown
# RSM Project Brief: repo-semantic-memory

## Repository Identity
- **Root:** `/path/to/repo-semantic-memory`
- **Index DB:** `.rsm/index.sqlite`
- **RSM version:** `0.37.1`
- **Total entities:** 3829
- **Entity breakdown:** source=787, test=1505, doc=1422

## Readiness / Freshness
- **Index status:** `fresh`
- **Indexed at:** 2026-06-16T02:16:05Z

## Main Code Areas
### `src/repo_semantic_memory/` (8 key entities)
- `function` **build_parser** — `src/repo_semantic_memory/cli.py`
- `function` **main** — `src/repo_semantic_memory/cli.py`
...

### `src/repo_semantic_memory/context/` (8 key entities)
- `class` **BM25Config** — `src/repo_semantic_memory/context/bm25.py`
- `class` **FieldedBM25Index** — `src/repo_semantic_memory/context/bm25.py`
...

## Test Areas
- `tests/context/` — context pack and ranking tests
- `tests/mcp/` — MCP handler tests
...

## Known Caveats
- Index staleness: re-index if the repository has changed.
- Ranking is BM25-based; lexical matches dominate.
...

## Common Agent Workflows
1. `rsm_prepare_context("your task description")`
2. `rsm_get_context_page(result_set_id, stream="files", ...)`
...
````

**When to generate one:**

- After indexing a new repository.
- When returning to a project after days or weeks.
- Before starting a new agent session on an unfamiliar repository.

> The project brief is a static file. Agents must read it as a regular file —
> it is not exposed as an MCP resource.

---

## 5. MCP — Repo/DB Mode

Expose a single repository index to MCP-compatible clients (VS Code, Claude Code, etc.).

```bash
uv run rsm mcp serve --repo /path/to/your/repo --db /path/to/your/repo/.rsm/index.sqlite
```

**Example `mcp.json` for VS Code:**

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

**Available tools in repo/db mode:**

| Tool | What it does |
|---|---|
| `rsm_search` | Find relevant indexed files, symbols, docs, and tests |
| `rsm_find_related` | Expand around a known file, symbol, or qualified name |
| `rsm_prepare_context` | Build a task-centered ContextPack for a coding agent |
| `rsm_get_context_page` | Page through a larger ContextPack result |

---

## 6. MCP — Store Mode

For working across multiple repositories, register them in the Index Store.

### Register repositories

```bash
uv run rsm store register /path/to/repo1 --index
uv run rsm store register /path/to/repo2 --index
```

### List registered repositories

```bash
uv run rsm store list
```

**Example output:**

```text
repo1    /path/to/repo1    /home/user/.local/share/repo-semantic-memory/indexes/repo1/index.sqlite
repo2    /path/to/repo2    /home/user/.local/share/repo-semantic-memory/indexes/repo2/index.sqlite
```

### Start MCP in store mode

```bash
uv run rsm mcp serve --store
```

**Example `mcp.json` for VS Code (store mode):**

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

**Available tools in store mode (7 tools):**

| Tool | What it does |
|---|---|
| `rsm_store_list_indexes` | List all registered repository indexes |
| `rsm_store_select_index` | Select the active repository index for this session |
| `rsm_store_current_index` | Show the currently active index |
| `rsm_search` | Find relevant indexed files, symbols, docs, and tests |
| `rsm_find_related` | Expand around a known file, symbol, or qualified name |
| `rsm_prepare_context` | Build a task-centered ContextPack |
| `rsm_get_context_page` | Page through a larger ContextPack result |

---

## 7. Evaluation and Benchmarks

Run deterministic benchmark evaluation against an existing index.

```bash
uv run rsm eval retrieval --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --json
uv run rsm eval compare --db .rsm/index.sqlite --dataset benchmarks/tasks.yaml --budget 4000 --json
```

Interpret benchmark results as internal and directional — not broad superiority claims.

---

## Next Reading

- [CLI usage](cli.md) — full command reference
- [MCP usage](mcp.md) — detailed MCP tool reference
- [Project brief](project_brief.md) — brief generation details
- [Quickstart](../quickstart.md) — first-run walkthrough
