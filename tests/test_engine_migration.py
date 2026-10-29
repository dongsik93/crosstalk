"""Schema-3 migration against the real, pinned v0.11 runtime and disposable state."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'assets/scripts'))
from crosstalk_lib import db, migrations
from crosstalk_lib.protocol import Error


class EngineMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ct-schema3-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / 'state'
        self.old = self.root / 'v011'
        with zipfile.ZipFile(REPO / 'tests/fixtures/crosstalk_v0_11.zip') as archive:
            archive.extractall(self.old)
        self.env = mock.patch.dict(os.environ, {'CROSSTALK_CONFIG_DIR': str(self.state)})
        self.env.start()
        self.addCleanup(self.env.stop)
        result = self.old_call('migrate')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['schema_version'], 2)
        self.path = self.state / 'mailbox.sqlite3'
        with closing(sqlite3.connect(self.path)) as conn, conn:
            for sid, kind, generation in [('a', 'codex', 7), ('b', 'claude', 11)]:
                conn.execute("INSERT INTO sessions VALUES(?,?,?,'ready','2026-10-29',NULL)", (sid, kind, 'cli-' + sid))
                conn.execute("INSERT INTO bindings VALUES(?,?,'ghostty',?,?,?,'before','before',1)",
                             (sid, 'instance-' + sid, 'ghostty:00000000-0000-0000-0000-00000000000' + ('1' if sid == 'a' else '2'), generation, '{}'))
            conn.execute("INSERT INTO challenges VALUES('nonce','a','surface','codex',2,7,9999999999,0)")
            for thread in ('thread-a', 'thread-b'):
                conn.execute("INSERT INTO threads VALUES(?,'a','b','analyze',10,'open')", (thread,))
            conn.execute("""INSERT INTO messages(seq,id,thread_id,kind,sender_session_id,recipient_session_id,
                           body,summary,round,processing_state,created_at,received_at,claim_version,
                           lease_token_hash,lease_expires_at,claim_binding_generation,claim_instance_id,attempt_count)
                           VALUES(17,'request-a','thread-a','request','a','b',?,'요약',1,'processing','later','received',
                                  3,?,9999999999,11,'instance-b',3)""", ('  원문\n$HOME\r\n', 'a' * 64))
            conn.execute("""INSERT INTO messages(seq,id,thread_id,kind,sender_session_id,recipient_session_id,
                           body,round,processing_state,created_at,completion_result)
                           VALUES(4,'request-b','thread-b','request','a','b','question',1,'completed','earlier',?)""",
                         (json.dumps({'reply_id': 'reply-b'}),))
            conn.execute("""INSERT INTO messages(seq,id,thread_id,kind,sender_session_id,recipient_session_id,
                           reply_to,body,round,created_at,verdict,confidence,verdict_source)
                           VALUES(40,'reply-b','thread-b','reply','b','a','request-b','answer',1,'earliest','agree','high','explicit')""")
            conn.execute("INSERT INTO delivery_attempts VALUES('attempt','request-a','surface',11,'unknown','before',NULL,'NOTIFICATION_UNKNOWN')")
            conn.execute("INSERT INTO events(event_type,metadata,created_at) VALUES('before','{}','before')")

    def old_call(self, *args, input=None, **extra):
        env = dict(os.environ, **extra)
        return subprocess.run([sys.executable, str(self.old / 'crosstalk'), *args], input=input,
                              env=env, capture_output=True, text=True, timeout=30)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return {table: ([row[1] for row in conn.execute(f'PRAGMA table_info({table})')],
                            conn.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall())
                    for table in ('sessions','bindings','challenges','threads','messages','delivery_attempts','events','review_runs')}

    def child(self, code):
        return subprocess.Popen([sys.executable, '-c', code],
                                env=dict(os.environ, PYTHONPATH=str(REPO / 'assets/scripts')),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_v2_requires_explicit_migration_without_mutation(self):
        before = self.path.read_bytes()
        with self.assertRaises(Error) as error:
            db.connect(readonly=True)
        self.assertEqual(error.exception.code, 'MIGRATION_REQUIRED')
        self.assertEqual(self.path.read_bytes(), before)

    def test_every_legacy_column_is_preserved_without_inferred_runs(self):
        before = self.snapshot()
        result = migrations.migrate()
        self.assertTrue(result['migrated'])
        with closing(sqlite3.connect(result['backup_path'])) as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(backup.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 3)
        with closing(db.connect(readonly=True)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 3)
            for table, (columns, rows) in before.items():
                projection = ','.join(columns)
                actual = [tuple(row) for row in conn.execute(f'SELECT {projection} FROM {table} ORDER BY rowid')]
                self.assertEqual(actual[:len(rows)], rows, table)
                if table != 'events': self.assertEqual(len(actual), len(rows), table)
            self.assertEqual([row[0] for row in conn.execute('SELECT execution_owner FROM threads')], ['mailbox-v2'] * 2)
            self.assertEqual([tuple(row) for row in conn.execute('SELECT protocol_version,engine_version FROM bindings')], [(2, 0)] * 2)
            for table in ('discussion_runs','discussion_rounds','discussion_actions','discussion_operations'):
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        stable = self.path.read_bytes()
        again = migrations.migrate()
        self.assertFalse(again['migrated'])
        self.assertEqual(again['backup_path'], result['backup_path'])
        self.assertEqual(self.path.read_bytes(), stable)

    def test_real_v011_writer_refuses_schema3_before_ui_or_db_changes(self):
        migrations.migrate()
        marker = self.root / 'ui-called'
        bridge = self.root / 'bridge'
        bridge.write_text('#!/bin/sh\ntouch ' + str(marker) + '\nexit 1\n')
        bridge.chmod(0o700)
        before = self.path.read_bytes()
        commands = [('send','claude','new'), ('receive',), ('reply','request-a','answer'),
                    ('ack','reply-b','--outcome','concluded','--result-stdin'),
                    ('recover','request-a','--reclaim','--expected-claim-version','3','--confirm-external-effects'),
                    ('retry','request-a'), ('migrate',)]
        for args in commands:
            with self.subTest(command=args[0]):
                result = self.old_call(*args, input='conclusion', CROSSTALK_BRIDGE=str(bridge))
                self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)['error']['code'], 'SCHEMA_TOO_NEW')
                self.assertFalse(marker.exists())
                self.assertEqual(self.path.read_bytes(), before)

    def test_fault_after_additions_rolls_back_existing_schema_and_data(self):
        before = self.snapshot()
        with mock.patch.object(db, 'event', side_effect=RuntimeError('fault before commit')):
            with self.assertRaisesRegex(RuntimeError, 'fault before commit'):
                migrations.migrate()
        self.assertEqual(self.snapshot(), before)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='discussion_runs'").fetchone())
        self.assertTrue(migrations.migrate()['migrated'])

    def test_failed_backup_does_not_begin_schema_change(self):
        before = self.snapshot()
        with mock.patch.object(migrations, '_backup', side_effect=OSError('backup space exhausted')):
            with self.assertRaisesRegex(OSError, 'backup space exhausted'):
                migrations.migrate()
        self.assertEqual(self.snapshot(), before)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_invalid_existing_relation_rolls_back_additive_upgrade(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE messages SET reply_to='missing-request' WHERE id='reply-b'")
        before = self.snapshot()
        with self.assertRaises(Error) as error:
            migrations.migrate()
        self.assertEqual(error.exception.code, 'MIGRATION_FAILED')
        self.assertEqual(self.snapshot(), before)

    def test_process_death_before_commit_and_retry(self):
        before = self.snapshot()
        process = self.child('from crosstalk_lib import db,migrations; import os; db.event=lambda *a,**k: os._exit(71); migrations.migrate()')
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 71, out + err)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(migrations.migrate()['migrated'])

    def test_commit_without_stdout_can_be_recovered_idempotently(self):
        process = self.child('from crosstalk_lib import migrations; import os; migrations.migrate(); os._exit(72)')
        out, err = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 72, out + err)
        result = migrations.migrate()
        self.assertFalse(result['migrated'])
        self.assertTrue(Path(result['backup_path']).is_file())
        self.assertEqual(len(list((self.state / 'backups').glob('*.sqlite3'))), 1)

    def test_concurrent_migration_applies_once(self):
        code = 'from crosstalk_lib import migrations; import json; print(json.dumps(migrations.migrate()))'
        processes = [self.child(code), self.child(code)]
        results = []
        for process in processes:
            out, err = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, err)
            results.append(json.loads(out))
        self.assertEqual(sum(result['migrated'] for result in results), 1)
        self.assertEqual(len(list((self.state / 'backups').glob('*.sqlite3'))), 1)


if __name__ == '__main__':
    unittest.main()
