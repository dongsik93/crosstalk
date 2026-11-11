"""A lost stdout/parser result must not lose a still-valid claim token."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from engine_helpers import EngineCase, ROOT, A, B, C
sys.path.insert(0,str(ROOT/'assets/scripts'))
from crosstalk_lib import cli, db, mailbox, sessions


class ClaimReceipts(EngineCase):
    def test_reply_token_can_be_read_again_without_new_claim_or_thread(self):
        request=self.call('send','antigravity','question','--id','keep-thread')
        peer=self.call('receive',request['id'],actor=C)
        answer=self.call('reply',request['id'],'answer\nwith\tcontrols\x1b and quotes "',
                         '--lease-token',peer['lease_token'],actor=C)
        received=self.call('receive',answer['id'])
        before=(self.state/'mailbox.sqlite3').read_bytes()
        restored=self.call('receipt',answer['id'])
        self.assertEqual(restored['lease_token'],received['lease_token'])
        self.assertEqual(restored['claim_version'],received['claim_version'])
        self.assertFalse(restored['reclaimed'])
        self.assertEqual((self.state/'mailbox.sqlite3').read_bytes(),before)
        self.assertNotIn('body',restored)
        self.call('receipt',answer['id'],actor=C,code=5)
        self.call('receipt',answer['id'],actor=B,code=7)
        next_request=self.call('send','antigravity','follow-up','--thread',request['thread_id'],
                               '--after-reply',answer['id'],'--lease-token',restored['lease_token'])
        self.assertEqual(next_request['thread_id'],request['thread_id'])
        self.call('receipt',answer['id'],code=5)

    def test_token_survives_exit_after_commit_before_stdout(self):
        request=self.call('send','claude','question','--id','stdout-lost')
        code="from crosstalk_lib import cli; import os; cli.dispatch(cli.parser().parse_args(['receive','stdout-lost'])); os._exit(42)"
        process=subprocess.run([sys.executable,'-c',code],env=self.env|{'TEST_ACTOR':B,'PYTHONPATH':str(ROOT/'assets/scripts')},
                               capture_output=True,text=True)
        self.assertEqual(process.returncode,42,process.stderr)
        self.assertEqual(process.stdout,'')
        receipt=self.call('receipt',request['id'],actor=B)
        row=self.rows('SELECT claim_version,attempt_count,lease_token_hash FROM messages WHERE id=?',request['id'])[0]
        self.assertEqual((row['claim_version'],row['attempt_count']),(1,1))
        self.assertEqual(hashlib.sha256(receipt['lease_token'].encode()).hexdigest(),row['lease_token_hash'])
        self.call('reply',request['id'],'same request resumed','--lease-token',receipt['lease_token'],actor=B)

    def test_disk_failure_rolls_back_claim_and_orphan_receipt_is_unusable(self):
        request=self.call('send','claude','question','--id','disk-failure')
        with patch.dict(os.environ,self.env|{'TEST_ACTOR':B}), closing(db.connect()) as conn:
            actor=sessions.actor(conn)
            args=cli.parser().parse_args(['receive',request['id']])
            # File reached disk, but directory persistence failed: DB must not commit ownership.
            with patch.object(mailbox.os,'fsync',side_effect=[None,OSError('disk full')]):
                with self.assertRaises(OSError):mailbox.receive(conn,actor,args)
        row=self.rows('SELECT processing_state,claim_version,attempt_count FROM messages WHERE id=?',request['id'])[0]
        self.assertEqual(row,dict(processing_state='queued',claim_version=0,attempt_count=0))
        self.call('receipt',request['id'],actor=B,code=5)
        claimed=self.call('receive',request['id'],actor=B)
        self.assertEqual(self.call('receipt',request['id'],actor=B)['lease_token'],claimed['lease_token'])

    def test_expired_and_rebound_claims_cannot_restore_old_authority(self):
        sent=self.call('send','claude','question','--id','expiry')
        old=self.call('receive',sent['id'],actor=B)
        with closing(sqlite3.connect(self.state/'mailbox.sqlite3')) as conn, conn:
            conn.execute('UPDATE messages SET lease_expires_at=0 WHERE id=?',(sent['id'],))
        self.assertEqual(self.call('receipt',sent['id'],actor=B,code=5)['error']['code'],'LEASE_EXPIRED')
        new=self.call('recover',sent['id'],'--reclaim','--expected-claim-version','1',
                      '--confirm-external-effects',actor=B)
        self.assertEqual(self.call('receipt',sent['id'],actor=B)['lease_token'],new['lease_token'])
        self.assertNotEqual(old['lease_token'],new['lease_token'])
        self.call('reply',sent['id'],'stale','--lease-token',old['lease_token'],actor=B,code=5)
        challenge=self.call('session','challenge','--surface',B,'--kind','claude',
                            '--session-id',self.logical[B],'--expected-generation','1','--protocol','3','--engine-version','1',actor=B)
        self.call('session','rebind','--challenge',challenge['challenge'],'--kind','claude',
                  '--protocol','3','--engine-version','1','--confirm-transfer',actor=B)
        self.call('receipt',sent['id'],actor=B,code=5)

    def test_receipt_is_private_and_diagnostics_do_not_contain_tokens(self):
        sent=self.call('send','claude','question','--id','private-token')
        claimed=self.call('receive',sent['id'],actor=B)
        folder=self.state/'claim-tokens';path=folder/'private-token-1.json'
        self.assertEqual(folder.stat().st_mode & 0o777,0o700)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        for value in [self.call('status',sent['id']),self.call('doctor','--offline')]:
            self.assertNotIn(claimed['lease_token'],json.dumps(value))
        path.unlink()  # An old/pre-patch claim cannot be reconstructed from its hash.
        self.assertEqual(self.call('receipt',sent['id'],actor=B,code=5)['error']['code'],'CLAIM_RECEIPT_UNAVAILABLE')

    def test_managed_take_uses_the_same_receipt_without_reclaiming(self):
        run=self.start()
        local=self.take(self.actions(run)[0]['action_id']);self.submit(local,'caller analysis')
        peer=self.take(self.actions(run,B)[0]['action_id'],B)
        saved=self.call('receipt',peer['message_id'],actor=B)
        self.assertEqual(saved['lease_token'],peer['lease_token'])
        resumed=self.call('run','take',peer['action_id'],'--lease-token',saved['lease_token'],actor=B)
        self.assertEqual(resumed['claim_version'],peer['claim_version'])
        self.submit(resumed,'peer analysis',B)
        compare=self.compare(run)
        saved=self.call('receipt',compare['message_id'])
        compare['lease_token']=saved['lease_token']
        self.decide(compare)
        self.assertEqual(self.call('run','status',run)['lifecycle'],'completed')


if __name__=='__main__':unittest.main()
