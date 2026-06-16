# MCP-First Documentation Positioning 69.6

## 1. Summary

Adjusted public-facing documentation so MCP is presented as a first-class RSM workflow for coding agents, not as a secondary technical detail. The README now leads with MCP, the quickstart splits CLI/MCP paths, and all relevant docs have been updated.

## 2. Problem

During wording review, the maintainer identified that README and documentation positioned RSM as CLI-first:

```
index -> search -> pack -> project brief
```

MCP appeared as a later section, making it look optional or secondary.

## 3. Docs Updated

| File | Change |
|---|---|
| `README.md` | Opening reframed as MCP-first, CLI also; new MCP quickstart section with tool table; store mode simplified |
| `docs/quickstart.md` | Added MCP first line, split mention |
| `docs/usage/mcp.md` | Added: "MCP is the recommended integration path…" as first line |
| `docs/usage/agent_workflows.md` | Added MCP-first opening paragraph with tool names |
| `docs/announcements/rsm_public_announcement_69_5.md` | MCP-first in all three drafts (GitHub, social, ROS Discourse); tools named |

## 4. README Changes

- ✅ Opening: "a local repository context layer for coding agents"
- ✅ MCP mentioned in first paragraph
- ✅ New flow: `Index -> configure MCP -> agent asks RSM -> start editing`
- ✅ MCP quickstart section with tool table (`rsm_search`, `rsm_find_related`, `rsm_prepare_context`, `rsm_get_context_page`)
- ✅ `mcp.json` example in quickstart
- ✅ Store mode simplified, still visible
- ✅ CLI still present and functional

## 5. MCP Docs Changes

- ✅ First line: "MCP is the recommended integration path"
- ✅ Tool reference already strong (untouched)
- ✅ Store mode docs already strong (untouched)

## 6. Announcement Changes

- ✅ All three drafts now lead with MCP
- ✅ Tools named: `rsm_search`, `rsm_find_related`, `rsm_prepare_context`, `rsm_get_context_page`
- ✅ Store mode mentioned: "one MCP server expose multiple registered indexes"
- ✅ CLI still mentioned: "also works from the CLI"

## 7. Remaining Risks

- None. CLI path remains fully documented and functional. MCP is now positioned as the recommended agent path without removing CLI from view.
- No code or behavior changed — purely documentation wording.

## 8. Recommendation

**Can the public announcement proceed after this MCP positioning pass?**

`yes, after wording review`

All docs now position MCP as the first-class integration path while keeping CLI visible and functional. The maintainer should review the final wording.
