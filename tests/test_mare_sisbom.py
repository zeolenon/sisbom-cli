"""Read-only tide regressions; requests use httpx.MockTransport, never authentication."""
import datetime as dt
import json
import unittest
from unittest.mock import patch

import httpx

from sisbom_cli.client import SISBOMClient


DAY = "2026-10-03"
URL = "https://sisbom.cbm.rn.gov.br/api/ws/tide_table/2026-10-03"
HEIGHTS = [{"time": "03:01", "height": 0.67}, {"time": "09:31", "height": 1.76}]


class TideTests(unittest.TestCase):
    def query(self, payload, date=DAY, status=200):
        self.requests = []

        def respond(request):
            self.requests.append(request)
            return httpx.Response(status, text=json.dumps(payload))

        with SISBOMClient(api_url="https://example.invalid/graphql") as client:
            client._http.close()
            client._http = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
            with patch.object(client, "_ensure_auth", side_effect=AssertionError("unexpected login")), \
                 patch("sisbom_cli.client.load_token", side_effect=AssertionError("unexpected token read")), \
                 patch("sisbom_cli.client.save_token", side_effect=AssertionError("unexpected token write")), \
                 patch("sisbom_cli.client.get_credentials", side_effect=AssertionError("unexpected credentials")):
                result = client.mare_sisbom(date)
            self.assertEqual(client._api_url, "https://example.invalid/graphql")
        return result

    def test_exact_day_and_public_route_contract(self):
        result = self.query([
            {"date": "2026-10-04", "heights": [{"time": "04:42", "height": 0.7}]},
            {"date": DAY, "heights": HEIGHTS},
            {"date": "2026-10-02", "heights": [{"time": "01:42", "height": 0.53}]},
        ])
        self.assertEqual(result["date"], DAY)
        self.assertEqual(result["heights"], HEIGHTS)
        self.assertEqual(result["location"], "Natal/RN")
        self.assertEqual(result["timezone"], "America/Fortaleza")
        self.assertEqual(str(self.requests[0].url), URL)
        self.assertEqual(self.requests[0].method, "GET")
        self.assertNotIn("authorization", self.requests[0].headers)
        self.assertNotIn("cookie", self.requests[0].headers)

    def test_default_date_is_brt_even_when_utc_is_next_day(self):
        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 4, 1, 30, tzinfo=dt.timezone.utc).astimezone(tz)

        with patch("datetime.datetime", FrozenDateTime):
            result = self.query([{"date": DAY, "heights": HEIGHTS}], date=None)
        self.assertEqual(result["date"], DAY)
        self.assertEqual(str(self.requests[0].url), URL)

    def test_missing_wrong_empty_duplicate_days_are_explicit_failures(self):
        for payload in [
            [{"date": "2026-10-02", "heights": HEIGHTS}],
            [{"heights": HEIGHTS}],
            [],
            [{"date": DAY, "heights": []}],
            [{"date": DAY}],
            [{"date": DAY, "heights": HEIGHTS}] * 2,
            {"date": DAY, "heights": HEIGHTS},
        ]:
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                self.query(payload)

    def test_404_is_explicit(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            self.query({}, status=404)

    def test_invalid_dates_fail_before_request(self):
        for date in ["", "20261003", "03/10/2026", "2026-02-30"]:
            with self.subTest(date=date), self.assertRaises(ValueError):
                self.query([], date=date)
            self.assertEqual(self.requests, [])

    def test_times_and_heights_must_be_valid(self):
        for entry in [
            {"time": "24:01", "height": 0.7},
            {"time": "03:61", "height": 0.7},
            {"time": "3:01", "height": 0.7},
            {"time": "03:01", "height": "0.7m"},
            {"time": "03:01", "height": True},
            {"time": "03:01", "height": float("nan")},
            {"time": "03:01", "height": float("inf")},
            {"time": "03:01"},
            "bad row",
        ]:
            with self.subTest(entry=entry), self.assertRaises(RuntimeError):
                self.query([{"date": DAY, "heights": [entry]}])


if __name__ == "__main__":
    unittest.main()
