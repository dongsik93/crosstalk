"""Cross-command disclosure and workflow ownership checks through the real CLI."""
import json
import sqlite3
import unittest
from engine_helpers import EngineCase, A, B, C


class EngineBoundaries(EngineCase):
    def test_early_reply_is_hidden_across_all_public_read_paths(self):
        run = self.start()
        local = self.take(self.actions(run)[0]['action_id'])
        peer = self.take(self.actions(run, B)[0]['action_id'], B)
        secret = 'PEER_SECRET_BEFORE_INITIAL_9e33'
        self.submit(peer, secret, B)
        reply = self.rows("SELECT id FROM messages WHERE kind='reply'")[0]['id']
        request = peer['message_id']
        database = self.state / 'mailbox.sqlite3'
        before = database.read_bytes()
        notifications = self.log.read_bytes()
        for command in [('run','next',run), ('run','status',run), ('run','report',run),
                        ('history',request), ('status',reply), ('doctor','--offline'),
                        ('receive',reply), ('recover',reply)]:
            with self.subTest(command=command):
                value = self.call(*command)
                self.assertNotIn(secret, json.dumps(value))
        self.assertNotIn(secret, json.dumps(self.call('run','export',run,code=5)))
        self.assertNotIn(secret, self.log.read_text())
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(self.log.read_bytes(), notifications)
        # The caller's earlier input handle survives a peer-driven run revision.
        self.submit(local, 'independent caller answer')
        self.assertIn(secret, json.dumps(self.call('run','report',run)))

    def test_pause_defers_initial_reply_disclosure_until_continue(self):
        run = self.start()
        local = self.take(self.actions(run)[0]['action_id'])
        peer = self.take(self.actions(run, B)[0]['action_id'], B)
        self.call('run','pause',run,'--operation-id','pause','--reason','explicit hold')
        secret = 'PEER_RESULT_SAVED_WHILE_PAUSED'
        self.submit(peer, secret, B)
        self.submit(local, 'caller position saved while paused')
        self.assertEqual(self.rows('SELECT lifecycle FROM discussion_runs')[0]['lifecycle'],'paused')
        self.assertNotIn(secret,json.dumps(self.call('run','report',run)))
        self.assertNotIn(secret,json.dumps(self.call('history',peer['message_id'])))
        self.assertFalse(self.actions(run))
        self.call('run','continue',run,'--operation-id','continue')
        self.assertIn(secret,json.dumps(self.call('run','report',run)))
        self.assertEqual(len([a for a in self.actions(run) if a['kind']=='compare']),1)

    def test_local_rebind_requires_explicit_epoch_handoff(self):
        run = self.start()
        local = self.take(self.actions(run)[0]['action_id'])
        issued = self.call('session','challenge','--surface',A,'--kind','codex',
                           '--session-id',self.logical[A],'--expected-generation','1',
                           '--protocol','3','--engine-version','1')
        self.call('session','rebind','--challenge',issued['challenge'],'--kind','codex',
                  '--protocol','3','--engine-version','1','--confirm-transfer')
        self.assertEqual(self.submit(local,'stale position',code=5)['error']['code'],'STALE_ACTION')
        self.call('run','continue',run,'--operation-id','handoff','--confirm-rebind')
        new = self.take(local['action_id'])
        self.assertGreater(new['action_epoch'],local['action_epoch'])
        self.assertEqual(new['input_digest'],local['input_digest'])
        self.submit(new,'current position')
        self.assertEqual(self.rows("SELECT count(*) AS n FROM discussion_actions WHERE kind='local_initial' AND status='completed'")[0]['n'],1)

    def test_unsupported_caller_and_old_readiness_create_no_work(self):
        result = self.call('run','start','claude','test','--operation-id','agy-caller',actor=C,code=7)
        self.assertEqual(result['error']['code'],'CAPABILITY_UNSUPPORTED')
        with sqlite3.connect(self.state/'mailbox.sqlite3') as conn:
            conn.execute('UPDATE bindings SET protocol_version=2,engine_version=0 WHERE session_id=?',(self.logical[A],))
        result = self.call('run','start','claude','test','--operation-id','old-caller',code=6)
        self.assertEqual(result['error']['code'],'PROTOCOL_MISMATCH')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM discussion_runs')[0]['n'],0)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM messages')[0]['n'],0)
        self.assertFalse(self.log.exists())


if __name__ == '__main__':
    unittest.main()
