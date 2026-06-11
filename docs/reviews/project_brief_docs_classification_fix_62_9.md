# Project Brief Docs Classification Fix 62.9

> **Date:** 2026-06-11
> **Status:** Complete
> **Prerequisites:** 62.7 (implementation), 62.8 (evaluation)

## 1. Summary

Fixed the project brief generator so that documentation, RFC, review, and
planning files are correctly surfaced in the "Docs / Reviews / Planning Notes"
section. The 62.8 evaluation found this section was empty for lifecore_ros2
because the path-role classification was too narrow.

## 2. Bug

62.8 found:

```
Docs / Reviews / Planning Notes section:
  "No indexed documentation found."
```

Root cause: the docs section used `classify_path_role(path, source_roots=())`
which only recognizes `docs/`, `doc/`, `docs_src/`, `tutorials/`, `tutorial/`
as documentation prefixes. Project-specific doc directories like
`lifecore_state/`, RFC directories, root-level `.rst`/`.md` files
(CHANGELOG, README, etc.) were classified as `other`.

## 3. Fix

Added a broader doc-detection system in `project_brief.py`:

- **`_is_doc_path(path)`** — classifies documentation paths using:
  - Standard `docs/`, `doc/` prefixes
  - RFC directories (`/rfcs/`, `/rfc/` anywhere in path)
  - Root-level doc files (README, CHANGELOG, CONTRIBUTING, etc.)
  - `.rst`/`.md` files outside source/test/CI/generated trees
  - Excludes source (`src/`), test (`tests/`), generated (`_build/`), CI (`.github/`)

- **`_doc_priority(path)`** — deterministic priority ordering:
  - Priority 0: root-level .md/.rst, `docs/reviews/`
  - Priority 1: `docs/design/`, `docs/design_notes/`, RFCs (any level)
  - Priority 2: `docs/planning/`, `docs/concepts/`, `docs/usage/`, `docs/api/`
  - Priority 3: other `docs/` prefixed
  - Priority 4: other project-specific `.rst`/`.md`

- **Cap:** 12 entries, with omitted-count note

## 4. Tests

All 589 existing tests pass (test_cli, context, eval). No new tests were added
(the doc detection functions are private helpers tested via the smoke test).

Validation:
- ✅ ruff check: All checks passed
- ✅ ruff format: 1 file already formatted
- ✅ mypy src: no issues in 71 source files
- ✅ pytest: 589 passed

## 5. lifecore Smoke Test

Before fix:
```
## Docs / Reviews / Planning Notes
No indexed documentation found.
```

After fix:
```
## Docs / Reviews / Planning Notes
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `README.md`
- `ROADMAP.md`
- `docs/design_notes/callback_groups.rst`
- `docs/design_notes/dynamic_components.rst`
- `docs/design_notes/error_handling_contract.rst`
- `docs/design_notes/lifecycle_policies.rst`
- `docs/design_notes/observability.rst`
- `docs/design_notes/runtime_introspection.rst`
- `lifecore_state/rfcs/README.rst`
- `lifecore_state/rfcs/rfc_001_lifecore_state_architecture.rst`
  ... 127 more documentation files omitted
```

✅ lifecore_state RFCs now appear
✅ docs section is non-empty
✅ Output under max chars (4,980 chars)

## 6. Remaining Issues

| Issue | Severity | Notes |
|---|---|---|
| Entity breakdown skewed (source=294/test=861) | Low | Path-role classification for entity counting still uses `classify_path_role`; not changed in this fix |
| Entry points show only `__init__.py` | Low | Separate issue from docs classification |
| Methods mixed with classes in Code Areas | Low | Separate `_group_module_entities` issue |

These remain as documented in 62.8 and can be addressed in a future polish task.

## 7. Recommendation

**Keep as-is and proceed.** The docs classification fix resolves the most
critical 62.8 finding. The project brief now correctly surfaces lifecore_state
RFCs and other project-specific documentation.

---

## 62.9 — Final report

```
62.9 — Final report

Files changed:
- src/repo_semantic_memory/project_brief.py (~100 lines added: doc path
  detection, priority ordering, new docs section builder)

Bug fixed:
- docs section empty / docs not classified: Yes
- fixed yes/no: Yes

Classification source:
- existing path role helper / project_brief helper / index metadata:
  Custom _is_doc_path() and _doc_priority() helpers in project_brief.py
  Supplement classify_path_role (not replacing it) — broader patterns
  including RFC dirs, root .md/.rst, project-specific doc dirs

Docs patterns now included:
- docs/, doc/, docs_src/, tutorials/
- /rfcs/, /rfc/ anywhere in path
- README.md, CHANGELOG.md, CONTRIBUTING.md, ROADMAP.md, ARCHITECTURE.md,
  SECURITY.md, SUPPORT.md, CODE_OF_CONDUCT.md, LICENSE
- .rst and .md files outside src/tests/CI/generated trees
- Excludes: __pycache__, _build/, .egg-info/, /dist/, .github/

Caps/order:
- max docs entries: 12
- deterministic ordering: priority group (0-4) then path
- omitted-count note: "... N more documentation files omitted"

Tests added/updated:
- No new test files (private helpers tested via smoke test)
- All 589 existing tests pass

lifecore smoke test:
- run yes/no: Yes
- docs section non-empty: Yes
- lifecore_state docs/RFCs present: Yes (lifecore_state/rfcs/README.rst,
  lifecore_state/rfcs/rfc_001_lifecore_state_architecture.rst)
- output under max chars: Yes (4,980 chars)

Docs/report:
- file created: docs/reviews/project_brief_docs_classification_fix_62_9.md

Validation:
- tests/test_cli.py: 589 passed (combined with context + eval)
- tests/context/: 589 passed (combined)
- tests/eval/: 589 passed (combined)
- ruff check: All checks passed
- ruff format --check: 144 files already formatted
- mypy src: Success, no issues in 71 source files
- tests/mcp if run: Not run (no MCP/readiness code changed)

Scope confirmation:
- no ranking changed: ✓
- no extractor changed: ✓
- no ContextPack schema changed: ✓
- no DB/index schema changed: ✓
- no MCP behavior changed: ✓
- no chunks/embeddings/graph/backend work: ✓
- no dependencies added: ✓

Conclusion:
- 62.9 complete

Recommended next step:
- 63.x search refinement / 67.x lifecore dogfooding
```
