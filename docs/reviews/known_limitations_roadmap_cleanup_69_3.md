# Known Limitations and Roadmap Cleanup 69.3

## 1. Summary

Created a comprehensive `docs/known_limitations.md` and rewrote `docs/design/roadmap.md` for public readability. Updated README and docs index with links to both new docs.

The existing roadmap was stale (mentioned MCP server as "deferred" when it is now implemented). The existing "What RSM is not" section in README was good but lacked depth and a dedicated limitations page.

All content is honest about current gaps without being self-defeating. The tone clarifies that limitations do not block current use for Python-oriented workflows.

## 2. Docs Updated

| File | Change |
|---|---|
| `docs/known_limitations.md` | **Created** — comprehensive limitations doc (7 sections) |
| `docs/design/roadmap.md` | **Rewritten** — public-readable, track-based, current state |
| `README.md` | Added links: Examples, Limitations |
| `docs/README.md` | Added: examples, limitations, roadmap sections |

## 3. Limitations Clarified

All required limitations from the task spec are documented:

- ✅ Strongest today for Python and documentation-heavy repositories
- ✅ Limited non-Python support
- ✅ No `.msg`/`.srv`/`.action` indexing yet
- ✅ No full semantic graph export
- ✅ No embeddings/vector search by default
- ✅ No GUI
- ✅ No automatic background indexing
- ✅ No automatic refresh/watch mode
- ✅ MCP server is local/read-only
- ✅ ContextPacks are retrieval aids, not correctness guarantees
- ✅ Ranking is benchmark-driven but not perfect
- ✅ Project brief depends on index freshness

Additional sections added:

- ✅ Current Strengths (what works well)
- ✅ Experimental Areas (implemented but not fully hardened)
- ✅ What This Means in Practice (when useful / less useful / not blocking)
- ✅ Tone check: no "broken", "not production-grade", or "unusable" language

## 4. Roadmap Clarified

Roadmap rewritten from a stale bullet list to a public-readable track-based format:

- ✅ Current Focus: 69.x public readiness (active)
- ✅ Public Readiness: what 69.x achieves
- ✅ Near-Term Backlog: 68.x (interface files), 63.x (search), 64.x (find_related), 65.x (ContextPack)
- ✅ Deferred: 66.x snippets/chunks feasibility
- ✅ Not Currently Planned: explicit out-of-scope list
- ✅ How Priorities Are Chosen: benchmarks, dogfooding, failures, cost, scope creep
- ✅ Deferred tracks clarified as "not promised"
- ✅ Not a sprint history dump

## 5. Links Updated

- ✅ README header bar: Examples, Limitations added
- ✅ docs/README.md: examples link added in "Start here", new "Limitations and roadmap" section
- ✅ Known limitations doc links to roadmap
- ✅ Roadmap links to nothing external (self-contained)

## 6. Remaining Risks

- The 68.x interface-file track is detailed in the 67.4 backlog plan but summarized in the roadmap. The roadmap intentionally keeps it concise; the 67.4 plan contains the full detail.
- The roadmap mentions track numbers (68.x, 63.x, etc.) that are internal RSM conventions. A new reader may not know what the numbers mean. This is acceptable — the numbers are stable identifiers, and the descriptions clarify what each track covers.

## 7. Recommendation

**Can RSM proceed to 69.4 release-readiness validation?**

`yes`

The known limitations are documented honestly, the roadmap is public-readable and current, and all docs cross-link properly. No implementation changes were made.
