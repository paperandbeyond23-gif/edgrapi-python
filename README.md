# edgrapi

**SEC EDGAR filings as clean JSON. Zero dependencies.**

[![PyPI](https://img.shields.io/pypi/v/edgrapi)](https://pypi.org/project/edgrapi/)
[![Python](https://img.shields.io/pypi/pyversions/edgrapi)](https://pypi.org/project/edgrapi/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

```bash
pip install edgrapi
```

Nothing else gets installed. No `requests`, no `pandas` — the client is standard library only, so it drops into a Lambda, a container, or someone else's dependency tree without an argument.

```python
from edgrapi import Client

c = Client("edgr_...")                 # or set EDGRAPI_KEY
c.holdings("berkshire")                # 13F, CUSIP-aggregated, diffed QoQ
c.insider("AAPL")                      # Form 4, code P separated from 10b5-1
c.clusters(days=15, min_insiders=3)    # several insiders buying at once
c.search("climate risk", forms="10-K") # full text, every filing since 2001
```

Or without writing any Python at all:

```bash
export EDGRAPI_KEY=edgr_...
edgrapi holdings berkshire --changes
edgrapi clusters --days 15 --min-insiders 3
edgrapi insider AAPL --limit 5 | jq '.transactions[0]'
```

Get a free key — 100 credits every month, no card — at **[edgrapi.com/app](https://edgrapi.com/app)**.

---

## Why this exists

The SEC's data is free. Parsing it correctly is the work, and most of the bugs are silent:

- **A 13F lists one holding once per sub-manager.** Berkshire's latest filing has 89 rows and 29 actual positions — Apple alone appears 12 times. Read the table as it arrives and you triple-count the portfolio.
- **A `putCall` row is a bet *against* the stock**, not a holding. Every quarter someone reports a fund is "long" a name it is actually short.
- **Filings before 2023 report value in thousands; newer ones in whole dollars.** Diff across that boundary without normalising and every position looks like it grew 1000×.
- **Share classes are separate CUSIPs.** Alphabet is `02079K305` (Class A) and `02079K107` (Class C). Merging them is as wrong as splitting Apple.
- **XBRL tags drift** between filers and across years, so the same line item arrives under a dozen different names.

`holdings()` handles all of that and labels every position new / added / reduced / exited against the prior quarter, so you get what changed rather than one quarter's snapshot.

## What you can call

| Method | What it returns |
|---|---|
| `company(ticker)` | CIK, legal name, SIC industry, fiscal-year end |
| `filings(ticker, form=, limit=)` | Filings newest first, filterable by form |
| `resolve(ticker=, cik=, cusip=)` | Map any identifier to the others |
| `subsidiaries(ident)` | Subsidiaries from the 10-K Exhibit 21 |
| `fundamentals(ticker, period=)` | Income statement, balance sheet, cash flow |
| `ratios(ticker)` | Margins, returns, leverage, liquidity |
| `xbrl(ident, concept=)` | Raw XBRL as JSON, optionally one tag |
| `shares(ticker, history=)` | Shares outstanding and public float |
| `sections(ticker, item=)` | Risk factors, MD&A, business — from 10-K/10-Q |
| `insider(ticker, ...)` | Form 4 transactions |
| `clusters(days=, min_insiders=)` | Market-wide cluster buys |
| `form144(ticker)` | Notices of proposed sale |
| `events(ticker, notable=)` | 8-K material events, item-coded |
| `restatements()` / `auditor_changes()` | Market-wide feeds |
| `activist(identifier, activist_only=)` | 13D/13G stakes above 5% |
| `holdings(identifier, changes=)` | 13F holdings, aggregated and diffed |
| `formd(ident)` | Form D private placements |
| `search(q, forms=, startdt=)` | Full-text search since 2001 |
| `download(accession)` | Raw filing document (read `.text` / `.content`, not as a dict) |

Anything added after this release is reachable with `c.get("/v1/whatever", param=...)`.

## Credits, errors and retries

Every response is the API's JSON dict with billing attached:

```python
r = c.insider("AAPL")
r["count"]            # the data
r.credits_cost        # what this call was billed
r.credits_remaining   # balance afterwards
```

Calls cost **1, 2, 3 or 5 credits** depending on the endpoint — a light lookup is 1, an XBRL parse is 3, pulling a full document is 5. A hard error refunds in full. A valid response that carried no rows keeps a 1-credit floor, on the endpoints that report a `count`.

Errors are typed, so you can branch on them:

```python
from edgrapi import Client, OutOfCredits, RateLimited, EdgrapiError

try:
    c.holdings("berkshire")
except OutOfCredits as e:
    print("needed", e.endpoint_cost, "credits")
except RateLimited as e:
    time.sleep(e.retry_after or 5)
except EdgrapiError as e:
    print(e.status, e.error, e.request_id)
```

429s and 5xx are retried automatically with exponential backoff, honouring `Retry-After`. A 404 is never retried — it will not start working.

## Worth knowing

- `holdings()` takes a fund, not a ticker — a name like `berkshire`, a CIK, or a filer ticker.
- `activist()` and `formd()` accept `"latest"` for the market-wide feed.
- Only open-market purchases (code **P**) mean an insider spent their own money. Option exercises and vesting also appear on Form 4 as acquisitions but say nothing; most sales are pre-scheduled 10b5-1.
- Data is public-domain SEC EDGAR. Nothing here is investment advice.

## Also available

The same data is exposed as a hosted **MCP server** at `https://api.edgrapi.com/mcp`, so an agent in Claude, Cursor or Cline can call it directly:

```json
{ "mcpServers": { "edgrapi": {
    "url": "https://api.edgrapi.com/mcp",
    "headers": { "Authorization": "Bearer edgr_YOUR_KEY" } } } }
```

Full REST docs at [edgrapi.com/docs](https://edgrapi.com/docs) · OpenAPI at [api.edgrapi.com/openapi.json](https://api.edgrapi.com/openapi.json)

## License

MIT
