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

## What I could NOT verify

**No real API call was ever made.** There was no key available in this session and
creating one is the owner's action, not mine. Consequences:

- Every method signature comes from the live OpenAPI spec, so paths and query parameter
  *names* are correct.
- **Response shapes are unexercised.** If any endpoint returns something unexpected, the
  client will still hand it back — it does not validate bodies — but the README examples
  showing `r["count"]` and similar are inferred, not confirmed.
- The one live check I did run: a deliberately invalid key against production returned
  `Edgrapi 401 (unauthorized): Invalid API key. [request_id=req_aebc3238f760069c]`. So the
  transport, error mapping and request-id extraction are confirmed against the real API.

**Recommended before upload:** set `EDGRAPI_KEY` and run each method once. A key with
~40 credits covers the whole surface.

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
