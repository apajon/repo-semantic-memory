# MCP Index Readiness and Freshness Contract — 62.6 Draft

> **Purpose:** Define readiness states for RSM's MCP server, when each state occurs, MCP behavior per state, and implementation requirements.  
> **Status:** Design phase (draft).  
> **Date:** 2026-06-10.

## 1. Overview

The RSM MCP server runs in two modes:
- **Repo mode** (`--repo`/`--db`): Fixed repository for the session.
- **Store mode** (`--store`): Multiple repositories; agent selects one per session.

Each mode has a distinct lifecycle and readiness model.

### 1.1 Readiness Definition

**Readiness** is the deterministic classification of whether an index database is usable for a given repository, considering:
- Database file existence and validity
- Schema/context-pack version alignment with current code
- Git-based freshness (indexed commit vs. current working tree)

Readiness affects:
- Whether MCP `initialize` succeeds or warns
- Whether tool invocations proceed or return recoverable uncertainties
- What instructions agents receive

## 2. Eight Readiness States

### 2.1 `ready` (Index is fresh and usable)

**When:**
- DB file exists and is readable
- Schema version matches current code
- Git metadata indicates: indexed_git_head == current git HEAD
- (or not a git repo, but metadata is otherwise complete)

**MCP behavior:**
- `initialize`: Returns success with index_status="fresh" in session.index_status
- Tools: Proceed normally
- Warnings: None
- Agent instructions: Standard task-first workflow

**Implementation:** Returned by `detect_index_status()` as IndexStatus.FRESH with reason `ok`

---

### 2.2 `missing_db` (Database file does not exist)

**When (repo mode):**
- `--db` path provided but file doesn't exist
- Or `--db` omitted and Index Store registry has no entry

**When (store mode):**
- Repository is not registered in Index Store
- (Can only reach this state via explicit `rsm_store_select_index` on unregistered repo)

**MCP behavior:**
- `initialize` (repo mode): Fails with error "db path does not exist" (current behavior)
- `initialize` (store mode): Succeeds but no active_index is set
- Tools (repo mode): All fail with same error
- Tools (store mode): Return no_active_index uncertainty if user didn't select first
- Warnings: None (design-time state)
- Agent instructions: Suggest building index or registering repo

**Implementation:** Detected by `detect_index_status()` — checks db_path existence
- Returns IndexStatus.MISSING with reason "explicit_db_missing" or "registered_db_missing"

---

### 2.3 `invalid_db` (Database is not readable or corrupted)

**When:**
- DB file exists but:
  - Is not a valid SQLite file
  - Can't be opened
  - Tables/schema don't exist (uninitialized)
  - Metadata rows are corrupt

**MCP behavior:**
- `initialize`: Fails with error "index database is invalid or corrupted"
- Tools: Fail with same error
- Warnings: None (hard error)
- Agent instructions: Suggest rebuilding index

**Implementation:** Raised by `compute_readiness()` on exception, returns:
- IndexStatus.UNKNOWN with reason "detection_error" (currently)
- **Proposal:** Distinguish this from other detection errors; add new reason "db_corrupt" or upgrade to "invalid_db" status

---

### 2.4 `schema_mismatch` (Database schema version doesn't match current code)

**When:**
- DB opens successfully but metadata shows schema_version or context_pack_version != current code

**MCP behavior:**
- `initialize`: Succeeds but warns: "index schema version doesn't match; results may be incomplete"
- Tools: Proceed with warning in response
- Warnings: In agent_instructions advising rebuild
- Agent instructions: Mention rebuild option

**Implementation:** Detected by `detect_index_status()` — checks schema/context-pack versions
- Returns IndexStatus.SCHEMA_MISMATCH with reason "schema_version_mismatch"

---

### 2.5 `empty_store` (Store mode only: no repositories registered)

**When (store mode only):**
- `rsm mcp serve --store` launched
- Index Store exists but has zero registered repositories

**MCP behavior:**
- `initialize`: Succeeds; active_index is None; detailed instructions
- Tools: Store tools work (list_indexes returns empty list)
- Tools: Repository tools return no_active_index uncertainty
- Warnings: None in session_info, but instructions emphasize "no repositories registered yet"
- Agent instructions: Guide to `rsm store register` or manual registration

**Implementation:** Not a separate status, but _initialize_result for store mode checks:
- If store_home exists and is readable, proceed (even if empty)
- No active_index → include detailed instructions about store registration

---

### 2.6 `no_active_index` (Store mode only: no index selected for this session)

**When (store mode only):**
- Agent calls a repository-specific tool (e.g., rsm_search)
- StoreSessionState.active_index is None (no rsm_store_select_index yet)

**MCP behavior:**
- `initialize`: Succeeds; active_index is None
- Tools: Repository tools return structured no_active_index uncertainty
  ```json
  {
    "active_repo": null,
    "uncertainties": [
      {
        "code": "no_active_index",
        "message": "Call rsm_store_list_indexes then rsm_store_select_index before repository tools.",
        "recoverable": true
      }
    ],
    "agent_instructions": [...]
  }
  ```
- Warnings: None; it's a recoverable flow
- Agent instructions: List-then-select workflow

**Implementation:** Handled by `_no_active_index_response()` in runtime.py
- Already implemented; no schema change needed

---

### 2.7 `stale_index` (Git HEAD changed since indexing)

**When:**
- DB exists and is valid
- Schema version matches
- Git metadata shows: indexed_git_head != current git HEAD (working tree at different commit)

**MCP behavior:**
- `initialize`: Succeeds; includes warning in session.index_status_reason
- Tools: Proceed but include advisory in response
- Warnings: index_status="stale", index_status_reason="git_head_changed"
- Agent instructions: "Index may be outdated; consider rebuilding"

**Implementation:** Detected by `detect_index_status()` — compares git commits
- Returns IndexStatus.STALE with reason "git_head_changed" (already implemented)

---

### 2.8 `unknown_freshness` (Can't determine if index is fresh)

**When:**
- DB exists, is valid, schema matches
- But can't detect git state because:
  - Repository is not a git repo
  - Git metadata is missing or incomplete in DB
  - Git operations fail (permission error, corrupted repo)

**MCP behavior:**
- `initialize`: Succeeds with advisory
- Tools: Proceed
- Warnings: index_status="unknown", index_status_reason="git_unavailable" or "not_git_repo"
- Agent instructions: "Freshness unknown; verify index is current before use"

**Implementation:** Detected by `detect_index_status()` — git errors fall through
- Returns IndexStatus.UNKNOWN with reason "git_unavailable" or other

---

## 3. State Transition Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ MCP server started (repo or store mode)                      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                    ┌──────────┴─────────┐
                    │                    │
            [repo mode]          [store mode]
                    │                    │
         ┌──────────▼────────┐  ┌────────▼────────┐
         │ validate_session()│  │ StoreSessionState
         │ --db required     │  │ ready()
         │                   │  │                 │
         └──────┬────────────┘  │  ┌──────────────▼─────┐
                │               │  │ empty_store (no    │
         ┌──────▼─────────┐    │  │ repos registered)  │
         │ DB exists?     │    │  │                     │
         ├─ YES ──────────┼────┘  └────────┬────────────┘
         │ NO │           │               │
         │    └──────┐    └──────────┐     │
         │  missing_db              │     │
         │           ▲              │     │
         └───────────┼──────────────┼─────┼────────────────────┐
                     │              │     │                    │
              [compute_readiness]   │     │            [agent calls tool]
                     │              │     │                    │
          ┌──────────▼──────────┐   │     │              ┌─────▼────┐
          │ open and read DB    │   │     │              │ has      │
          │                     │   │     │              │ active_  │
          ├─ ERROR ────────┐    │   │     │              │ index?   │
          │ invalid_db     ◄────┘   │     │              │          │
          │                │        │     │              ├─ NO ─────┼──▶ no_active_index
          │ ─ OK ──────────┼────┐   │     │              │ YES      │
          │                │    │   │     │              └──────────┘
          └────────────────┘    │   │     │
                                │   │     │
                   ┌────────────▼───▼─────▼─────────┐
                   │ check schema/context versions  │
                   │                                │
                   ├─ MISMATCH ──────────────────┐  │
                   │ schema_mismatch              │  │
                   │                              ▲  │
                   │ ─ OK ──────────┐            │  │
                   │                │            │  │
                   └────────────────┼────────────┘  │
                                    │               │
                       ┌────────────▼───────────┐   │
                       │ check git metadata     │   │
                       │                        │   │
                       ├─ NO (not git) ───┐    │   │
                       │ unknown_freshness│    │   │
                       │                   │    │   │
                       ├─ ERROR ──────┐    │    │   │
                       │ unknown_     │    │    │   │
                       │ freshness    │    │    │   │
                       │              ◄────┘    │   │
                       │              │         │   │
                       ├─ HEAD ≠ INDEXED ──┐   │   │
                       │ stale_index        ◄───┘   │
                       │                   │        │
                       ├─ HEAD == INDEXED ─┐       │
                       │ ready              ◄────────
                       │                     
                       └────────────────────┘
```

---

## 4. Implementation Checklist

### 4.1 Phase 1: Compute readiness in session creation

- [ ] **Repo mode:** Update `validate_session()` to call `compute_readiness()` and return it in SessionConfig
  - Decision: Always compute (no opt-out)
  - Timing: Synchronous, cheap (no network)

- [ ] **Store mode:** Update `_tool_store_select_index()` to call `compute_readiness()` when creating ActiveIndex
  - Only after confirming db_path exists (no redundant checks)

### 4.2 Phase 2: Surface readiness in MCP responses

- [ ] Update `_initialize_result()` to include explicit readiness state in session_info:
  ```python
  "index_status": readiness.index_status,
  "index_status_reason": readiness.index_status_reason,
  ```
  (Already done for repo mode; ensure store mode also surfaces indexed_at, indexed_git_head when available)

- [ ] For stale/unknown indices: include advisory in agent_instructions within initialize

### 4.3 Phase 3: Add tests

- [ ] Test missing_db: validate_session() with nonexistent --db path
- [ ] Test invalid_db: SQLite file that can't be read or initialized
- [ ] Test empty_store: serve_stdio with no registered repositories
- [ ] Test no_active_index: call repository tool on store session with no active index
- [ ] Test stale_index: repo with git HEAD changed since indexing
- [ ] Test schema_mismatch: DB with old schema version
- [ ] Test unknown_freshness: non-git repo or git errors

### 4.4 Phase 4: Documentation and report

- [ ] Update `docs/usage/mcp.md` to describe readiness states and agent behavior per state
- [ ] Create `docs/reviews/mcp_readiness_freshness_contract_62_6.md` with:
  - Readiness state definitions (from this draft)
  - Current implementation status
  - Gaps and remediation
  - Test coverage
  - Recommendation: Can 62.7 proceed? (yes/with warnings/not yet)

---

## 5. Questions and Design Decisions

### Q1: Should readiness be optional or always computed?

**Decision:** Always computed (no opt-out).
- Cost: One stat + one potential DB open per session creation (negligible).
- Benefit: Predictable, no silent staleness surprises.
- Agents get consistent readiness info in every initialize response.

### Q2: Should stale indices block tool invocation or just warn?

**Decision:** Warn and proceed (tools work).
- Rationale: Agent can decide whether to rebuild; stale != wrong.
- Context: Index may be slightly outdated but still useful for current task.
- Fallback: rsm_store_select_index can regenerate if needed.

### Q3: Should invalid_db be a separate status or collapse into unknown?

**Decision:** Propose upgrading to separate status "invalid_db" if feasible.
- Current: Raises exception → returns unknown with reason "detection_error"
- Proposed: Catch exception and return IndexStatus.INVALID (new enum value)
- Benefit: Agents can distinguish "rebuild index" from "something weird happened"

### Q4: Should no_active_index be a persistent state or only transient?

**Decision:** Transient (per-tool-call, not stored in session).
- Current implementation: Checked per invoke_tool() call.
- Rationale: Session persists but selection is ephemeral; agent re-selects if needed.
- Benefit: Simple, no session re-initialization overhead.

---

## 6. Current Implementation Status

### What's Already Working ✅

- `ReadinessInfo` dataclass (frozen, JSON-safe)
- `compute_readiness()` function
- `detect_index_status()` with full precedence logic
- `IndexStatus` enum with FRESH, MISSING, STALE, MAYBE_STALE, SCHEMA_MISMATCH, UNKNOWN
- `IndexStatusReason` constants for diagnostic codes
- `_no_active_index_response()` for store mode tool errors
- `_initialize_result()` includes index_status in session_info (repo mode)

### What's Partially Wired 🟡

- Repo mode: readiness never computed (validate_session never calls compute_readiness)
- Store mode: readiness never computed (select_index creates ActiveIndex without it)
- Store mode initialize: active_index.readiness not populated in response

### What's Missing ❌

- No tests for missing_db, invalid_db, stale, schema_mismatch states in MCP context
- No test for empty_store behavior
- No test for store mode readiness reporting
- Documentation gap: readiness contract not formally specified in docs/usage/mcp.md

---

## 7. Next Steps (62.6 Implementation)

1. Update `validate_session()` to compute readiness synchronously
2. Update `_tool_store_select_index()` to compute readiness when selecting index
3. Add 7 tests covering missing_db, invalid_db, empty_store, stale, etc.
4. Update `_initialize_result()` if needed to surface readiness in store mode
5. Write final report with answer: Can 62.7 proceed?

---

