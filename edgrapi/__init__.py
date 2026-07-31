# -*- coding: utf-8 -*-
"""edgrapi — a tiny Python client for the Edgrapi SEC EDGAR data API.

Parsed SEC filings as clean JSON: company financials, insider trades (Form 4),
8-K events, 13F fund holdings, and 13D/13G activist stakes. No LLM in the data
path — every value is lifted straight from the filing, so you can verify any
number on EDGAR yourself.

Get a free API key (100 calls/month) at https://edgrapi.com.

    from edgrapi import Client
    c = Client("your_key")
    c.fundamentals("AAPL")     # income statement, balance sheet, cash flow
    c.insider("AAPL")          # Form 4 trades, scored buy vs sell
    c.events("AAPL")           # 8-K events, item-coded
    c.holdings("berkshire")    # 13F holdings, diffed vs last quarter
"""
import urllib.parse

import requests

__version__ = "0.1.0"
__all__ = ["Client", "EdgrapiError"]

DEFAULT_BASE = "https://api.edgrapi.com"


class EdgrapiError(Exception):
    """Raised when the API returns a non-2xx status. Carries the HTTP status and
    the server's error detail so you can act on it (e.g. 401 = bad key, 402/429 =
    out of credits, 404 = unknown ticker)."""

    def __init__(self, status, detail):
        self.status = status
        self.detail = detail
        super().__init__("Edgrapi %s: %s" % (status, detail))


class Client:
    """Client for the Edgrapi SEC-data API.

    Args:
        api_key: your key from https://edgrapi.com (free tier available).
        base_url: override the API host (defaults to https://api.edgrapi.com).
        timeout: per-request timeout in seconds.
        session: an existing ``requests.Session`` to reuse, if you want.

    Every method returns the parsed JSON body as a dict. Failed calls raise
    ``EdgrapiError``. The exact credit cost of a call is returned by the API in
    the ``X-Credits-Cost`` response header; the balance in ``X-Credits-Remaining``.
    """

    def __init__(self, api_key, base_url=DEFAULT_BASE, timeout=30, session=None):
        if not api_key:
            raise ValueError("api_key is required — get a free one at https://edgrapi.com")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._s = session or requests.Session()
        self._s.headers.update({
            "X-API-Key": api_key,
            "User-Agent": "edgrapi-python/%s" % __version__,
            "Accept": "application/json",
        })

    # ---- internals ----
    @staticmethod
    def _enc(v):
        return urllib.parse.quote(str(v).strip(), safe="")

    def _get(self, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        resp = self._s.get(self.base_url + path, params=params, timeout=self.timeout)
        if resp.status_code >= 400:
            detail = resp.text
            try:
                body = resp.json()
                detail = body.get("detail") or body.get("error") or detail
            except ValueError:
                pass
            raise EdgrapiError(resp.status_code, detail)
        return resp.json()

    # ---- company & filings ----
    def company(self, ticker):
        """Company profile and CIK for a ticker."""
        return self._get("/v1/company/%s" % self._enc(ticker))

    def filings(self, ticker, form=None, limit=None):
        """Recent SEC filings for a company, optionally filtered by ``form``."""
        return self._get("/v1/filings/%s" % self._enc(ticker), form=form, limit=limit)

    # ---- financials ----
    def fundamentals(self, ticker, period=None, limit=None):
        """Income statement, balance sheet and cash flow, normalized from XBRL.
        ``period`` is 'annual' or 'quarterly'."""
        return self._get("/v1/fundamentals/%s" % self._enc(ticker), period=period, limit=limit)

    def ratios(self, ticker):
        """Computed financial ratios for a company."""
        return self._get("/v1/ratios/%s" % self._enc(ticker))

    def sections(self, ticker, form=None):
        """Extracted 10-K / 10-Q sections (business, risk factors, MD&A, ...)."""
        return self._get("/v1/sections/%s" % self._enc(ticker), form=form)

    # ---- insider, events & ownership ----
    def insider(self, ticker, limit=None, form=None):
        """Form 4 insider transactions, scored buy vs sell (code P = open-market buy)."""
        return self._get("/v1/insider/%s" % self._enc(ticker), limit=limit, form=form)

    def events(self, ticker, limit=None, notable=None):
        """8-K material events with item codes; ``notable=True`` skips routine ones."""
        return self._get("/v1/events/%s" % self._enc(ticker), limit=limit, notable=notable)

    def activist(self, identifier, limit=None):
        """13D / 13G activist stakes for a company (ticker or CIK)."""
        return self._get("/v1/activist/%s" % self._enc(identifier), limit=limit)

    def holdings(self, identifier, limit=None, changes=None):
        """13F fund holdings, diffed against the prior quarter. ``identifier`` can be
        a famous-fund alias (e.g. 'berkshire'), a manager name, or a CIK."""
        return self._get("/v1/holdings/%s" % self._enc(identifier), limit=limit, changes=changes)
