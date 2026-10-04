"""Offline checks for duplicate protection and uncertain HTTP writes."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from sisbom_cli.sisdo import BASE_URL, Form, SISDOClient, parse_orders


def order_html() -> str:
    return '''<div id="heading99"><span>OP nº 123 na Local
      Unidade Lançamento: Unidade</span></div><div id="collapse99">
      <label>Data Início:</label><p>30/10/2026 07:00</p>
      <label>Cidade:</label><p>Apodi</p>
      <label>Tipo Operação:</label><p>Ref. GU</p>
      <label>Qtd de Vagas:</label><p>0</p>
      <table><tr><td>Ord</td><td>Matrícula</td><td>Posto</td><td>Nome</td></tr>
      <tr><td>1</td><td>111.111-1</td><td>SD</td><td>TESTE</td></tr></table>
      <form method="post" action="/sisdo/99/op/editar">
      <input name="_token" value="private-csrf">
      <input name="st_obs99" value="Teste"></form></div>'''


def vacant_html() -> str:
    html = order_html().replace('<label>Qtd de Vagas:</label><p>0</p>', '<label>Qtd de Vagas:</label><p>2</p>')
    html = html.replace("<table>", "<label>Status:</label><p>Digitado</p><table>")
    return html + '''
      <form method="post" action="/sisdo/99/op/inserirefetivo">
      <input name="_token" value="private-csrf">
      <input name="st_matricula_efetivo99"><input name="st_policial_efetivo99"></form>'''


class SISDOTests(unittest.TestCase):
    def test_listing_keeps_printed_number_separate_and_omits_csrf(self) -> None:
        order = parse_orders(order_html())[0]
        self.assertEqual((order["id"], order["numero"]), (99, "123"))
        self.assertEqual(order["militares"], [{"matricula": "111.111-1", "posto": "SD", "nome": "TESTE"}])
        self.assertNotIn("private-csrf", str(order))

    def test_does_not_follow_mutating_get_after_post(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.method)
            return httpx.Response(302, headers={"location": "/sisdo/99/op/publicar"})

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaisesRegex(RuntimeError, "Redirecionamento inesperado"):
                client._request("POST", "/sisdo/op/criar", data={"x": "y"})
        self.assertEqual(calls, ["POST"])

    def test_timeout_is_not_retried_and_does_not_expose_ticket(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.method)
            raise httpx.ReadTimeout(f"Secret URL {req.url}", request=req)

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaises(RuntimeError) as caught:
                client._request("POST", "/sisdo/op/criar?ticket=private-ticket", data={"x": "y"})
        self.assertEqual(calls, ["POST"])
        self.assertNotIn("private-ticket", str(caught.exception))

    def test_foreign_redirect_does_not_receive_cookie(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.url.host)
            return httpx.Response(302, headers={"location": "https://example.org/home"})

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server), cookies={"sisdo_session": "private"})) as client:
            with self.assertRaises(RuntimeError):
                client._request("GET", "/home")
        self.assertEqual(calls, ["sisdo.cbm.rn.gov.br"])

    def test_success_status_without_new_order_is_not_success(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.method)
            return httpx.Response(200, text="Validation failed")

        fields = {"st_obs": "Teste"}
        form = Form(BASE_URL + "/sisdo/op/criar", "post", {"_token": "private"})
        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with patch.object(client, "prepare_create", return_value=(form, {"unidade_lancamento": "Unidade"})):
                with patch.object(client, "list_orders", return_value=[]):
                    with self.assertRaisesRegex(RuntimeError, "não foi confirmada"):
                        client.create(fields)
        self.assertEqual(calls, ["POST"])

    def test_wrong_printed_number_never_sends_insertion(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.method)
            return httpx.Response(200, text=vacant_html())

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaisesRegex(RuntimeError, "ID/número"):
                client.insert(99, "456", "2222222", "SEGUNDO", executar=True)
        self.assertEqual(calls, ["GET"])

    def test_already_present_matricula_is_not_inserted_twice(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.method)
            return httpx.Response(200, text=vacant_html())

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaisesRegex(RuntimeError, "já está"):
                client.insert(99, "123", "111.111-1", "TESTE", executar=True)
        self.assertEqual(calls, ["GET"])

    def test_insertion_success_requires_server_readback(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append((req.method, req.url.path))
            if req.url.path == "/getpolicialrelatorio":
                return httpx.Response(200, text="SD SEGUNDO")
            return httpx.Response(200, text=vacant_html())

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaisesRegex(RuntimeError, "não foi confirmado"):
                client.insert(99, "123", "2222222", "SEGUNDO", executar=True)
        self.assertEqual([p for m, p in calls if m == "POST"], ["/sisdo/99/op/inserirefetivo"])

    def test_name_mismatch_never_sends_insertion(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.method)
            return httpx.Response(200, text="SD OUTRO" if req.url.path == "/getpolicialrelatorio" else vacant_html())

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaisesRegex(RuntimeError, "nome esperado"):
                client.insert(99, "123", "2222222", "SEGUNDO", executar=True)
        self.assertNotIn("POST", calls)

    def test_rejected_initial_ticket_can_be_replaced_before_any_write(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append((req.method, req.url.path))
            if req.url.path == "/":
                if req.url.params["ticket"] == "first":
                    return httpx.Response(302, headers={"location": "/login"})
                return httpx.Response(302, headers={"location": "/home", "set-cookie": "sisdo_session=private; Path=/"})
            return httpx.Response(200, text="home")

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            client._authenticated = False
            with patch("sisbom_cli.sisdo.SISBOMClient") as sisbom:
                gql = sisbom.return_value.__enter__.return_value._gql
                gql.side_effect = [{"CreateSsoTicket": {"token": "first"}}, {"CreateSsoTicket": {"token": "second"}}]
                client.connect()
                self.assertEqual(gql.call_count, 2)
        self.assertEqual(calls, [("GET", "/"), ("GET", "/"), ("GET", "/home")])

    def test_login_redirect_after_post_does_not_replay_write(self) -> None:
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.method)
            return httpx.Response(302, headers={"location": "/login"})

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaises(RuntimeError):
                client._request("POST", "/sisdo/op/criar", data={"x": "y"})
        self.assertEqual(calls, ["POST"])

    def test_vacancy_reduction_targets_only_a_current_empty_row(self) -> None:
        occupied = '<tr><td>1</td><td>1111111</td><td>SD</td><td>TESTE</td></tr>'
        blank = lambda n: f'<tr><td>{n}</td><td></td><td></td><td></td><td><a href="/sisdo/99/op/{n}/vaga/excluir">Lixeira</a></td></tr>'
        html = vacant_html().replace(occupied, occupied)
        html = html.replace('</table>', blank(801) + blank(802) + '</table>')
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            nonlocal html
            calls.append(req.url.path)
            if req.url.path == "/sisdo/99/op/802/vaga/excluir":
                html = html.replace(blank(802), '').replace('<label>Qtd de Vagas:</label><p>2</p>', '<label>Qtd de Vagas:</label><p>1</p>')
                return httpx.Response(302, headers={"location": "/sisdo/op/listar/digitadas"})
            return httpx.Response(200, text=html)

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            result = client.reduce_vacancies(99, "123", 2, executar=True)
        self.assertEqual(len(result["vagas_vazias"]), 1)
        self.assertEqual(len(result["militares"]), 1)
        self.assertEqual([p for p in calls if p.endswith("vaga/excluir")], ["/sisdo/99/op/802/vaga/excluir"])

    def test_vacancy_occupied_after_preview_is_not_deleted(self) -> None:
        blank = '<tr><td>2</td><td></td><td></td><td></td><td><a href="/sisdo/99/op/802/vaga/excluir">Lixeira</a></td></tr>'
        before = vacant_html().replace('<p>2</p>', '<p>1</p>').replace('</table>', blank + '</table>')
        after = before.replace(blank, '<tr><td>2</td><td>2222222</td><td>SD</td><td>SEGUNDO</td></tr>').replace('<label>Qtd de Vagas:</label><p>1</p>', '<label>Qtd de Vagas:</label><p>0</p>')
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            calls.append(req.url.path)
            return httpx.Response(200, text=before if len(calls) == 1 else after)

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaisesRegex(RuntimeError, "mudou durante"):
                client.reduce_vacancies(99, "123", 1, executar=True)
        self.assertFalse(any(p.endswith("vaga/excluir") for p in calls))

    def test_personnel_removal_uses_form_record_and_keeps_a_vacancy(self) -> None:
        html = vacant_html().replace('<label>Qtd de Vagas:</label><p>2</p>', '<label>Qtd de Vagas:</label><p>0</p>')
        html = html.replace('<td>TESTE</td>', '<td>TESTE <a data-target="#modalFuncao501"></a></td>')
        html += '<form method="post" action="/sisdo/99/op/501/efetivo/excluir"><input name="_token" value="private"><textarea name="justificativa" maxlength="1000" required></textarea></form>'
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            nonlocal html
            calls.append((req.method, req.url.path))
            if req.method == "POST":
                html = html.replace('<td>111.111-1</td><td>SD</td><td>TESTE <a data-target="#modalFuncao501"></a></td>', '<td></td><td></td><td><a href="/sisdo/99/op/501/vaga/excluir">Lixeira</a></td>')
                html = html.replace('<label>Qtd de Vagas:</label><p>0</p>', '<label>Qtd de Vagas:</label><p>1</p>')
            return httpx.Response(200, text=html)

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            result = client.remove(99, "123", "1111111", "TESTE", "Permuta autorizada de teste", executar=True)
        self.assertFalse(result["militares"])
        self.assertEqual(len(result["vagas_vazias"]), 1)
        self.assertEqual([p for m, p in calls if m == "POST"], ["/sisdo/99/op/501/efetivo/excluir"])

    def test_print_rejects_html_even_when_http_status_is_success(self) -> None:
        def server(req: httpx.Request) -> httpx.Response:
            if req.url.path.endswith('/impressao'):
                return httpx.Response(200, text='<html>Login</html>')
            return httpx.Response(200, text=order_html() + '<a href="/sisdo/99/op/impressao">Imprimir</a>')
        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            with self.assertRaisesRegex(RuntimeError, "PDF válido"):
                client.print_pdf(99, "123")

    def test_add_vacancies_keeps_existing_personnel_and_requires_readback(self) -> None:
        html = vacant_html().replace('<label>Qtd de Vagas:</label><p>2</p>', '<label>Qtd de Vagas:</label><p>0</p>')
        html += '<form method="post" action="/sisdo/99/op/maisvagas"><input name="_token" value="private"><input name="st_vagas99" type="number" min="1" max="100"></form>'
        calls = []

        def server(req: httpx.Request) -> httpx.Response:
            nonlocal html
            calls.append((req.method, req.url.path))
            if req.method == "POST":
                rows = ''.join(f'<tr><td>{n}</td><td></td><td></td><td></td><td><a href="/sisdo/99/op/{n}/vaga/excluir">Lixeira</a></td></tr>' for n in (801, 802))
                html = html.replace('</table>', rows + '</table>').replace('<label>Qtd de Vagas:</label><p>0</p>', '<label>Qtd de Vagas:</label><p>2</p>')
            return httpx.Response(200, text=html)

        with SISDOClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            result = client.add_vacancies(99, "123", 2, executar=True)
        self.assertEqual(len(result["militares"]), 1)
        self.assertEqual(len(result["vagas_vazias"]), 2)
        self.assertEqual([p for m, p in calls if m == "POST"], ["/sisdo/99/op/maisvagas"])


if __name__ == "__main__":
    unittest.main()
