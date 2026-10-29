import unittest
from engine_helpers import EngineCase,A,B,C

class EngineProtocolTests(EngineCase):
    def test_actual_cli_one_round_to_saved_report(self):
        run=self.start();self.both(run)
        handle=self.compare(run);result=self.decide(handle)
        self.assertEqual(result['observed']['lifecycle'],'completed')
        report=self.call('run','report',run)['report']
        self.assertEqual(report['outcome'],'concluded')
        self.assertEqual(report['original_topic'],'Exact original topic\n한글')
        self.assertEqual(report['lifecycle'],'completed')
        self.assertEqual(report['rounds'][0]['peer_result']['body'],'peer initial')
        repeated=self.decide(handle)
        self.assertEqual(result['decision_id'],repeated['decision_id'])
        self.assertEqual(len(self.rows('SELECT * FROM messages')),2)

    def test_continue_keeps_prior_position_and_is_idempotent(self):
        run=self.start();self.both(run);handle=self.compare(run)
        first=self.decide(handle,'continue')
        same=self.decide(handle,'continue')
        self.assertEqual(first['message_id'],same['message_id'])
        self.assertEqual(len(self.rows("SELECT * FROM messages WHERE kind='request'")),2)
        peer=self.take(self.actions(run,B)[0]['action_id'],B)
        self.assertEqual(peer['input']['caller_position']['body'],'My fixed position')
        self.assertEqual(peer['input']['followup_body'],'Examine this counterexample')
        self.submit(peer,'Second-round answer',B)
        comparison=self.compare(run)
        self.assertEqual(comparison['input']['caller_position']['body'],'My fixed position')
        self.decide(comparison,outcome='diverged')
        report=self.call('run','report',run)['report']
        self.assertEqual(report['outcome'],'diverged')
        self.assertEqual(len(report['rounds']),2)

    def test_continue_at_cap_records_override_without_extra_request(self):
        run=self.start(max_rounds=1);self.both(run)
        self.decide(self.compare(run),'continue')
        report=self.call('run','report',run)['report']
        self.assertEqual(report['outcome'],'round_limit')
        self.assertEqual(report['decision']['requested_decision'],'continue')
        self.assertEqual(report['decision']['applied_decision'],'finish')
        self.assertEqual(report['decision']['override_reason'],'round_limit')
        self.assertEqual(len(self.rows("SELECT * FROM messages WHERE kind='request'")),1)

    def test_start_retry_uses_original_snapshot_and_conflicts_different_topic(self):
        config=self.state/'config.json';config.write_text('{"language":"en"}')
        run=self.start()
        config.write_text('{"language":"ko"}')
        self.assertEqual(self.start(),run)
        saved=self.rows('SELECT config_snapshot FROM discussion_runs WHERE run_id=?',run)[0]['config_snapshot']
        self.assertIn('"language":"en"',saved)
        self.call('run','start','claude','different','--operation-id','start',code=5)
        self.call('run','start','claude','another','--operation-id','new-start',code=5)
        self.assertEqual(len(self.rows('SELECT * FROM discussion_runs')),1)

    def test_invalid_handles_and_json_never_confirm_result(self):
        run=self.start();handle=self.take(self.actions(run)[0]['action_id'])
        flags=['run','submit',handle['action_id'],'--operation-id','bad','--action-epoch',str(handle['action_epoch']),'--input-digest',handle['input_digest'],'--result-stdin']
        for text in ('{"body":"a","body":"b"}','{"body":"a","confidence":NaN}','{"body":"a","unexpected":1}'):
            self.call(*flags,text=text,code=2)
        bad=dict(handle,input_digest='wrong')
        self.submit(bad,code=5)
        bad=dict(handle,action_epoch=handle['action_epoch']+1)
        self.submit(bad,code=5)
        self.assertEqual(self.rows('SELECT status FROM discussion_actions WHERE action_id=?',handle['action_id'])[0]['status'],'pending')

    def test_completed_result_conflict_preserves_first_body(self):
        run=self.start();local=self.take(self.actions(run)[0]['action_id'])
        self.submit(local,'first')
        self.submit(local,'changed',op='different-operation',code=5)
        peer=self.take(self.actions(run,B)[0]['action_id'],B);self.submit(peer,'peer',B)
        self.decide(self.compare(run),outcome='unresolved')
        report=self.call('run','report',run)['report']
        self.assertEqual(report['initial_position']['body'],'first')
        self.assertEqual(report['outcome'],'unresolved')

    def test_view_commands_are_read_only_and_redact_tokens(self):
        run=self.start();self.both(run);handle=self.compare(run)
        before=(self.state/'mailbox.sqlite3').read_bytes()
        for command in ('status','next','report'):
            data=self.call('run',command,run)
            self.assertNotIn(handle['lease_token'],str(data))
        self.call('doctor','--offline')
        self.assertEqual((self.state/'mailbox.sqlite3').read_bytes(),before)
        events=self.rows('SELECT metadata FROM events')
        self.assertNotIn(handle['lease_token'],str(events))


if __name__=='__main__':unittest.main()
