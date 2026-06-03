# Ranking v2 Regression Evaluation — Prompt 58.6

> **Date:** 2026-06-01
> **Method:** MCP `rsm_build_context_pack` via `mcp_repo-semantic4`
> **Parameters:** `budget_chars=32000`, `detail_level=compact`, `max_entities=40`, `max_files=30`
> **Scope:** Ranking changes from Prompts 58.1–58.5

---

## Indexes

| Repo    | repo_id            | git status | indexed_at  |
|---------|--------------------|------------|-------------|
| django  | `b227c76f87be96f5` | fresh      | 2026-05-28  |
| ansible | `098ea0b96c16f6b3` | fresh      | 2026-05-28  |
| httpx   | `9221ac6e57b4c410` | fresh      | 2026-05-27  |
| typer   | `23e0782084e407be` | fresh      | 2026-05-27  |

---

## Task 1 — Django URL Resolution

**Task:**
> Find how Django resolves URL patterns into view execution, including resolver
> implementation files and relevant tests.

**result_set_id:** `pack_17fb473f4f`
**Entities available:** 65 total / 40 shown
**Files:** 31

### Selected central files

| File | Key entities | Verdict |
|------|-------------|---------|
| `django/urls/resolvers.py` | `URLResolver` (class + 8 methods), `ResolverMatch`, `get_resolver`, `_get_cached_resolver`, `get_ns_resolver`, `resolve_error_handler`, `_reverse_with_prefix` | ✅ correct, ranks 1–2 |
| `django/core/checks/urls.py` | `check_resolver` | ✅ correct |
| `django/urls/exceptions.py` | `Resolver404` | ✅ correct |
| `django/urls/base.py` | `translate_url` | ✅ useful |
| `django/conf/urls/i18n.py` | `i18n_patterns` | ⚠️ marginal (URL helper, not core resolver path) |

### Missing central files

| File | Why it matters |
|------|---------------|
| `django/urls/conf.py` | Defines `path()`, `re_path()`, `include()` — the public URL registration API |
| `django/core/handlers/base.py` | Implements `BaseHandler.resolve_request()` — the request-to-resolver dispatch bridge |

### Selected test files

| File | Entity | Verdict |
|------|--------|---------|
| `tests/urlpatterns/test_resolvers.py` | `ResolverLazyIncludeTests.test_lazy_route_resolves` | ✅ correct test hit |
| `tests/urlpatterns_reverse/views.py` | `pass_resolver_match_view` | ⚠️ test helper view, not a test suite |

No broader test module (`tests/urlpatterns/tests.py`, `tests/urlconf_include/`) was selected.

### Selection reasons

| File | Reason selected |
|------|----------------|
| `django/urls/resolvers.py` | `URLResolver` class name + `resolve` method name + module path `urls.resolvers` all strong BM25 hits |
| `django/template/defaultfilters.py` | `_property_resolver` — `resolver` stem collision from Django template layer |
| `django/db/backends/base/features.py` | `supports_explaining_query_execution` — no relation to URL resolution; likely via low-signal padding |
| Storage/feed/template `.url` methods | BM25 `url` token matches bare `.url` method name across 10+ unrelated subsystems |

### Remaining noise

| File | Entity | Cause |
|------|--------|-------|
| `django/db/backends/base/features.py` | `BaseDatabaseFeatures.supports_explaining_query_execution` | DB layer, irrelevant |
| `django/contrib/staticfiles/utils.py` | `matches_patterns` | `patterns` stem match |
| `django/template/defaultfilters.py` | `_property_resolver` | `resolver` stem match in template layer |
| `django/template/defaulttags.py` | `url` | `.url` method collision |
| `django/contrib/admin/checks.py` | `_check_view_on_site_url` | `url` in method name |
| `django/contrib/admin/options.py` | `get_view_on_site_url` | `url` in method name |
| `django/contrib/staticfiles/storage.py` | `HashedFilesMixin.url` | `.url` method |
| `django/core/files/storage/base.py` | `Storage.url` | `.url` method |
| `django/core/files/storage/memory.py` | `InMemoryStorage.url` | `.url` method |
| `django/core/files/storage/filesystem.py` | `FileSystemStorage.url` | `.url` method |
| `django/db/models/fields/files.py` | `FieldFile.url` | `.url` method |
| `django/utils/feedgenerator.py` | `Stylesheet.url` | `.url` method |
| `django/templatetags/static.py` | `StaticNode.url` | `.url` method |
| `django/contrib/auth/middleware.py` | `LoginRequiredMiddleware.get_login_url` | `url` in name |
| `django/contrib/auth/views.py` | `LoginView.get_default_redirect_url`, `LogoutView.get_default_redirect_url` | `url` in name |
| `django/core/management/utils.py` | `normalize_path_patterns` | `patterns` stem |

**Root cause:** 12+ entities in the top 40 match the `url` token as a bare method name from
storage, feeds, templates, and auth. The 58.1 generic token stripping does not suppress `url`
as a token; `.url` as a one-word method name carries no discriminating co-occurrence.

### Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| central_file | 4/5 | `resolvers.py` correct; `conf.py` and `handlers/base.py` absent |
| support_files | 3/5 | `exceptions.py`, `base.py` present; many noisy `.url` method files |
| tests | 3/5 | `test_resolvers.py` found; only 1 method shown; broader suites absent |
| noise_reduced | 2/5 | 12+ irrelevant `.url` method entities in top 40 |
| **overall** | **3/5** | Usable; agent must filter `.url` storage/feed/template entities manually |

---

## Task 2 — Ansible Plugin/Module Discovery

**Task:**
> Find how Ansible discovers and loads modules/plugins, including loader
> implementation files and relevant tests.

**result_set_id:** `pack_e568dd8658`
**Entities available:** 60 total / 40 shown
**Files:** 11

### Selected central files

| File | Key entities | Verdict |
|------|-------------|---------|
| `lib/ansible/plugins/loader.py` | `PluginLoader`, `_CacheLoader`, `Jinja2Loader`, `add_dirs_to_loader`, `_configure_collection_loader`, `init_plugin_loader`, `get_fqcr_and_name`, `get_plugin_loader_namespace`, `_does_collection_support_ansible_version` | ✅ correct, rank 1 |
| `lib/ansible/utils/collection_loader/_collection_finder.py` | `_AnsibleCollectionLoader`, `_AnsibleCollectionFinder._get_loader`, `_AnsibleCollectionPkgLoaderBase`, `_AnsibleCollectionPkgLoader`, `_AnsibleInternalRedirectLoader`, `_iter_modules_impl` | ✅ correct |
| `lib/ansible/_internal/_yaml/_loader.py` | `AnsibleLoader`, `AnsibleInstrumentedLoader` | ✅ correct (internal YAML loader implementation) |
| `lib/ansible/module_utils/_internal/_ansiballz/_loader.py` | module | ✅ correct (module packaging loader) |
| `lib/ansible/parsing/yaml/loader.py` | `AnsibleLoader` factory | ⚠️ YAML data loader, tangential to plugin discovery |
| `lib/ansible/vars/plugins.py` | `_prime_vars_loader` | ⚠️ vars plugin loading, relevant at the edges |
| `lib/ansible/template/__init__.py` | `Templar._loader` | ⚠️ property accessor, not loader core |

### Missing central files

| File | Why it matters |
|------|---------------|
| `test/units/plugins/test_plugins.py` | Direct unit test for `PluginLoader`; test branch algorithm did not surface it |

### Selected test files

| File | Entity | Verdict |
|------|--------|---------|
| `test/lib/ansible_test/_internal/cgroup.py` | `MountEntry.loads`, `CGroupEntry.loads` | ❌ false positive — `loads` is a classmethod deserializer for Linux cgroup entries, completely unrelated to plugin loading |

No actual plugin/module loader tests were selected.

### Selection reasons

| File | Reason selected |
|------|----------------|
| `lib/ansible/plugins/loader.py` | `loader` in path, class names, and function names; very strong BM25 signal |
| `test/lib/ansible_test/_internal/cgroup.py` | `CGroupEntry.loads` / `MountEntry.loads` — BM25 stems `loads` → `load`, overlapping with `loader` query token |
| `test/units/plugins/test_plugins.py` absent | Test branch resolves stem from source path: `loader.py` → stem `loader` → looks for `test_loader.py`, which does not exist; `test_plugins.py` stem is `plugins`, not `loader` |

### Remaining noise

| File | Entity | Cause |
|------|--------|-------|
| `test/lib/ansible_test/_internal/cgroup.py` | `MountEntry.loads`, `CGroupEntry.loads` | `loads` stem matches `loader` query; no semantic filter |
| `lib/ansible/playbook/block.py` | `Block.set_loader` | `loader` in name but refers to data-file loader, not plugin loader |
| `lib/ansible/playbook/task.py` | `Task.set_loader` | Same |
| `lib/ansible/playbook/role/__init__.py` | `Role.set_loader` | Same |

**Root cause:** BM25 stemming maps `loads` → `load` which overlaps with the `loader` token in the
task. The test-infrastructure path `test/lib/ansible_test/_internal/` is not excluded by the
runtime-named-path guard (which targets `plugins/test/` patterns, not `ansible_test/`).

### Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| central_file | 5/5 | `plugins/loader.py` and `_collection_finder.py` both top-ranked |
| support_files | 4/5 | Internal loaders present; playbook `set_loader` methods are marginal |
| tests | 1/5 | `test_plugins.py` absent; cgroup FP is the only test-path entity |
| noise_reduced | 3/5 | cgroup FP is significant but isolated; playbook noise is minor |
| **overall** | **3/5** | Central files excellent; test gap and cgroup FP require 58.7 fixes |

---

## Task 3 — HTTPX Public HTTP Client API

**Task:**
> Find the public API for making HTTP requests with sync and async clients and
> where those clients are implemented.

**result_set_id:** `pack_39e744f401`
**Entities available:** 85 total / 40 shown
**Files:** 16

### Selected central files

| File | Key entities | Verdict |
|------|-------------|---------|
| `httpx/__init__.py` | module root | ✅ correct (public export surface) |
| `httpx/_api.py` | `request`, `stream`, `get`, `post`, `put`, `patch`, `delete`, `head`, `options` | ✅ correct, all 9 top-level functions |
| `httpx/_client.py` | `AsyncClient` + all request methods (`get`, `post`, `put`, `patch`, `delete`, `head`, `options`, `request`, `stream`) | ✅ correct; sync `Client` also in file (in remaining 45 entities) |
| `httpx/_transports/default.py` | `AsyncHTTPTransport`, `HTTPTransport` | ✅ correct |
| `httpx/_transports/base.py` | `AsyncBaseTransport` | ✅ correct |
| `httpx/_transports/__init__.py` | module | ✅ correct |
| `httpx/_exceptions.py` | `HTTPError`, `HTTPStatusError` | ✅ correct |
| `httpx/_types.py` | `SyncByteStream`, `AsyncByteStream` | ✅ correct |
| `docs/advanced/clients.md` | "Making requests" section (lines 51–75) | ✅ useful doc context |
| `docs/async.md` | "Making Async requests" section (lines 13–27) | ✅ useful doc context |

### Missing central files

None. All expected files are present or inferred from the selected file. Sync `Client`
is in `httpx/_client.py` and present in the remaining 45 entities not shown in the
compact preview.

### Selected test files

None. No `tests/` path entities were selected.

### Selection reasons

| File | Reason selected |
|------|----------------|
| `httpx/__init__.py` | Public API root; all client types re-exported; strong public-API path prior (58.2) |
| `httpx/_api.py` | All 7 method names (`get`, `post`, …) are exact task token matches via BM25 |
| `httpx/_client.py` | `AsyncClient` class + method names align strongly; `client` in path |
| `docs/advanced/clients.md` | Markdown doc entity; `clients` + `requests` tokens match |
| `httpx/_main.py` | `main` function included; CLI entry point matching on common function name |

### Remaining noise

| File | Entity | Cause |
|------|--------|-------|
| `httpx/_main.py` | `main()` | CLI entry point; no relation to HTTP client API; `main` is a high-frequency name |

**Root cause:** `httpx/_main.py` has a single entity (`main`) that scores above threshold
because `main` is a common BM25 token. Minor noise; easily filtered.

### Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| central_file | 5/5 | All public-facing files present |
| support_files | 5/5 | Exceptions, types, transports, docs all correctly included |
| tests | 1/5 | No test files selected |
| noise_reduced | 4/5 | Only `_main.py` is noise; very clean result |
| **overall** | **4/5** | Best result of the four; test absence is the only meaningful gap |

---

## Task 4 — Typer Command Registration

**Task:**
> Find how Typer turns @app.command() and @app.callback() declarations into
> executable Click commands, including the implementation files and core tests.

**result_set_id:** `pack_b16deb88b0`
**Entities available:** 76 total / 40 shown
**Files:** 11

### Selected central files

| File | Key entities | Verdict |
|------|-------------|---------|
| `typer/_click/core.py` | `Command` class + 17 methods (`__init__`, `invoke`, `main`, `make_context`, `parse_args`, `shell_complete`, …), `Context.command_path`, `_complete_visible_commands` | ✅ correct (vendored Click Command); **ranks 1–2, dominates compact budget** |
| `typer/core.py` | `TyperCommand`, `TyperGroup._click_resolve_command`, `TyperGroup.add_command`, `TyperGroup.get_command`, `TyperGroup.resolve_command`, `TyperGroup.list_commands`, `TyperGroup.format_commands` | ✅ correct |
| `typer/main.py` | `Typer.command` (rank 36) | ✅ present but low-ranked; `Typer.callback()` and `Typer` class likely in remaining 36 entities |
| `typer/cli.py` | `callback` | ⚠️ Typer's own CLI tool callback; not the `@app.callback()` registration mechanism |

### Missing central files

`typer/main.py` IS selected (rank 36 with `Typer.command()`), but `typer/_click/core.py`
occupies 17+ entity slots in the compact preview, crowding out `Typer.callback()` and the
`Typer` class from the visible top 40.

### Selected test files

None. No `tests/` path entities were selected. Typer's `tests/` directory does not appear
to be indexed (all 11 files are source + `docs_src/`).

### Selection reasons

| File | Reason selected |
|------|----------------|
| `typer/_click/core.py` | `Command` class name + `command` token in task query — very strong BM25; hundreds of method entities each scoring positively |
| `typer/core.py` | `TyperCommand`, `TyperGroup` — `typer` + `command` strong compound match |
| `typer/main.py` | `Typer.command()` method name matches; ranks low because BM25 pool dominated by click internals |
| `docs_src/*/tutorial*.py` | `callback()` function name — direct lexical match on `@app.callback()` token; path prior (58.2) insufficient to suppress |

### Remaining noise

| File | Entity | Cause |
|------|--------|-------|
| `docs_src/commands/callback/tutorial002_py310.py` | `callback()` | Tutorial example, not implementation |
| `docs_src/commands/callback/tutorial003_py310.py` | `callback()`, `new_callback()` | Tutorial example |
| `docs_src/commands/callback/tutorial004_py310.py` | `callback()` | Tutorial example (rank ~18 — high) |
| `docs_src/commands/one_or_multiple/tutorial001_py310.py` | `callback()` | Tutorial example (rank ~39) |
| `docs_src/commands/one_or_multiple/tutorial002_py310.py` | `callback()` | Tutorial example (rank ~40) |
| `docs/tutorial/commands/context.md` | "Executable callback" section | Tutorial doc |
| `typer/cli.py` | `callback()` | Typer's own CLI callback, not `@app.callback()` |

**Root causes:**
1. `typer/_click/core.py` (vendored Click) generates 17+ high-scoring entities for `command`
   tokens, dominating the compact preview and displacing `typer/main.py` content from visible ranks.
2. `docs_src/` tutorial files rank above 40 despite the 58.2 public-API path prior — the
   `callback` token match is too strong relative to the discount applied.

### Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| central_file | 4/5 | `core.py` and `_click/core.py` correct; `main.py` present at rank 36 |
| support_files | 3/5 | `cli.py` marginal; vendor file dominates compact preview budget |
| tests | 1/5 | No test files; Typer tests not indexed |
| noise_reduced | 2/5 | 5 `docs_src/` tutorial files in top 40; vendor file crowds view |
| **overall** | **3/5** | Structurally correct but needs vendor-path damping and `docs_src/` cleanup |

---

## Overall Verdict

| Task | central_file | support_files | tests | noise_reduced | overall |
|------|-------------|---------------|-------|--------------|---------|
| Django URL resolution | 4/5 | 3/5 | 3/5 | 2/5 | **3/5** |
| Ansible plugin loading | 5/5 | 4/5 | 1/5 | 3/5 | **3/5** |
| HTTPX public API | 5/5 | 5/5 | 1/5 | 4/5 | **4/5** |
| Typer command registration | 4/5 | 3/5 | 1/5 | 2/5 | **3/5** |
| **Average** | **4.5/5** | **3.75/5** | **1.5/5** | **2.75/5** | **3.25/5** |

Ranking v2 (58.1–58.5) delivers correct central file selection in all four tasks.
The strongest result is HTTPX: a clean, focused pack with minimal noise.
Ansible is correct on core files but has one clear false positive (cgroup).
Django and Typer both show surface-level BM25 noise that the current stripping
and path-prior logic does not yet fully suppress.

**Systemic gaps across all four tasks:**

1. **Test files** — score 1/5 on 3 of 4 tasks. Test branch algorithm finds tests when
   the source stem matches exactly; fails when tests are named by domain (`test_plugins.py`
   vs. `test_loader.py`) or when the test suite is not indexed.
2. **`.url` method proliferation** (Django) — `url` token hits 12+ unrelated entities from
   storage, feeds, templates, and auth; needs a name-role weight or context co-occurrence filter.
3. **`docs_src/` tutorial noise** (Typer) — tutorial `callback()` examples score in the top 40
   despite 58.2 public-API path prior; needs stronger `docs_src/` discount.
4. **Vendor file budget dominance** (Typer) — `typer/_click/core.py` occupies 17+ entity slots
   in the compact 40-entity preview; needs a per-file entity cap or vendor-path damping.
5. **BM25 false positives via stem matching** (Ansible cgroup) — `loads` matches `loader`
   query; no semantic filter exists to break this collision.

---

## 58.7 Cleanup Targets

**Required: YES**

### Target 1 — Django `.url` method noise (high priority)

**Problem:** 12+ entities matching `.url` as a bare method name are in the top 40
(`Storage.url`, `FieldFile.url`, `StaticNode.url`, `Stylesheet.url`, `HashedFilesMixin.url`, etc.).
All are irrelevant to URL routing/resolution.

**Likely fix:** Apply a name-role penalty when `url` appears as the sole method name without
any co-occurring term from the resolver/pattern vocabulary. Alternatively, add `url` to a
context-dependent suppression list when the query intent is URL *routing* not URL *generation*.

**Test to add:** Assert that `Storage.url`, `FieldFile.url`, `StaticNode.url`, and
`Stylesheet.url` entities are not selected when the task is "Django URL resolver".

---

### Target 2 — Ansible `cgroup.loads` false positive (high priority)

**Problem:** `test/lib/ansible_test/_internal/cgroup.py` is selected with `MountEntry.loads`
and `CGroupEntry.loads`. BM25 stems `loads` → `load` which overlaps with `loader` query tokens.
Zero semantic relation to plugin loading.

**Likely fix:** Extend the runtime-named-path exclusion to cover `test/lib/ansible_test/`
infrastructure paths, or apply a path-depth penalty for deeply nested test infrastructure.

**Test to add:** Assert that `cgroup.py` is not selected for the Ansible plugin loader task.
Assert that `test/units/plugins/test_plugins.py` IS selected when available.

---

### Target 3 — Typer `docs_src/` tutorial noise (medium priority)

**Problem:** Five `docs_src/commands/callback/tutorial*.py` and
`docs_src/commands/one_or_multiple/tutorial*.py` files rank in the top 40 because their
`callback()` function name directly matches the task's `@app.callback()` phrasing.

**Likely fix:** Increase the `docs_src/` path discount in the public-API path prior (58.2),
or add a `docs_src/` exclusion to the default ranking profile.

**Test to add:** Assert that no `docs_src/` entities appear in the top 20 ranked entities
for the "Typer command registration" task.

---

### Target 4 — Vendor file compact budget dominance (medium priority)

**Problem:** `typer/_click/core.py` generates 17+ method entities occupying most of the
40-entity compact preview. `typer/main.py` with `Typer.command()` and `Typer.callback()`
is pushed to rank 36, invisible at default compact budget for most agents.

**Likely fix:** Apply a per-file entity deduplication cap in the compact preview (e.g., max
5 entities per unique file path), or apply a vendor-path damping factor for files under
`_click/` that mirror a published package name.

**Test to add:** Assert that `typer/main.py` appears in the top 20 ranked entities for
the "Typer command registration" task. Assert that fewer than 8 entities from
`typer/_click/core.py` are in the top 20.

---

### Target 5 — Test file selection (medium priority, all tasks)

**Problem:** 3 of 4 tasks scored 1/5 on tests. The test branch algorithm resolves tests
only when the source file stem maps to a `test_<stem>.py` filename. This misses:
- Domain-named tests: `test_plugins.py` for `loader.py`
- Repos where `tests/` is not indexed (Typer, HTTPX)

**Likely fixes:**
1. Expand test branch resolution to also probe `test_<parent_dir>.py` and
   `test_<class_name_lower>.py` patterns.
2. Verify that `tests/` directories are indexed in all benchmark repos.

**Test to add:** Update `TestBranchRegressions` in `tests/context/test_ranking_v2_regression.py`
to cover the domain-stem mismatch case (source stem ≠ test file stem).
