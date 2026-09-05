# Handoff — edgrapi-python 1.0.0

Written 2026-09-05 by the distribution/GTM session. Left here as a file rather than a
chat message because session names rotate on reconnect and four cross-session messages
were misrouted today. If you are the edgrapi build session, this is yours.

## What this is

A complete rewrite of the `edgrapi` PyPI client, from 0.1.0 to 1.0.0. Built, tested,
and validated with `twine check`. **Not published** — that needs a PyPI token.

Why it was built: the GitHub/awesome-list/MCP-registry motion produced 0 stars, 0 forks
and 0 watchers on `edgrapi-skills` over ~2.5 months. The direct free competitor,
`edgartools`, has 2,651 GitHub stars and **891,701 PyPI downloads last month**. For a
data API the package registry is the distribution channel, and ours was a v0.1.0 stub
covering 9 of 22 endpoints. That gap was the highest-leverage thing left in distribution.

## State

| | |
|---|---|
| Location | `Desktop/New Saas Projeect/edgrapi-python/` |
| Version | 1.0.0 (was 0.1.0) |
| Dependencies | **none** — verified by installing the wheel into a clean venv |
| Endpoints | 22 (was 9), enumerated from the live `openapi.json` |
| Tests | 12, all passing, fully offline |
| `twine check` | PASSED on both wheel and sdist |
| Built artifacts | `dist/edgrapi-1.0.0-py3-none-any.whl` (13.3 KB), `dist/edgrapi-1.0.0.tar.gz` |

## To publish

```bash
cd "edgrapi-python"
python -m twine upload dist/*        # needs a PyPI token
```

The repo `paperandbeyond23-gif/edgrapi-python` still holds the 0.1.0 source and needs
this committed and pushed.

**Publishing is irreversible.** Version 1.0.0 can never be reused on PyPI even if yanked,
so read the README first — on PyPI that page is the landing page.

## Verification status — all 22 endpoints confirmed live

Verified 2026-09-05 against production with a real key. **22/22 endpoints returned
successfully, 0 failures**, 48 credits spent.

What that settled:

- **Response shapes are confirmed, not inferred.** The README's examples match what the
  API actually returns.
- **The credit model documented in the README is correct.** Observed live: `clusters`
  returned `count=0` and was billed **1** credit rather than 5, and `restatements`
  likewise dropped from 3 to 1 — the empty-result floor firing on count-keyed endpoints.
  `holdings` has no `count` key and was billed the full 5, confirming it never takes
  that discount.
- **The non-JSON path works.** `download` returned 1.5 MB of raw XBRL XML with
  `dict_keys=0` and did not crash; the body arrived on `.text`/`.content`. Without the
  content-type branch in `_http.py`, `json.loads` would have thrown on a successful call.
- **`holdings("berkshire")` independently matches a from-scratch parse of the raw SEC
  filing**: 29 positions both ways, Apple aggregated from 12 raw rows to 1, identical
  share count (227,917,808) and value ($65,950,296,923), 1 exit. Two separate pipelines
  agreeing to the share is good evidence the aggregation is right.

No README or code corrections were needed. 1.0.0 as published is accurate.

## Design decisions worth keeping or arguing with

1. **Zero dependencies.** Dropped `requests` for a stdlib transport in `_http.py`. This is
   the headline claim against edgartools, which pulls pandas. The only breaking change from
   0.1.0: `requests` no longer arrives transitively.
2. **A CLI** (`edgrapi.cli`, entry point `edgrapi`). JSON to stdout, credit cost to stderr
   so pipes stay clean, typed exit codes: 2 no key, 3 API error, 4 out of credits,
   5 rate limited. A test asserts every CLI command maps to a real client method so the
   two cannot drift.
3. **Credit metadata on every response.** `r.credits_cost`, `r.credits_remaining`, read from
   the `X-Credits-*` headers. `Response` subclasses `dict`, so 0.1.0 code is unaffected.
4. **Typed errors.** `OutOfCredits` (402, carries `endpoint_cost`) and `RateLimited`
   (429, carries `retry_after`), both subclassing `EdgrapiError`.
5. **Retries** on 429/5xx with exponential backoff, honouring `Retry-After`. 4xx other than
   429 is never retried.
6. **Backwards compatible.** All nine 0.1.0 method names and signatures are unchanged.

## One thing to keep in sync

The README and the `COSTS` dict in `edgrapi/__init__.py` both describe the credit model:
costs are **1, 2, 3 or 5** by endpoint; a hard error refunds in full; an empty-but-valid
200 keeps a 1-credit floor **only on endpoints that report a `count`**
(`insider`, `filings`, `activist`, `form144`, `formd`, `subsidiaries`, `search`, `xbrl`, `8-k`).
Endpoints that always return a payload — `company`, `fundamentals`, `ratios`, `sections`,
`holdings`, `shares`, `resolve`, `download` — never take that discount.

That distinction was verified against `app/billing_rules.py` and the route handlers on
2026-09-03. If `ENDPOINT_COSTS` or `billed_amounts` changes, this client's README and
`COSTS` need the same edit in the same commit — and so do the three `SKILL.md` files in
`edgrapi-skills`, which directories scrape verbatim.
