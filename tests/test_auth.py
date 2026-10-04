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
