# MCP runtime design

A full MCP runtime server is intentionally deferred.

## Why defer runtime

- Tool contracts are still pre-stable.
- The MVP should stay local-first and scriptable without a daemon.
- Security boundaries need review before exposing agent-facing query execution.
- CLI, `.ai/`, JSONL, and pure handlers cover current offline workflows.

## Future runtime requirements

A future runtime must:

- read only from explicitly configured local repository/index paths
- return source citations and uncertainty records
- enforce bounded output for context windows
- avoid hidden re-indexing or mutation
- avoid network access, remote APIs, LLM calls, embeddings, vector databases, and arbitrary command execution
- remain deterministic for identical local inputs

## Static `.ai/` vs MCP runtime

`.ai/` export is a portable snapshot. A future MCP runtime would be a live local query surface over the current index. Both must preserve the rule that source code, docs, tests, and Git history are authoritative.
