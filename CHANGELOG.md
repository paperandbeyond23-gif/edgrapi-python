# Changelog

## 1.0.0 — 2026-09-05

First stable release. Rewritten from 0.1.0.

### Added
- **Zero dependencies.** Dropped `requests` for a stdlib transport, so `pip install edgrapi` installs exactly one package.
- **CLI**: `edgrapi holdings berkshire --changes`. JSON to stdout, credit cost to stderr, typed exit codes (2 no key, 3 API error, 4 out of credits, 5 rate limited).
- **Full endpoint coverage** — 9 methods to 22, adding `clusters`, `search`, `xbrl`, `shares`, `resolve`, `subsidiaries`, `form144`, `formd`, `restatements`, `auditor_changes`, `download`, `xbrl_by_accession`.
- **Credit metadata on every response**: `r.credits_cost`, `r.credits_remaining`.
- **Typed errors**: `OutOfCredits` (402, carries `endpoint_cost`) and `RateLimited` (429, carries `retry_after`), both subclassing `EdgrapiError`.
- **Automatic retries** on 429 and 5xx with exponential backoff, honouring `Retry-After`. 4xx other than 429 is never retried.
- `EDGRAPI_KEY` environment variable support.
- `Client.get()` escape hatch for endpoints newer than this release.
- `py.typed` marker; gzip response handling; offline test suite.

### Changed
- Errors now carry the server's `error` slug and `request_id` alongside the detail.

### Compatibility
All 0.1.0 methods keep their names and signatures. The only breaking change is that
`requests` is no longer installed as a dependency — import it yourself if your own
code relied on it arriving via this package.
