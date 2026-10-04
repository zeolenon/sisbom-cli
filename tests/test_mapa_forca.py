import unittest
from unittest.mock import patch
from click.testing import CliRunner
from sisbom_cli.client import SISBOMClient
from sisbom_cli.cli import cli


class ForceMapTests(unittest.TestCase):
    def test_garrison_filters_keep_vehicle_and_functions(self):
        rows = [dict(date='2026-10-04', _lotacao='TEST', _viatura='vtr-test', prefixo='TEST-01',
                     guarnicao=[dict(str_nomecurto='FICTICIO', str_matricula='1111111', str_funcao='Motorista', bo_ativo=True)]),
                dict(date='2026-10-03', _lotacao='TEST'), dict(date='2026-10-04', _lotacao='OTHER')]
        with SISBOMClient() as client, patch.object(client, '_gql', return_value={'MapaGuarnicoesMilitar': rows}) as gql:
            result = client.mapa_forca_guarnicoes('2026-10-04', 'TEST')
        self.assertEqual(result, rows[:1])
        self.assertEqual(gql.call_args.kwargs['variables'], {'date': '2026-10-04'})
        self.assertIn('str_funcao', gql.call_args.args[0])
        self.assertIn('_viatura', gql.call_args.args[0])

    def test_cli_displays_vehicle_and_function_from_registry(self):
        with patch('sisbom_cli.cli.SISBOMClient') as cls:
            client = cls.return_value.__enter__.return_value
            client.mapa_forca_militares.return_value = []
            client.mapa_forca_guarnicoes.return_value = [dict(atividade='Teste', prefixo='TEST-01',
                guarnicao=[dict(str_nomecurto='FICTICIO', str_matricula='1111111', str_funcao='Motorista')])]
            result = CliRunner().invoke(cli, ['mapa-forca', '--lotacao', 'TEST', '--date', '2026-10-04'])
        self.assertEqual(result.exit_code, 0, result.output)
        for value in ('TEST-01', 'FICTICIO', 'Motorista'):
            self.assertIn(value, result.output)
