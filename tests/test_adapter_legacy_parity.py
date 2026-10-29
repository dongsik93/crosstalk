"""Golden low-level parity with the legacy wrapper, using no live terminal apps."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'assets/scripts'
sys.path.insert(0, str(SCRIPTS))
from crosstalk_lib.adapters import registry
from crosstalk_lib.adapters import terminal

A = '00000000-0000-0000-0000-000000000001'
B = '00000000-0000-0000-0000-000000000002'


class AdapterLegacyParity(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.log = self.root / 'calls'
        self.env = dict(os.environ, PATH=str(self.root) + ':' + os.environ['PATH'],
                        CROSSTALK_CONFIG_DIR=str(self.root / 'state'), TEST_LOG=str(self.log),
                        CROSSTALK_BACKEND='ghostty', CROSSTALK_SURFACE_ID='ghostty:' + A,
                        CODEX_THREAD_ID='')
        cmux = self.root / 'cmux'
        cmux.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_LOG'], 'a') as out: out.write(json.dumps(['cmux', *sys.argv[1:]])+'\\n')
if sys.argv[1]=='identify': print('{"caller": {"surface_ref": "surface:1"}}')
elif sys.argv[1]=='list-panes': print('pane:1')
elif sys.argv[1]=='list-pane-surfaces': print('surface:1 ct-codex\\nsurface:2 ct-claude')
elif sys.argv[1]=='read-screen': print('legacy screen body')
''')
        cmux.chmod(0o700)
        osa = self.root / 'osascript'
        osa.write_text(f'''#!/usr/bin/env python3
import json, os, sys
args=sys.argv[2:]
with open(os.environ['TEST_LOG'], 'a') as out: out.write(json.dumps(['osascript',*args])+'\\n')
if args[0]=='exists': print(args[1])
elif args[0]=='list': print({A!r}+'\\n'+{B!r})
elif args[0]=='tty': print('/dev/ttys777')
''')
        osa.chmod(0o700)
        ps = self.root / 'ps'
        ps.write_text('''#!/usr/bin/env python3
import sys
if 'pid=,pgid=,tpgid=,stat=,comm=' in sys.argv:
 print('42 42 42 S+ /opt/bin/codex')
 print('43 43 42 S /opt/bin/claude')
 print('41 42 42 Ss+ /usr/bin/login')
elif 'lstart=' in sys.argv: print('Thu Oct 29 12:00:00 2026')
''')
        ps.chmod(0o700)

    def run_tool(self, script, *args, success=True):
        result = subprocess.run(['bash', str(SCRIPTS / script), *args], env=self.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout.strip()

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def reset(self):
        self.log.write_text('')

    def test_cmux_input_and_capture_match_legacy(self):
        payload = '한글 "quotes"; $(touch SHOULD_NOT_EXIST) `false`\nsecond line'
        self.run_tool('crosstalk_bridge.sh', 'send', 'surface:2', payload)
        old = [call for call in self.calls() if call[1] in ('send', 'send-key')]
        self.reset()
        self.run_tool('crosstalk_terminal.sh', 'send', 'surface:2', payload, '2')
        new = [call for call in self.calls() if call[1] in ('send', 'send-key')]
        self.assertEqual(new, old)
        self.assertIn(payload, new[0])
        self.assertEqual(self.run_tool('crosstalk_bridge.sh', 'capture', 'surface:2'),
                         self.run_tool('crosstalk_terminal.sh', 'capture', 'surface:2'))
        self.assertFalse((ROOT / 'SHOULD_NOT_EXIST').exists())

    def test_ghostty_literal_input_matches_legacy(self):
        address = 'ghostty:' + B
        self.run_tool('crosstalk_bridge.sh', 'label', address, 'claude')
        self.reset()
        self.run_tool('crosstalk_bridge.sh', 'send', address, 'quoted "; payload')
        old = [call for call in self.calls() if call[1] in ('text', 'key')]
        self.reset()
        self.run_tool('crosstalk_terminal.sh', 'send', address, 'quoted "; payload', '2')
        new = [call for call in self.calls() if call[1] in ('text', 'key')]
        self.assertEqual(new, old)

    def test_driver_has_no_workflow_dispatch_or_reverse_bridge_call(self):
        driver = (SCRIPTS / 'crosstalk_terminal.sh').read_text()
        self.assertNotIn('crosstalk_bridge.sh', driver)
        self.assertNotIn('crosstalk_lib', driver)
        for operation in ('run', 'reply', 'launch', 'extract-verdict'):
            self.run_tool('crosstalk_terminal.sh', operation, success=False)
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(terminal, 'DRIVER', SCRIPTS / 'crosstalk_terminal.sh'):
            registry.call_terminal('send', 'ghostty:' + B, 'wake up')
        self.assertTrue(any(call[1]=='text' and call[-1]=='wake up' for call in self.calls()))

    def test_exact_identity_parity_separates_terminal_and_cli_evidence(self):
        legacy = json.loads(self.run_tool('crosstalk_bridge.sh', 'strict-identity'))
        with mock.patch.dict(os.environ, self.env, clear=True):
            adapted = json.loads(registry.call_terminal('strict-identity'))
            target = json.loads(registry.call_terminal('target-identity', 'ghostty:' + B))
        self.assertEqual(adapted, legacy)
        self.assertEqual((target['surface_id'], target['kind'], target['process_id']), ('ghostty:' + B, 'codex', '42'))
        self.assertEqual(target['cli_session_id'], '')


if __name__ == '__main__':
    unittest.main()
