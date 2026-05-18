# CHANGELOG

<!-- version list -->

## v0.5.0 (2026-05-18)

### Bug Fixes

- Address repo-map merge feedback items
  ([`a94fe33`](https://github.com/apajon/repo-semantic-memory/commit/a94fe33bd0edb92a8bc094349ee910df11fce065))

- Refine repo map citation format and path indexing flow
  ([`cca5e5a`](https://github.com/apajon/repo-semantic-memory/commit/cca5e5a401e4a3abc192955976604916a927fd2d))

### Chores

- Polish repo map budget and naming details
  ([`f560950`](https://github.com/apajon/repo-semantic-memory/commit/f560950f71d3c663246090cdd1b6e0d74e881a0c))

- Revert unrelated uv lockfile change
  ([`4d40cd4`](https://github.com/apajon/repo-semantic-memory/commit/4d40cd40c1d8e2117d60af1db5a3dff73e204415))

- Start repo map implementation plan
  ([`e0a7c9a`](https://github.com/apajon/repo-semantic-memory/commit/e0a7c9aa7a50312db563c14eae8b8812e0089cee))

### Features

- Add compact repo map generator and CLI command
  ([`13b3010`](https://github.com/apajon/repo-semantic-memory/commit/13b3010f3b351679e99084ad0f3359de96194650))

### Testing

- Align version constant test with package version
  ([`5f0df03`](https://github.com/apajon/repo-semantic-memory/commit/5f0df03f3e43db792e18f4b025d1216b8ca28cf5))


## v0.4.0 (2026-05-18)

### Bug Fixes

- Avoid duplicate python module entities in index output
  ([`93b7d77`](https://github.com/apajon/repo-semantic-memory/commit/93b7d7705478419bdfba616792d90ef570f9d881))

- Finalize sqlite store and CLI formatting
  ([`867e7d7`](https://github.com/apajon/repo-semantic-memory/commit/867e7d717bd959346b7d35cbb3b63756ee665657))

- Tighten python module filtering and assertion coverage
  ([`780c473`](https://github.com/apajon/repo-semantic-memory/commit/780c473f11f075595a28616d34a5e6de63b24589))

### Chores

- Revert unrelated uv lockfile change
  ([`f160d3c`](https://github.com/apajon/repo-semantic-memory/commit/f160d3c9b39ce8c69211c8348baa7c464f11a57d))

- Update plan after reproducing CI failure
  ([`58a95a0`](https://github.com/apajon/repo-semantic-memory/commit/58a95a01114878ea0f4bcb3b9b9a26853c1f2db5))

### Features

- Add sqlite store and CLI index/inspect commands
  ([`0b85784`](https://github.com/apajon/repo-semantic-memory/commit/0b8578427a12aa28555a8fc663e1093f48dcb17b))


## v0.3.0 (2026-05-18)

### Bug Fixes

- Align python qualified names and unresolved inherits modeling
  ([`7901455`](https://github.com/apajon/repo-semantic-memory/commit/790145592f601d5ffbd9a8ce4e855e59b9ce2fb9))

- Refine python ast typing and extractor tests
  ([`0586bc0`](https://github.com/apajon/repo-semantic-memory/commit/0586bc06104370fd2ffa2dd58645d841300fcf70))

### Chores

- Drop unrelated lockfile delta
  ([`d8eb106`](https://github.com/apajon/repo-semantic-memory/commit/d8eb106a837cb5a3a3124d72c244f8cfc5b12bcb))

- Plan python ast extractor implementation
  ([`5ec99a2`](https://github.com/apajon/repo-semantic-memory/commit/5ec99a2ae59deb925bc2b2eb0b20517e4e158b31))

- Polish extractor docs and cli output consistency
  ([`86f1334`](https://github.com/apajon/repo-semantic-memory/commit/86f1334e05ecf1e0559229ebbabcde1f4785655b))

- Refresh uv lockfile for 0.2.0 metadata
  ([`93a9a62`](https://github.com/apajon/repo-semantic-memory/commit/93a9a62cdb2f37afe1eed0581b03b643201cb377))

- Revert unintended lockfile change
  ([`3e6edcf`](https://github.com/apajon/repo-semantic-memory/commit/3e6edcfc0da51ec31af5597395101df6adb7cba7))

### Features

- Add python ast extractor and index-python cli
  ([`3f2bc78`](https://github.com/apajon/repo-semantic-memory/commit/3f2bc7818092927a7df08a943b28804287bafed7))

### Testing

- Cover module name variants and normalize unresolved ids
  ([`d992a76`](https://github.com/apajon/repo-semantic-memory/commit/d992a7656284bdd60a33c9ec9f0a8663428233fd))

- Extend module name edge case coverage
  ([`91baf53`](https://github.com/apajon/repo-semantic-memory/commit/91baf5329ac994bab37fd3f6804eada3222a7fa8))

- Update deterministic package version assertion
  ([`e2464cd`](https://github.com/apajon/repo-semantic-memory/commit/e2464cd678d5fd204eebe03492947bfbecf6e734))


## v0.2.0 (2026-05-17)

### Bug Fixes

- Align filesystem scan with PR review feedback
  ([`d103f67`](https://github.com/apajon/repo-semantic-memory/commit/d103f679ba620db9506edcc5509a09c8b9eb0b70))

- Harden filesystem reads against io errors
  ([`b56a74f`](https://github.com/apajon/repo-semantic-memory/commit/b56a74fdb64a039793d21eaddb5ff32a0e347558))

- Refine scan table formatting and line counting
  ([`8bbaac4`](https://github.com/apajon/repo-semantic-memory/commit/8bbaac4595654bb7aff5571c33048915dbea29d2))

### Chores

- Polish extractor constant and table width logic
  ([`683cdc9`](https://github.com/apajon/repo-semantic-memory/commit/683cdc948a66c3b6aa636c87c277d360c2de26a0))

### Features

- Add filesystem extractor and scan cli command
  ([`319eb42`](https://github.com/apajon/repo-semantic-memory/commit/319eb428acc9e0aec9afd3a9181f6cefbc84c46b))

### Testing

- Tighten filesystem extractor typing and ignored-dir coverage
  ([`1ec0f81`](https://github.com/apajon/repo-semantic-memory/commit/1ec0f816ccb3a49d9c0143d7cd9ea3913c445685))


## v0.1.0 (2026-05-17)

- Initial Release

## v1.0.0 (2026-05-17)

- Initial Release
