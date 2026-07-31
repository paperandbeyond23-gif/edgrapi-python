# edgrapi

A tiny Python client for the [Edgrapi](https://edgrapi.com) SEC EDGAR data API.

Parsed SEC filings as clean JSON: company financials, insider trades (Form 4),
8-K events, 13F fund holdings, and 13D/13G activist stakes. There's **no LLM in
the data path** — every value is lifted straight from the filing, so you can
verify any number on EDGAR yourself.

The heavy lifting (XBRL parsing, CUSIP mapping, quarter-over-quarter diffs)
happens server-side, so this client stays tiny and has one dependency
(`requests`).

## Install

```bash
pip install edgrapi
```

Get a free API key (100 calls/month, no card) at <https://edgrapi.com>.

## Usage

```python
from edgrapi import Client

c = Client("your_key")

# Financials — income statement, balance sheet, cash flow (normalized from XBRL)
c.fundamentals("AAPL")
c.fundamentals("AAPL", period="quarterly", limit=8)
c.ratios("AAPL")

# Insider trades (Form 4), scored buy vs sell
c.insider("NVDA")

# 8-K material events, item-coded
c.events("TSLA")
c.events("TSLA", notable=True)   # skip routine 8-Ks

# 13F fund holdings, diffed against last quarter
c.holdings("berkshire")          # famous-fund alias
c.holdings("burry")

# 13D / 13G activist stakes
c.activist("AAPL")

# Company profile + CIK, and recent filings
c.company("MSFT")
c.filings("MSFT", form="10-K")

# Extracted 10-K / 10-Q sections (business, risk factors, MD&A)
c.sections("AAPL")
```

Every method returns the parsed JSON body as a `dict`.

## Errors

Failed calls raise `EdgrapiError`, which carries the HTTP status and the
server's detail:

```python
from edgrapi import Client, EdgrapiError

c = Client("your_key")
try:
    c.fundamentals("NOTATICKER")
except EdgrapiError as e:
    print(e.status, e.detail)   # e.g. 404 unknown ticker
```

Common statuses: `401` bad key, `402` / `429` out of credits, `404` unknown
ticker. Calls that return no data are not charged. The exact credit cost of each
call comes back in the `X-Credits-Cost` response header, and your remaining
balance in `X-Credits-Remaining`.

## Notes

- This is a thin HTTP client. The API it talks to is a hosted service; if you'd
  rather run everything locally with no API key, [edgartools](https://github.com/dgunning/edgartools)
  is an excellent open-source library that parses EDGAR on your own machine.
- Data is public SEC EDGAR content, surfaced for research. Not investment advice.

## License

[MIT](LICENSE).
