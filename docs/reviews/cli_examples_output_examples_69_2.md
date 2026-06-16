# CLI Examples and Output Examples 69.2

## 1. Summary

Added concrete CLI examples with representative output snippets across all major RSM workflows:
indexing, discovery, ContextPack, project brief, MCP repo/db mode, and MCP store mode.

Created a central `docs/usage/examples.md` hub and added cross-references from existing docs.

All output snippets were captured from real `uv run rsm` commands against the
`repo-semantic-memory` repository itself (indexed at `.rsm/index.sqlite`).

## 2. Docs Updated

| File | Change |
|---|---|
| `docs/usage/examples.md` | **Created** — central examples hub with 7 sections |
| `docs/quickstart.md` | Added end-to-end annotated flow + cross-ref to examples |
| `docs/usage/cli.md` | Added cross-ref banner to examples |
| `docs/usage/mcp.md` | Added cross-ref banner to examples |
| `docs/usage/project_brief.md` | Added output excerpt + cross-ref to examples |

## 3. Examples Added

- **indexing:** `rsm index . --db .rsm/index.sqlite` with real progress output
- **discovery:** `rsm repo-map` with representative Markdown output
- **ContextPack:** `rsm pack --task "..." --budget 8000` with real symbol/file/citation output
- **project brief:** `rsm project-brief --force` with real output excerpt
- **MCP repo/db:** `rsm mcp serve --repo ... --db ...` with `mcp.json` config + tool table
- **store mode:** `rsm store register/list` + `rsm mcp serve --store` with `mcp.json` config + tool table
- **evaluation:** `rsm eval retrieval/compare` commands

## 4. Output Capture

All output snippets captured from real commands:

```bash
uv run rsm index . --db .rsm/index.sqlite
uv run rsm repo-map --db .rsm/index.sqlite --budget 4000 --profile agent_standard
uv run rsm pack --db .rsm/index.sqlite --task "find where context pack ranking happens" --budget 8000 --profile agent_standard
uv run rsm project-brief --db .rsm/index.sqlite --force
uv run rsm --help
uv run rsm index --help
uv run rsm pack --help
uv run rsm project-brief --help
uv run rsm mcp serve --help
uv run rsm store --help
```

Key finding: `rsm search` is not a CLI command — search is MCP-only (`rsm_search` tool).
The CLI equivalent for broad discovery is `rsm repo-map`.

## 5. Sanitization

- ✅ Absolute paths replaced with `/path/to/...` placeholders
- ✅ Machine-specific timestamps kept (informative)
- ✅ Entity counts kept (representative of a real repo)
- ✅ No user names in output
- ✅ No long hashes beyond commit short SHAs

## 6. Issues Found

None. The existing docs were already well-structured. The main gap was the
absence of concrete output examples showing what users would actually see.

## 7. Recommendation

**Can RSM proceed to 69.3 known limitations and roadmap cleanup?**

`yes`

The examples are concrete, based on real command output, sanitized, and
organized by workflow step. The docs now give users a clear picture of what
RSM produces before they install or configure it.
