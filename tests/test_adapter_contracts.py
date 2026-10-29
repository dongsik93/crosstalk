"""Built-in adapter contracts and safe process/data boundaries; no live terminals."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/scripts'))
from crosstalk_lib.adapters import cli, registry
from crosstalk_lib.adapters.contracts import CapabilitySet, LaunchSpec, SurfaceRef
from crosstalk_lib.adapters import terminal
from crosstalk_lib.protocol import Error

A = 'ghostty:00000000-0000-0000-0000-000000000001'


class AdapterContracts(unittest.TestCase):
    def test_imports_have_no_process_or_state_side_effects(self):
        code = '''import os
from unittest.mock import patch
before = dict(os.environ)
with patch('subprocess.Popen', side_effect=AssertionError('process during import')), patch('sqlite3.connect', side_effect=AssertionError('DB during import')):
    from crosstalk_lib.adapters import contracts, cli, terminal, registry
assert dict(os.environ) == before
'''
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'must-not-exist'
            env = dict(os.environ, PYTHONPATH=str(ROOT / 'assets/scripts'), CROSSTALK_CONFIG_DIR=str(state))
            result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(state.exists())

    def test_surface_validation(self):
        self.assertEqual(SurfaceRef.parse(A).address(), A)
        self.assertEqual(SurfaceRef.parse('surface:23').backend, 'cmux')
        self.assertEqual(SurfaceRef.parse('cmux:surface:23').address(), 'surface:23')
        for value in ('ghostty:../bad', 'surface:1; echo no', 'tmux:1'):
            with self.assertRaises(ValueError):
                SurfaceRef.parse(value)

    def test_cli_arguments_and_permissions_match_existing_contract(self):
        with mock.patch('shutil.which', side_effect=lambda name: '/opt/bin/' + name):
            for kind, expected in [('claude', ()), ('codex', ()), ('agy', ('--prompt-interactive',))]:
                spec = cli.build_launch_spec(kind, cwd='/work/한글 dir', runtime='/work/runtime/crosstalk',
                                            config='/private/state', ready='/tmp/ready', startup='/tmp/startup')
                self.assertEqual(spec.argv, expected)
                self.assertEqual(spec.permission_mode, 'default')
                self.assertIn('--protocol 3 --engine-version 1', spec.bootstrap_instruction)
                self.assertIn('handler=discussion', spec.bootstrap_instruction)
                self.assertNotIn('--model', spec.argv)
                approved = cli.build_launch_spec(kind, cwd='/work', runtime='/work/crosstalk',
                                                 config='/state', ready='/tmp/r', startup='/tmp/s', auto_approve=True)
                self.assertEqual(approved.argv[0], '--yolo' if kind == 'codex' else '--dangerously-skip-permissions')
            with self.assertRaises(Error):
                cli.build_launch_spec('agy', cwd='/work', runtime='/work/crosstalk', config='/state',
                                      ready='/tmp/r', startup='/tmp/s', role='caller')

    def test_launch_env_is_restricted_and_frozen(self):
        source = {'PATH': '/bin', 'CROSSTALK_CONFIG_DIR': '/state'}
        spec = LaunchSpec('/bin/cli', (), '/work', source, 'bootstrap')
        source['BASH_ENV'] = '/evil'
        self.assertNotIn('BASH_ENV', spec.env_delta)
        with self.assertRaises(TypeError):
            spec.env_delta['PATH'] = 'changed'
        with self.assertRaises(ValueError):
            LaunchSpec('/bin/cli', (), '/work', {'BASH_ENV': '/evil'}, 'bootstrap')

    def test_capability_unknown_is_not_support(self):
        caps = CapabilitySet({'input_submission': 'unknown'}, 'observed')
        with self.assertRaises(ValueError):
            caps.require('input_submission')
        with mock.patch.object(terminal, 'GHOSTTY_DICTIONARY', Path('/not-a-real-dictionary')):
            caps = terminal.TerminalAdapter('ghostty').capabilities()
        self.assertEqual(caps.features['screen_capture'], 'unsupported')
        self.assertNotEqual(caps.features['input_submission'], 'supported')
        with self.assertRaises(Error):
            terminal.TerminalAdapter('ghostty').capture(A)

    def test_capabilities_observe_dictionary_not_version_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            dictionary = Path(tmp) / 'Ghostty.sdef'
            dictionary.write_text('<dictionary><suite><class name="terminal"><property name="id"/><property name="tty"/></class><command name="split"/><command name="input text"/><command name="send key"/></suite></dictionary>')
            with mock.patch.object(terminal, 'GHOSTTY_DICTIONARY', dictionary), mock.patch('shutil.which', return_value='/usr/bin/osascript'):
                caps = terminal.TerminalAdapter('ghostty').capabilities()
            caps.require('input_submission', 'exact_addressing', 'native_split')
            self.assertIn(str(dictionary), ' '.join(caps.evidence))

    def test_explicit_provider_must_advertise_its_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = Path(tmp) / 'provider'
            marker = Path(tmp) / 'operations'
            response = Path(tmp) / 'capabilities.json'
            provider.write_text('#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\nPath(os.environ["CAP_LOG"]).write_text(" ".join(sys.argv[1:]))\nprint(Path(os.environ["CAP_RESPONSE"]).read_text())\n')
            provider.chmod(0o700)
            with mock.patch.dict(os.environ, {'CROSSTALK_BRIDGE': str(provider), 'CAP_LOG': str(marker), 'CAP_RESPONSE': str(response)}):
                for payload in ({}, {'backend': 'cmux', 'features': {'input_submission': 'supported'}},
                                {'backend': 'ghostty', 'features': {'input_submission': True}}):
                    response.write_text(json.dumps(payload))
                    caps = terminal.TerminalAdapter('ghostty').capabilities()
                    with self.assertRaises(ValueError):
                        caps.require('input_submission')
                    self.assertEqual(marker.read_text(), 'capabilities')
                response.write_text(json.dumps({'backend': 'ghostty', 'features': {'input_submission': 'supported', 'exact_addressing': 'supported'}}))
                caps = terminal.TerminalAdapter('ghostty').capabilities()
                caps.require('input_submission', 'exact_addressing')
                self.assertEqual(caps.features['native_split'], 'unknown')
                self.assertEqual(marker.read_text(), 'capabilities')

    def test_identity_uses_process_evidence_not_labels(self):
        context = {'surface_id': A, 'processes': [
            {'process_id': '1', 'process_start': 'old', 'executable': '/usr/bin/login'},
            {'process_id': '2', 'process_start': 'new', 'executable': '/opt/bin/codex'}]}
        result = cli.identify_cli_context(context, cli_session_id='thread')
        self.assertEqual((result['kind'], result['process_id']), ('codex', '2'))
        context['processes'].append({'process_id': '3', 'process_start': 'now', 'executable': '/opt/bin/claude'})
        with self.assertRaises(Error):
            cli.identify_cli_context(context)

    def test_registry_never_dispatches_workflow_to_terminal_driver(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CROSSTALK_BRIDGE', None)
            with mock.patch.object(registry, 'invoke') as invoke:
                for op in ('run', 'receive', 'reply', 'recover', 'extract-verdict'):
                    with self.assertRaises(Error):
                        registry.call_terminal(op)
                invoke.assert_not_called()

    def test_submission_failure_after_input_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / 'helper'
            marker = Path(tmp) / 'submitted'
            helper.write_text('#!/bin/sh\nprintf submitted > "$MARKER"\nexit 1\n')
            helper.chmod(0o700)
            with mock.patch.dict(os.environ, {'MARKER': str(marker)}):
                with self.assertRaises(Error) as error:
                    terminal.invoke('send', A, 'body', driver=helper)
            self.assertEqual(error.exception.code, 'NOTIFICATION_UNKNOWN')
            self.assertTrue(marker.exists())

    def test_timeout_kills_only_owned_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / 'helper'
            helper.write_text('#!/bin/sh\nsleep 20\n')
            helper.chmod(0o700)
            with self.assertRaises(Error) as error:
                terminal.invoke('self', driver=helper, timeout=0.05)
            self.assertEqual(error.exception.code, 'TERMINAL_TIMEOUT')


if __name__ == '__main__':
    unittest.main()
