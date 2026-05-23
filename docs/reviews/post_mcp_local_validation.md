Post-MCP local validation

Status: passed with output-ergonomics follow-up recommended.

This report validates the first local stdio MCP-compatible JSON-RPC prototype for RSM. It is a technical validation report, not user-facing onboarding documentation.

Verdict

MCP raw output passed, Copilot client integration passed, output ergonomics improvement recommended.

Detailed status:

MCP local transport                  OK
JSON-RPC initialize/tools/list        OK
Tool surface phase 1                  OK
rsm_status                            OK
rsm_search_symbols                    OK
rsm_build_context_pack                OK
Copilot can call RSM MCP tools         OK
Raw MCP paths                         OK
Copilot summary fidelity              Partially OK, needs output ergonomics hardening

1. Server handshake and JSON-RPC transport

The server responds correctly to initialize with:

protocolVersion: 2024-11-05
serverInfo.name: repo-semantic-memory
serverInfo.version: 0.24.0

The server instructions correctly describe the session as read-only local RSM tooling, with fixed --repo and --db configuration for the session.

The direct JSON-RPC smoke test confirms:

initialize      OK
tools/list      OK
shutdown        OK
no traceback    OK

2. Phase 1 tool surface

The phase 1 MCP tool surface exposes the expected read-only tools:

rsm_status
rsm_search_symbols
rsm_explain_entity
rsm_build_context_pack
rsm_query_graph
rsm_validate_patch_context
rsm_get_git_summary

No evidence was found that write or execution tools are exposed.

The following remain absent as intended:

rsm_index
rsm_export_ai
rsm_export_jsonl
rsm_import_jsonl
invariant writes
test execution
patch application
arbitrary command execution

This matches the intended phase 1 safety model.

3. rsm_status

The Copilot client successfully called rsm_status.

Observed values:

Entities: 1,358
Relations: 2,701
Package Version: 0.24.0
Schema Version: 0.1.0
Context Pack Version: 0.1.0
Auto-index: false
Read-only: true
Extractors: filesystem, markdown_outline, python_ast, python_exports, test_relationships

This confirms that the MCP server can expose the indexed repository status without mutating the index.

4. Direct rsm_search_symbols validation

A direct JSON-RPC call was made with:

{
  "name": "rsm_search_symbols",
  "arguments": {
    "query": "context pack ranking",
    "limit": 10
  }
}

The raw MCP output returned real repository paths and symbols, including:

src/repo_semantic_memory/context/context_pack.py
src/repo_semantic_memory/context/render_markdown.py
src/repo_semantic_memory/context/pack_builder.py
src/repo_semantic_memory/context/ranking.py
tests/context/test_pack_builder.py

Representative returned symbols:

repo_semantic_memory.context.context_pack
repo_semantic_memory.context.context_pack.ContextPack
repo_semantic_memory.context.render_markdown.render_context_pack_markdown
repo_semantic_memory.context.pack_builder.build_context_pack
repo_semantic_memory.context.pack_builder._ranking_reason_priority
repo_semantic_memory.context.pack_builder._trim_ranking_breakdown
repo_semantic_memory.context.pack_builder._select_ranking_breakdowns
repo_semantic_memory.context.ranking
tests.context.test_pack_builder.test_ranking_breakdown_is_deterministic

The direct output did not contain previously hallucinated paths or symbols such as:

src/rsm/semantic/ranking.py
src/rsm/semantic/context_pack.py
src/rsm/cli/pack.py
ContextPackRanker
RankingProfile
ContextPackBuilder

Conclusion:

rsm_search_symbols raw MCP output is correct.

5. Direct rsm_build_context_pack validation

A direct JSON-RPC call was made with:

{
  "name": "rsm_build_context_pack",
  "arguments": {
    "task": "Find where context pack ranking is implemented",
    "budget_chars": 8000,
    "format": "markdown",
    "profile": "agent_standard",
    "explain_ranking": true,
    "include_semantic_components": true
  }
}

The context pack returned real repository paths, including:

src/repo_semantic_memory/context/ranking.py
src/repo_semantic_memory/context/context_pack.py
src/repo_semantic_memory/context/render_markdown.py
src/repo_semantic_memory/context/pack_builder.py
src/repo_semantic_memory/mcp/handlers.py
src/repo_semantic_memory/mcp/runtime.py
tests/context/test_pack_builder.py
src/repo_semantic_memory/eval/baselines.py
src/repo_semantic_memory/mcp/tools.py

The pack selected relevant entities around context-pack ranking and rendering, including:

repo_semantic_memory.context.ranking
repo_semantic_memory.context.context_pack
repo_semantic_memory.context.context_pack.ContextPack
repo_semantic_memory.context.render_markdown.render_context_pack_markdown
repo_semantic_memory.context.pack_builder.build_context_pack
repo_semantic_memory.context.pack_builder._ranking_reason_priority
repo_semantic_memory.context.pack_builder._trim_ranking_breakdown
repo_semantic_memory.context.pack_builder._select_ranking_breakdowns
repo_semantic_memory.context.ranking.RankingBreakdown
repo_semantic_memory.context.ranking.RankingReason
repo_semantic_memory.mcp.handlers.handle_build_context_pack
repo_semantic_memory.mcp.runtime._tool_build_context_pack
repo_semantic_memory.mcp.tools.BuildContextPackRequest

A structural relation was also returned:

kind: contains
source: repo_semantic_memory.context.ranking
target: repo_semantic_memory.context.ranking.RankingBreakdown

Conclusion:

rsm_build_context_pack raw MCP output is correct and useful for local dogfooding.

6. Copilot strict rsm_search_symbols validation

When instructed to print raw returned fields and avoid inference, Copilot successfully called rsm_search_symbols.

The returned symbols matched the direct JSON-RPC output:

context_pack
ContextPack
render_context_pack_markdown
build_context_pack
_ranking_reason_priority
_trim_ranking_breakdown
_ranking_fixture_root
_select_ranking_breakdowns
ranking
test_ranking_breakdown_is_deterministic

Scores were also preserved in the Copilot-rendered output.

Observed weakness:

Copilot sometimes displayed shortened file names such as `pack_builder.py` instead of the full repo-relative path `src/repo_semantic_memory/context/pack_builder.py`.

The full paths were present in the raw MCP payload under source_range.path.

Conclusion:

Copilot can call the tool, but output rendering is more reliable when prompts explicitly request raw fields.

7. Copilot strict rsm_build_context_pack validation

When instructed to print raw selected files and selected relations before summarizing, Copilot successfully called rsm_build_context_pack.

It extracted the expected files:

ranking.py
context_pack.py
render_markdown.py
pack_builder.py
handlers.py
runtime.py
test_pack_builder.py
baselines.py
tools.py

It also printed the selected relation:

kind: contains
source: repo_semantic_memory.context.ranking
target: repo_semantic_memory.context.ranking.RankingBreakdown

Its summary was broadly consistent with the raw output:

Core ranking models: ranking.py
Context pack builder: pack_builder.py
Integration points: handlers.py, runtime.py, tools.py
Tests/baselines: test_pack_builder.py, baselines.py

Observed weakness:

Copilot summarized file paths as short basenames instead of preserving full repo-relative paths.

Conclusion:

Copilot integration is usable, but MCP output should become more machine-friendly to reduce summarization loss.

8. Initial non-strict Copilot hallucination

An earlier non-strict Copilot test produced invented paths and symbols such as:

src/rsm/semantic/ranking.py
src/rsm/semantic/context_pack.py
src/rsm/cli/pack.py
ContextPackRanker
RankingProfile
ContextPackBuilder

Direct JSON-RPC output proved that these did not come from RSM.

Classification:

Client summarization / inference issue, not MCP server failure.

This validates the need for both:

1. stricter usage prompts for agents
2. more explicit MCP result fields

9. Safety status

Based on the observed tests and tool surface:

Read-only phase 1                  OK
No auto-indexing                   OK
No exposed write tools             OK
No arbitrary command execution      OK
No patch application               OK
No test execution                  OK
No Docker / cloud / daemon / HTTP  OK

rsm_get_git_summary may use bounded local Git inspection through existing fixed logic, but this is not arbitrary command execution.

10. Final classification

MCP server issue found:                 no
MCP raw output passed:                  yes
Copilot tool call passed:               yes
Client summarization issue observed:    yes
Output ergonomics hardening recommended: yes

Final status:

MCP local dogfooding passed with output-ergonomics follow-up recommended.

11. Recommended follow-up: Prompt 46

The next step should be MCP output ergonomics hardening.

Recommended changes:

1. Add top-level `path` to `rsm_search_symbols` results.
2. Add top-level `start_line` and `end_line` to `rsm_search_symbols` results.
3. Add top-level numeric `score` where available.
4. Add `selected_files` to `rsm_build_context_pack`.
5. Keep `suggested_files_to_inspect` for compatibility.
6. Add compact `agent_instructions` to relevant MCP tool outputs.
7. Update MCP usage docs to tell agents to rely on:
   - path
   - start_line
   - end_line
   - selected_files
   - selected_entities
   - selected_relations

Suggested agent_instructions:

{
  "agent_instructions": [
    "Use only paths listed in this response.",
    "Do not infer missing paths, symbols, or class names.",
    "Verify edits against cited source ranges."
  ]
}