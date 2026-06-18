# Public Announcement Draft 69.5

## 1. Summary

Created four announcement drafts for RSM's first public announcement:
- Full GitHub/repository announcement (~750 words)
- Short social post (~150 words)
- ROS Discourse community post (~400 words)
- 8 tagline options

All drafts are honest, readable, non-hype, and clear about pre-1.0 experimental status and current limitations.

## 2. Drafts Created

| Draft | File | Length | Status |
|---|---|---|---|
| GitHub / Repository | `docs/announcements/rsm_public_announcement_69_5.md#1` | ~750 words | Draft |
| Short Social | `docs/announcements/rsm_public_announcement_69_5.md#2` | ~150 words | Draft |
| ROS Discourse | `docs/announcements/rsm_public_announcement_69_5.md#3` | ~400 words | Draft |
| Taglines | `docs/announcements/rsm_public_announcement_69_5.md#4` | 8 options | Draft |

## 3. Positioning

- **Core message:** Give coding agents the right repo context before they edit code.
- **Human background:** Built because coding agents waste context re-reading repos from scratch.
- **Target audience:** Developers using coding agents on real Python/doc-heavy repositories.
- **Maturity:** Clear about experimental pre-1.0 status. Honest about what works and what doesn't.
- **Tone:** Technical, personal, direct. No hype, no marketing language, no "AI-powered" claims.

## 4. Limitations Included

All drafts mention current limitations:

- Python + Markdown strongest; limited non-Python support
- No embeddings/vector search (by design)
- No GUI, no auto-indexing, no watch mode
- ContextPacks are aids, not guarantees
- No `.msg`/`.srv`/`.action` indexing (relevant for ROS 2 users)

Full limitations doc linked in all drafts.

## 5. Channels Covered

| Channel | Draft | Notes |
|---|---|---|
| GitHub Release / Discussions | Section 1 | Full announcement, command examples, MCP mention |
| LinkedIn / Mastodon / Bluesky / X | Section 2 | Short, one concrete benefit, link placeholder |
| ROS Discourse | Section 3 | Community sharing tone, honest about `.msg` gap |
| README / social bios | Section 4 | 8 tagline options |

## 6. Remaining Pre-Post Checklist

- [ ] Review wording — ensure no overclaiming, no hype language.
- [ ] Verify all links resolve correctly against the current `main` branch.
- [ ] Ensure the release validation (69.4) passed cleanly.
- [ ] Check that the quickstart flow works from a fresh clone.
- [ ] Confirm the roadmap and limitations docs are up to date.
- [ ] Decide which channels to post to.
- [ ] Do not post until the maintainer explicitly approves.

## 7. Recommendation

**Can RSM public announcement proceed?**

`yes, after wording review`

All drafts are complete, honest, and ready for human review. No overclaiming detected. Limitations are clearly stated with links to full documentation. The drafts should be reviewed by the maintainer for tone and wording preferences before posting.
