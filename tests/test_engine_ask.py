import json
import unittest
from engine_helpers import EngineCase,A,B

class EngineAskTests(EngineCase):
    def test_peer_first_ask_is_sampled_without_callback_or_fake_ack(self):
        run=self.start(mode='ask');initial=self.take(self.actions(run)[0]['action_id']);peer=self.take(self.actions(run,B)[0]['action_id'],B)
        before=self.log.read_text()
        answer=self.submit(peer,'peer independent answer',B)
        self.assertEqual(self.log.read_text(),before)
        self.assertTrue(self.call('run','report',run).get('redacted'))
        self.submit(initial,'caller independent answer')
        status=self.call('run','status',run);self.assertEqual(status['outcome'],'sampled')
        self.assertEqual(status['lifecycle'],'completed')
        self.assertFalse(self.rows("SELECT * FROM discussion_actions WHERE kind='compare'"))
        reply=self.rows("SELECT * FROM messages WHERE kind='reply'")[0]
        self.assertEqual(reply['processing_state'],'queued')
        self.assertIsNone(reply['completion_result'])
        self.assertFalse(self.call('receive')['actionable'])
        doctor=self.call('doctor','--offline')
        self.assertFalse(any(x['id']==reply['id'] for x in doctor['messages']))
        report=self.call('run','report',run)['report']
        self.assertIsNone(report['decision'])
        self.assertEqual(report['individual_answers']['peer']['body'],'peer independent answer')
        self.assertEqual(self.log.read_text(),before)

    def test_normal_mailbox_ask_keeps_its_legacy_receipt_semantics(self):
        run=self.start(mode='ask');self.both(run)
        sent=self.call('send','claude','ordinary ask','--mode','ask')
        request=self.call('receive',actor=B)
        self.assertEqual(request['id'],sent['id'])
        answer=self.call('reply',sent['id'],'ordinary response','--lease-token',request['lease_token'],actor=B)
        reply=self.call('receive')
        self.assertEqual(reply['id'],answer['id'])
        self.call('ack',reply['id'],'--lease-token',reply['lease_token'],'--outcome','observed','--result-stdin',text='observed')

if __name__=='__main__':unittest.main()
