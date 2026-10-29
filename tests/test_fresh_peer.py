"""Fresh peers are actual new launches with durable input-specific provenance."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/scripts'))
from crosstalk_lib.adapters import registry, terminal
from crosstalk_lib.adapters.contracts import LaunchSpec, SurfaceRef
from crosstalk_lib.protocol import Error

A = 'ghostty:00000000-0000-0000-0000-000000000001'
B = 'ghostty:00000000-0000-0000-0000-000000000002'


class FreshPeerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.config = self.root / 'state'
        self.env = patch.dict(os.environ, {'CROSSTALK_CONFIG_DIR': str(self.config)})
        self.env.start(); self.addCleanup(self.env.stop)
        self.events = []
        self.created_files = []
        self.addCleanup(lambda: [path.unlink(missing_ok=True) for path in self.created_files])
        self.process = '42'
        self.timeout = False
        self.spec = LaunchSpec('/opt/bin/codex', (), str(Path.cwd()),
                               {'PATH':'/bin','CROSSTALK_CONFIG_DIR':str(self.config)}, 'bootstrap')
        self.adapter = type('Adapter', (), {})()
        def create(anchor, spec, *, ready, startup, label, max_wait, on_created=None):
            self.created_files.extend((ready,startup))
            self.events.append(('split', anchor))
            on_created(B, spec, ready, startup)
            if self.timeout:
                raise Error('PEER_NOT_READY', 'pending approval')
            return SurfaceRef.parse(B)
        self.adapter.launch_peer = create
        for item in (patch.object(registry, 'terminal', return_value=self.adapter),
                     patch.object(registry, 'build_launch_spec', return_value=self.spec),
                     patch.object(registry, 'invoke', side_effect=self.invoke),
                     patch.object(registry, 'wait_ready', side_effect=lambda *args: self.events.append(('wait', args[0])))):
            item.start();self.addCleanup(item.stop)

    def invoke(self, operation, *args, **kwargs):
        self.events.append((operation, *args))
        if operation == 'context':
            return json.dumps({'surface_id':B,'processes':[{'process_id':self.process,'process_start':'started','executable':'/opt/bin/codex'}]})
        return A if operation == 'self' else args[0] if args else ''

    def launch(self, **kwargs):
        return registry.launch('codex', anchor=A, fresh_for_input='input-one', **kwargs)

    def test_new_launch_receipt_is_private_and_retry_does_not_split(self):
        self.assertEqual(self.launch(), B)
        receipt = registry.fresh_receipt(self.config, B, 'input-one')
        self.assertEqual(receipt['origin'], 'new_cli_process')
        self.assertEqual(receipt['process_id'], '42')
        self.assertEqual(receipt['cli_options'], [])
        self.assertEqual(receipt['argv'], [receipt['startup_prompt']])
        self.assertEqual(self.launch(), B)
        self.assertEqual(sum(e[0]=='split' for e in self.events), 1)
        for path in (self.config/'inputs/launches').glob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        with self.assertRaises(Error):registry.fresh_receipt(self.config, B, 'another-input')

    def test_pending_launch_reuses_exact_child_and_permission_cannot_expand(self):
        self.timeout = True
        with self.assertRaises(Error):self.launch()
        intent = json.loads((self.config/'inputs/launches/input-input-one.json').read_text())
        self.assertEqual(intent['state'], 'pending')
        self.assertEqual(intent['surface_id'], B)
        with self.assertRaises(Error):self.launch(auto_approve=True)
        self.timeout = False
        self.assertEqual(self.launch(), B)
        self.assertEqual(sum(e[0]=='split' for e in self.events), 1)

    def test_changed_process_does_not_overwrite_fresh_receipt(self):
        self.launch()
        path = self.config/'inputs/launches'/ (B.removeprefix('ghostty:')+'.json')
        before = path.read_bytes()
        self.process = 'replacement'
        with self.assertRaises(Error):self.launch()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sum(e[0]=='split' for e in self.events), 1)

    def test_unknown_creation_outcome_never_launches_duplicate(self):
        def lost_address(*args, **kwargs):
            self.created_files.extend((kwargs['ready'],kwargs['startup']))
            self.events.append(('split', A))
            raise Error('TERMINAL_TIMEOUT', 'split response lost')
        self.adapter.launch_peer = lost_address
        with self.assertRaises(Error):self.launch()
        with self.assertRaises(Error):self.launch()
        self.assertEqual(sum(e[0]=='split' for e in self.events), 1)

    def test_invalid_preflight_does_not_pin_nonexistent_launch(self):
        with patch.object(registry, 'build_launch_spec', side_effect=Error('CAPABILITY_UNSUPPORTED','no binary')):
            with self.assertRaises(Error):self.launch()
        self.assertFalse((self.config/'inputs/launches/input-input-one.json').exists())
        self.assertEqual(self.launch(), B)

    def test_public_launch_flag_is_parsed_without_legacy_reuse(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CROSSTALK_BRIDGE', None)
            with patch.object(registry, 'launch', return_value=B) as launch:
                self.assertEqual(registry.call_terminal('launch','codex','--fresh-for-input','input-one','--auto-approve'), B)
                launch.assert_called_once_with('codex',auto_approve=True,fresh_for_input='input-one')
        with self.assertRaises(Error):registry.launch('claude',anchor=A,fresh_for_input='input-one')
        with self.assertRaises(Error):registry.launch('codex',anchor=A,fresh_for_input='../escape')

    def test_terminal_records_exact_child_before_publishing_launch(self):
        self.config.mkdir(mode=0o700)
        ready, startup = self.root/'ready', self.root/'startup'
        ready.touch();startup.touch()
        events = []
        def invoke(command, *args, **kwargs):
            events.append(command)
            if command=='split':return B.removeprefix('ghostty:')
            if command=='label':self.assertIn('recorded',events)
            return ''
        def record(surface, spec, ready, startup):
            self.assertEqual(surface,B)
            self.assertFalse(Path(str(ready)+'.surface').exists())
            events.append('recorded')
        with patch.object(terminal,'invoke',side_effect=invoke), patch.object(terminal,'wait_ready'):
            result=terminal.TerminalAdapter('ghostty').launch_peer(A,self.spec,ready=ready,startup=startup,
                                                                 label='codex',on_created=record)
        self.assertEqual(result.address(),B)
        self.assertEqual(events[:3],['split','recorded','label'])


if __name__ == '__main__':
    unittest.main()
