"""Installer tests use isolated homes and real subprocess smoke checks."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[1] / 'assets/scripts/crosstalk_lib/installer.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_release_inventory_covers_all_runtime_modules_and_templates(self):
        package = Path(__file__).resolve().parents[1] / 'assets/scripts/crosstalk_lib'
        modules = {str(path.relative_to(package).with_suffix('')) for path in package.rglob('*.py')}
        self.assertEqual(set(installer.RUNTIME_MODULES), modules)
        templates = {path.name for path in (package / 'engine/templates').glob('*.md')}
        self.assertEqual(set(installer.RUNTIME_TEMPLATES), templates)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.root = self.base / 'state'
        self.source = self.base / 'source'
        self.source.mkdir()
        self.env = mock.patch.dict(os.environ, {'CROSSTALK_CONFIG_DIR': str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        contents = {
            'VERSION': '0.12.0\n',
            'assets/scripts/crosstalk': '''#!/usr/bin/env python3
import json, os, pathlib, sqlite3, sys
root=pathlib.Path(os.environ['CROSSTALK_CONFIG_DIR'])
if sys.argv[1]=='migrate':
    with sqlite3.connect(root/'mailbox.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS messages(processing_state TEXT)')
        db.execute('PRAGMA user_version=3')
    print(json.dumps({'backup_path':str(root/'migration.backup')}))
elif sys.argv[1]=='capabilities':
    print(json.dumps({'protocol_version':3,'runtime_version':'0.12.0','schema_version':3,'engine_version':1}))
else:
    print(json.dumps({'runtime_healthy':True}))
''',
            'assets/scripts/crosstalk_bridge.sh': '#!/bin/bash\necho bridge\n',
            'assets/scripts/crosstalk_ghostty.sh': '#!/bin/bash\ntrue\n',
            'assets/scripts/crosstalk_terminal.sh': '#!/bin/bash\ntrue\n',
            'assets/scripts/crosstalk_lib/__init__.py': '',
            'assets/scripts/crosstalk_lib/cli.py': '# fixture CLI above\n',
            'assets/codex-skills/crosstalk/SKILL.md': 'protocol 2 skill',
            'assets/codex-skills/crosstalk/mailbox.md': 'legacy mailbox',
            'assets/codex-skills/crosstalk/discussion.md': 'protocol 3 discussion',
            'assets/user-commands/crosstalk.md': 'new command',
            'assets/agy-commands/crosstalk-peer.toml': 'prompt="new"',
            'assets/rules/en/default.md': 'new rule',
            'assets/personas/en/default.md': 'new persona',
        }
        for name in installer.RUNTIME_MODULES:
            contents.setdefault(f'assets/scripts/crosstalk_lib/{name}.py', '# fixture runtime module\n')
        for name in installer.RUNTIME_TEMPLATES:
            contents[f'assets/scripts/crosstalk_lib/engine/templates/{name}'] = 'fixture task template'
        for rel, body in contents.items():
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)

    def install(self, **kwargs):
        return installer.install(self.source, self.home, **kwargs)

    def test_install_complete_and_smoke_via_wrapper_from_unrelated_cwd(self):
        result = self.install(language='ko')
        self.assertTrue(result['installed'])
        self.assertEqual(installer.inspect(self.root)['status'], 'healthy')
        self.assertFalse((self.root / 'maintenance.json').exists())
        executable = self.home / '.local/bin/crosstalk'
        run = subprocess.run([str(executable), 'capabilities', '--json'], cwd='/', capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['protocol_version'], 3)
        self.assertEqual(json.loads((self.root / 'config.json').read_text())['language'], 'ko')
        self.assertEqual((self.root / 'mailbox.sqlite3').stat().st_mode & 0o077, 0)

    def test_custom_files_config_and_presets_are_preserved(self):
        self.root.mkdir(mode=0o700)
        config = {'language': 'en', 'custom': {'value': 42}}
        (self.root / 'config.json').write_text(json.dumps(config))
        rule = self.root / 'rules/en/default.md'
        rule.parent.mkdir(parents=True)
        rule.write_text('personal rule')
        command = self.home / '.claude/commands/crosstalk.md'
        command.parent.mkdir(parents=True)
        command.write_text('personal command')
        result = self.install()
        self.assertEqual(rule.read_text(), 'personal rule')
        self.assertEqual(json.loads((self.root / 'config.json').read_text())['custom'], {'value': 42})
        backups = [entry for entry in result['backups'] if entry['path'] == str(command)]
        self.assertEqual(Path(backups[0]['backup']).read_text(), 'personal command')
        self.assertEqual(command.read_text(), 'new command')

    def test_unrelated_symlink_blocks_before_database_mutation(self):
        local = self.home / '.local/bin/crosstalk'
        local.parent.mkdir(parents=True)
        local.symlink_to('/unrelated/tool')
        with self.assertRaisesRegex(ValueError, 'Unrelated'):
            self.install()
        self.assertEqual(os.readlink(local), '/unrelated/tool')
        self.assertFalse((self.root / 'mailbox.sqlite3').exists())

    def test_destination_symlink_ancestor_is_rejected(self):
        other = self.base / 'other'
        other.mkdir()
        (self.home / '.codex').symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.install()
        self.assertEqual(list(other.iterdir()), [])

    def test_partial_install_resumes_same_release(self):
        with mock.patch.object(installer, '_put', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                self.install()
        manifest = json.loads((self.root / installer.MANIFEST).read_text())
        self.assertEqual(manifest['phase'], 'activated')
        self.assertTrue((self.root / 'maintenance.json').exists())
        self.assertEqual(installer.inspect(self.root)['status'], 'incomplete')
        result = self.install()
        self.assertTrue(result['installed'])
        self.assertEqual(json.loads((self.root / installer.MANIFEST).read_text())['install_id'], manifest['install_id'])
        self.assertFalse((self.root / 'maintenance.json').exists())

    def test_partial_install_rejects_different_release(self):
        with mock.patch.object(installer, '_pointer', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.install()
        (self.source / 'assets/codex-skills/crosstalk/SKILL.md').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'exact interrupted release'):
            self.install()

    def test_failure_before_pointer_keeps_previous_runtime(self):
        self.install()
        previous = os.readlink(self.root / 'current')
        (self.source / 'assets/user-commands/crosstalk.md').write_text('update')
        real_invoke = installer._invoke
        def fail_migrate(argv, *args):
            if argv[-1] == 'migrate':
                raise ValueError('DB migration failed')
            return real_invoke(argv, *args)
        with mock.patch.object(installer, '_invoke', side_effect=fail_migrate):
            with self.assertRaisesRegex(ValueError, 'DB migration failed'):
                self.install()
        self.assertEqual(os.readlink(self.root / 'current'), previous)
        self.assertEqual((self.home / '.claude/commands/crosstalk.md').read_text(), 'new command')
        self.assertTrue((self.root / 'mailbox.sqlite3').exists())

    def test_legacy_downgrade_rejected_without_touching_v2_messages(self):
        self.install()
        db = self.root / 'mailbox.sqlite3'
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO messages VALUES('completed')")
        old = db.read_bytes()
        (self.source / 'VERSION').write_text('0.10.6')
        with self.assertRaisesRegex(ValueError, 'down-migration'):
            self.install()
        self.assertEqual(db.read_bytes(), old)

    def test_active_claim_requires_explicit_quiescence(self):
        self.install()
        with sqlite3.connect(self.root / 'mailbox.sqlite3') as conn:
            conn.execute("INSERT INTO messages VALUES('processing')")
        with self.assertRaisesRegex(ValueError, 'Active claims'):
            self.install()
        self.assertTrue(self.install(quiesced=True)['installed'])

    def test_uninstall_only_unchanged_owned_files_and_preserves_state(self):
        self.install()
        skill = self.home / '.codex/skills/crosstalk/SKILL.md'
        skill.write_text('user customization')
        unknown = skill.parent / 'personal.txt'
        unknown.write_text('keep')
        worktree = self.root / 'reviews/worktree'
        worktree.mkdir(parents=True)
        (worktree / 'user.txt').write_text('important')
        result = installer.uninstall(self.home)
        self.assertIn(str(skill), result['retained_modified'])
        self.assertEqual(skill.read_text(), 'user customization')
        self.assertEqual(unknown.read_text(), 'keep')
        self.assertTrue((self.root / 'mailbox.sqlite3').exists())
        self.assertTrue((self.root / 'config.json').exists())
        self.assertEqual((worktree / 'user.txt').read_text(), 'important')
        self.assertFalse((self.home / '.claude/scripts/crosstalk').exists())
        self.assertFalse((self.home / '.local/bin/crosstalk').is_symlink())
        self.assertTrue(installer.uninstall(self.home)['uninstalled'])

    def test_uninstall_preserves_retargeted_symlink(self):
        self.install()
        local = self.home / '.local/bin/crosstalk'
        local.unlink()
        local.symlink_to('/new/tool')
        result = installer.uninstall(self.home)
        self.assertIn(str(local), result['retained_modified'])
        self.assertEqual(os.readlink(local), '/new/tool')

    def test_uninstall_refuses_active_claims(self):
        self.install()
        with sqlite3.connect(self.root / 'mailbox.sqlite3') as conn:
            conn.execute("INSERT INTO messages VALUES('processing')")
        with self.assertRaisesRegex(ValueError, 'Active claims'):
            installer.uninstall(self.home)
        self.assertTrue((self.home / '.local/bin/crosstalk').exists())
        self.assertEqual(installer.inspect(self.root)['status'], 'healthy')


    def test_uninstall_reinstall_restages_and_retains_modified_release(self):
        self.install()
        release = (self.root / 'current').resolve()
        modified = release / 'assets/scripts/crosstalk_lib/cli.py'
        modified.write_text('# personal edit')
        unknown = release / 'personal.txt'
        unknown.write_text('personal extra file')
        installer.uninstall(self.home)
        result = self.install()
        retained = Path(result['retained_release'])
        self.assertEqual((retained / 'assets/scripts/crosstalk_lib/cli.py').read_text(), '# personal edit')
        self.assertEqual((retained / 'personal.txt').read_text(), 'personal extra file')
        self.assertEqual(installer.inspect(self.root)['status'], 'healthy')
        self.assertEqual(modified.read_text(), '# personal edit')
        current = (self.root / 'current').resolve() / 'assets/scripts/crosstalk_lib/cli.py'
        self.assertEqual(current.read_text(), '# fixture CLI above\n')

    def test_invalid_python_and_shell_sources_return_operational_json(self):
        repo = Path(__file__).resolve().parents[1]
        for rel, invalid in [('assets/scripts/crosstalk_lib/cli.py', 'def broken(\n'),
                             ('assets/scripts/crosstalk_bridge.sh', 'if then\n')]:
            with self.subTest(rel=rel):
                path = self.source / rel
                original = path.read_text()
                path.write_text(invalid)
                result = subprocess.run([sys.executable, str(repo / 'assets/scripts/crosstalk'), 'install',
                                         '--source', str(self.source), '--home', str(self.home)],
                                        capture_output=True, text=True, timeout=30)
                path.write_text(original)
                self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)['error']['code'], 'OPERATION_FAILED')
                self.assertNotIn('Traceback', result.stderr)
                self.assertFalse((self.root / 'mailbox.sqlite3').exists())

    def test_install_timeout_returns_operational_json_from_cli(self):
        repo = Path(__file__).resolve().parents[1]
        argv = ['install', '--source', str(self.source), '--home', str(self.home)]
        code = ("import sys,subprocess; from unittest.mock import patch; "
                "sys.path.insert(0," + repr(str(repo / 'assets/scripts')) + "); "
                "from crosstalk_lib.cli import main; "
                "from crosstalk_lib import installer\n"
                "with patch.object(installer, '_invoke', side_effect=subprocess.TimeoutExpired('migrate',30)):\n"
                "    sys.exit(main(" + repr(argv) + "))\n")
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['error']['code'], 'OPERATION_FAILED')
        self.assertNotIn('Traceback', result.stderr)
        self.assertTrue((self.root / 'maintenance.json').exists())
        self.assertTrue(self.install()['installed'])

    def test_malformed_manifest_is_a_value_error(self):
        self.root.mkdir(mode=0o700)
        (self.root / installer.MANIFEST).write_text('{"phase":"complete"}')
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            installer.inspect(self.root)


    def test_uninstall_without_manifest_refuses_guess(self):
        with self.assertRaisesRegex(ValueError, 'manifest'):
            installer.uninstall(self.home)

    def test_immutable_release_corruption_detected(self):
        self.install()
        target = (self.root / 'current').resolve() / 'assets/scripts/crosstalk_lib/cli.py'
        target.write_text('# tampered')
        self.assertEqual(installer.inspect(self.root)['status'], 'incomplete')
        self.install()
        self.assertEqual(target.read_text(), '# tampered')
        replacement = (self.root / 'current').resolve() / 'assets/scripts/crosstalk_lib/cli.py'
        self.assertNotEqual(replacement, target)
        self.assertEqual(replacement.read_bytes(), (self.source / 'assets/scripts/crosstalk_lib/cli.py').read_bytes())
        self.assertEqual(installer.inspect(self.root)['status'], 'healthy')

    def test_bridge_wrapper_blocks_maintenance(self):
        self.install()
        (self.root / 'maintenance.json').write_text('{}')
        run = subprocess.run([str(self.home / '.claude/scripts/crosstalk_bridge.sh')], capture_output=True, text=True)
        self.assertEqual(run.returncode, 6)
        self.assertIn('incomplete', run.stderr)

    def test_insecure_state_permissions_are_not_silently_changed(self):
        self.root.mkdir(mode=0o755)
        self.root.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'private'):
            self.install()
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o755)
        self.assertFalse((self.root / 'mailbox.sqlite3').exists())


    def test_real_migration_commit_survives_lost_stdout_and_resume(self):
        repo = Path(__file__).resolve().parents[1]
        self.root.mkdir(mode=0o700)
        database = self.root / 'mailbox.sqlite3'
        with sqlite3.connect(database) as conn:
            conn.execute("CREATE TABLE messages(id TEXT,thread_id TEXT,reply_to TEXT,sender TEXT,recipient TEXT,body TEXT,mode TEXT,round INTEGER,status TEXT,created_at TEXT,received_at TEXT)")
            conn.execute("INSERT INTO messages VALUES('saved','saved',NULL,'pane-a','pane-b','keep me','analyze',1,'pending','2026-10-29',NULL)")
        database.chmod(0o600)
        invoke = installer._invoke
        def lost_stdout(argv, *args):
            result = invoke(argv, *args)
            if argv[-1] == 'migrate':
                raise RuntimeError('lost stdout after commit')
            return result
        with mock.patch.object(installer, '_invoke', side_effect=lost_stdout):
            with self.assertRaisesRegex(RuntimeError, 'lost stdout'):
                installer.install(repo, self.home)
        manifest = json.loads((self.root / installer.MANIFEST).read_text())
        self.assertTrue(Path(manifest['migration_backup']).is_file())
        self.assertFalse((self.root / 'current').exists())
        with sqlite3.connect(database) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT body FROM messages').fetchone()[0], 'keep me')
        result = installer.install(repo, self.home)
        self.assertEqual(result['migration_backup'], manifest['migration_backup'])
        self.assertTrue(result['installed'])
        self.assertEqual(installer.inspect(self.root)['status'], 'healthy')


    def test_presets_only_does_not_create_database_or_runtime(self):
        result = installer.refresh_presets(self.source, self.home, 'ko')
        self.assertTrue(result['presets_refreshed'])
        self.assertTrue((self.root / 'rules/en/default.md').exists())
        self.assertFalse((self.root / 'mailbox.sqlite3').exists())
        self.assertFalse((self.root / 'current').exists())

    def test_real_repository_install_wrapper_doctor_and_remove(self):
        repo = Path(__file__).resolve().parents[1]
        env = dict(os.environ, HOME=str(self.home))
        command = [sys.executable, str(repo / 'assets/scripts/crosstalk'), 'install',
                   '--source', str(repo), '--home', str(self.home)]
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        executable = self.home / '.local/bin/crosstalk'
        caps = subprocess.run([str(executable), 'capabilities', '--json'], cwd='/', env=env,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(caps.returncode, 0, caps.stdout + caps.stderr)
        data = json.loads(caps.stdout)
        self.assertEqual(data['installation_health']['status'], 'healthy')
        self.assertEqual(data['schema_version'], 3)
        self.assertTrue(Path(data['mailbox_instructions']).is_file())
        doctor = subprocess.run([str(executable), 'doctor', '--offline'], cwd='/', env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertEqual(json.loads(doctor.stdout)['issues'], [])
        remove = subprocess.run([str(executable), 'uninstall'], cwd='/', env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(remove.returncode, 0, remove.stdout + remove.stderr)
        self.assertTrue((self.root / 'mailbox.sqlite3').exists())
        self.assertFalse(executable.exists())
        reinstall = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(reinstall.returncode, 0, reinstall.stdout + reinstall.stderr)
        self.assertTrue(executable.exists())
        self.assertEqual(installer.inspect(self.root)['status'], 'healthy')


    def test_real_missing_skill_is_diagnosed_and_blocks_work(self):
        repo = Path(__file__).resolve().parents[1]
        installer.install(repo, self.home)
        skill = self.home / '.codex/skills/crosstalk/SKILL.md'
        skill.unlink()
        database = self.root / 'mailbox.sqlite3'
        before = database.read_bytes()
        executable = self.home / '.local/bin/crosstalk'
        diagnosis = subprocess.run([str(executable), 'doctor', '--offline'],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(diagnosis.returncode, 0, diagnosis.stdout + diagnosis.stderr)
        issues = json.loads(diagnosis.stdout)['issues']
        self.assertTrue(any(item['code'] == 'INSTALLATION_INCOMPLETE' and str(skill) in item['detail'] for item in issues))
        send = subprocess.run([str(executable), 'send', 'codex', 'must not be saved'],
                              capture_output=True, text=True, timeout=30)
        self.assertNotEqual(send.returncode, 0)
        self.assertEqual(json.loads(send.stdout)['error']['code'], 'INSTALLATION_INCOMPLETE')
        self.assertEqual(database.read_bytes(), before)

    def test_bootstrap_diagnoses_missing_modules_without_importing_them(self):
        repo = Path(__file__).resolve().parents[1]
        installer.install(repo, self.home)
        package = (self.root / 'current').resolve() / 'assets/scripts/crosstalk_lib'
        executable = self.home / '.local/bin/crosstalk'
        database = self.root / 'mailbox.sqlite3'
        before = database.read_bytes()
        manifest = (self.root / installer.MANIFEST).read_bytes()
        for name in ('mailbox.py', 'doctor.py', 'cli.py', 'db.py', 'installer.py', '__init__.py'):
            with self.subTest(module=name):
                module = package / name
                original = module.read_bytes()
                module.unlink()
                try:
                    for command in (['doctor', '--offline', '--json'], ['receive']):
                        result = subprocess.run([str(executable), *command], cwd='/',
                                                capture_output=True, text=True, timeout=30)
                        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
                        data = json.loads(result.stdout)
                        self.assertEqual(data['error']['code'], 'INSTALLATION_INCOMPLETE')
                        self.assertIn(name, str(data['issues']))
                        self.assertIn('source', data['next_action'])
                        self.assertNotIn('Traceback', result.stderr)
                finally:
                    module.write_bytes(original)
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual((self.root / installer.MANIFEST).read_bytes(), manifest)

    def test_bootstrap_refuses_corrupt_runtime_before_import(self):
        repo = Path(__file__).resolve().parents[1]
        installer.install(repo, self.home)
        module = (self.root / 'current').resolve() / 'assets/scripts/crosstalk_lib/mailbox.py'
        marker = self.base / 'should-not-run'
        module.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
        result = subprocess.run([str(self.home / '.local/bin/crosstalk'), 'doctor', '--offline'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['error']['code'], 'INSTALLATION_INCOMPLETE')
        self.assertFalse(marker.exists())


    def test_missing_required_file_fails_without_installation(self):
        (self.source / 'assets/scripts/crosstalk_lib/cli.py').unlink()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            self.install()
        self.assertFalse((self.root / installer.MANIFEST).exists())

    def test_missing_engine_assets_preserve_existing_installation(self):
        self.install()
        before_manifest = (self.root / installer.MANIFEST).read_bytes()
        before_database = (self.root / 'mailbox.sqlite3').read_bytes()
        before_pointer = os.readlink(self.root / 'current')
        paths = ['assets/codex-skills/crosstalk/discussion.md', 'assets/scripts/crosstalk_terminal.sh']
        paths += [f'assets/scripts/crosstalk_lib/engine/templates/{name}' for name in installer.RUNTIME_TEMPLATES]
        for rel in paths:
            with self.subTest(path=rel):
                source = self.source / rel
                original = source.read_bytes()
                source.unlink()
                try:
                    with self.assertRaisesRegex(ValueError, 'Incomplete release'):
                        self.install()
                    self.assertEqual((self.root / installer.MANIFEST).read_bytes(), before_manifest)
                    self.assertEqual((self.root / 'mailbox.sqlite3').read_bytes(), before_database)
                    self.assertEqual(os.readlink(self.root / 'current'), before_pointer)
                finally:
                    source.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
