"""Exercise the initial-position barrier through all public executable paths."""
import json
import unittest
from engine_helpers import EngineCase, A, B

SECRET_BODY='peer private initial analysis: 8f56ec3'
SECRET_SUMMARY='peer private conclusion: 37b812a'
SECRET_REASON='peer private reason: 986be1f'


class BarrierTests(EngineCase):
    def peer_first(self):
        run=self.start()
        local=self.take(self.actions(run)[0]['action_id'])
        peer=self.take(self.actions(run,B)[0]['action_id'],B)
        result=self.call('run','submit',peer['action_id'],'--operation-id','peer-private',
                         '--action-epoch',str(peer['action_epoch']),'--input-digest',peer['input_digest'],
                         '--lease-token',peer['lease_token'],'--claim-version',str(peer['claim_version']),
                         '--binding-generation',str(peer['binding_generation']),'--result-stdin',actor=B,
                         payload={'body':SECRET_BODY,'summary':SECRET_SUMMARY,'verdict':'disagree','reason':SECRET_REASON})
        return run,local,peer,result['result_id']

    def test_peer_first_has_no_public_read_or_notification_leak(self):
        run,local,peer,reply=self.peer_first()
        before=(self.state/'mailbox.sqlite3').read_bytes()
        values=[self.call('run','next',run), self.call('run','status',run),
                self.call('run','report',run,'--json'), self.call('history',peer['message_id']),
                self.call('status',reply),self.call('recover',reply),self.call('doctor','--offline'),
                self.call('receive',reply),self.call('receive')]
        denied=self.call('run','export',run,code=5)
        self.assertEqual(denied['error']['code'],'INITIAL_POSITION_REQUIRED')
        for value in values+[denied]:
            encoded=json.dumps(value)
            for secret in (SECRET_BODY,SECRET_SUMMARY,SECRET_REASON):
                self.assertNotIn(secret,encoded)
        for secret in (SECRET_BODY,SECRET_SUMMARY,SECRET_REASON):
            self.assertNotIn(secret,self.log.read_text())
        self.assertFalse((self.state/'exports').exists())
        self.assertEqual((self.state/'mailbox.sqlite3').read_bytes(),before)
        self.assertTrue(self.call('run','report',run)['redacted'])
        self.submit(local,'caller independent first position')
        exposed=self.call('run','report',run)
        self.assertIn(SECRET_BODY,json.dumps(exposed))

    def test_hidden_reply_does_not_block_unrelated_ready_mailbox_message(self):
        run,local,peer,reply=self.peer_first()
        ordinary=self.call('send','codex','ordinary ready message','--id','ordinary',actor=B)
        received=self.call('receive')
        self.assertEqual(received['id'],ordinary['id'])
        self.assertEqual(received['body'],'ordinary ready message')
        self.assertEqual(self.rows('SELECT processing_state FROM messages WHERE id=?',reply)[0]['processing_state'],'queued')
        self.assertEqual(self.rows('SELECT claim_version FROM messages WHERE id=?',reply)[0]['claim_version'],0)

    def test_dispatch_exposes_no_body_or_lease_and_does_not_claim(self):
        run=self.start()
        action=self.actions(run,B)[0]
        before=(self.state/'mailbox.sqlite3').read_bytes()
        dispatch=self.call('receive',actor=B)
        self.assertEqual(dispatch['handler'],'discussion')
        self.assertEqual(dispatch['action_id'],action['action_id'])
        self.assertEqual(dispatch['next_action']['command'],'run take')
        self.assertNotIn('body',dispatch)
        self.assertNotIn('lease_token',dispatch)
        self.assertEqual((self.state/'mailbox.sqlite3').read_bytes(),before)
        handle=self.take(action['action_id'],B)
        self.assertEqual(handle['claim_version'],1)
        self.assertIn('Exact original topic',handle['input']['task_text'])

    def test_peer_initial_input_never_contains_stored_caller_position(self):
        run=self.start()
        caller=self.take(self.actions(run)[0]['action_id'])
        self.submit(caller,'caller secret prior opinion f432cb1')
        peer=self.take(self.actions(run,B)[0]['action_id'],B)
        self.assertNotIn('f432cb1',json.dumps(peer))
        self.assertIsNone(peer['input']['caller_position'])

    def test_raw_mutations_cannot_bypass_engine_ownership(self):
        run,local,peer,reply=self.peer_first()
        commands=[(('reply',peer['message_id'],'raw answer'),B),
                  (('ack',reply,'--outcome','concluded','--result-stdin'),A),
                  (('send','claude','raw followup','--thread',peer['message_id'],'--after-reply',reply),A),
                  (('cancel',peer['message_id'],'--reason','raw cancel'),A)]
        before=(self.state/'mailbox.sqlite3').read_bytes()
        for args,actor in commands:
            result=self.call(*args,actor=actor,text='raw completion',code=5)
            self.assertEqual(result['error']['code'],'RUN_MANAGED_BY_ENGINE')
        self.assertEqual((self.state/'mailbox.sqlite3').read_bytes(),before)

    def test_explicit_cancel_releases_partial_transcript_without_fabricating_initial(self):
        run,local,peer,reply=self.peer_first()
        self.call('run','cancel',run,'--operation-id','cancel','--reason','user stops')
        value=self.call('run','report',run)['report']
        self.assertTrue(value['partial'])
        self.assertEqual(value['outcome'],'cancelled')
        self.assertIn(SECRET_BODY,json.dumps(value))
        self.assertIn('caller',value['missing_participants'])
        self.assertIsNone(value['initial_position'])
        self.assertIn(SECRET_BODY,json.dumps(self.call('history',peer['message_id'])))
        self.assertEqual(self.submit(local,'late initial',code=5)['error']['code'],'RUN_TERMINAL')


if __name__=='__main__':
    unittest.main()
