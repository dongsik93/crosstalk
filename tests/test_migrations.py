#!/usr/bin/env python3
"""Migration invariants using disposable databases and the actual v0.10.6 writer."""
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'assets/scripts'))
from crosstalk_lib import db, migrations
from crosstalk_lib.protocol import Error

A = 'ghostty:00000000-0000-0000-0000-000000000001'
B = 'ghostty:00000000-0000-0000-0000-000000000002'
LEGACY_CLI = Path(__file__).with_name('fixtures') / 'crosstalk_v0_10_6.py'
LEGACY_SCHEMA = '''
CREATE TABLE messages (
 id TEXT PRIMARY KEY, thread_id TEXT NOT NULL,
 reply_to TEXT UNIQUE REFERENCES messages(id), sender TEXT NOT NULL, recipient TEXT NOT NULL,
 body TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('analyze','ask')),
 round INTEGER NOT NULL CHECK(round BETWEEN 1 AND 10),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','received','replied')),
 created_at TEXT NOT NULL, received_at TEXT, notify_error TEXT
);
CREATE INDEX inbox ON messages(recipient,status,created_at);
CREATE INDEX thread ON messages(thread_id,created_at);
'''


@contextmanager
def connection(path):
    with closing(sqlite3.connect(path)) as conn:
        with conn:
            yield conn


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.state = self.root / 'state'
        self.state.mkdir(mode=0o700)
        self.path = self.state / 'mailbox.sqlite3'
        self.env = mock.patch.dict(os.environ, {'CROSSTALK_CONFIG_DIR': str(self.state)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def legacy(self, summary=True):
        conn = sqlite3.connect(self.path)
        conn.executescript(LEGACY_SCHEMA)
        if summary:
            conn.execute("ALTER TABLE messages ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
        # Deliberately non-alphabetic IDs and regressing clocks; rowid is the queue order.
        items = [
            ('pending-z', 'pending-z', None, A, B, '한글 "quoted" $HOME\\n' * 20, 'analyze', 1, 'pending', '2026-10-29', None),
            ('interrupted-a', 'interrupted-a', None, B, A, 'received request', 'analyze', 1, 'received', '2026-10-28', '2026-10-28'),
            ('answered-m', 'answered-m', None, A, B, 'answered request', 'analyze', 1, 'replied', '2026-10-27', '2026-10-27'),
            ('reply-z', 'answered-m', 'answered-m', B, A, 'answer [AGREE]', 'analyze', 1, 'pending', '2026-10-26', None),
            ('ask-z', 'ask-z', None, B, A, 'ask request', 'ask', 1, 'replied', '2026-10-25', '2026-10-25'),
            ('reply-a', 'ask-z', 'ask-z', A, B, 'seen answer', 'ask', 1, 'received', '2026-10-24', '2026-10-24'),
        ]
        for row in items:
            conn.execute('INSERT INTO messages(id,thread_id,reply_to,sender,recipient,body,mode,round,status,created_at,received_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)', row)
        if summary:
            conn.execute("UPDATE messages SET summary='요약' WHERE id='pending-z'")
        conn.commit()
        conn.close()
        self.path.chmod(0o600)
        return items

    def dump(self):
        with connection(self.path) as conn:
            return '\n'.join(conn.iterdump())

    def process(self, code=None):
        code = code or 'from crosstalk_lib.migrations import migrate; import json; print(json.dumps(migrate()))'
        return subprocess.Popen([sys.executable, '-c', code], env=dict(os.environ, PYTHONPATH=str(REPO/'assets/scripts')),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_new_database_and_idempotent_migrate(self):
        result = migrations.migrate()
        self.assertTrue(result['created'])
        self.assertEqual(self.path.stat().st_mode & 0o077, 0)
        self.assertEqual(self.state.stat().st_mode & 0o077, 0)
        before = self.dump()
        self.assertEqual(migrations.migrate(), {'schema_version': 3, 'migrated': False})
        self.assertEqual(before, self.dump())
        self.assertFalse((self.state/'backups').exists())
        with closing(db.connect(readonly=True)) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_empty_database_left_by_interrupted_initialization_can_resume(self):
        with connection(self.path):
            pass
        self.path.chmod(0o600)
        self.assertTrue(migrations.migrate()['created'])
        with closing(db.connect(readonly=True)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 3)

    def test_database_with_unrecognized_tables_is_not_adopted(self):
        with connection(self.path) as conn:
            conn.execute('CREATE TABLE private_data(value TEXT)')
        self.path.chmod(0o600)
        before = self.dump()
        with self.assertRaises(Error) as error:
            migrations.migrate()
        self.assertEqual(error.exception.code, 'UNSUPPORTED_SCHEMA')
        self.assertEqual(before, self.dump())

    def test_sparse_rowids_remain_fifo_order(self):
        self.legacy()
        with connection(self.path) as conn:
            conn.execute("UPDATE messages SET rowid=100 WHERE id='reply-a'")
        migrations.migrate()
        with closing(db.connect(readonly=True)) as conn:
            self.assertEqual([r[0] for r in conn.execute('SELECT seq FROM messages ORDER BY seq')], [1,2,3,4,5,100])

    def test_preserves_every_message_and_relationship_with_backup(self):
        old = self.legacy()
        before = self.dump()
        result = migrations.migrate()
        self.assertEqual(result['message_count'], len(old))
        backup_path = Path(result['backup_path'])
        self.assertEqual(backup_path.stat().st_mode & 0o077, 0)
        with connection(backup_path) as backup:
            self.assertEqual('\n'.join(backup.iterdump()), before)
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        with closing(db.connect(readonly=True)) as conn:
            actual = conn.execute('SELECT * FROM messages ORDER BY seq').fetchall()
            self.assertEqual([r['seq'] for r in actual], list(range(1, len(old)+1)))
            self.assertEqual([r['id'] for r in actual], [r[0] for r in old])
            for expected, row in zip(old, actual):
                for name, value in zip(('id','thread_id','reply_to','sender','recipient','body','mode','round','status','created_at','received_at'), expected):
                    if name not in ('sender','recipient','mode','status'):
                        self.assertEqual(row[name], value)
                sender = conn.execute('SELECT legacy_surface FROM sessions WHERE session_id=?', (row['sender_session_id'],)).fetchone()[0]
                recipient = conn.execute('SELECT legacy_surface FROM sessions WHERE session_id=?', (row['recipient_session_id'],)).fetchone()[0]
                self.assertEqual((sender,recipient), expected[3:5])
            self.assertEqual(actual[0]['summary'], '요약')
            self.assertEqual([r['processing_state'] for r in actual], ['queued','recovery_required','completed','queued','completed','recovery_required'])
            self.assertEqual(actual[3]['verdict_source'], 'legacy_marker')
            self.assertEqual(actual[3]['verdict'], 'none')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM bindings').fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions WHERE status='unresolved'").fetchone()[0], 2)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 3)
            self.assertEqual(conn.execute("SELECT state FROM delivery_attempts WHERE message_id='reply-a'").fetchone()[0], 'suppressed')
        after = self.dump()
        self.assertFalse(migrations.migrate()['migrated'])
        self.assertEqual(after, self.dump())

    def test_missing_summary_is_empty_without_changing_body(self):
        old = self.legacy(summary=False)
        migrations.migrate()
        with closing(db.connect(readonly=True)) as conn:
            actual = conn.execute('SELECT body,summary FROM messages ORDER BY seq').fetchall()
            self.assertEqual([r['body'] for r in actual], [r[5] for r in old])
            self.assertEqual([r['summary'] for r in actual], [''] * len(old))

    def test_schema_creation_failure_rolls_back_entire_conversion(self):
        self.legacy()
        before = self.dump()
        original = migrations._execute_schema
        def fail(conn):
            original(conn)
            raise RuntimeError('injected after new tables')
        with mock.patch.object(migrations, '_execute_schema', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                migrations.migrate()
        self.assertEqual(before, self.dump())
        self.assertTrue(migrations.migrate()['migrated'])

    def test_process_death_before_commit_keeps_legacy_and_can_retry(self):
        self.legacy()
        before = self.dump()
        child = self.process('from crosstalk_lib import migrations,db; import os; db.event=lambda *a,**k: os._exit(97); migrations.migrate()')
        out, err = child.communicate(timeout=20)
        self.assertEqual(child.returncode, 97, (out,err))
        self.assertEqual(before, self.dump())
        self.assertTrue(migrations.migrate()['migrated'])

    def test_simultaneous_migrations_apply_once(self):
        self.legacy()
        processes = [self.process(), self.process()]
        results = []
        for child in processes:
            out, err = child.communicate(timeout=20)
            self.assertEqual(child.returncode, 0, err)
            results.append(json.loads(out))
        self.assertEqual(sum(bool(r['migrated']) for r in results), 1)
        self.assertEqual(len(list((self.state/'backups').glob('*.sqlite3'))), 1)
        with closing(db.connect(readonly=True)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 6)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM events WHERE event_type='migrated'").fetchone()[0], 1)

    def test_process_death_after_commit_leaves_complete_v3(self):
        self.legacy()
        child = self.process('from crosstalk_lib import migrations; import os; migrations.migrate(); os._exit(98)')
        out, err = child.communicate(timeout=20)
        self.assertEqual(child.returncode, 98, (out,err))
        before = self.dump()
        recovered = migrations.migrate()
        self.assertFalse(recovered['migrated'])
        self.assertEqual(recovered['message_count'], 6)
        self.assertEqual(Path(recovered['backup_path']), next((self.state/'backups').glob('*.sqlite3')))
        with connection(recovered['backup_path']) as backup:
            self.assertEqual(backup.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 6)
            self.assertIn('sender', [r[1] for r in backup.execute('PRAGMA table_info(messages)')])
        self.assertEqual(before, self.dump())
        with closing(db.connect(readonly=True)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 6)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_idempotent_result_recovers_migration_metadata_after_other_events(self):
        self.legacy()
        original = migrations.migrate()
        with connection(self.path) as conn:
            db.event(conn, 'unrelated', message_count=999, backup_path='not-a-migration')
        before = self.dump()
        recovered = migrations.migrate()
        self.assertFalse(recovered['migrated'])
        self.assertEqual(recovered['backup_path'], original['backup_path'])
        self.assertEqual(recovered['message_count'], original['message_count'])
        self.assertEqual(before, self.dump())

    def test_backup_is_private_before_sqlite_opens_it(self):
        self.legacy()
        real_connect = sqlite3.connect
        observed = []
        def inspect_backup(path, *args, **kwargs):
            if Path(path).parent.name == 'backups':
                observed.append(Path(path).stat().st_mode & 0o077)
            return real_connect(path, *args, **kwargs)
        old_umask = os.umask(0o022)
        try:
            with mock.patch.object(migrations.sqlite3, 'connect', side_effect=inspect_backup):
                migrations.migrate()
        finally:
            os.umask(old_umask)
        self.assertEqual(observed, [0])

    def test_newer_schema_rejected_without_changes(self):
        migrations.migrate()
        with connection(self.path) as conn:
            conn.execute('PRAGMA user_version=99')
        before = self.path.read_bytes()
        with self.assertRaises(Error) as error:
            migrations.migrate()
        self.assertEqual(error.exception.code, 'SCHEMA_TOO_NEW')
        self.assertEqual(before, self.path.read_bytes())

    def test_backup_failure_prevents_conversion(self):
        self.legacy()
        before = self.dump()
        real_connect = sqlite3.connect
        def failing_backup(path, *args, **kwargs):
            if Path(path).parent.name == 'backups':
                raise sqlite3.OperationalError('database or disk is full')
            return real_connect(path, *args, **kwargs)
        with mock.patch.object(migrations.sqlite3, 'connect', side_effect=failing_backup):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'disk is full'):
                migrations.migrate()
        self.assertEqual(before, self.dump())

    def test_unsafe_permissions_refuse_before_backup(self):
        self.legacy()
        self.path.chmod(0o644)
        before = self.path.read_bytes()
        with self.assertRaises(Error) as error:
            migrations.migrate()
        self.assertEqual(error.exception.code, 'UNSAFE_PERMISSIONS')
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse((self.state/'backups').exists())

    def test_invalid_relationship_rolls_back(self):
        self.legacy()
        with connection(self.path) as conn:
            conn.execute("UPDATE messages SET recipient=? WHERE id='reply-z'", (B,))
        before = self.dump()
        with self.assertRaises(Error):
            migrations.migrate()
        self.assertEqual(before, self.dump())

    def test_thread_participant_mismatch_rolls_back(self):
        self.legacy()
        with connection(self.path) as conn:
            conn.execute("INSERT INTO messages(id,thread_id,sender,recipient,body,mode,round,status,created_at,summary) VALUES('next','answered-m',?,?,'bad follow-up','analyze',2,'pending','2026-10-30','')", (B,A))
        before = self.dump()
        with self.assertRaises(Error):
            migrations.migrate()
        self.assertEqual(before, self.dump())

    def test_reply_to_uncompleted_request_rolls_back(self):
        self.legacy()
        with connection(self.path) as conn:
            conn.execute("UPDATE messages SET status='received' WHERE id='answered-m'")
        before = self.dump()
        with self.assertRaises(Error):
            migrations.migrate()
        self.assertEqual(before, self.dump())

    def add_followup(self, *, round_number=2, row_id='next-round'):
        with connection(self.path) as conn:
            conn.execute("UPDATE messages SET status='received' WHERE id='reply-z'")
            conn.execute("INSERT INTO messages(id,thread_id,sender,recipient,body,mode,round,status,created_at,summary) VALUES(?,'answered-m',?,?,'continued question','analyze',?,'pending','2026-10-30','next summary')", (row_id,A,B,round_number))

    def test_multiround_migration_retains_causality_through_bind_and_recovery(self):
        self.legacy()
        with connection(self.path) as conn:
            conn.execute("DELETE FROM messages WHERE id NOT IN ('answered-m','reply-z')")
        self.add_followup()
        bridge = self.root / 'bridge'
        bridge.write_text("#!/usr/bin/env python3\nimport os,json,sys\nactor=os.environ['TEST_ACTOR']\nif sys.argv[1]=='strict-identity': print(json.dumps(dict(surface_id=actor,kind='codex' if actor=="+repr(A)+" else 'claude',process_id=actor,process_start='test',cli_session_id='')))\nelse: sys.exit(1)\n")
        bridge.chmod(0o700)
        env = dict(os.environ, CROSSTALK_BRIDGE=str(bridge))
        cli = REPO / 'assets/scripts/crosstalk'
        def call(actor, *argv, text=None, ok=True):
            completed = subprocess.run([sys.executable,str(cli),*argv], input=text, capture_output=True,
                                       text=True, env=env | {'TEST_ACTOR':actor}, timeout=10)
            self.assertEqual(completed.returncode == 0, ok, (argv,completed.stdout,completed.stderr))
            return json.loads(completed.stdout)
        migrated = call(A, 'migrate')
        self.assertEqual(migrated['message_count'], 3)
        logical = {}
        with closing(db.connect(readonly=True)) as conn:
            rows = conn.execute('SELECT * FROM messages ORDER BY seq').fetchall()
            self.assertEqual([r['id'] for r in rows], ['answered-m','reply-z','next-round'])
            self.assertEqual([r['body'] for r in rows], ['answered request','answer [AGREE]','continued question'])
            self.assertEqual(rows[2]['caused_by_reply_id'], 'reply-z')
            self.assertEqual(rows[1]['processing_state'], 'completed')
            self.assertEqual(json.loads(rows[1]['completion_result']), {'next_request_id':'next-round'})
            logical = {r['legacy_surface']:r['session_id'] for r in conn.execute('SELECT * FROM sessions')}
        for address, kind in ((A,'codex'),(B,'claude')):
            challenge = call(address,'session','challenge','--surface',address,'--kind',kind,'--session-id',logical[address])
            call(address,'session','bind','--challenge',challenge['challenge'],'--kind',kind,'--protocol','2')
        self.assertFalse(call(A,'recover','reply-z')['reclaimable'])
        call(A,'recover','reply-z','--reclaim','--expected-claim-version','0','--confirm-external-effects',ok=False)
        call(A,'ack','reply-z','--outcome','concluded','--result-stdin',text='obsolete conclusion',ok=False)
        received = call(B,'receive')
        self.assertTrue(received['actionable'])
        self.assertEqual((received['id'],received['round'],received['body']), ('next-round',2,'continued question'))
        new_pane = 'ghostty:00000000-0000-0000-0000-000000000003'
        challenge = call(B,'session','challenge','--surface',new_pane,'--kind','claude','--session-id',logical[B],'--expected-generation','1')
        call(new_pane,'session','rebind','--challenge',challenge['challenge'],'--kind','claude','--protocol','2','--confirm-transfer')
        self.assertTrue(call(new_pane,'recover','next-round')['reclaimable'])
        resumed = call(new_pane,'recover','next-round','--reclaim','--expected-claim-version','1','--confirm-external-effects')
        self.assertEqual((resumed['id'],resumed['claim_version'],resumed['body']), ('next-round',2,'continued question'))
        self.assertTrue(resumed['actionable'])
        with closing(db.connect(readonly=True)) as conn:
            self.assertEqual(conn.execute('SELECT state FROM threads').fetchone()[0], 'open')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 3)
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())

    def test_followup_without_preceding_round_rolls_back(self):
        self.legacy()
        self.add_followup(round_number=3)
        before = self.dump()
        with self.assertRaisesRegex(Error, 'preceding reply'):
            migrations.migrate()
        self.assertEqual(before, self.dump())

    def test_followup_without_preceding_reply_rolls_back(self):
        self.legacy()
        self.add_followup()
        with connection(self.path) as conn:
            conn.execute("DELETE FROM messages WHERE id='reply-z'")
        before = self.dump()
        with self.assertRaisesRegex(Error, 'preceding reply'):
            migrations.migrate()
        self.assertEqual(before, self.dump())

    def test_followup_with_ambiguous_preceding_round_rolls_back(self):
        self.legacy()
        self.add_followup()
        self.add_followup(round_number=1, row_id='duplicate-first-round')
        before = self.dump()
        with self.assertRaisesRegex(Error, 'ambiguous request rounds'):
            migrations.migrate()
        self.assertEqual(before, self.dump())

    def test_followup_before_its_reply_rolls_back(self):
        self.legacy()
        self.add_followup()
        with connection(self.path) as conn:
            conn.execute("UPDATE messages SET rowid=100 WHERE id='reply-z'")
        before = self.dump()
        with self.assertRaisesRegex(Error, 'order does not establish causality'):
            migrations.migrate()
        self.assertEqual(before, self.dump())

    def test_legacy_writer_cannot_write_or_notify_after_migration(self):
        self.legacy()
        migrations.migrate()
        old_cli = self.root / 'old-crosstalk'
        old_cli.write_bytes(LEGACY_CLI.read_bytes())
        fake_bridge = self.root / 'bridge'
        fake_bridge.write_text("#!/usr/bin/env python3\nimport os,sys\nif sys.argv[1]=='self': print(os.environ['TEST_ACTOR'])\nelif sys.argv[1]=='list-peers': print("+repr(B+"\tclaude")+")\nelif sys.argv[1]=='send':\n with open(os.environ['TEST_LOG'],'a') as f: f.write('notification\\n')\nelse: print('en')\n")
        fake_bridge.chmod(0o700)
        log = self.root / 'notifications'
        before = self.dump()
        env = dict(os.environ, CROSSTALK_BRIDGE=str(fake_bridge), TEST_ACTOR=A, TEST_LOG=str(log))
        commands = [('send','claude','must not save'), ('receive',), ('reply','pending-z','must not reply'), ('retry','pending-z')]
        for argv in commands:
            with self.subTest(argv=argv):
                result = subprocess.run([sys.executable,str(old_cli),*argv], env=env, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(before, self.dump())
                self.assertFalse(log.exists())


if __name__ == '__main__':
    unittest.main()
