"""Real staged-runtime repairs preserve the active tree until a replacement is ready."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('repair_installer', REPO / 'assets/scripts/crosstalk_lib/installer.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class RuntimeRepairTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='crosstalk-runtime-repair-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.root = self.base / 'state'
        self.source = self.base / 'source'
        self.source.mkdir()
        # A stable, genuine source release makes retries independent of concurrent repo edits.
        shutil.copytree(REPO / 'assets', self.source / 'assets', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(REPO / 'plugins/crosstalk/hooks', self.source / 'plugins/crosstalk/hooks',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(REPO / 'VERSION', self.source / 'VERSION')
        patch = mock.patch.dict(os.environ, {'HOME': str(self.home), 'CROSSTALK_CONFIG_DIR': str(self.root)})
        patch.start()
        self.addCleanup(patch.stop)
        self.install()
        self.original_release = (self.root / 'current').resolve()
        self.database = self.root / 'mailbox.sqlite3'
        with sqlite3.connect(self.database) as conn:
            conn.execute("INSERT INTO events(event_type,metadata,created_at) VALUES('preserved_fixture','{\"note\":\"keep\"}','2026-10-29')")
        self.config = self.root / 'config.json'
        self.config.write_bytes(b'{"language":"ko","active_rules":"custom","active_persona":"mine","unknown":{"keep":[1,2]}}\n')
        self.database_bytes = self.database.read_bytes()
        self.config_bytes = self.config.read_bytes()

    def install(self):
        return installer.install(self.source, self.home)

    def manifest(self):
        return json.loads((self.root / installer.MANIFEST).read_text())

    def damage(self):
        module = self.original_release / 'assets/scripts/crosstalk_lib/mailbox.py'
        module.unlink()
        modified = self.original_release / 'assets/scripts/crosstalk_lib/protocol.py'
        modified.write_text('# user modification, retained for inspection\n')
        unknown = self.original_release / 'personal-notes.txt'
        unknown.write_text('Keep this unknown file.\n')
        return modified, unknown

    def assert_repaired(self, result):
        current = (self.root / 'current').resolve()
        self.assertNotEqual(current, self.original_release)
        self.assertEqual(result['retained_release'], str(self.original_release))
        self.assertEqual((current / 'assets/scripts/crosstalk_lib/mailbox.py').read_bytes(),
                         (self.source / 'assets/scripts/crosstalk_lib/mailbox.py').read_bytes())
        self.assertEqual(self.database.read_bytes(), self.database_bytes)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.assertEqual(installer.inspect(self.root)['status'], 'healthy')
        self.assertFalse((self.root / 'maintenance.json').exists())
        check = subprocess.run([str(self.home / '.local/bin/crosstalk'), 'doctor', '--offline'],
                               capture_output=True, text=True, timeout=30, cwd='/')
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertEqual(json.loads(check.stdout)['issues'], [])

    def test_source_cli_repairs_missing_module_and_preserves_modified_leftovers(self):
        modified, unknown = self.damage()
        diagnosis = subprocess.run([str(self.home / '.local/bin/crosstalk'), 'doctor', '--offline', '--json'],
                                   capture_output=True, text=True, timeout=30, cwd='/')
        self.assertEqual(diagnosis.returncode, 7, diagnosis.stdout + diagnosis.stderr)
        self.assertEqual(json.loads(diagnosis.stdout)['error']['code'], 'INSTALLATION_INCOMPLETE')
        self.assertIn('mailbox.py', diagnosis.stdout)
        self.assertNotIn('Traceback', diagnosis.stderr)
        run = subprocess.run([sys.executable, str(self.source / 'assets/scripts/crosstalk'),
                              'install', '--source', str(self.source), '--home', str(self.home)],
                             capture_output=True, text=True, timeout=60, cwd='/')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assert_repaired(json.loads(run.stdout))
        self.assertEqual(modified.read_text(), '# user modification, retained for inspection\n')
        self.assertEqual(unknown.read_text(), 'Keep this unknown file.\n')
        self.assertFalse((self.original_release / 'assets/scripts/crosstalk_lib/mailbox.py').exists())

    def test_staging_write_failure_keeps_active_pointer_and_existing_tree(self):
        modified, unknown = self.damage()
        previous_pointer = os.readlink(self.root / 'current')
        original_write = installer._write
        def disk_full(path, *args, **kwargs):
            if '.staging-' in str(path) and path.name == 'mailbox.py':
                raise OSError('simulated staging disk full')
            return original_write(path, *args, **kwargs)
        with mock.patch.object(installer, '_write', side_effect=disk_full):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.install()
        selected = self.manifest()['release_path']
        self.assertEqual(self.manifest()['phase'], 'staging')
        self.assertEqual(os.readlink(self.root / 'current'), previous_pointer)
        self.assertEqual(modified.read_text(), '# user modification, retained for inspection\n')
        self.assertEqual(unknown.read_text(), 'Keep this unknown file.\n')
        self.assertFalse(Path(selected).exists())
        self.assertEqual(list((self.root / 'releases').glob('.staging-*')), [])
        self.assertEqual(self.database.read_bytes(), self.database_bytes)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.assert_repaired(self.install())
        self.assertEqual(self.manifest()['release_path'], selected)

    def _interrupt_activation(self, after_pointer):
        self.damage()
        code = '''import os
from crosstalk_lib import installer
original = installer._pointer
def interrupt(root, release):
    if AFTER:
        original(root, release)
    os._exit(73)
installer._pointer = interrupt
installer.install(SOURCE, HOME)
'''.replace('AFTER', repr(after_pointer)).replace('SOURCE', repr(str(self.source))).replace('HOME', repr(str(self.home)))
        env = dict(os.environ, PYTHONPATH=str(self.source / 'assets/scripts'), PYTHONDONTWRITEBYTECODE='1')
        run = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 73, run.stdout + run.stderr)
        interrupted = self.manifest()
        selected = Path(interrupted['release_path'])
        self.assertEqual(interrupted['phase'], 'migrated')
        self.assertTrue((selected / 'assets/scripts/crosstalk_lib/mailbox.py').is_file())
        self.assertEqual((self.root / 'current').resolve(), selected if after_pointer else self.original_release)
        self.assertTrue(self.original_release.exists())
        self.assertEqual(self.database.read_bytes(), self.database_bytes)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.assert_repaired(self.install())
        self.assertEqual(self.manifest()['release_path'], str(selected))
        self.assertEqual(self.manifest()['install_id'], interrupted['install_id'])

    def test_exit_before_pointer_switch_resumes_same_repair(self):
        self._interrupt_activation(after_pointer=False)

    def test_exit_after_pointer_switch_resumes_same_repair(self):
        self._interrupt_activation(after_pointer=True)

    def test_retry_with_different_source_does_not_replace_pending_repair(self):
        self.damage()
        with mock.patch.object(installer, '_stage', side_effect=OSError('stage interrupted')):
            with self.assertRaises(OSError):
                self.install()
        before = (self.root / installer.MANIFEST).read_bytes()
        (self.source / 'assets/user-commands/crosstalk.md').write_text('different release')
        with self.assertRaisesRegex(ValueError, 'exact interrupted release'):
            self.install()
        self.assertEqual((self.root / installer.MANIFEST).read_bytes(), before)
        self.assertEqual((self.root / 'current').resolve(), self.original_release)
        self.assertEqual(self.database.read_bytes(), self.database_bytes)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)

    def test_incomplete_source_rejected_before_any_state_change(self):
        manifest = (self.root / installer.MANIFEST).read_bytes()
        for name in installer.RUNTIME_MODULES:
            with self.subTest(module=name):
                module = self.source / f'assets/scripts/crosstalk_lib/{name}.py'
                content = module.read_bytes()
                module.unlink()
                try:
                    run = subprocess.run([sys.executable, str(REPO / 'assets/scripts/crosstalk'),
                                          'install', '--source', str(self.source), '--home', str(self.home)],
                                         capture_output=True, text=True, timeout=30, cwd='/')
                    self.assertEqual(run.returncode, 7, run.stdout + run.stderr)
                    self.assertIn('Incomplete release', json.loads(run.stdout)['error']['message'])
                    self.assertEqual((self.root / 'current').resolve(), self.original_release)
                    self.assertEqual((self.root / installer.MANIFEST).read_bytes(), manifest)
                    self.assertEqual(self.database.read_bytes(), self.database_bytes)
                    self.assertEqual(self.config.read_bytes(), self.config_bytes)
                finally:
                    module.write_bytes(content)

    def test_staged_import_failure_never_activates_replacement(self):
        module = self.source / 'assets/scripts/crosstalk_lib/mailbox.py'
        original = module.read_bytes()
        module.write_bytes(b'raise RuntimeError("staged import fails")\n' + original)
        with self.assertRaisesRegex(ValueError, 'staged import fails'):
            self.install()
        self.assertEqual((self.root / 'current').resolve(), self.original_release)
        self.assertEqual((self.original_release / 'assets/scripts/crosstalk_lib/mailbox.py').read_bytes(), original)
        self.assertEqual(self.database.read_bytes(), self.database_bytes)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)

    def _assert_reported_import_error_blocks_activation(self, prefix):
        # Engine dispatch imports mailbox earlier now; fail inside doctor's DB inspection
        # so this still proves an exit-zero JSON failure cannot authorize activation.
        module = self.source / 'assets/scripts/crosstalk_lib/db.py'
        injected = ('\n_original_connect = connect\n'
                    'def connect(*args, **kwargs):\n'
                    '    import sys\n'
                    '    if len(sys.argv) > 1 and sys.argv[1] == "doctor":\n' +
                    ''.join('        ' + line + '\n' for line in prefix.decode().splitlines()) +
                    '    return _original_connect(*args, **kwargs)\n')
        module.write_bytes(module.read_bytes() + injected.encode())
        run = subprocess.run([sys.executable, str(REPO / 'assets/scripts/crosstalk'),
                              'install', '--source', str(self.source), '--home', str(self.home)],
                             capture_output=True, text=True, timeout=30, cwd='/')
        self.assertEqual(run.returncode, 7, run.stdout + run.stderr)
        self.assertIn('runtime/database diagnosis failed', json.loads(run.stdout)['error']['message'])
        staged = Path(self.manifest()['release_path']) / 'assets/scripts/crosstalk'
        report = subprocess.run([sys.executable, str(staged), 'doctor', '--offline'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
        self.assertIs(json.loads(report.stdout)['runtime_healthy'], False)
        self.assertEqual((self.root / 'current').resolve(), self.original_release)
        self.assertEqual(self.database.read_bytes(), self.database_bytes)
        self.assertEqual(self.config.read_bytes(), self.config_bytes)

    def test_caught_oserror_report_blocks_activation(self):
        self._assert_reported_import_error_blocks_activation(b'raise OSError("caught import failure")\n')

    def test_caught_sqlite_error_report_blocks_activation(self):
        self._assert_reported_import_error_blocks_activation(b'import sqlite3\nraise sqlite3.OperationalError("caught DB failure")\n')

    def test_caught_protocol_error_report_blocks_activation(self):
        self._assert_reported_import_error_blocks_activation(b'from .protocol import Error\nraise Error("DB_BUSY", "caught protocol failure")\n')

    def test_missing_or_false_health_report_fails_closed(self):
        for report in ({}, {'runtime_healthy': False}, {'runtime_healthy': 'true'}, []):
            with self.subTest(report=report), mock.patch.object(installer, '_invoke', return_value=report):
                with self.assertRaisesRegex(ValueError, 'diagnosis failed'):
                    installer._check_runtime('unused', self.root, self.home)

    def test_notification_issues_do_not_block_valid_runtime_repair(self):
        with sqlite3.connect(self.database) as conn:
            for sid, kind in [('a', 'codex'), ('b', 'claude')]:
                conn.execute("INSERT INTO sessions(session_id,kind,status,created_at) VALUES(?,?,'unresolved','now')", (sid, kind))
            conn.execute("INSERT INTO threads(thread_id,caller_session_id,peer_session_id,mode) VALUES('t','a','b','analyze')")
            conn.execute("INSERT INTO messages(id,thread_id,kind,sender_session_id,recipient_session_id,body,round,created_at) VALUES('q','t','request','a','b','preserve queued work',1,'now')")
            conn.execute("INSERT INTO delivery_attempts(attempt_id,message_id,state,started_at,error_code) VALUES('attempt','q','unknown','now','NOTIFICATION_UNKNOWN')")
        before = self.database.read_bytes()
        self.damage()
        self.assertTrue(self.install()['installed'])
        self.assertEqual(self.database.read_bytes(), before)
        check = subprocess.run([str(self.home / '.local/bin/crosstalk'), 'doctor', '--offline'],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        report = json.loads(check.stdout)
        self.assertIs(report['runtime_healthy'], True)
        self.assertTrue(any(issue['code'] == 'NOTIFICATION_UNKNOWN' for issue in report['issues']))


if __name__ == '__main__':
    unittest.main()
