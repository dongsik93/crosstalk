"""Protocol contracts through the executable, with isolated terminal identities."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'assets/scripts/crosstalk'
A = 'ghostty:00000000-0000-0000-0000-000000000001'
B = 'ghostty:00000000-0000-0000-0000-000000000002'


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        bridge = self.root / 'bridge'
        bridge.write_text('''#!/usr/bin/env python3
import json, os, sys
if sys.argv[1]=='strict-identity':
 print(json.dumps(dict(surface_id=os.environ['TEST_SURFACE'], kind=os.environ['TEST_KIND'], process_id=os.environ['TEST_SURFACE'], process_start='fixture-start')))
elif sys.argv[1]=='target-identity':
 print(json.dumps(dict(surface_id=sys.argv[2],kind='codex' if sys.argv[2].endswith('1') else 'claude',process_id=sys.argv[2],process_start='fixture-start')))
elif sys.argv[1]=='get-language': print('en')
elif sys.argv[1]=='send': pass
else: sys.exit(1)
''')
        bridge.chmod(0o755)
        self.env = dict(os.environ, CROSSTALK_CONFIG_DIR=str(self.root / 'state'),
                        CROSSTALK_BRIDGE=str(bridge), CODEX_THREAD_ID='')
        self.call('migrate')
        for surface, kind in ((A, 'codex'), (B, 'claude')):
            nonce = self.call('session', 'challenge', '--surface', surface, '--kind', kind)['challenge']
            self.call('session', 'bind', '--challenge', nonce, '--kind', kind,
                      '--protocol', '2', actor=surface)

    def call(self, *args, actor=A, stdin=None, code=0, **env):
        result = subprocess.run([sys.executable, str(CLI), *args], input=stdin,
                                env=self.env | dict(TEST_SURFACE=actor, TEST_KIND='codex' if actor==A else 'claude') | env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def request(self, key='test'):
        sent = self.call('send', 'claude', 'private body', '--id', key)
        return self.call('receive', sent['id'], actor=B)

    def test_explicit_verdict_and_conflicts(self):
        request = self.request()
        flags = ('--lease-token', request['lease_token'])
        answer = self.call('reply', request['id'], 'Example [AGREE]', *flags, actor=B)
        received = self.call('receive', answer['id'])
        self.assertEqual(received['verdict'], 'none')
        conflict = self.call('reply', request['id'], 'Example [AGREE]', *flags,
                             '--verdict', 'agree', actor=B, code=5)
        self.assertEqual(conflict['error']['code'], 'REPLY_CONFLICT')

    def test_validation_does_not_complete_request(self):
        request = self.request()
        bad = self.call('reply', request['id'], 'answer', '--lease-token', request['lease_token'],
                        '--verdict', 'disagree', actor=B, code=2)
        self.assertEqual(bad['error']['code'], 'INVALID_ARGUMENT')
        self.call('reply', request['id'], 'answer', '--lease-token', request['lease_token'],
                  '--confidence', '0.85', actor=B, code=2)
        self.assertEqual(self.call('status', request['id'])[0]['processing_state'], 'processing')

    def test_diagnostics_are_read_only_and_redacted(self):
        request = self.request()
        path = self.root / 'state/mailbox.sqlite3'
        before = path.read_bytes()
        doctor = self.call('doctor', '--offline', '--json')
        status = self.call('status')
        self.assertEqual(before, path.read_bytes())
        encoded = json.dumps([doctor, status])
        self.assertNotIn(request['lease_token'], encoded)
        self.assertNotIn('private body', encoded)
        with sqlite3.connect(path) as conn:
            events = str(conn.execute('SELECT * FROM events').fetchall())
        self.assertNotIn(request['lease_token'], events)
        self.assertNotIn('private body', events)

    def test_ask_ack_and_idempotent_ack(self):
        sent = self.call('send', 'claude', 'one answer', '--mode', 'ask')
        request = self.call('receive', sent['id'], actor=B)
        answer = self.call('reply', sent['id'], 'answer', '--lease-token', request['lease_token'], actor=B)
        self.assertEqual(answer['delivery_state'], 'suppressed')
        reply = self.call('receive', answer['id'])
        args = ('ack', reply['id'], '--lease-token', reply['lease_token'], '--outcome', 'observed', '--result-stdin')
        self.call(*args, stdin='observed answer')
        self.call(*args, stdin='observed answer')
        self.assertEqual(self.call('status', reply['id'])[0]['processing_state'], 'completed')

    def test_invalid_argument_json_is_locale_independent(self):
        result = self.call('reply', 'missing', '--confidence', 'nonsense', code=2, LC_ALL='C')
        self.assertEqual(result['error']['code'], 'INVALID_ARGUMENT')
        self.assertIn('retryable', result['error'])
        self.assertFalse(result['saved'])


if __name__ == '__main__':
    unittest.main()
