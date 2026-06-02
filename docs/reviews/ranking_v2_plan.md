# RSM Ranking v2 — Context Selection Design

> Prompt 58.0 — analysis and planning only.
> Target design model: Claude Opus 4.7 / 4.8. Implementation model later: Claude Sonnet 4.6.
> **No code changes are made in this prompt.** This document specifies the design and the
> implementation prompt sequence (58.1–58.6) that follow.
>
> **58.1 — Query intent parser and generic-token downweighting: ✅ implemented.**
> Added `src/repo_semantic_memory/context/query_intent.py` (`QueryIntent` dataclass,
> `parse_query_intent()`). Generic stop tokens (`find`, `how`, `files`, `implementation`, `test`,
> `tests`, `behavior`, `code`, `work`, `works`, function words) are stripped from BM25 lexical
> scoring; domain tokens (`loader`, `resolver`, `handler`, `dispatch`, `url`, `plugin`, `timeout`,
> `transport`, `middleware`) are preserved via allowlist guard. `pack_builder.build_context_pack`
> now passes `lexical_tokens` (filtered) to `_rank_entities`; intent detection (`_task_hints`,
> `_is_code_task`) still uses the full raw token set. 42 unit tests added in
> `tests/context/test_query_intent.py`. Non-goals still deferred: test-file
> branch (58.3), support-file expansion (58.4), selection reasons (58.5), regression eval (58.6).
>
> **58.2 — Task-aware path priors: ✅ implemented.**
> Added `is_runtime_test_named_path()`, `is_public_api_file()`, and `path_prior_multiplier()` to
> `src/repo_semantic_memory/context/path_roles.py`. Priors are additive deltas applied in
> `_score_entity` when a `QueryIntent` is available. Key behaviours: `tests` intent boosts real
> test roots (`tests/`, `test/`) and penalises runtime-named paths (`lib/ansible/plugins/test/`);
> `implementation` intent penalises docs/examples; `public_api` intent modestly boosts
> `__init__.py`; `config_build_release` intent boosts pyproject/setup/config files. Fixed the
> long-standing bug where `source_path.startswith("tests/")` was used instead of `path_role ==
> TEST_ROLE`, so Ansible `test/units/...` paths are now boosted correctly. Tests extended in
> `tests/context/test_path_roles.py`. Non-goals still deferred: test-file branch (58.3),
> support-file expansion (58.4), selection reasons (58.5), regression eval (58.6).

---

## 1. Executive summary

### Why current ranking fails

RSM's context-pack ranking is a **single-pool, field-weighted BM25 lexical scorer** with a small
set of additive structural bonuses. Every word in the natural-language task is tokenized and scored
literally against entity fields — including `source_path`, which is weighted `2.0`
(`bm25.py` `DEFAULT_FIELD_WEIGHTS`). This produces three systemic problems:

1. **Generic task verbs leak into lexical scoring.** Words like `find`, `how`, `files`,
   `implementation`, `behavior`, `code`, `where` are treated as meaningful query terms. They match
   real path/name tokens (`find.py`, `django/core/files/...`, runtime modules literally named
   `test`), boosting noise.
2. **One central file is found, but its support cluster is not pulled in.** A strong central hit
   (`django/urls/resolvers.py`, `lib/ansible/plugins/loader.py`) ranks first, but the adjacent
   dispatch/handler/loader files that complete the flow are only reachable through generic graph
   expansion, which is undirected and capped, and so they are crowded out by lexical noise.
3. **Tests are not retrieved as a first-class, intent-driven section.** The "tests" task hint only
   boosts paths that literally start with `tests/` (`pack_builder.py` `_score_entity`), so Ansible's
   `test/units/...` root (singular `test/`) is missed, while runtime files under
   `lib/ansible/plugins/test/` are *lexically* matched by the literal token `test`.

### What Ranking v2 should improve

- A deterministic **query intent parser** that classifies what the task is actually asking for and
  **downweights generic phrases** before they reach lexical scoring.
- **Task-aware path priors** so intent (tests / public API / implementation / config) maps to the
  right role buckets instead of fixed global penalties.
- **Role-specific candidate pools** with a **central-file boost**, **deterministic support-file
  expansion**, and an **independent test-file retrieval branch** returned as its own section.
- **Machine-readable selection reasons** on every selected file.

### What it must not try to solve yet

Ranking v2 is a **selection-quality** change on top of the existing static index and context-pack
format. It explicitly does **not** introduce chunks, embeddings, BM25 replacement, Semble
integration, indexing changes, scoped-indexing changes, context-pack format changes, or any
repository-specific hardcoded answers. (See §12.)

---

## 2. Current ranking pipeline

All paths below are in `src/repo_semantic_memory/context/`.

### Task text tokenization and scoring (today)

- `build_context_pack` (`pack_builder.py`) calls `_tokenize(task)` →
  `bm25.tokenize_text`. Tokenization is identifier/path aware (delimiter + camelCase splitting)
  and **has no stopword/generic-phrase filtering**. For example
  `"Find how URL resolver implementation files work"` →
  `('find', 'how', 'url', 'resolver', 'implementation', 'files', 'work')`.
- `_is_code_task` and `_task_hints` derive coarse flags from the same raw tokens. `_task_hints`
  produces a subset of `{implementation, tests, public_api, cleanup_ownership, documentation}`
  using fixed token sets (`_CODE_TASK_TOKENS`, `_TEST_TASK_TOKENS`, `_PUBLIC_API_TASK_TOKENS`, …).
- `_rank_entities` builds a `FieldedBM25Index` over each entity's
  `qualified_name / name / source_path / kind / semantic_components / relation_labels /
  metadata / id` fields and scores every entity with `_score_entity`.
- `_score_entity` = BM25 lexical score (+ exact-field boost `_EXACT_FIELD_MATCH_BOOST=6.0`,
  + `_SOURCE_CITATION_BONUS=2`) plus additive `path_role` / `task_intent` / `component` / `penalty`
  components driven by the coarse task hints. Entities with `breakdown.total < 1` are dropped.

### How files/entities are selected

- Ranked entities with at least one reason are added to `selected_entity_ids` (a single flat pool,
  ordered by `-total` then entity id). There is **no separation** between implementation, tests,
  public API, etc. — everything competes in one list, then the budget truncator (`_truncate_to_budget`)
  decides what survives.

### How relations are used

- Graph-seed-eligible entities (`_is_graph_seed_eligible`) feed `select_graph_neighbors`
  (`graph_selection.py`): weighted BFS over typed relations (`DEFAULT_RELATION_WEIGHTS`,
  `max_depth=2`, `max_entities=30`, depth decay `0.5`), with import-aware weighting
  (`import_scoring.py`). This is the only support-file expansion mechanism, and it is **undirected
  by intent** — it expands all neighbor kinds generically and is capped globally.
- Relation ordering for the budget cap is intent-aware via `_relation_task_priority`, but this only
  reorders relations already incident to selected entities; it does not pull in missing files.

### How tests are selected (or not)

- A static `tests` relation type exists (`extractors/test_relationships.py`) and graph expansion
  weights it at `0.9`. But there is **no test-retrieval branch**: tests only appear if a test entity
  already scored into the flat pool or happened to be a graph neighbor of a seed. The "tests" hint
  boost in `_score_entity` is gated on `source_path.startswith("tests/")` (plural only).

### Where lexical noise enters

- `source_path` is BM25-weighted `2.0`, so generic task words that coincide with path/file tokens
  (`find`, `files`, `test`, `storage`) directly raise a file's lexical score.
- There is no notion of "this token is a generic task verb, not a domain term", so noise files rank
  alongside genuine central files and consume budget.

---

## 3. Failure taxonomy

| Class | Description | Observed examples |
|---|---|---|
| **F1 — generic verb/token noise** | Task verbs/nouns (`find`, `how`, `implementation`, `files`, `behavior`, `code`, `where`) are scored as domain terms. | `"find how"` boosts `lib/ansible/modules/find.py`; `"implementation files"` boosts `django/core/files/storage/*`. |
| **F2 — path-name false positives** | A generic token literally matches a file/dir name with unrelated meaning. | token `test` matches runtime `lib/ansible/plugins/test/*.py`; token `url` matches `staticfiles/finders.py` lexically; `storage`/`files` noise. |
| **F3 — missing support-file expansion** | Central file is found, but adjacent dispatch/handler/loader/public-API files are not pulled in. | Django: missing `core/handlers/base.py`, `urls/conf.py`, `urls/base.py`, `urls/__init__.py`. Ansible: missing `executor/module_common.py`, `utils/collection_loader/_collection_finder.py`, `module_utils/`. |
| **F4 — missing tests** | No intent-driven test retrieval; `test/` (singular) roots and relation-linked tests are missed. | Django: missing `tests/urlpatterns/test_resolvers.py`, `tests/urlpatterns_reverse/tests.py`. Ansible: missing `test/units/plugins/test_plugins.py`. |
| **F5 — no task intent model** | Coarse boolean hints only; no parsed intent, no generic-phrase downweighting, ambiguous tokens (`test`) handled literally. | `"tests"` hint misses Ansible `test/units/`; runtime `plugins/test/` wrongly boosted. |
| **F6 — lack of selection reasons** | Reasons exist as human strings + `RankingReason` categories, but there is no stable, per-file machine-readable reason list a caller can branch on (central vs support vs test vs intent-match). | `why_selected` is free-text; no `"support file for selected central file"`-style typed reasons. |

---

## 4. Proposed Ranking v2 architecture

Ranking v2 keeps the existing deterministic BM25 core and graph expansion but wraps them in an
**intent-directed, multi-pool selection pipeline**:

```
task text
  │
  ├─▶ [A] Query intent parser ............ parsed intent + domain tokens + downweighted generics
  │
  ├─▶ [B] Generic phrase/token downweighting (feeds lexical scoring)
  │
  ▼
[C] Candidate scoring (BM25 + task-aware path priors)
  │
  ├─▶ [D] Role-specific candidate pools:
  │        • implementation   • tests   • public API
  │        • docs             • config  • error handling
  │
  ├─▶ [E] Central-file boost (strongest in-intent hit per pool)
  │
  ├─▶ [F] Support-file expansion (intent-directed, capped)
  │
  ├─▶ [G] Test-file retrieval branch (independent, capped, separate section)
  │
  ▼
[H] Selection reasons (machine-readable, per file)
  │
  ▼
budget truncation → context pack
```

Design components:

- **Query intent parser (A):** deterministic classifier over task tokens (see §5).
- **Generic phrase/token downweighting (B):** before BM25 scoring, generic phrases are removed or
  weighted down so they cannot boost `source_path` matches. Domain tokens are preserved.
- **Task-aware path priors (C):** intent maps to role-bucket multipliers, replacing fixed global
  penalties (see §6).
- **Role-specific candidate pools (D):** candidates are bucketed by `PathRole` + entity kind so each
  intent draws from the right pool rather than a single flat list.
- **Central-file boost (E):** the top in-pool, intent-aligned file gets a deterministic boost and is
  marked as the central seed for expansion.
- **Support-file expansion (F):** deterministic, intent-directed expansion from the central file/entity
  (see §7), capped to avoid noise.
- **Test-file branch (G):** independent retrieval, returned as a separate section (see §8).
- **Selection reasons (H):** typed reasons per file (see §9).

---

## 5. Query intent parser

A deterministic function mapping task tokens to a set of intents (multiple may fire). It extends the
existing `_task_hints` rather than replacing the index. No NLP model; pure token logic.

### Intents to extract

| Intent | Fires when the task asks for… | Example trigger tokens (illustrative, not exhaustive) |
|---|---|---|
| `tests` | tests / coverage / regression | `test`, `tests`, `coverage`, `regression`, `pytest` |
| `public_api` | the public surface / exports | `public`, `api`, `export(s)`, `__init__`, `interface` |
| `implementation` | where something is implemented | `implementation`, `implemented`, `logic`, `core`, `source` |
| `config_build_release` | configuration / build / release | `config`, `pyproject`, `build`, `release`, `packaging`, `ci` |
| `error_handling` | error / exception flow | `error`, `errors`, `exception(s)`, `raise`, `failure`, `handling` |
| `architecture_flow` | cross-file flow / dispatch | `flow`, `dispatch`, `pipeline`, `routing`, `lifecycle`, `architecture` |

The parser returns `(intents: set, domain_tokens: tuple, downweighted_tokens: tuple)`.

### Generic phrases/tokens to downweight

Remove or heavily downweight before lexical scoring (deterministic stop-set):

```
find        find how      implementation files   relevant files
including   behavior      code                   where
how         files         work                   the / a / of (function words)
```

These never contribute positive `source_path` lexical mass. (They may still trigger an *intent* via
the parser — e.g. `find` signals a localization task — but they must not boost a file literally named
`find.py`.)

### Tokens that must remain meaningful (do not over-filter)

The downweighting must be conservative. The following are **domain tokens** and must survive:

- `loader` — meaningful in Ansible plugin loading.
- `resolve` / `resolver` — meaningful in Django URL routing.
- `handler`, `dispatch`, `router`, `route`, `url`, `pattern` — meaningful dispatch terms.
- `test` — **ambiguous**: it is an intent signal (tests pool) but must **not** lexically boost runtime
  modules/dirs named `test`/`tests` (e.g. `lib/ansible/plugins/test/`). The parser routes `test` to the
  test-file branch (§8) and to test *roles*, not to lexical path matching against runtime code.

Design rule: **generic-token downweighting is an allowlist-guarded stop-set, never a blanket removal
of any token that appears in a stop phrase.** Domain tokens that happen to co-occur with generics are
preserved.

---

## 6. Task-aware path priors

Replace fixed global penalties with **intent-conditioned role multipliers**. Priors are applied as
score deltas on top of BM25, keyed on `classify_path_role` (`path_roles.py`) plus a small set of
filename signals. No hardcoded repository paths.

Rules (deterministic, intent-gated):

- **tests intent →** boost `test` role: paths under `tests/`, `test/` (both singular and plural — fixes
  the Ansible `test/units/` miss), and `test_*.py` / `*_test.py` filenames.
  - **Disambiguation:** a path is only treated as a *unit-test root* when its **top-level** segment is a
    test root (`tests/`, `test/`). Runtime paths whose `test`/`tests` segment is **nested under a source
    package** (e.g. `lib/ansible/plugins/test/`) are **not** test roots and receive no test boost. This
    directly fixes F2/F4.
- **public_api intent →** boost `__init__.py`, top-level package modules, confirmed `PublicAPI`
  components and `exports` sources/targets (existing signals in `_score_entity`), and related docs.
- **implementation intent →** prioritize `source` role over `doc` / `example` / `test` roles; prefer the
  source package containing the central entity.
- **config_build_release intent →** boost `pyproject.toml`, `setup.cfg`/`setup.py`, `config/` and CI
  files (config/CI roles).
- **error_handling / architecture_flow intents →** no path penalty; rely on support-file expansion and
  relation signals (§7) to reach handler/dispatch files.

Guardrail: **never apply a fixed global penalty that overrides an explicit matching intent.** If the
task asks for tests, the test role must not be net-penalized; if it asks for docs, docs must not be
suppressed by the public-API doc downrank. Priors are *conditional*, not global.

---

## 7. Support-file expansion

Deterministic expansion from the central file/entity into its support cluster, layered on the existing
graph machinery (`select_graph_neighbors`) but **intent-directed and bounded**.

Expansion sources (in priority order):

1. **From central file → its imports/exports.** Follow `imports` / `exports` relations
   (import-class-weighted via `import_scoring.py`) to first-party local targets only; skip stdlib and
   common third-party.
2. **From central entity → its containing module/class.** Follow `contains` upward so a central function
   pulls in its module and the module's package `__init__.py`.
3. **From implementation file → its public-API wrapper.** If an implementation file is selected and a
   sibling `__init__.py`/exports surface re-exports its symbols, include that wrapper as support.
4. **From resolver/router/handler terms → adjacent dispatch files.** When the parsed intent is
   `architecture_flow` (or the central file matches dispatch domain tokens), prefer neighbors reachable
   via `calls`/`uses`/`imports` whose path/name carries dispatch role signals (handler/dispatch/base).
   This is the deterministic path to Django `core/handlers/base.py` and `urls/conf.py`/`base.py` without
   hardcoding those paths.

Caps and guardrails:

- Bound support expansion to a small, deterministic number of files per central file (e.g. a fixed
  `max_support_files`), tie-broken by relation weight then entity id.
- Only expand from **first-party local** targets; never expand into generated/build artifacts
  (`is_generated_artifact_path`) or markdown/tooling noise.
- Expansion must produce a typed reason per added file (`"support file for selected central file"`,
  `"related to <flow> via <relation>"`).

---

## 8. Test-file retrieval branch

When the `tests` intent fires, retrieve tests **independently** of the implementation pool and return
them as a **separate section** in the pack (not interleaved with implementation files).

Retrieval order (deterministic, stop at cap):

1. **Test relationship relations first.** Use existing `tests` relations
   (`extractors/test_relationships.py`) from selected central/support files to their test entities —
   highest confidence.
2. **Then path/name matching.** Files under top-level `tests/` or `test/` roots and `test_*.py` /
   `*_test.py` filenames whose tokens overlap the central file/module name. Excludes nested runtime
   `…/test/` packages (§6 disambiguation).
3. **Then package proximity.** Test files in the test root that mirror the central file's package path
   (e.g. `tests/<pkg>/test_<module>.py`).

Output and caps:

- Tests are returned in a **dedicated `tests` section**, not mixed into implementation files.
- Cap the number of test files (deterministic `max_test_files`), ordered by retrieval tier then entity
  id.
- Each test file carries a typed reason indicating which tier selected it
  (`"linked via tests relation"`, `"test path mirrors central module"`).

---

## 9. Selection reasons

Every selected file must carry **machine-readable** reasons in addition to the existing human strings.
Reasons are a stable, enumerable vocabulary so callers can branch on them.

Example payload shape:

```json
{
  "path": "django/core/handlers/base.py",
  "reasons": [
    "matches dispatch intent",
    "related to URL resolver flow",
    "support file for selected central file"
  ]
}
```

Design requirements:

- Reasons come from a **closed vocabulary** mapped to the existing `RankingReason.category` set
  (`lexical`, `path_role`, `task_intent`, `component`, `graph`, `penalty`) plus new selection-role tags
  (`central_file`, `support_file`, `test_file`, `intent_match`). The vocabulary is enumerable and
  deterministic.
- Reasons are attached at selection time (central boost, support expansion, test branch each emit their
  own reason), reusing the existing `append_reason` / `dedupe_stable_reasons` plumbing.
- Reasons must remain **deterministic and order-stable** (sorted/deduped) so pack output is
  reproducible.

---

## 10. Prompt sequence

Implementation is split into focused prompts. Each is independently testable and reversible. Default
implementation model: Claude Sonnet 4.6.

### 58.1 — Query intent parser and generic-token downweighting ✅
- **Goal:** Add a deterministic intent parser and generic-phrase stop-set; downweight generics before
  BM25; preserve domain tokens.
- **Files touched:** new `context/query_intent.py` (`QueryIntent` dataclass, `parse_query_intent()`);
  `context/pack_builder.py` (`build_context_pack` now calls `parse_query_intent` and passes
  `lexical_tokens` to `_rank_entities`; intent detection still uses full raw tokens).
- **Tests:** 42 new tests in `tests/context/test_query_intent.py` covering intent detection, generic
  downweighting, domain token preservation, backward compat, and focused BM25 score comparisons.
- **Risks mitigated:** allowlist guard prevents stripping domain tokens (`loader`, `resolve`, `test` →
  intent-only path, not lexical scoring against runtime `plugins/test/`).
- **Validation:** 885 tests pass; ruff + mypy clean.

### 58.2 — Task-aware path priors ✅
- **Goal:** Replace fixed global penalties with intent-conditioned role multipliers; fix `test/` singular
  root handling and nested-runtime-`test` disambiguation.
- **Files touched:** `context/path_roles.py` (`is_runtime_test_named_path`, `is_public_api_file`,
  `path_prior_multiplier`, 5 scoring constants), `context/pack_builder.py` (`_score_entity` —
  fixed `startswith("tests/")` → `path_role == TEST_ROLE`, wired `path_prior_multiplier`).
- **Tests:** `tests/context/test_path_roles.py` extended with `TestIsRuntimeTestNamedPath`,
  `TestIsPublicApiFile`, `TestPathPriorMultiplier`, `TestPathPriorIntegration`.
- **Risks:** double-counting boosts; intent collisions (implementation + tests). Keep priors additive
  and conditional.
- **Validation:** unit tests + eval; confirm docs/test roles not net-penalized under matching intent.

### 58.3 — Test-file retrieval branch
- **Goal:** Independent test retrieval (relations → path/name → proximity), returned as a separate
  section, capped.
- **Files likely touched:** `context/pack_builder.py` (new selection branch), reuse
  `extractors/test_relationships.py` outputs; possibly `context/context_pack.py` for a tests grouping in
  reasons (no format change to existing fields).
- **Tests:** new tests asserting Ansible `test/units/...` retrieval and exclusion of `plugins/test/`.
- **Risks:** mixing tests into implementation pool; cap tuning. Keep section separation explicit.
- **Validation:** unit tests + eval test-localization tasks.

### 58.4 — Support-file expansion
- **Goal:** Intent-directed, bounded expansion from central file to imports/exports, containing module,
  public-API wrapper, and dispatch-adjacent files.
- **Files likely touched:** `context/pack_builder.py`, `context/graph_selection.py` (directed expansion
  config), reuse `context/import_scoring.py`.
- **Tests:** expansion tests on fixture repos; assert dispatch/handler/loader neighbors pulled in and
  generated/tooling excluded.
- **Risks:** expansion blowups → noise. Enforce `max_support_files` cap and first-party-only rule.
- **Validation:** unit tests + eval implementation-localization tasks.

### 58.5 — Selection reasons in context pack
- **Goal:** Emit closed-vocabulary, machine-readable reasons per selected file (central/support/test/
  intent), reusing existing reason plumbing.
- **Files likely touched:** `context/ranking.py`, `context/pack_builder.py`,
  `context/context_pack.py`, `context/render_markdown.py`.
- **Tests:** reason-vocabulary tests; determinism/order-stability tests.
- **Risks:** reason inflation increasing char cost/budget pressure. Keep reasons deduped and capped per
  item (existing `_cap_reasons_per_item`).
- **Validation:** unit tests + golden pack snapshots.

### 58.6 — Regression eval on Django / Ansible / Typer
- **Goal:** Validate end-to-end improvements against §11 targets without hardcoding answers.
- **Files likely touched:** `benchmarks/tasks.yaml`, `benchmarks/public_repos.yaml`,
  `src/repo_semantic_memory/eval/*` (only if new metrics needed).
- **Tests:** eval runner over pinned public repos; assert inclusion/noise-reduction expectations as
  thresholds, not exact gold sets.
- **Risks:** overfitting to specific commits. Pin commits; express targets as "must include / should
  reduce", not exact ranking.
- **Validation:** `rsm eval retrieval` / `rsm eval compare` reports.

---

## 11. Regression targets

Expressed as inclusion / noise-reduction expectations, **not** hardcoded benchmark answers or exact
rankings.

**Django URL routing** should:
- include `django/urls/resolvers.py` (central),
- include `django/core/handlers/base.py`,
- include at least one of `django/urls/conf.py` or `django/urls/base.py`,
- include at least one `tests/urlpatterns*` file,
- reduce `staticfiles/` and `core/files/storage/*` noise.

**Ansible plugin loading** should:
- include `lib/ansible/plugins/loader.py` (central),
- include at least one of `lib/ansible/executor/module_common.py` or the collection loader
  (`utils/collection_loader/_collection_finder.py`),
- include `test/units/plugins/test_plugins.py`,
- reduce `lib/ansible/modules/find.py` and `lib/ansible/plugins/test/*.py` noise.

**HTTPX public API** should:
- include `httpx/__init__.py`,
- include `httpx/_client.py`.

These are validated as thresholds in 58.6 against pinned commits.

---

## 12. Non-goals

Explicitly deferred — **not** part of Ranking v2:

- chunking
- BM25 replacement (Ranking v2 keeps the existing field-weighted BM25 core)
- embeddings / vector retrieval
- Semble backend integration
- LLM reranking
- repository-specific hardcoded answers or paths
- indexing / scoped-indexing changes
- context-pack output **format** changes (Ranking v2 adds reasons within existing fields; it does not
  redefine the pack schema)

---

## Final response

**Verdict:** RSM's selection failures are a *ranking and selection-architecture* problem, not an
indexing or recall problem. The static index already contains the right entities and relations
(`tests`, `imports`/`exports`, `contains`, dispatch-capable graph); the central file is consistently
found. The defect is that one flat lexical pool lets generic task verbs boost noise, has no intent
model, never expands the support cluster deterministically, and never retrieves tests as a first-class
section. Ranking v2 fixes this by wrapping the existing BM25 + graph core in an intent-directed,
multi-pool pipeline with machine-readable reasons — no new heavy machinery.

**Implementation sequence:** 58.1 query intent parser + generic downweighting → 58.2 task-aware path
priors → 58.3 test-file branch → 58.4 support-file expansion → 58.5 selection reasons → 58.6 regression
eval (Django / Ansible / Typer / HTTPX).

**Key files inspected:**
- `src/repo_semantic_memory/context/pack_builder.py` (`build_context_pack`, `_rank_entities`,
  `_score_entity`, `_task_hints`, `_relation_task_priority`)
- `src/repo_semantic_memory/context/bm25.py` (field weights, tokenizer)
- `src/repo_semantic_memory/context/path_roles.py` (role classification, source-root inference)
- `src/repo_semantic_memory/context/graph_selection.py` (weighted BFS expansion)
- `src/repo_semantic_memory/context/import_scoring.py` (import classification/weighting)
- `src/repo_semantic_memory/context/ranking.py` & `context_pack.py` (reasons / breakdowns / output)
- `src/repo_semantic_memory/extractors/test_relationships.py` (static `tests` relations)
- `benchmarks/tasks.yaml`, `src/repo_semantic_memory/eval/*` (regression harness)

**Risks:**
- Over-filtering domain tokens (`loader`, `resolve`, ambiguous `test`) — mitigated by an
  allowlist-guarded stop-set.
- Intent collisions and additive double-counting of priors — keep priors conditional and additive.
- Support/test expansion blowups producing new noise — enforce deterministic caps and first-party-only
  expansion.
- Overfitting eval to specific commits — pin commits and express targets as inclusion/noise thresholds.

**Recommended first implementation prompt:** **58.1 — Query intent parser and generic-token
downweighting.** It removes the largest, most visible source of noise (generic verbs boosting `find.py`,
`files/*`, runtime `test/`), is self-contained, has clear unit tests, and unblocks the task-aware path
priors (58.2) and downstream branches.
