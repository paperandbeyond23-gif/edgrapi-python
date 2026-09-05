# -*- coding: utf-8 -*-
"""Transport layer: stdlib-only HTTP with retries, so installing edgrapi pulls
in nothing at all.

Kept separate from the client surface so the retry/backoff policy has one home
and can be unit-tested without touching the network.
"""
import gzip
import json as _json
import time
import urllib.error
import urllib.parse
import urllib.request

__all__ = ["EdgrapiError", "RateLimited", "OutOfCredits", "Response", "request"]

# 429 and 5xx are worth retrying; a 4xx that isn't 429 will never succeed on retry.
_RETRY_STATUS = frozenset((429, 500, 502, 503, 504))


class EdgrapiError(Exception):
    """A non-2xx response from the API.

    Carries the HTTP status, the server's ``error`` slug and its human-readable
    ``detail`` so callers can branch on the machine-readable part rather than
    matching on prose.
    """

    def __init__(self, status, detail, error=None, body=None, request_id=None):
        self.status = status
        self.detail = detail
        self.error = error
        self.body = body or {}
        self.request_id = request_id
        msg = "Edgrapi %s" % status
        if error:
            msg += " (%s)" % error
        if detail:
            msg += ": %s" % detail
        if request_id:
            msg += " [request_id=%s]" % request_id
        super().__init__(msg)


class RateLimited(EdgrapiError):
    """429 — too many requests. ``retry_after`` is seconds, when the server said."""

    def __init__(self, *a, **kw):
        self.retry_after = kw.pop("retry_after", None)
        super().__init__(*a, **kw)


class OutOfCredits(EdgrapiError):
    """402 — the key has no credits left for a call of this weight.

    ``endpoint_cost`` is what the call would have cost. The free tier refills
    monthly; see https://edgrapi.com/pricing.
    """

    def __init__(self, *a, **kw):
        self.endpoint_cost = kw.pop("endpoint_cost", None)
        super().__init__(*a, **kw)


class Response(dict):
    """The decoded JSON body, with billing metadata attached.

    Behaves exactly like the ``dict`` the API returned, so existing code keeps
    working, but also carries what the call cost:

        r = client.insider("AAPL")
        r["count"]          # the data, as before
        r.credits_cost      # what this call was billed
        r.credits_remaining # balance after the call
    """

    credits_cost = None
    credits_remaining = None
    request_id = None
    status = 200
    #: Raw response body. For JSON endpoints this is the JSON text (the dict is
    #: the parsed form); for endpoints that return a document — ``download`` sends
    #: back the raw filing as text/html — the dict is empty and the document is
    #: here. ``content`` is the same body as undecoded bytes.
    text = None
    content = None


def _decode(raw, headers):
    if (headers.get("Content-Encoding") or "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def request(url, headers, timeout=30, retries=2, backoff=0.5, _opener=None):
    """GET ``url`` and return a :class:`Response`.

    Retries 429 and 5xx up to ``retries`` times with exponential backoff,
    honouring ``Retry-After`` when the server sends one. Raises
    :class:`OutOfCredits`, :class:`RateLimited` or :class:`EdgrapiError`.
    """
    opener = _opener or urllib.request.urlopen
    attempt = 0
    while True:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with opener(req, timeout=timeout) as resp:
                raw = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                text = raw.decode("utf-8", "replace")
                ctype = (resp.headers.get("Content-Type") or "").lower()
                # `download` returns a raw filing document (text/html), not JSON;
                # blindly json.loads-ing it would crash on success. Parse JSON by
                # default, but skip it for document content types, and fall back to
                # raw if a body that looked like JSON isn't. Non-JSON bodies live in
                # `.text` / `.content`; a 200 never raises here.
                _is_doc = any(t in ctype for t in
                              ("html", "xml", "text/plain", "octet-stream", "pdf", "csv"))
                if _is_doc:
                    out = Response()
                else:
                    try:
                        out = Response(_json.loads(text) if text.strip() else {})
                    except ValueError:
                        out = Response()
                out.text = text
                out.content = raw
                out.status = resp.status
                out.credits_cost = _int_or_none(resp.headers.get("X-Credits-Cost"))
                out.credits_remaining = _int_or_none(resp.headers.get("X-Credits-Remaining"))
                out.request_id = resp.headers.get("X-Request-Id")
                return out
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                payload = _json.loads(_decode(raw, e.headers) or "{}")
            except ValueError:
                payload = {}
            status = e.code
            detail = payload.get("detail") or payload.get("message") or (raw[:200].decode("utf-8", "replace") if raw else "")
            slug = payload.get("error")
            rid = payload.get("request_id") or e.headers.get("X-Request-Id")

            if status in _RETRY_STATUS and attempt < retries:
                wait = _int_or_none(e.headers.get("Retry-After"))
                time.sleep(wait if wait is not None else backoff * (2 ** attempt))
                attempt += 1
                continue

            if status == 402:
                raise OutOfCredits(status, detail, slug, payload, rid,
                                   endpoint_cost=payload.get("endpoint_cost")) from None
            if status == 429:
                raise RateLimited(status, detail, slug, payload, rid,
                                  retry_after=_int_or_none(e.headers.get("Retry-After"))) from None
            raise EdgrapiError(status, detail, slug, payload, rid) from None
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                attempt += 1
                continue
            raise EdgrapiError(0, "network error: %s" % e.reason) from None


def build_url(base, path, params):
    """Join ``base`` + ``path`` and append the non-``None`` query params."""
    q = {k: v for k, v in params.items() if v is not None}
    for k, v in list(q.items()):
        if isinstance(v, bool):
            q[k] = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            q[k] = ",".join(str(x) for x in v)
    url = base.rstrip("/") + path
    return url + ("?" + urllib.parse.urlencode(q) if q else "")
