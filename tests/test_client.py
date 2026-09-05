# -*- coding: utf-8 -*-
"""Offline tests: no network, no key, no API. They exercise URL building,
the retry policy and error mapping, which is where client bugs actually live.
"""
import io
import json
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, "..")
from edgrapi import Client, EdgrapiError, OutOfCredits, RateLimited  # noqa: E402
from edgrapi._http import build_url, request  # noqa: E402


class FakeResp:
    def __init__(self, body, headers=None, status=200):
        self._b = json.dumps(body).encode()
        self.headers = headers or {}
        self.status = status
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def http_error(code, payload, headers=None):
    return urllib.error.HTTPError(
        "u", code, "err", headers or {}, io.BytesIO(json.dumps(payload).encode()))


class TestUrls(unittest.TestCase):
    def test_drops_none_and_encodes_bools(self):
        u = build_url("https://a.com", "/v1/x", {"a": None, "b": True, "c": False, "d": 3})
        self.assertNotIn("a=", u)
        self.assertIn("b=true", u)
        self.assertIn("c=false", u)
        self.assertIn("d=3", u)

    def test_list_params_are_comma_joined(self):
        u = build_url("https://a.com", "/v1/x", {"forms": ["10-K", "8-K"]})
        self.assertIn("forms=10-K%2C8-K", u)

    def test_path_segments_are_encoded(self):
        c = Client("edgr_test")
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.return_value = FakeResp({"ok": 1})
            c.holdings("berkshire hathaway/x")
        called = m.call_args[0][0].full_url
        self.assertIn("berkshire%20hathaway%2Fx", called)

    def test_empty_identifier_rejected_before_network(self):
        c = Client("edgr_test")
        with self.assertRaises(ValueError):
            c.company("   ")


class TestAuthAndMeta(unittest.TestCase):
    def test_key_from_env(self):
        with mock.patch.dict("os.environ", {"EDGRAPI_KEY": "edgr_env"}):
            self.assertEqual(Client().api_key, "edgr_env")

    def test_missing_key_raises_with_signup_url(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as e:
                Client()
        self.assertIn("edgrapi.com", str(e.exception))

    def test_credit_headers_attach_to_response(self):
        c = Client("edgr_test")
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.return_value = FakeResp(
                {"count": 2},
                {"X-Credits-Cost": "5", "X-Credits-Remaining": "95"})
            r = c.insider("AAPL")
        self.assertEqual(r["count"], 2)
        self.assertEqual(r.credits_cost, 5)
        self.assertEqual(r.credits_remaining, 95)


class TestErrors(unittest.TestCase):
    def test_402_maps_to_out_of_credits_with_cost(self):
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.side_effect = http_error(402, {"error": "out_of_credits", "endpoint_cost": 5})
            with self.assertRaises(OutOfCredits) as e:
                request("https://a.com/v1/x", {}, retries=0)
        self.assertEqual(e.exception.endpoint_cost, 5)
        self.assertEqual(e.exception.status, 402)

    def test_429_maps_to_rate_limited(self):
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.side_effect = http_error(429, {"error": "rate_limited"})
            with self.assertRaises(RateLimited):
                request("https://a.com/v1/x", {}, retries=0)

    def test_404_is_plain_error_and_not_retried(self):
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.side_effect = http_error(404, {"error": "not_found", "detail": "no such ticker"})
            with self.assertRaises(EdgrapiError) as e:
                request("https://a.com/v1/x", {}, retries=3)
        self.assertEqual(m.call_count, 1)          # never retried
        self.assertEqual(e.exception.error, "not_found")

    def test_500_is_retried_then_succeeds(self):
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.side_effect = [http_error(500, {}), FakeResp({"ok": True})]
            with mock.patch("edgrapi._http.time.sleep"):
                out = request("https://a.com/v1/x", {}, retries=2)
        self.assertTrue(out["ok"])
        self.assertEqual(m.call_count, 2)


class TestNonJsonBody(unittest.TestCase):
    """`download` returns a raw filing document, not JSON. A 200 must never crash
    on json.loads, and the document must be reachable on `.text`/`.content`."""

    class RawResp:
        def __init__(self, data, headers): self._d = data; self.headers = headers; self.status = 200
        def read(self): return self._d
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def test_download_returns_raw_document_not_parsed(self):
        html = b"<?xml version='1.0'?>\n<html>filing body</html>"
        c = Client("edgr_test")
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.return_value = self.RawResp(
                html, {"Content-Type": "text/html; charset=utf-8", "X-Credits-Cost": "1"})
            r = c.download("0000320193-25-000079")   # would raise before the fix
        self.assertEqual(r.text, html.decode())      # document on .text
        self.assertEqual(r.content, html)            # raw bytes on .content
        self.assertEqual(dict(r), {})                # not parsed into the dict
        self.assertEqual(r.credits_cost, 1)          # metadata still attached

    def test_json_still_parses_without_content_type(self):
        # regression guard: a JSON body with no Content-Type header must still parse
        c = Client("edgr_test")
        with mock.patch("edgrapi._http.urllib.request.urlopen") as m:
            m.return_value = FakeResp({"count": 3})
            r = c.filings("AAPL")
        self.assertEqual(r["count"], 3)


class TestCli(unittest.TestCase):
    def test_every_command_maps_to_a_real_method(self):
        from edgrapi.cli import COMMANDS
        c = Client("edgr_test")
        for name, (method, _p, _o) in COMMANDS.items():
            self.assertTrue(hasattr(c, method), "%s -> missing %s" % (name, method))


if __name__ == "__main__":
    unittest.main()
