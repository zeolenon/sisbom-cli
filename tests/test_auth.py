import json
import subprocess
import unittest
from unittest.mock import patch

from sisbom_cli.auth import get_credentials


class AuthTests(unittest.TestCase):
    def test_session_is_only_passed_via_environment(self):
        with patch('sisbom_cli.auth._get_bw_session', return_value='synthetic-session'), patch(
            'sisbom_cli.auth.subprocess.check_output', return_value=json.dumps(
                {'login': {'username': 'synthetic', 'password': 'synthetic'}})) as run:
            get_credentials()
        self.assertNotIn('synthetic-session', run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs['env']['BW_SESSION'], 'synthetic-session')

    def test_provider_error_does_not_expose_session(self):
        with patch('sisbom_cli.auth._get_bw_session', return_value='synthetic-session'), patch(
            'sisbom_cli.auth.subprocess.check_output', side_effect=subprocess.CalledProcessError(
                1, ['bw'], stderr='synthetic-session')), patch('sisbom_cli.auth.time.sleep'):
            with self.assertRaises(RuntimeError) as caught:
                get_credentials()
        self.assertNotIn('synthetic-session', str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


class LoginPrivacyTests(unittest.TestCase):
    def test_fresh_login_result_has_no_token_or_preview(self):
        from sisbom_cli.client import SISBOMClient
        with SISBOMClient() as client, patch('sisbom_cli.client.load_token', return_value=None), patch('sisbom_cli.client.get_credentials', return_value=('synthetic', 'synthetic')), patch('sisbom_cli.client.save_token'), patch.object(client, '_gql', return_value={'seiLogin': {'token': 'synthetic-private-jwt', 'forca_id': 'synthetic-force'}}):
            result = client.login()
        self.assertTrue(result['ok'])
        self.assertNotIn('token', result)
        self.assertNotIn('token_preview', result)
        self.assertNotIn('synthetic-private-jwt', json.dumps(result))

    def test_login_endpoint_explicit_and_no_credentials_in_output(self):
        from click.testing import CliRunner
        from sisbom_cli.cli import cli
        with patch('sisbom_cli.cli.SISBOMClient') as factory:
            factory.return_value.__enter__.return_value.login.return_value = {'ok': True, 'cached': True}
            result = CliRunner().invoke(cli, ['login', '--api-url', 'https://sisbom.cbm.rn.gov.br/api', '--json'])
        self.assertEqual(result.exit_code, 0)
        factory.assert_called_once_with(api_url='https://sisbom.cbm.rn.gov.br/api')
        self.assertTrue(json.loads(result.output)['ok'])
