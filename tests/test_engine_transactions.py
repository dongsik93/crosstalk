import json
import os
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
from engine_helpers import EngineCase,A,B,CLI,ROOT
sys.path.insert(0,str(ROOT/'assets/scripts'))
from crosstalk_lib import db,mailbox,sessions
from crosstalk_lib.engine import service
from crosstalk_lib.protocol import Error

class EngineTransactionTests(EngineCase):
    def local(self,actor=A):
        patch=mock.patch.dict(os.environ,self.env);patch.start();self.addCleanup(patch.stop)
        conn=db.connect();self.addCleanup(conn.close)
        binding=dict(conn.execute(sessions.BINDING+'WHERE b.session_id=? AND b.active=1',(self.logical[actor],)).fetchone())
        return conn,binding

    def args(self,handle,op):
        return SimpleNamespace(id=handle['action_id'],operation_id=op,action_epoch=handle['action_epoch'],input_digest=handle['input_digest'],
                               lease_token=handle.get('lease_token'),claim_version=handle.get('claim_version'),binding_generation=handle.get('binding_generation'))

    def test_initial_transaction_rolls_back_request_actions_and_operation(self):
        conn,actor=self.local()
        args=SimpleNamespace(peer='claude',max_rounds=10,mode='analyze',peer_session=None,rules=None,persona=None,language=None,operation_id='failure-start')
        real=service._create_action
        def fail_after_peer(*items,**kwargs):
            result=real(*items,**kwargs)
            if items[2]=='peer_analysis':raise RuntimeError('after peer action')
            return result
        with mock.patch.object(service,'_create_action',side_effect=fail_after_peer),self.assertRaisesRegex(RuntimeError,'peer action'):
            service.start(conn,actor,args,'topic')
        for table in ('messages','threads','discussion_runs','discussion_actions','discussion_operations'):
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0,table)

    def test_reply_and_engine_result_rollback_together(self):
        run=self.start();peer=self.take(self.actions(run,B)[0]['action_id'],B)
        conn,actor=self.local(B)
        with mock.patch.object(service,'_advance_tx',side_effect=RuntimeError('after result')),self.assertRaises(RuntimeError):
            service.submit(conn,actor,self.args(peer,'failed-submit'),{'body':'saved only atomically'})
        self.assertEqual(len(self.rows("SELECT * FROM messages WHERE kind='reply'")),0)
        self.assertEqual(self.rows('SELECT status,result_ref FROM discussion_actions WHERE action_id=?',peer['action_id'])[0],{'status':'pending','result_ref':None})
        self.assertEqual(self.rows('SELECT processing_state FROM messages WHERE id=?',peer['message_id'])[0]['processing_state'],'processing')

    def decision_payload(self,handle,decision='continue'):
        value=dict(decision=decision,comparison_summary='compare',caller_position='position',cited_result_ids=handle['input']['cited_result_ids'],unresolved_questions=[],closing_summary='conclusion')
        if decision=='continue':value.update(followup_body='follow up',continuation_reason='resolve gap')
        else:value['requested_outcome']='concluded'
        return value

    def test_continue_rollback_includes_ack_request_and_decision(self):
        run=self.start();self.both(run);handle=self.compare(run);conn,actor=self.local()
        with mock.patch.object(service,'_create_action',side_effect=RuntimeError('after next request')),self.assertRaises(RuntimeError):
            service.decide(conn,actor,self.args(handle,'failed-decide'),self.decision_payload(handle))
        self.assertEqual(len(self.rows('SELECT * FROM messages')),2)
        self.assertEqual(self.rows('SELECT processing_state FROM messages WHERE id=?',handle['message_id'])[0]['processing_state'],'processing')
        self.assertEqual(self.rows('SELECT status FROM discussion_actions WHERE action_id=?',handle['action_id'])[0]['status'],'pending')

    def test_stored_finish_survives_finalizer_failure_without_peer_reanalysis(self):
        run=self.start();self.both(run);handle=self.compare(run);conn,actor=self.local()
        with mock.patch.object(service,'_finalize_tx',side_effect=RuntimeError('finalizer interrupted')),self.assertRaises(RuntimeError):
            service.decide(conn,actor,self.args(handle,'finish-interrupted'),self.decision_payload(handle,'finish'))
        self.assertEqual(self.call('run','status',run)['phase'],'finalizing')
        self.assertEqual(self.rows('SELECT processing_state FROM messages WHERE id=?',handle['message_id'])[0]['processing_state'],'completed')
        result=self.call('run','advance',run)
        self.assertEqual(result['lifecycle'],'completed')
        self.assertEqual(len(self.rows('SELECT * FROM messages')),2)
        self.assertEqual(self.call('run','report',run)['report']['decision']['closing_summary'],'conclusion')

    def test_postcommit_reporting_fault_preserves_run_and_same_operation(self):
        conn,actor=self.local()
        args=SimpleNamespace(peer='claude',max_rounds=10,mode='analyze',peer_session=None,rules=None,persona=None,language=None,operation_id='postcommit')
        with mock.patch.object(service,'observe',side_effect=sqlite3.OperationalError('read failure')):
            with self.assertRaises(Error) as caught:service.start(conn,actor,args,'topic')
        self.assertTrue(caught.exception.saved)
        run=caught.exception.run_id
        result=self.call('run','start','claude','topic','--operation-id','postcommit')
        self.assertEqual(result['run_id'],run)
        self.assertEqual(len(self.rows('SELECT * FROM messages')),1)

    def test_terminal_io_occurs_after_engine_transaction(self):
        conn,actor=self.local()
        args=SimpleNamespace(peer='claude',max_rounds=10,mode='analyze',peer_session=None,rules=None,persona=None,language=None,operation_id='outside-lock')
        checks=[]
        def notify(dbconn,*args,**kwargs):
            checks.append(dbconn.in_transaction)
            return {'delivery_state':'submitted'}
        with mock.patch.object(service.delivery,'notify',side_effect=notify):service.start(conn,actor,args,'topic')
        self.assertEqual(checks,[False])

    def test_concurrent_different_decisions_confirm_exactly_one(self):
        run=self.start();self.both(run);handle=self.compare(run)
        flags=['run','decide',handle['action_id'],'--action-epoch',str(handle['action_epoch']),'--input-digest',handle['input_digest'],'--lease-token',handle['lease_token'],'--claim-version',str(handle['claim_version']),'--binding-generation',str(handle['binding_generation']),'--result-stdin']
        procs=[]
        for index,outcome in enumerate(('concluded','diverged')):
            payload=self.decision_payload(handle,'finish');payload['requested_outcome']=outcome
            proc=subprocess.Popen([sys.executable,str(CLI),*flags,'--operation-id','race-'+str(index)],env=self.env|{'TEST_ACTOR':A},stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            proc.stdin.write(json.dumps(payload));proc.stdin.close();proc.stdin=None;procs.append(proc)
        results=[]
        for proc in procs:
            output,error=proc.communicate(timeout=30);results.append(proc.returncode)
        self.assertEqual(sorted(results),[0,5])
        self.assertEqual(len(self.rows('SELECT * FROM messages')),2)
        self.assertEqual(self.call('run','status',run)['lifecycle'],'completed')

if __name__=='__main__':unittest.main()
