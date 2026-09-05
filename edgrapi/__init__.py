# -*- coding: utf-8 -*-
"""edgrapi — SEC EDGAR filings as clean JSON, with no dependencies.

The SEC's data is free. Parsing it correctly is the work, and most of the bugs
are silent: a 13F lists one holding once per sub-manager, so a raw table
double-counts unless you aggregate by CUSIP; a ``putCall`` row is a bet against
the stock, not a holding; filings before 2023 report value in thousands and
newer ones in whole dollars. This client talks to an API that has already done
that work.

    from edgrapi import Client

    c = Client("edgr_...")                  # or set EDGRAPI_KEY
    c.holdings("berkshire")                 # 13F, CUSIP-aggregated, diffed QoQ
    c.insider("AAPL")                       # Form 4, code P separated from 10b5-1
    c.clusters(days=15, min_insiders=3)     # several insiders buying at once
    c.events("AAPL", notable=True)          # 8-K, item-coded
    c.search("climate risk", forms="10-K")  # full text, every filing since 2001

Every response is the API's JSON dict plus what the call cost::

    r = c.insider("AAPL")
    r["count"], r.credits_cost, r.credits_remaining

Free key, no card: https://edgrapi.com/app
"""
import os

from ._http import (EdgrapiError, OutOfCredits, RateLimited, Response,
                    build_url, request)

__version__ = "1.0.0"
__all__ = ["Client", "EdgrapiError", "OutOfCredits", "RateLimited", "Response",
           "__version__"]

DEFAULT_BASE = "https://api.edgrapi.com"

#: What each endpoint costs, by weight. Mirrors the server's own table — light
#: lookups cost 1, multi-MB XBRL parses cost 3, full document pulls cost 5.
#: A hard error refunds in full; a valid 200 that carried no rows keeps a
#: 1-credit floor, but only on endpoints that report a ``count``.
COSTS = {
    "company": 1, "filings": 1, "events": 1, "resolve": 1, "search": 1,
    "download": 1, "shares": 2, "formd": 2, "subsidiaries": 2,
    "fundamentals": 3, "ratios": 3, "xbrl": 3, "form144": 3,
    "sections": 5, "insider": 5, "holdings": 5, "activist": 5,
}


class Client:
    """Client for the Edgrapi SEC-data API.

    Args:
        api_key: your key. Falls back to the ``EDGRAPI_KEY`` environment
            variable, which is the usual way to avoid committing one.
        base_url: override the API host.
        timeout: per-request timeout in seconds.
        retries: how many times to retry 429 and 5xx responses.

    Methods return a :class:`Response` — the API's JSON dict, plus
    ``credits_cost`` and ``credits_remaining``. Failures raise
    :class:`EdgrapiError`, or its subclasses :class:`OutOfCredits` (402) and
    :class:`RateLimited` (429).
    """

    def __init__(self, api_key=None, base_url=DEFAULT_BASE, timeout=30, retries=2):
        key = api_key or os.environ.get("EDGRAPI_KEY")
        if not key:
            raise ValueError(
                "No API key. Pass Client('edgr_...') or set EDGRAPI_KEY. "
                "Free key, no card: https://edgrapi.com/app"
            )
        self.api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self._headers = {
            "X-API-Key": key,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "edgrapi-python/%s" % __version__,
        }

    def __repr__(self):
        return "Client(base_url=%r, key=%s…)" % (self.base_url, self.api_key[:9])

    def get(self, path, **params):
        """Call any ``/v1`` path directly. Useful for endpoints added after this
        release — the named methods below are thin wrappers over this."""
        return request(build_url(self.base_url, path, params), self._headers,
                       timeout=self.timeout, retries=self.retries)

    # ── company, filings, identity ────────────────────────────────────────
    def company(self, ticker):
        """Profile for a ticker: CIK, legal name, SIC industry, fiscal-year end."""
        return self.get("/v1/company/%s" % _seg(ticker))

    def filings(self, ticker, form=None, limit=None):
        """Filings for a company, newest first. ``form`` filters (10-K, 8-K, 4)."""
        return self.get("/v1/filings/%s" % _seg(ticker), form=form, limit=limit)

    def resolve(self, ticker=None, cik=None, cusip=None):
        """Resolve any one of ticker / CIK / CUSIP to the others."""
        return self.get("/v1/resolve", ticker=ticker, cik=cik, cusip=cusip)

    def subsidiaries(self, ident):
        """Subsidiaries disclosed in the 10-K's Exhibit 21."""
        return self.get("/v1/subsidiaries/%s" % _seg(ident))

    # ── financials ────────────────────────────────────────────────────────
    def fundamentals(self, ticker, period=None, limit=None):
        """Income statement, balance sheet and cash flow, normalized from XBRL.
        ``period`` is ``'annual'`` or ``'quarterly'``."""
        return self.get("/v1/fundamentals/%s" % _seg(ticker), period=period, limit=limit)

    def ratios(self, ticker):
        """Margins, returns, leverage and liquidity, derived from fundamentals.
        Price-based ratios are absent by design — EDGAR carries no market price."""
        return self.get("/v1/ratios/%s" % _seg(ticker))

    def xbrl(self, ident, period=None, limit=None, concept=None):
        """Raw XBRL as JSON. ``concept`` narrows to a single tag."""
        return self.get("/v1/xbrl/%s" % _seg(ident), period=period, limit=limit, concept=concept)

    def xbrl_by_accession(self, accession):
        """XBRL for one specific filing, by accession number."""
        return self.get("/v1/xbrl/by-accession/%s" % _seg(accession))

    def shares(self, ticker, history=None):
        """Shares outstanding and public float. ``history=True`` for the series."""
        return self.get("/v1/shares/%s" % _seg(ticker), history=history)

    def sections(self, ticker, form=None, item=None):
        """Narrative sections of a 10-K/10-Q — risk factors, MD&A, business."""
        return self.get("/v1/sections/%s" % _seg(ticker), form=form, item=item)

    # ── insider activity ──────────────────────────────────────────────────
    def insider(self, ticker, limit=None, form=None, min_value=None, days=None,
                min_insiders=None):
        """Form 4 transactions. Code P is an open-market purchase — someone
        spending their own money — as opposed to a pre-scheduled 10b5-1 sale."""
        return self.get("/v1/insider/%s" % _seg(ticker), limit=limit, form=form,
                        min_value=min_value, days=days, min_insiders=min_insiders)

    def clusters(self, days=None, min_insiders=None, min_value=None, limit=None):
        """Market-wide cluster buys: several insiders at the same company buying
        inside one window. One insider buying can be routine; three usually isn't."""
        return self.get("/v1/insider/clusters", days=days, min_insiders=min_insiders,
                        min_value=min_value, limit=limit)

    def form144(self, ticker, limit=None):
        """Form 144 notices of proposed sale."""
        return self.get("/v1/form144/%s" % _seg(ticker), limit=limit)

    # ── events & ownership ────────────────────────────────────────────────
    def events(self, ticker, limit=None, notable=None, item=None):
        """8-K material events, typed by item code. ``notable=True`` drops routine ones."""
        return self.get("/v1/events/%s" % _seg(ticker), limit=limit, notable=notable, item=item)

    def restatements(self, limit=None, days=None):
        """Market-wide feed of restatements (Item 4.02)."""
        return self.get("/v1/events/restatements", limit=limit, days=days)

    def auditor_changes(self, limit=None, days=None):
        """Market-wide feed of auditor changes (Item 4.01)."""
        return self.get("/v1/events/auditor-changes", limit=limit, days=days)

    def activist(self, identifier="latest", activist_only=None, min_percent=None, limit=None):
        """13D/13G stakes above 5%. Pass a ticker, or ``'latest'`` for the
        market-wide feed. ``activist_only=True`` keeps 13D (activist intent)
        and drops 13G (passive)."""
        return self.get("/v1/activist/%s" % _seg(identifier), activist_only=activist_only,
                        min_percent=min_percent, limit=limit)

    def holdings(self, identifier, limit=None, changes=None):
        """13F fund holdings, aggregated by CUSIP across sub-managers, put/call
        flagged, and diffed against the prior quarter so you get what changed
        rather than one quarter's snapshot.

        ``identifier`` takes a fund name (``'berkshire'``), a CIK, or a filer
        ticker. ``changes=True`` returns only positions that moved."""
        return self.get("/v1/holdings/%s" % _seg(identifier), limit=limit, changes=changes)

    # ── private markets & search ──────────────────────────────────────────
    def formd(self, ident="latest", limit=None):
        """Form D private placements. ``'latest'`` for the market-wide feed."""
        return self.get("/v1/formd/%s" % _seg(ident), limit=limit)

    def search(self, q, forms=None, startdt=None, enddt=None, limit=None, offset=None):
        """Full-text search across every filing since 2001."""
        return self.get("/v1/search/fulltext", q=q, forms=forms, startdt=startdt,
                        enddt=enddt, limit=limit, offset=offset)

    def download(self, accession, file=None, cik=None):
        """Fetch a raw filing document from EDGAR by accession number.

        Unlike the other methods this returns a document, not JSON, so read it
        off the response's ``.text`` (or ``.content`` for bytes) rather than as a
        dict::

            doc = c.download("0000320193-25-000079").text
        """
        return self.get("/v1/download", accession=accession, file=file, cik=cik)


def _seg(v):
    """URL-encode one path segment, rejecting empties early with a clear message."""
    import urllib.parse
    s = str(v or "").strip()
    if not s:
        raise ValueError("expected a ticker, CIK or identifier, got an empty value")
    return urllib.parse.quote(s, safe="")
