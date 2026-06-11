# RSM Project Brief

> **Status:** Implemented in 62.7
> **Command:** `rsm project-brief`

## What It Is

The `rsm project-brief` command generates a compact, deterministic Markdown
summary of an indexed repository. The generated file is designed to be read by
coding agents before they use RSM MCP tools — it provides immediate orientation
without repeated search calls.

## Quick Start

```bash
# Generate a project brief for an indexed repo
rsm project-brief --db /path/to/.rsm/index.sqlite

# Specify a custom output path
rsm project-brief --db .rsm/index.sqlite --output my_brief.md

# Overwrite existing output
rsm project-brief --db .rsm/index.sqlite --force

# Use a smaller character budget (default: 15000)
rsm project-brief --db .rsm/index.sqlite --max-chars 8000
```

## Output

The command writes a Markdown file containing:

1. **Repository Identity** — root path, DB path, RSM version, entity counts
2. **Readiness / Freshness** — index status (fresh, stale, unknown), warnings
3. **Purpose / Scope** — short orientation paragraph
4. **Main Code Areas** — modules and key entities grouped by directory
5. **Important Entry Points** — `__init__.py` modules and top-level classes
6. **Test Areas** — directories containing test files
7. **Docs / Reviews / Planning Notes** — documentation files in the index
8. **Common Agent Workflows** — how to use RSM tools on this repo
9. **Known Caveats** — staleness warnings, ranking limitations
10. **Suggested Benchmark Tasks** — reference to benchmark cases

## Default Output Path

If `--output` is not specified, the brief is written to
`PROJECT_CONTEXT.md` in the **same directory as the index DB**.

For example, if the index lives at `.rsm/index.sqlite`, the brief is
written to `.rsm/PROJECT_CONTEXT.md`.

This avoids writing files inside the target source repository by default.

## Character Budget

The default budget is **15,000 characters** (~3,750 tokens at 4 chars/token).

Use `--max-chars` to increase or decrease. If the generated content exceeds
the budget, sections are truncated deterministically from the bottom, and a
truncation note is appended.

## Overwrite Behavior

- If the output file already exists and `--force` is **not** provided,
  the command fails with a clear error message.
- Use `--force` to overwrite the existing file.

## Determinism

The generator is **fully deterministic**: the same index database always
produces the same output. There are no LLM calls, no network access, and
no randomized ordering.

## Freshness

The "Readiness / Freshness" section reports the index status:

- `fresh` — index is up to date with the repository
- `stale` — repository HEAD has changed since indexing
- `maybe_stale` — working tree is dirty
- `unknown` — freshness could not be determined

A warning banner is displayed for any state other than `fresh`.

**Always check freshness before trusting the brief.** Re-index with
`rsm index` if the brief warns about staleness.

## When to Generate

- After indexing a new repository
- After re-indexing an existing repository
- When returning to a project after days or weeks
- Before starting a new agent session on an unfamiliar repository

Generation is **explicit only**. There is no automatic generation after
indexing — the user must run `rsm project-brief` explicitly.

## Limitations

- **No auto-generation.** The user must remember to run the command.
- **No MCP resource.** The brief is a static file, not exposed as an MCP
  resource. Agents must read it as a regular file.
- **No content extraction.** The brief lists entity metadata (names, paths),
  not file contents or code snippets.
- **No per-repo customization.** All briefs follow the same template.
