#!/usr/bin/env python3
"""Ownership and interruption contracts against real SQLite transactions."""
import argparse
import contextlib
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'assets/scripts'))
from crosstalk_lib import cli, db, mailbox, sessions
from crosstalk_lib.protocol import Error


class Leases(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()/'state'
        self.env=patch.dict(os.environ,{'CROSSTALK_CONFIG_DIR':str(self.root)})
        self.env.start()
        self.conn=db.connect(initialize=True)
        self.actors=[]
        for sid,kind in (('a','codex'),('b','claude')):
            self.conn.execute("INSERT INTO sessions VALUES(?,?,NULL,'ready','now',NULL)",(sid,kind))
            self.conn.execute("INSERT INTO bindings VALUES(?,?, 'ghostty',?,1,'test','now','now',1)",(sid,sid+'instance',sid+'surface'))
            self.actors.append({'session_id':sid,'instance_id':sid+'instance','generation':1})
        self.conn.commit()
        self.a,self.b=self.actors
        self.notifications=patch('crosstalk_lib.delivery.notify',return_value={'notification_error':None,'delivery_state':'submitted'})
        self.notifications.start()

    def tearDown(self):
        self.notifications.stop();self.conn.close();self.env.stop();self.tmp.cleanup()

    def send(self, mid='request', **kwargs):
        args=argparse.Namespace(id=mid,peer='claude',peer_session=None,thread=None,after_reply=None,lease_token=None,mode='analyze',summary='')
        for key,value in kwargs.items(): setattr(args,key,value)
        return mailbox.send(self.conn,self.a,args,'question')

    def receive(self,actor,mid):
        return mailbox.receive(self.conn,actor,argparse.Namespace(id=mid,replay=False))

    def reply(self,token,body='answer',**kwargs):
        args=argparse.Namespace(id='request',lease_token=token,verdict='none',confidence='unknown',reason='',summary='first summary')
        for key,value in kwargs.items(): setattr(args,key,value)
        return mailbox.reply(self.conn,self.b,args,body)

    def reclaim(self,version,actor=None):
        return mailbox.recover(self.conn,actor or self.b,argparse.Namespace(id='request',reclaim=True,confirm_external_effects=True,expected_claim_version=version))

    def expire(self):
        self.conn.execute('UPDATE messages SET lease_expires_at=0 WHERE id=?',('request',));self.conn.commit()

    def assert_code(self,code,callback):
        with self.assertRaises(Error) as caught: callback()
        self.assertEqual(caught.exception.code,code)

    def test_expiry_is_read_only_and_never_ordinary_receive(self):
        self.send();claim=self.receive(self.b,'request');self.expire()
        before=self.conn.total_changes
        status=mailbox.recover(self.conn,self.b,argparse.Namespace(id='request',reclaim=False))
        self.assertTrue(status['reclaimable']);self.assertEqual(before,self.conn.total_changes)
        self.assertFalse(self.receive(self.b,'request')['actionable'])
        self.assert_code('LEASE_EXPIRED',lambda: mailbox.renew(self.conn,self.b,argparse.Namespace(id='request',lease_token=claim['lease_token'])))
        self.assert_code('LEASE_EXPIRED',lambda:self.reply(claim['lease_token']))
        current=self.reclaim(claim['claim_version'])
        self.assertEqual(current['id'],claim['id']);self.assertEqual(current['claim_version'],2)
        self.assert_code('STALE_LEASE',lambda:self.reply(claim['lease_token']))
        self.reply(current['lease_token'])

    def test_recover_compare_and_swap_attempt_limit(self):
        self.send();first=self.receive(self.b,'request');self.expire()
        self.assert_code('STALE_LEASE',lambda:self.reclaim(0))
        self.reclaim(1);self.expire();self.reclaim(2);self.expire()
        exhausted=self.reclaim(3)
        self.assertEqual(exhausted['processing_state'],'failed')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],1)
        self.assertIsNone(self.conn.execute('SELECT lease_token_hash FROM messages').fetchone()[0])

    def test_reply_retries_confirm_saved_payload_after_expiry(self):
        self.send();claim=self.receive(self.b,'request')
        reply=self.reply(claim['lease_token'],verdict='agree',confidence='high')
        self.assertEqual(self.reply('lost',verdict='agree',confidence='high')['id'],reply['id'])
        self.assert_code('REPLY_CONFLICT',lambda:self.reply('lost',verdict='disagree',reason='changed'))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages WHERE kind='reply'").fetchone()[0],1)
        self.assertIsNone(self.conn.execute("SELECT lease_token_hash FROM messages WHERE id='request'").fetchone()[0])

    def test_cancel_fences_result_without_deleting_body(self):
        self.send();claim=self.receive(self.b,'request')
        mailbox.cancel(self.conn,self.a,argparse.Namespace(id='request',reason='stop'))
        self.assert_code('STALE_LEASE',lambda:self.reply(claim['lease_token']))
        self.assertEqual(self.conn.execute("SELECT body FROM messages WHERE id='request'").fetchone()[0],'question')

    def test_rebind_fences_claim_even_without_deadline_expiry(self):
        self.send();claim=self.receive(self.b,'request')
        self.conn.execute("UPDATE bindings SET active=0 WHERE session_id='b'")
        self.conn.execute("INSERT INTO bindings VALUES('b','new','ghostty','new-surface',2,'test','now','now',1)")
        self.conn.commit()
        self.assert_code('STALE_BINDING',lambda:self.reply(claim['lease_token']))
        new_actor={'session_id':'b','instance_id':'new','generation':2}
        self.assert_code('STALE_BINDING',lambda:mailbox.renew(self.conn,new_actor,argparse.Namespace(id='request',lease_token=claim['lease_token'])))

    def test_ack_is_atomic_idempotent_and_closes_thread(self):
        self.send();claim=self.receive(self.b,'request');reply=self.reply(claim['lease_token'])
        incoming=self.receive(self.a,reply['id'])
        args=argparse.Namespace(id=reply['id'],lease_token=incoming['lease_token'],outcome='concluded')
        result=mailbox.ack(self.conn,self.a,args,'comparison')
        self.assertEqual(mailbox.ack(self.conn,self.a,args,'comparison'),result)
        self.assert_code('STATE_CONFLICT',lambda:mailbox.ack(self.conn,self.a,args,'different'))
        self.assertEqual(self.conn.execute('SELECT state FROM threads').fetchone()[0],'closed')
        self.assertNotIn('lease_token_hash',mailbox.envelope(mailbox.message(self.conn,reply['id'],self.a)))

    def test_followup_commit_links_reply_and_duplicate_new_id_returns_same(self):
        self.send();claim=self.receive(self.b,'request');reply=self.reply(claim['lease_token'])
        incoming=self.receive(self.a,reply['id'])
        first=self.send('round2',thread='request',after_reply=reply['id'],lease_token=incoming['lease_token'])
        second=self.send('different-id',thread='request',after_reply=reply['id'],lease_token='lost')
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(self.conn.execute('SELECT processing_state FROM messages WHERE id=?',(reply['id'],)).fetchone()[0],'completed')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],3)

    def test_transaction_failure_does_not_leave_reply_or_completion(self):
        self.send();claim=self.receive(self.b,'request')
        with patch('crosstalk_lib.mailbox.complete',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError): self.reply(claim['lease_token'])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],1)
        self.assertEqual(self.conn.execute('SELECT processing_state FROM messages').fetchone()[0],'processing')
        self.reply(claim['lease_token'])

    def test_explicit_verdict_does_not_parse_body(self):
        self.send();claim=self.receive(self.b,'request');reply=self.reply(claim['lease_token'],'example [AGREE]')
        self.assertEqual(mailbox.message(self.conn,reply['id'],self.a)['verdict'],'none')

    def test_saved_response_errors_keep_committed_ids_for_request_reply_and_followup(self):
        original=mailbox.message
        def read_fault(conn,*args):
            if not conn.in_transaction:
                raise sqlite3.OperationalError('database is locked')
            return original(conn,*args)
        def invoke(actor,args):
            out,err=io.StringIO(),io.StringIO()
            with patch.object(sessions,'actor',return_value=actor),patch.object(mailbox,'message',side_effect=read_fault),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                self.assertEqual(cli.main(args),4)
            result=json.loads(out.getvalue())
            self.assertTrue(result['saved'])
            self.assertEqual(result['error']['code'],'DB_BUSY')
            self.assertTrue(result['message_id'])
            return result['message_id']
        mid=invoke(self.a,['send','claude','question','--id','request'])
        self.assertEqual(mid,'request')
        claim=self.receive(self.b,mid)
        rid=invoke(self.b,['reply',mid,'answer','--lease-token',claim['lease_token']])
        self.assertEqual(self.conn.execute('SELECT reply_to FROM messages WHERE id=?',(rid,)).fetchone()[0],mid)
        reply_claim=self.receive(self.a,rid)
        next_id=invoke(self.a,['send','claude','question','--id','next','--thread',mid,'--after-reply',rid,'--lease-token',reply_claim['lease_token']])
        self.assertEqual(next_id,'next')
        self.assertEqual(self.conn.execute('SELECT completion_result FROM messages WHERE id=?',(rid,)).fetchone()[0],json.dumps({'next_request_id':'next'}))
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],3)

    def test_ack_does_not_read_database_after_commit(self):
        self.send();claim=self.receive(self.b,'request');reply=self.reply(claim['lease_token'])
        incoming=self.receive(self.a,reply['id'])
        original=mailbox.message
        def read_fault(conn,*args):
            if not conn.in_transaction: raise sqlite3.OperationalError('post-commit read failed')
            return original(conn,*args)
        with patch.object(mailbox,'message',side_effect=read_fault):
            result=mailbox.ack(self.conn,self.a,argparse.Namespace(id=reply['id'],lease_token=incoming['lease_token'],outcome='concluded'),'comparison')
        self.assertTrue(result['saved'])
        self.assertEqual(result['message_id'],reply['id'])
        self.assertEqual(self.conn.execute('SELECT state FROM threads').fetchone()[0],'closed')

    def test_older_uncompleted_reply_cannot_close_later_request(self):
        self.send();claim=self.receive(self.b,'request');reply=self.reply(claim['lease_token'])
        incoming=self.receive(self.a,reply['id'])
        # Simulates an old v2 fixture without migration's follow-up completion evidence.
        with self.conn:
            self.conn.execute("INSERT INTO messages(id,thread_id,kind,sender_session_id,recipient_session_id,body,round,created_at) VALUES('later','request','request','a','b','later question',2,'now')")
        args=argparse.Namespace(id=reply['id'],lease_token=incoming['lease_token'],outcome='concluded')
        self.assert_code('STATE_CONFLICT',lambda:mailbox.ack(self.conn,self.a,args,'old conclusion'))
        self.assertEqual(self.conn.execute('SELECT state FROM threads').fetchone()[0],'open')
        self.assertEqual(self.receive(self.b,'later')['id'],'later')


if __name__=='__main__': unittest.main()
