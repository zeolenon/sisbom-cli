import unittest
from unittest.mock import patch
import httpx
from click.testing import CliRunner
from sisbom_cli.voluntariado import VoluntariadoClient, parse_list, parse_profile, plan_profile
from sisbom_cli.commands.voluntariado import standalone


def listing(unit='11662', month='2026-11-01', opened=True, rows=None):
    if rows is None: rows = [('TESTE A','1111111','SD','OUTRA UNIDADE')]
    content = ''.join('<tr>'+''.join('<td>'+c+'</td>' for c in row)+'</tr>' for row in rows)
    if not rows: content = '<tr><td colspan="4">Nenhum voluntário para esta lotação neste ciclo.</td></tr>'
    return f'''<h3>Voluntários para Diária Operacional por Lotação</h3>
    <form action="/sisdo/voluntariado" method="get">
    <select name="lotacao_id"><option selected value="{unit}">Quartel interesse</option></select>
    <select name="mes_referencia"><option selected value="{month}">Ciclo</option></select></form>
    <table><thead><tr><th>Nome</th><th>Matrícula</th><th>Graduação</th><th>Lotação atual</th></tr></thead><tbody>{content}</tbody></table>
    <form action="/sisdo/voluntariado/exportar" method="post"><button {'disabled' if opened else ''}>Exportar / Gerar Lista Definitiva</button></form>'''


def profile(month='novembro', opened=True):
    return f'''<h3>Voluntariado para Diária Operacional — {month}/2026</h3>
    <form action="/usuario/voluntariado" method="post">
    <input type="hidden" name="_token" value="synthetic-test-only">
    <input type="radio" name="bo_voluntario" value="1" checked>
    <input type="radio" name="bo_voluntario" value="0">
    <input type="checkbox" name="lotacoes[]" id="a" value="11662" checked><label for="a">Apodi</label>
    <input type="checkbox" name="lotacoes[]" id="b" value="11660" checked><label for="b">Mossoró</label>
    <input type="checkbox" name="lotacoes[]" id="c" value="11667"><label for="c">Assú</label>
    <button {'disabled' if not opened else ''}>Salvar resposta</button></form>'''


class VolunteerTests(unittest.TestCase):
    def test_canonical_group_registers_commands_and_preserves_os(self):
        from sisbom_cli.commands.sisdo import sisdo
        self.assertTrue({'voluntarios','voluntariado-perfil','voluntariado-prever','listar','escala','criar'} <= sisdo.commands.keys())
        with patch('sisbom_cli.commands.voluntariado.VoluntariadoClient.profile',return_value=parse_profile(profile())):
            result=CliRunner().invoke(sisdo,['voluntariado-perfil'])
        self.assertEqual(result.exit_code,0,result.output)
        self.assertIn('"competencia": "2026-11"',result.output)
    def test_valid_and_unit_distinct_from_current_assignment(self):
        x = parse_list(listing(), '11662', '2026-11')
        self.assertEqual(x['total'],1)
        self.assertEqual(x['militares'][0]['lotacao_atual'],'OUTRA UNIDADE')
        self.assertNotEqual(x['militares'][0]['quartel_interesse'],'OUTRA UNIDADE')
        self.assertEqual(x['situacao'],'provisoria')
    def test_duplicate_normalizes_registration(self):
        rows=[('TESTE','111.111-1','SD','U'),('TESTE','1111111','SD','U')]
        x=parse_list(listing(rows=rows),'11662','2026-11')
        self.assertEqual((x['total'],x['duplicatas_descartadas']),(1,1))
    def test_conflicting_duplicate_fails(self):
        with self.assertRaises(RuntimeError):
            parse_list(listing(rows=[('A','1111111','SD','U'),('B','1111111','SD','U')]),'11662','2026-11')
    def test_closed_and_empty(self):
        x=parse_list(listing(opened=False,rows=[]),'11662','2026-11')
        self.assertEqual((x['situacao'],x['total']),('definitiva_disponivel',0))
        self.assertFalse(x['lista_definitiva_gerada'])
    def test_errors_never_become_zero(self):
        for html in ('login','<h3>Voluntários para Diária Operacional por Lotação</h3>', listing(month='2026-10-01'), listing().replace('<tbody>','<tbody><tr><td>erro</td></tr>')):
            with self.subTest(html=html[:30]),self.assertRaises(RuntimeError): parse_list(html,'11662','2026-11')
    def test_pagination_fails_instead_of_partial_data(self):
        with self.assertRaisesRegex(RuntimeError,'Paginação'):
            parse_list(listing()+'<a href="/sisdo/voluntariado?page=2">2</a>','11662','2026-11')
    def test_multiple_units_preserved_and_total_deduped(self):
        calls=[]
        def server(req):
            calls.append(req)
            return httpx.Response(200,text=listing(unit=req.url.params['lotacao_id']))
        with VoluntariadoClient(httpx.Client(transport=httpx.MockTransport(server))) as client:
            x=client.list_volunteers('2026-11',['apodi','mossoro','apodi'])
        self.assertEqual((len(calls),x['total_vinculos'],x['total_militares']),(2,2,1))
        self.assertTrue(all(r.method=='GET' for r in calls))
    def test_session_redirect_fails(self):
        with VoluntariadoClient(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={'location':'/login'})))) as c:
            with self.assertRaises(RuntimeError): c.list_volunteers('2026-11',['apodi'])
    def test_http_error_and_timeout_fail(self):
        for code in (403,500):
            with VoluntariadoClient(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(code)))) as c:
                with self.assertRaises(RuntimeError): c.list_volunteers('2026-11',['apodi'])
        def timeout(req): raise httpx.ReadTimeout('hidden',request=req)
        with VoluntariadoClient(httpx.Client(transport=httpx.MockTransport(timeout))) as c:
            with self.assertRaises(RuntimeError): c.profile()
    def test_missing_cached_token_does_not_login(self):
        with patch('sisbom_cli.voluntariado.load_token',return_value=None),patch('sisbom_cli.voluntariado.SISBOMClient.login') as login:
            with VoluntariadoClient() as c:
                with self.assertRaisesRegex(RuntimeError,'Nenhuma renovação'): c.profile()
            login.assert_not_called()
    def test_rejected_cached_token_does_not_refresh_or_leak(self):
        with patch('sisbom_cli.voluntariado.load_token',return_value='synthetic'),patch('sisbom_cli.voluntariado.SISBOMClient._gql_raw',side_effect=RuntimeError('private')),patch('sisbom_cli.voluntariado.SISBOMClient.login') as login:
            with VoluntariadoClient() as c:
                with self.assertRaises(RuntimeError) as err:c.profile()
            self.assertNotIn('private',str(err.exception)); login.assert_not_called()
    def test_profile_two_units_and_no_token(self):
        x=parse_profile(profile())
        self.assertEqual(x['quarteis'],['11660','11662'])
        self.assertEqual(x['competencia'],'2026-11')
        self.assertNotIn('synthetic-test-only',str(x))
    def test_addition_preserves_two_existing_units(self):
        x=plan_profile(parse_profile(profile()),'2026-11',['11667'],'adicionar')
        self.assertEqual(x['depois'],['11660','11662','11667'])
        self.assertEqual(x['removidos'],[]); self.assertFalse(x['envio_habilitado'])
    def test_removal_and_replacement_require_explicit_preview_flag(self):
        for mode in ('remover','substituir'):
            with self.assertRaises(ValueError):plan_profile(parse_profile(profile()),'2026-11',['11662'],mode)
        x=plan_profile(parse_profile(profile()),'2026-11',['11662'],'substituir',True)
        self.assertEqual(x['removidos'],['11660'])
    def test_wrong_competence_closed_unknown_and_empty_destination(self):
        for month,units,mode,current in [('2026-10',['11662'],'adicionar',profile()),('2026-11',['999'],'adicionar',profile()),('2026-11',['11662'],'adicionar',profile(opened=False)),('2026-11',['11660','11662'],'remover',profile())]:
            with self.assertRaises((RuntimeError,ValueError)):plan_profile(parse_profile(current),month,units,mode,True)
    def test_cli_error_is_nonzero_without_empty_json(self):
        with patch('sisbom_cli.commands.voluntariado.VoluntariadoClient.list_volunteers',side_effect=RuntimeError('Sessão expirada')):
            x=CliRunner().invoke(standalone,['voluntarios','--competencia','2026-11','--quartel','apodi','--json'])
        self.assertNotEqual(x.exit_code,0); self.assertNotIn('"total": 0',x.output)
    def test_cli_preview_never_posts(self):
        with patch('sisbom_cli.commands.voluntariado.VoluntariadoClient.profile',return_value=parse_profile(profile())),patch('sisbom_cli.voluntariado.VoluntariadoClient._request') as request:
            x=CliRunner().invoke(standalone,['voluntariado-prever','--competencia','2026-11','--quartel','assu'])
        self.assertEqual(x.exit_code,0,x.output); request.assert_not_called()
        self.assertIn('"executado": false',x.output)

if __name__=='__main__':unittest.main()

class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.diary = Path(self.temp.name) / 'inscricao.json'

    def client(self, handler):
        return VoluntariadoClient(httpx.Client(transport=httpx.MockTransport(handler)))

    def test_additive_post_preserves_current_and_confirms_then_no_repost(self):
        from urllib.parse import parse_qs
        calls = []
        saved = False
        def server(req):
            nonlocal saved
            calls.append(req.method)
            if req.method == 'POST':
                fields = parse_qs(req.content.decode())
                self.assertEqual(fields['lotacoes[]'], ['11660','11662','11667'])
                self.assertEqual(fields['bo_voluntario'], ['1'])
                saved = True
                return httpx.Response(302,headers={'location':'/usuario/voluntariado'})
            html = profile()
            if saved: html = html.replace('id="c" value="11667"','id="c" value="11667" checked')
            return httpx.Response(200,text=html)
        with self.client(server) as c:
            result = c.enroll('2026-11',['assu'],execute=True,journal=self.diary)
            self.assertTrue(result['confirmado'] and result['executado'])
            again = c.enroll('2026-11',['assu'],execute=True,journal=self.diary)
            self.assertTrue(again['idempotente'])
        self.assertEqual(calls.count('POST'),1)
        self.assertNotIn('synthetic-test-only', self.diary.read_text())

    def test_preview_no_post_and_execution_requires_diary(self):
        calls=[]
        def server(req):
            calls.append(req.method)
            return httpx.Response(200,text=profile())
        with self.client(server) as c:
            result=c.enroll('2026-11',['assu'])
            self.assertFalse(result['executado']);self.assertTrue(result['envio_habilitado'])
            with self.assertRaises(ValueError): c.enroll('2026-11',['assu'],execute=True)
        self.assertNotIn('POST',calls)

    def test_changed_profile_or_expected_hash_blocks_post(self):
        calls=[]
        def server(req):
            calls.append(req.method)
            html=profile()
            if len(calls)>1:html=html.replace('id="b" value="11660" checked','id="b" value="11660"')
            return httpx.Response(200,text=html)
        with self.client(server) as c:
            with self.assertRaisesRegex(RuntimeError,'mudou'):
                c.enroll('2026-11',['assu'],execute=True,journal=self.diary)
        self.assertNotIn('POST',calls)
        with self.client(lambda r:httpx.Response(200,text=profile())) as c:
            with self.assertRaisesRegex(RuntimeError,'mudou'):
                c.enroll('2026-11',['assu'],execute=True,expected_hash='wrong',journal=self.diary)

    def test_timeout_is_durable_and_next_execution_never_reposts(self):
        calls=[]
        def server(req):
            calls.append(req.method)
            if req.method=='POST':raise httpx.ReadTimeout('private-token',request=req)
            return httpx.Response(200,text=profile())
        with self.client(server) as c:
            with self.assertRaisesRegex(RuntimeError,'não confirmada') as err:
                c.enroll('2026-11',['assu'],execute=True,journal=self.diary)
            self.assertNotIn('private-token',str(err.exception))
            with self.assertRaisesRegex(RuntimeError,'anterior'):
                c.enroll('2026-11',['assu'],execute=True,journal=self.diary)
        self.assertEqual(calls.count('POST'),1)
        self.assertIn('reconciliacao_necessaria',self.diary.read_text())

    def test_wrong_cycle_closed_unknown_csrf_and_unconfirmed_post(self):
        for html, month, unit in [(profile(),'2026-10','assu'),(profile(opened=False),'2026-11','assu'),(profile(),'2026-11','999'),(profile().replace('name="_token"','name="unexpected"'),'2026-11','assu')]:
            calls=[]
            def server(req):
                calls.append(req.method);return httpx.Response(200,text=html)
            with self.client(server) as c:
                with self.assertRaises((RuntimeError,ValueError)):
                    c.enroll(month,[unit],execute=True,journal=self.diary)
            self.assertNotIn('POST',calls)
        with self.client(lambda r:httpx.Response(200,text=profile())) as c:
            with self.assertRaisesRegex(RuntimeError,'não confirmada'):
                c.enroll('2026-11',['assu'],execute=True,journal=self.diary)

    def test_noop_and_unexpected_redirect_do_not_leak_or_replay(self):
        calls=[]
        def server(req):
            calls.append(req.method)
            if req.method=='POST':return httpx.Response(307,headers={'location':'https://example.invalid/private'})
            return httpx.Response(200,text=profile())
        with self.client(server) as c:
            noop=c.enroll('2026-11',['apodi'],execute=True,journal=self.diary)
            self.assertTrue(noop['idempotente']);self.assertNotIn('POST',calls)
            with self.assertRaisesRegex(RuntimeError,'não confirmada'):
                c.enroll('2026-11',['assu'],execute=True,journal=self.diary)
        self.assertEqual(calls.count('POST'),1)

    def test_cli_subscription_preview_registered_without_post(self):
        from sisbom_cli.cli import cli
        with patch('sisbom_cli.commands.voluntariado.VoluntariadoClient.enroll',return_value={'executado':False}) as enroll:
            result=CliRunner().invoke(cli,['sisdo','voluntariado-inscrever','--competencia','2026-11','--quartel','assu'])
        self.assertEqual(result.exit_code,0,result.output)
        self.assertFalse(enroll.call_args.kwargs['execute'])
