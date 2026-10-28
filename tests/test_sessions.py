#!/usr/bin/env python3
"""Session ownership tests with exact, isolated fake terminal identities."""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'assets/scripts'))
from crosstalk_lib import db, sessions
from crosstalk_lib.protocol import Error

A='ghostty:00000000-0000-0000-0000-000000000001'
B='ghostty:00000000-0000-0000-0000-000000000002'
C='ghostty:00000000-0000-0000-0000-000000000003'

class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'CROSSTALK_CONFIG_DIR':str(Path(self.tmp.name).resolve()/'state')})
        self.env.start()
        self.conn=db.connect(initialize=True)
    def tearDown(self):
        self.conn.close();self.env.stop();self.tmp.cleanup()
    def bind(self,address=A,kind='claude'):
        challenge=sessions.challenge(self.conn,address,kind)
        with patch.object(sessions,'identity',return_value={'surface_id':address,'process_id':address,'process_start':'test'}):
            return sessions.bind(self.conn,challenge['challenge'],kind)
    def test_wrong_pane_kind_protocol_and_replay(self):
        challenge=sessions.challenge(self.conn,A,'claude')
        for address,kind,protocol in ((B,'claude',2),(A,'codex',2),(A,'claude',1)):
            with patch.object(sessions,'identity',return_value={'surface_id':address,'process_id':address,'process_start':'test'}),self.assertRaises(Error):
                sessions.bind(self.conn,challenge['challenge'],kind,protocol=protocol)
        with patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'test'}):
            bound=sessions.bind(self.conn,challenge['challenge'],'claude')
            self.assertEqual(sessions.actor(self.conn)['session_id'],bound['session_id'])
            with self.assertRaises(Error): sessions.bind(self.conn,challenge['challenge'],'claude')
    def test_expired_challenge(self):
        challenge=sessions.challenge(self.conn,A,'claude')
        with self.conn:self.conn.execute('UPDATE challenges SET expires_at=0')
        with patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'test'}),self.assertRaises(Error):
            sessions.bind(self.conn,challenge['challenge'],'claude')
    def test_rebind_requires_transfer_and_monotonic_generation(self):
        first=self.bind()
        change=sessions.challenge(self.conn,B,'claude',session_id=first['session_id'],expected_generation=1)
        with patch.object(sessions,'identity',return_value={'surface_id':B,'process_id':B,'process_start':'test'}):
            with self.assertRaises(Error): sessions.bind(self.conn,change['challenge'],'claude')
            second=sessions.bind(self.conn,change['challenge'],'claude',confirm_transfer=True)
            self.assertEqual(second['generation'],2)
            self.assertNotEqual(first['instance_id'],second['instance_id'])
        with patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'test'}),self.assertRaises(Error): sessions.actor(self.conn)
        with self.assertRaises(Error): sessions.challenge(self.conn,C,'claude',session_id=first['session_id'],expected_generation=1)
    def test_same_kind_is_ambiguous_without_explicit_session(self):
        self.bind(A,'claude');first=self.bind(B,'codex');self.bind(C,'codex')
        with patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'test'}):caller=sessions.actor(self.conn)
        with self.assertRaises(Error):sessions.peer(self.conn,'codex',caller)
        self.assertEqual(sessions.peer(self.conn,'codex',caller,first['session_id'])['surface_id'],B)
    def test_existing_surface_cannot_be_stolen(self):
        self.bind()
        challenge=sessions.challenge(self.conn,A,'codex')
        with patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'test'}),self.assertRaises(Error):
            sessions.bind(self.conn,challenge['challenge'],'codex',confirm_transfer=True)
    def test_changed_codex_cli_identity_needs_rebind(self):
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'one'}):self.bind(A,'codex')
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'two'}),patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'test'}),self.assertRaises(Error):
            sessions.actor(self.conn)

    def test_same_pane_new_process_cannot_inherit_binding(self):
        self.bind()
        with patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'new'}),self.assertRaises(Error):
            sessions.actor(self.conn)
    def test_nonce_consumption_is_atomic(self):
        challenge=sessions.challenge(self.conn,A,'claude')
        def attempt():
            conn=db.connect()
            try:
                return sessions.bind(conn,challenge['challenge'],'claude')['ready']
            except Error:return False
            finally:conn.close()
        with patch.object(sessions,'identity',return_value={'surface_id':A,'process_id':A,'process_start':'test'}),ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(lambda _:attempt(),range(2))),1)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM bindings WHERE active=1').fetchone()[0],1)
    def test_notify_uses_runtime_paths_without_implied_transfer(self):
        bound=self.bind()
        parser=argparse.ArgumentParser()
        sessions.add_parser(parser.add_subparsers(dest='command'))
        args=parser.parse_args(['session','challenge','--surface',B,'--kind','claude','--session-id',bound['session_id'],'--expected-generation','1','--notify'])
        with patch.object(sessions,'bridge') as mocked:
            sessions.run(args)
        prompt=mocked.call_args.args[2]
        self.assertIn('crosstalk_bridge.sh bind '+B,prompt)
        self.assertIn('capabilities --json',prompt)
        self.assertIn('CROSSTALK_CONFIG_DIR=',prompt)
        self.assertIn('mailbox_instructions',prompt)
        self.assertNotIn('--confirm-transfer',prompt)
        args.confirm_transfer=True
        with patch.object(sessions,'bridge') as mocked:sessions.run(args)
        self.assertIn('--confirm-transfer',mocked.call_args.args[2])

if __name__=='__main__':unittest.main()
