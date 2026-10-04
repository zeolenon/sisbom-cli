"""Catalog and download behavior with mock public HTTP, no login or delivery."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from sisbom_cli.client import SISBOMClient


DOCS = [
    {"_id": "2026_BG 182", "bg_num": "BG 182", "year": "2026", "url": "https://example.test/bg182.pdf", "date_ref": "1790910000000"},
    {"_id": "2026_181", "bg_num": "181", "year": "2026", "url": "https://example.test/bg181.pdf"},
    {"_id": "2026_ADIT_182", "bg_num": "ADITAMENTO AO BGCB Nº 182", "year": "2026", "url": "https://example.test/adit.pdf"},
]


class BulletinTests(unittest.TestCase):
    def client(self):
        def respond(request):
            if request.method == "POST":
                variables = json.loads(request.content).get("variables", {})
                docs = DOCS
                if "bg_num" in variables:
                    docs = [d for d in docs if d["bg_num"] == variables["bg_num"]]
                return httpx.Response(200, json={"data": {"Docs": docs}})
            return httpx.Response(200, content=b"%PDF-readonly-test")

        client = SISBOMClient()
        client._http.close()
        client._http = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
        self.addCleanup(client.close)
        for name in ["login", "_ensure_auth"]:
            guard = patch.object(client, name, side_effect=AssertionError("unexpected authentication"))
            guard.start()
            self.addCleanup(guard.stop)
        return client

    def test_public_catalog_normalizes_prefix_and_preserves_source_identity(self):
        docs = self.client().list_bgs(year="2026")
        regular = next(d for d in docs if d["_id"] == "2026_BG 182")
        self.assertEqual(regular["bg_num"], "182")
        self.assertEqual(regular["source_bg_num"], "BG 182")
        self.assertEqual(regular["url"], DOCS[0]["url"])
        self.assertEqual(docs[0]["_id"], "2026_BG 182")

    def test_download_lookup_accepts_numeric_and_source_alias(self):
        client = self.client()
        for number in ["182", "BG 182"]:
            with self.subTest(number=number):
                docs = client.list_bgs(year="2026", bg_num=number)
                self.assertEqual([d["_id"] for d in docs], ["2026_BG 182"])

    def test_addenda_are_never_treated_as_regular_bulletins(self):
        docs = self.client().list_bgs(year="2026")
        adit = next(d for d in docs if d["_id"] == "2026_ADIT_182")
        self.assertEqual(adit["bg_num"], "ADITAMENTO AO BGCB Nº 182")
        self.assertEqual(len(self.client().list_bgs(year="2026", bg_num=adit["bg_num"])), 1)

    def test_download_filename_uses_canonical_regular_number(self):
        with tempfile.TemporaryDirectory(prefix="sisbom-bg-parser-test-") as dest:
            path = self.client().download_bg(DOCS[0], dest_dir=dest)
            self.assertEqual(Path(path).name, "BG_182_2026-10-02.pdf")
            self.assertEqual(Path(path).read_bytes(), b"%PDF-readonly-test")


if __name__ == "__main__":
    unittest.main()
