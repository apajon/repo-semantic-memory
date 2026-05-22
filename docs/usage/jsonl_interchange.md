# JSONL interchange

JSONL export/import is the machine-facing portability surface for indexed entities, relations, and metadata.

```bash
uv run rsm export-jsonl --db .rsm/index.sqlite --out .rsm/export
uv run rsm import-jsonl --in .rsm/export --db .rsm/imported.sqlite
```

Use JSONL when another local tool needs a batch representation of the index. Use `.ai/`
when an agent needs compact, file-based context artifacts. MCP-style handlers/contracts
exist, but no MCP runtime server is shipped yet.

JSONL records are derived from the repository index. They do not replace source code, docs, tests, or Git history as source of truth.
