import hashlib
import json
from pathlib import Path

import httpx
import unittest
import tempfile
from unittest.mock import patch

from sisbom_cli.commands import repositorio as ri


def item(tmp_path):
    content = b"%PDF-1.7\nfixture\n%%EOF"
    (tmp_path / "manual.pdf").write_bytes(content)
    return {"id_fonte": "source-1", "tipo": "manual", "nome_proposto": "Manual SISBOM — Guia",
            "tema": "Mapeamento de Processos", "arquivo_local": "manual.pdf",
            "sha256": hashlib.sha256(content).hexdigest(), "text_sha256": "text1"}


class RepositoryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_cached_auth_failure_never_calls_network_or_login(self):
        requests = []
        c = ri.RepositoryClient(httpx.MockTransport(lambda r: requests.append(r)))
        with patch.object(ri, "load_token", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Sessão canônica"):
                c.require_cached_auth()
        assert requests == []
        c.close()


    def test_pdf_hash_size_and_unknown_dates(self):
        tmp_path = self.root
        source = item(tmp_path)
        path, sha, payload, key = ri.validate_item(source, tmp_path)
        assert payload["status_doc"] == "pendente"
        assert "data_manual" not in payload
        source["ano_edicao"] = 2026
        assert "data_manual" not in ri.validate_item(source, tmp_path)[2]
        path.write_bytes(b"<html>erro</html>")
        with self.assertRaisesRegex(RuntimeError, "PDF"):
            ri.validate_item(source, tmp_path)


    def test_all_status_dedup_and_changed_catalog_stop(self):
        tmp_path = self.root
        source = item(tmp_path)
        sha = source["sha256"]
        for status in ["aprovado", "pendente", "reprovado"]:
            row = {"_id": "old", "url": "url", "status_doc": status, "nome": "Outro título"}
            baseline = [{"source": "Repositorio", **row, "sha256": sha}]
            with self.assertRaisesRegex(RuntimeError, "Correspondência"):
                ri.check_catalog([row], baseline, source, sha)
        with self.assertRaisesRegex(RuntimeError, "Catálogo mudou"):
            ri.check_catalog([{"_id": "new", "url": "new"}], [], source, sha)
        with self.assertRaisesRegex(RuntimeError, "não retornaram"):
            ri.check_catalog([], [{"source": "Repositorio", "_id": "old"}], source, sha)


    def test_bulletins_excluded_and_dates_not_invented(self):
        tmp_path = self.root
        source = item(tmp_path)
        source["nome_proposto"] = "Manual BG 129"
        with self.assertRaisesRegex(RuntimeError, "Boletins"):
            ri.validate_item(source, tmp_path)
        source["nome_proposto"] = "Manual Guia"
        source["data_manual"] = "2026"
        with self.assertRaisesRegex(RuntimeError, "YYYY-MM"):
            ri.validate_item(source, tmp_path)


    def test_success_pending_file_and_id_verified_then_idempotent(self):
        tmp_path = self.root
        source = item(tmp_path)
        journal = tmp_path / "journal.json"
        calls = []
        rows = []
        url = "https://storage.cbm.rn.gov.br/v0/repositorio/manual/x.pdf"
        def handler(request):
            calls.append((request.method, str(request.url)))
            if str(request.url) == ri.UPLOAD:
                assert b'name="arquivo"' in request.content
                assert b'manual-mapeamento-de-processos' in request.content
                return httpx.Response(200, json={"url": url})
            if request.method == "GET":
                return httpx.Response(200, content=(tmp_path / "manual.pdf").read_bytes())
            body = json.loads(request.content)
            if "mutation" in body["query"]:
                payload = body["variables"]["input"]
                assert payload["status_doc"] == "pendente"
                assert "data_manual" not in payload
                rows.append({"_id": "new-id", **payload})
                return httpx.Response(200, json={"data": {"CreateRepositorio": {"status": "success"}}})
            return httpx.Response(200, json={"data": {"Repositorio": rows}})
        c = ri.RepositoryClient(httpx.MockTransport(handler))
        result = ri.register(c, source, tmp_path, [], journal, "Nome confirmado")
        assert result["id"] == "new-id" and result["status_doc"] == "pendente"
        result2 = ri.register(c, source, tmp_path, [], journal, "Nome confirmado")
        assert result2["idempotente"]
        assert sum(url == ri.UPLOAD for _, url in calls) == 1
        assert sum(method == "POST" and url == ri.API for method, url in calls) == 4
        c.close()


    def test_timeout_has_durable_intent_and_never_reuploads(self):
        tmp_path = self.root
        source = item(tmp_path)
        journal = tmp_path / "journal.json"
        calls = []
        def handler(request):
            calls.append(str(request.url))
            if str(request.url) == ri.UPLOAD:
                raise httpx.ReadTimeout("uncertain")
            return httpx.Response(200, json={"data": {"Repositorio": []}})
        c = ri.RepositoryClient(httpx.MockTransport(handler))
        with self.assertRaisesRegex(RuntimeError, "não concluído"):
            ri.register(c, source, tmp_path, [], journal, "Nome")
        saved = next(iter(json.loads(journal.read_text())["operacoes"].values()))
        assert saved["fase"] == "upload_iniciado" and saved["necessita_reconciliacao"]
        with self.assertRaisesRegex(RuntimeError, "anterior"):
            ri.register(c, source, tmp_path, [], journal, "Nome")
        assert calls.count(ri.UPLOAD) == 1
        c.close()


    def test_status_or_remote_hash_divergence_blocks_next_item(self):
        tmp_path = self.root
        source = item(tmp_path)
        _, sha, payload, key = ri.validate_item(source, tmp_path)
        url = "https://storage.cbm.rn.gov.br/v0/x.pdf"
        c = ri.RepositoryClient(httpx.MockTransport(lambda r: httpx.Response(200, content=b"%PDF-other")))
        entry = {"payload": payload, "url": url, "sha256": sha}
        for status in ["aprovado", "pendente"]:
            with self.assertRaisesRegex(RuntimeError, "diverge"):
                ri.reconcile(c, entry, [{"_id": "id", **payload, "url": url, "status_doc": status}])
        c.close()

    def test_queue_exhaustion_and_total_drift(self):
        ids = [f"00000000-0000-0000-0000-{i:012d}" for i in range(216)]
        calls = []
        def handler(request):
            start = int(request.url.params['start'])
            calls.append(start)
            rows = [{'_id': x} for x in ids[start:start+100]]
            return httpx.Response(200, json={'recordsTotal': 216, 'recordsFiltered': 216, 'data': rows})
        c = ri.RepositoryClient(httpx.MockTransport(handler))
        with patch.object(ri, 'load_token', return_value='test-cache'):
            result = c.queue()
        assert result['exaurido'] and [p['quantidade'] for p in result['paginas']] == [100,100,16]
        assert calls == [0,100,200]
        c.close()
        def drift(request):
            start = int(request.url.params['start'])
            total = 216 if start == 0 else 217
            return httpx.Response(200,json={'recordsTotal':total,'recordsFiltered':total,'data':[{'_id':x} for x in ids[start:start+100]]})
        c = ri.RepositoryClient(httpx.MockTransport(drift))
        with patch.object(ri, 'load_token', return_value='test-cache'):
            with self.assertRaisesRegex(RuntimeError,'mudou'):
                c.queue()
        c.close()


if __name__ == "__main__":
    unittest.main()
