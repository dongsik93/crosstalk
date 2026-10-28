#!/usr/bin/env python3
"""Persisted notification state and bounded helper tests."""
import os
import argparse
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'assets/scripts'))
from crosstalk_lib import db, delivery, doctor, mailbox, sessions
from crosstalk_lib.protocol import Error, now
A='ghostty:00000000-0000-0000-0000-000000000001'
B='ghostty:00000000-0000-0000-0000-000000000002'

class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'CROSSTALK_CONFIG_DIR':str(Path(self.tmp.name).resolve()/'state')})
        self.env.start();self.conn=db.connect(initialize=True)
        self.ids=[]
        for address,kind in ((A,'claude'),(B,'codex')):
            challenge=sessions.challenge(self.conn,address,kind)
            with patch.object(sessions,'identity',return_value={'surface_id':address,'process_id':address,'process_start':'test'}):
                self.ids.append(sessions.bind(self.conn,challenge['challenge'],kind)['session_id'])
        with self.conn:
            self.conn.execute('INSERT INTO threads(thread_id,caller_session_id,peer_session_id,mode) VALUES(?,?,?,?)',('m',*self.ids,'analyze'))
            self.conn.execute('INSERT INTO messages(id,thread_id,kind,sender_session_id,recipient_session_id,body,round,created_at) VALUES(?,?,?,?,?,?,?,?)',('m','m','request',*self.ids,'sensitive body',1,now()))
            delivery.seed(self.conn,'m')
        self.row=self.conn.execute('SELECT * FROM messages WHERE id=?',('m',)).fetchone()
    def tearDown(self):self.conn.close();self.env.stop();self.tmp.cleanup()
    def bridge(self,*args):
        if args[0]=='target-identity':
            return json.dumps(dict(surface_id=B,kind='codex',process_id=B,process_start='test'))
        return 'en' if args[0]=='get-language' else ''

    def test_saved_before_io_no_write_transaction_and_idempotent_notify(self):
        def bridge(*args):
            self.assertFalse(self.conn.in_transaction)
            return self.bridge(*args)
        with patch.object(delivery,'bridge',side_effect=bridge) as mock:
            self.assertEqual(delivery.notify(self.conn,self.row)['delivery_state'],'submitted')
            calls=[call.args[0] for call in mock.call_args_list]
            self.assertEqual(calls[-2:],['target-identity','send'])
            before=mock.call_count
            delivery.notify(self.conn,self.row)
            self.assertEqual(before,mock.call_count)
        self.assertEqual(self.conn.execute('SELECT processing_state FROM messages').fetchone()[0],'queued')
    def test_timeout_unknown_retry_same_message(self):
        def bridge(*args):
            if args[0]=='send':raise Error('TERMINAL_TIMEOUT','timeout')
            return self.bridge(*args)
        with patch.object(delivery,'bridge',side_effect=bridge),self.assertRaises(Error) as raised:
            delivery.notify(self.conn,self.row)
        self.assertTrue(raised.exception.saved)
        self.assertEqual(raised.exception.message_id,'m')
        self.assertEqual(delivery.latest(self.conn,'m')['state'],'unknown')
        with patch.object(delivery,'bridge',side_effect=self.bridge):
            delivery.notify(self.conn,self.row,retry=True)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM messages').fetchone()[0],1)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM delivery_attempts').fetchone()[0],2)
    def test_failure_does_not_log_body_or_helper_stderr(self):
        with patch.object(delivery,'bridge',side_effect=Error('NOTIFICATION_FAILED','SECRET')),self.assertRaises(Error):
            delivery.notify(self.conn,self.row)
        self.assertEqual(delivery.latest(self.conn,'m')['state'],'failed')
        events=' '.join(row['metadata'] for row in self.conn.execute('SELECT * FROM events'))
        self.assertNotIn('sensitive body',events);self.assertNotIn('SECRET',events)
    def test_saved_identity_survives_post_submission_database_failure(self):
        original_event=db.event
        def event(conn,kind,**kwargs):
            if kind=='notification_finished': raise sqlite3.OperationalError('disk full')
            return original_event(conn,kind,**kwargs)
        with patch.object(delivery,'bridge',side_effect=self.bridge),patch.object(db,'event',side_effect=event),self.assertRaises(Error) as raised:
            delivery.notify(self.conn,self.row)
        self.assertTrue(raised.exception.saved)
        self.assertEqual(raised.exception.message_id,'m')
        self.assertEqual(raised.exception.code,'NOTIFICATION_UNKNOWN')
        self.assertEqual(delivery.result(delivery.latest(self.conn,'m'))['delivery_state'],'unknown')

    def test_foreground_identity_change_or_malformed_target_never_receives_input(self):
        for observed in ('not json', json.dumps(dict(surface_id=B,kind='codex',process_id='replacement',process_start='test')),
                         json.dumps(dict(surface_id=B,kind='shell',process_id=B,process_start='test'))):
            calls=[]
            def bridge(*args):
                calls.append(args)
                return observed if args[0]=='target-identity' else self.bridge(*args)
            with patch.object(delivery,'bridge',side_effect=bridge),self.assertRaises(Error) as raised:
                delivery.notify(self.conn,self.row,retry=True)
            self.assertTrue(raised.exception.saved)
            self.assertEqual(raised.exception.code,'STALE_BINDING')
            self.assertFalse(any(args[0]=='send' for args in calls))
            self.assertEqual(delivery.latest(self.conn,'m')['state'],'failed')

    def test_orphan_inflight_is_effectively_unknown(self):
        with self.conn:self.conn.execute("UPDATE delivery_attempts SET state='in_flight'")
        self.assertEqual(delivery.result(delivery.latest(self.conn,'m'))['delivery_state'],'unknown')

    def test_partial_send_helper_exit_is_unknown_not_confirmed_failure(self):
        helper=Path(self.tmp.name)/'helper'
        marker=Path(self.tmp.name)/'typed'
        helper.write_text('#!/usr/bin/env python3\nimport pathlib,sys\npathlib.Path(sys.argv[2]).write_text("input submitted")\nsys.exit(1)\n')
        helper.chmod(0o700)
        real_bridge=delivery.bridge
        def bridge(*args):
            if args[0]=='send': return real_bridge('send',str(marker))
            return self.bridge(*args)
        with patch.dict(os.environ,{'CROSSTALK_BRIDGE':str(helper)}),patch.object(delivery,'bridge',side_effect=bridge),self.assertRaises(Error) as raised:
            delivery.notify(self.conn,self.row)
        self.assertTrue(marker.exists())
        self.assertTrue(raised.exception.saved)
        self.assertEqual(raised.exception.code,'NOTIFICATION_UNKNOWN')
        self.assertEqual(delivery.latest(self.conn,'m')['state'],'unknown')

    def test_doctor_and_status_use_latest_delivery_history_retains_prior_failure(self):
        with patch.object(delivery,'bridge',side_effect=Error('NOTIFICATION_FAILED','before any send')),self.assertRaises(Error):
            delivery.notify(self.conn,self.row)
        with patch.object(delivery,'bridge',side_effect=self.bridge):
            delivery.notify(self.conn,self.row,retry=True)
        before=(db.root()/'mailbox.sqlite3').read_bytes()
        with patch.object(delivery,'bridge',side_effect=AssertionError('diagnostics contacted terminal')):
            report=doctor.inspect()
            actor={'session_id':self.ids[0]}
            status=mailbox.query(self.conn,actor,argparse.Namespace(command='status',id='m',limit=50,offset=0))
            history=mailbox.query(self.conn,actor,argparse.Namespace(command='history',id='m',limit=50,offset=0))
        self.assertEqual(len(report['delivery']),1)
        self.assertEqual(report['delivery'][0]['state'],'submitted')
        self.assertFalse(any(issue.get('message_id')=='m' for issue in report['issues']))
        self.assertEqual(status[0]['latest_delivery']['state'],'submitted')
        self.assertEqual([attempt['state'] for attempt in history[0]['delivery_attempts']],['failed','submitted'])
        self.assertEqual(before,(db.root()/'mailbox.sqlite3').read_bytes())
    def test_helper_timeout_terminates_owned_group(self):
        helper=Path(self.tmp.name)/'helper'
        helper.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n');helper.chmod(0o700)
        with patch.dict(os.environ,{'CROSSTALK_BRIDGE':str(helper)}),patch.object(delivery,'BRIDGE_TIMEOUT',0.1),self.assertRaises(Error) as raised:
            delivery.bridge('self')
        self.assertEqual(raised.exception.code,'TERMINAL_TIMEOUT')

    def test_simultaneous_retry_does_not_submit_twice(self):
        entered, observed, release=threading.Event(),threading.Event(),threading.Event()
        counter=[]
        original_latest=delivery.latest
        def latest(conn,mid):
            value=original_latest(conn,mid)
            if value and value['state']=='in_flight':observed.set()
            return value
        def bridge(*args):
            if args[0]=='send':
                counter.append(args)
                entered.set()
                self.assertTrue(release.wait(3))
            return self.bridge(*args)
        def retry():
            conn=db.connect()
            try:return delivery.notify(conn,self.row,retry=True)
            finally:conn.close()
        with patch.object(delivery,'bridge',side_effect=bridge),patch.object(delivery,'latest',side_effect=latest),ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(retry)
            self.assertTrue(entered.wait(3))
            second=pool.submit(retry)
            try:self.assertTrue(observed.wait(3))
            finally:release.set()
            self.assertEqual(first.result()['delivery_state'],'submitted')
            self.assertEqual(second.result()['delivery_state'],'submitted')
        self.assertEqual(len(counter),1)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM delivery_attempts').fetchone()[0],1)

if __name__=='__main__':unittest.main()
