"""Run workflow recovery reuses existing mailbox claims and binding fences."""
import json
from contextlib import closing
import sqlite3
import unittest
from engine_helpers import EngineCase, A, B


class RecoveryTests(EngineCase):
    def expire(self,mid):
        with closing(sqlite3.connect(self.state/'mailbox.sqlite3')) as conn, conn:
            conn.execute('UPDATE messages SET lease_expires_at=0 WHERE id=?',(mid,))

    def reclaim(self,handle,actor=A):
        return self.call('recover',handle['message_id'],'--reclaim',
                         '--expected-claim-version',str(handle['claim_version']),
                         '--confirm-external-effects',actor=actor)

    def rebind(self,actor):
        current=self.rows('SELECT generation FROM bindings WHERE session_id=? AND active=1',self.logical[actor])[0]['generation']
        kind='codex' if actor==A else 'claude'
        request=self.call('session','challenge','--surface',actor,'--kind',kind,'--session-id',self.logical[actor],
                          '--expected-generation',str(current),'--protocol','3','--engine-version','1',actor=actor)
        return self.call('session','rebind','--challenge',request['challenge'],'--kind',kind,
                         '--protocol','3','--engine-version','1','--confirm-transfer',actor=actor)

    def test_peer_recover_reuses_message_action_and_rejects_old_token(self):
        run=self.start()
        peer=self.take(self.actions(run,B)[0]['action_id'],B)
        self.expire(peer['message_id'])
        recovered=self.reclaim(peer,B)
        self.assertEqual(recovered['id'],peer['message_id'])
        self.assertEqual(recovered['claim_version'],peer['claim_version']+1)
        old=self.submit(peer,'old attempt',actor=B,op='old',code=5)
        self.assertEqual(old['error']['code'],'STALE_LEASE')
        current=self.call('run','take',peer['action_id'],'--lease-token',recovered['lease_token'],actor=B)
        self.assertEqual(current['action_id'],peer['action_id'])
        self.submit(current,'recovered peer answer',actor=B,op='new')
        self.assertEqual(len(self.rows("SELECT id FROM messages WHERE run_id=? AND kind='request'",run)),1)
        self.assertEqual(self.call('run','status',run)['round'],1)

    def test_comparison_recovery_never_repeats_peer_analysis(self):
        run=self.start();self.both(run)
        comparison=self.compare(run)
        peer_before=self.rows("SELECT action_id,result_ref,result_hash FROM discussion_actions WHERE run_id=? AND kind='peer_analysis'",run)
        self.expire(comparison['message_id'])
        recovered=self.reclaim(comparison)
        current=self.call('run','take',comparison['action_id'],'--lease-token',recovered['lease_token'])
        self.assertEqual(current['input_digest'],comparison['input_digest'])
        denied=self.decide(comparison,op='stale',code=5)
        self.assertEqual(denied['error']['code'],'STALE_LEASE')
        finished=self.decide(current,op='finish')
        self.assertEqual(finished['lifecycle'],'completed')
        self.assertEqual(peer_before,self.rows("SELECT action_id,result_ref,result_hash FROM discussion_actions WHERE run_id=? AND kind='peer_analysis'",run))
        self.assertEqual(len(self.rows("SELECT id FROM messages WHERE run_id=? AND kind='request'",run)),1)

    def test_rebinding_local_action_requires_explicit_epoch_handoff(self):
        run=self.start();local=self.take(self.actions(run)[0]['action_id'])
        self.rebind(A)
        self.assertEqual(self.submit(local,'old context',op='old',code=5)['error']['code'],'STALE_ACTION')
        self.assertEqual(self.call('run','continue',run,'--operation-id','no-confirm',code=5)['error']['code'],'STALE_ACTION')
        self.call('run','continue',run,'--operation-id','handoff','--confirm-rebind')
        fresh=self.take(local['action_id'])
        self.assertEqual(fresh['action_epoch'],local['action_epoch']+1)
        self.assertEqual(fresh['input_digest'],local['input_digest'])
        self.assertEqual(self.submit(local,'late old',op='late-old',code=5)['error']['code'],'STALE_ACTION')
        self.submit(fresh,'new instance first position',op='fresh')
        self.assertEqual(self.rows('SELECT status FROM discussion_actions WHERE action_id=?',local['action_id'])[0]['status'],'completed')

    def test_peer_rebind_fences_old_submission_and_recover_is_separate(self):
        run=self.start();peer=self.take(self.actions(run,B)[0]['action_id'],B)
        self.rebind(B)
        denied=self.submit(peer,'old peer',actor=B,op='old',code=5)
        self.assertIn(denied['error']['code'],('STALE_BINDING','STALE_LEASE'))
        status=self.call('recover',peer['message_id'],actor=B)
        self.assertTrue(status['reclaimable'])
        recovered=self.reclaim(peer,B)
        fresh=self.call('run','take',peer['action_id'],'--lease-token',recovered['lease_token'],actor=B)
        self.submit(fresh,'new peer',actor=B,op='new')
        self.assertEqual(self.call('run','status',run)['round'],1)

    def test_pause_accepts_inflight_results_but_defers_comparison_and_notifications(self):
        run=self.start();local=self.take(self.actions(run)[0]['action_id']);peer=self.take(self.actions(run,B)[0]['action_id'],B)
        notifications=self.log.read_bytes()
        self.call('run','pause',run,'--operation-id','pause','--reason','user waits')
        self.submit(peer,'peer while paused',B)
        self.submit(local,'caller while paused')
        self.assertEqual(self.log.read_bytes(),notifications)
        self.assertEqual(self.call('run','status',run)['lifecycle'],'paused')
        self.assertEqual(self.rows("SELECT COUNT(*) n FROM discussion_actions WHERE run_id=? AND kind='compare'",run)[0]['n'],0)
        self.assertTrue(self.call('run','report',run).get('redacted'), 'Paused initial submission must not release the peer result')
        self.assertNotIn('peer while paused',json.dumps(self.call('history',peer['message_id'])))
        self.call('run','continue',run,'--operation-id','continue')
        self.assertEqual(self.call('run','status',run)['phase'],'comparing')
        self.assertIn('peer while paused',json.dumps(self.call('run','report',run)))
        comparison=self.compare(run)
        self.call('run','pause',run,'--operation-id','pause-again','--reason','stop comparing')
        self.assertIn('peer while paused',json.dumps(self.call('run','report',run)))
        self.assertEqual(self.decide(comparison,op='paused-decision',code=5)['error']['code'],'RUN_PAUSED')
        self.call('run','continue',run,'--operation-id','continue-again')
        self.assertEqual(self.decide(comparison,op='done')['lifecycle'],'completed')

    def test_continue_does_not_revive_expired_comparison_lease(self):
        run=self.start();self.both(run);comparison=self.compare(run)
        self.call('run','pause',run,'--operation-id','pause','--reason','wait')
        self.expire(comparison['message_id'])
        self.call('run','continue',run,'--operation-id','continue')
        self.assertEqual(self.decide(comparison,op='expired',code=5)['error']['code'],'LEASE_EXPIRED')
        recovered=self.reclaim(comparison)
        fresh=self.call('run','take',comparison['action_id'],'--lease-token',recovered['lease_token'])
        self.assertEqual(self.decide(fresh,op='final')['lifecycle'],'completed')

    def test_cancel_invalidates_claims_and_retains_partial_records(self):
        run=self.start();local=self.take(self.actions(run)[0]['action_id']);peer=self.take(self.actions(run,B)[0]['action_id'],B)
        result=self.call('run','cancel',run,'--operation-id','cancel','--reason','scope changed')
        self.assertFalse(result['process_stopped'])
        self.assertEqual(self.submit(peer,'late peer',actor=B,code=5)['error']['code'],'RUN_TERMINAL')
        self.assertEqual(self.submit(local,'late caller',code=5)['error']['code'],'RUN_TERMINAL')
        self.assertEqual(self.rows('SELECT processing_state,lease_token_hash FROM messages WHERE id=?',peer['message_id'])[0],
                         {'processing_state':'cancelled','lease_token_hash':None})
        report=self.call('run','report',run)['report']
        self.assertTrue(report['partial'])
        self.assertIsNone(report['rounds'][0]['peer_result'])

    def test_take_repetition_without_token_does_not_reclaim(self):
        run=self.start();peer=self.take(self.actions(run,B)[0]['action_id'],B)
        denied=self.call('run','take',peer['action_id'],actor=B,code=5)
        self.assertEqual(denied['error']['code'],'ACTION_NOT_READY')
        same=self.call('run','take',peer['action_id'],'--lease-token',peer['lease_token'],actor=B)
        self.assertEqual(same['claim_version'],peer['claim_version'])
        self.assertEqual(same['lease_token'],peer['lease_token'])

    def test_paused_recover_cannot_mutate_message_at_attempt_limit(self):
        run=self.start();peer=self.take(self.actions(run,B)[0]['action_id'],B)
        with closing(sqlite3.connect(self.state/'mailbox.sqlite3')) as conn, conn:
            conn.execute('UPDATE messages SET lease_expires_at=0,attempt_count=3 WHERE id=?',(peer['message_id'],))
        self.call('run','pause',run,'--operation-id','pause','--reason','user paused')
        before=(self.state/'mailbox.sqlite3').read_bytes()
        result=self.call('recover',peer['message_id'],'--reclaim','--expected-claim-version',str(peer['claim_version']),
                         '--confirm-external-effects',actor=B,code=5)
        self.assertEqual(result['error']['code'],'RUN_PAUSED')
        self.assertEqual((self.state/'mailbox.sqlite3').read_bytes(),before)


if __name__=='__main__':
    unittest.main()
