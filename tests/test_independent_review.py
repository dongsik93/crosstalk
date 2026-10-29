"""Independent review uses native user sources and fresh-peer evidence, not caller prose."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
from engine_helpers import EngineCase, A, B, C

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'assets/scripts'))
from crosstalk_lib import intake, db, sessions, cli
from crosstalk_lib.engine import service
from crosstalk_lib.protocol import Error


class IndependentReviewTests(EngineCase):
    def setUp(self):
        super().setUp()
        self.claude = self.root/'claude'
        self.env['CLAUDE_CONFIG_DIR'] = str(self.claude)
        transcript = self.claude/'projects/project/claude-session.jsonl'
        transcript.parent.mkdir(parents=True)
        self.trigger = '야 옆에 애랑 독립적으로 좀 검토해'
        def human(mid,text):
            return dict(type='user',sessionId='claude-session',uuid=mid,promptId=mid,origin={'kind':'human'},
                        turnOrigin='human',promptSource='typed',isSidechain=False,message={'content':text})
        records=[human('question','Compose와 XML 중 이 화면에 적합한 것을 판단해줘.'),
                 dict(type='assistant',message={'content':'PRIVATE_CLAUDE_COMPOSE_IS_BEST'}),
                 human('constraints','기존 접근성 동작을 유지해야 해.'),human('request',self.trigger)]
        transcript.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in records)+'\n')
        with patch.dict(os.environ,self.env|{'TEST_ACTOR':B}):
            self.capture = intake.capture(dict(hook_event_name='UserPromptSubmit',session_id='claude-session',
                                                transcript_path=str(transcript),prompt=self.trigger,prompt_id='request'))
        self.bundle = self.call('input','prepare',self.capture['capture_id'],'--from-message','question',actor=B)
        with sqlite3.connect(self.state/'mailbox.sqlite3') as conn:
            conn.execute('UPDATE sessions SET cli_session_id=? WHERE session_id=?',('new-codex-thread',self.logical[A]))

    def begin(self, **kwargs):
        return self.call('run','start','codex','--input-id',self.bundle['input_id'],
                         '--review-mode','independent','--operation-id','independent-start',actor=B,**kwargs)

    def receipt(self, input_id=None):
        folder = self.state/'inputs/launches'
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        prompt = 'Crosstalk startup check. Read /tmp/ct-startup.fixture.'
        path = folder/(A.removeprefix('ghostty:')+'.json')
        path.write_text(json.dumps(dict(input_id=input_id or self.bundle['input_id'],surface_id=A,kind='codex',
                                       origin='new_cli_process',process_id=A,process_start='fixture',launch_id='launch-fixture',
                                       cli_options=[],startup_prompt=prompt,argv=[prompt])))
        path.chmod(0o600)

    def attach(self, run, **kwargs):
        return self.call('run','continue',run,'--peer-surface',A,'--operation-id','attach-peer',actor=B,**kwargs)

    def test_caller_cannot_rewrite_or_use_raw_send(self):
        error = self.call('send','codex','PRIVATE_CLAUDE_COMPOSE_IS_BEST',actor=B,code=5)
        self.assertEqual(error['error']['code'],'RUN_MANAGED_BY_ENGINE')
        self.call('run','start','codex','PRIVATE_CLAUDE_COMPOSE_IS_BEST','--input-id',self.bundle['input_id'],
                  '--review-mode','independent','--operation-id','bad-body',actor=B,code=2)
        self.call('run','start','codex','--input-id',self.bundle['input_id'],'--rules','biased',
                  '--operation-id','bad-rules',actor=B,code=2)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM discussion_runs')[0]['n'],0)

    def test_first_input_excludes_caller_views_and_selected_presets(self):
        (self.state/'config.json').write_text(json.dumps({'active_rules':'bias','active_persona':'bias'}))
        for kind in ('rules','personas'):
            path=self.state/kind/'en/bias.md';path.parent.mkdir(parents=True)
            path.write_text('PRIVATE_BIASED_PRESET: choose Compose')
        started=self.begin();run=started['run_id']
        self.assertEqual(started['phase'],'preparing')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM messages')[0]['n'],0)
        self.receipt();self.attach(run)
        self.call('send','codex','PRIVATE_OTHER_CALLER_OPINION',actor=C,code=5)
        peer=self.take(self.actions(run,A)[0]['action_id'],A)
        transmitted=json.dumps(peer['input'],ensure_ascii=False)
        self.assertIn('Compose와 XML',transmitted)
        self.assertIn('접근성',transmitted)
        self.assertNotIn('PRIVATE_',transmitted)
        self.assertEqual(peer['input']['config_snapshot']['rules']['name'],'none')
        self.assertNotIn('PRIVATE_',self.log.read_text())
        self.call('send','codex','extra hidden opinion',actor=B,code=5)
        self.assertEqual(self.begin()['run_id'],run)

    def test_existing_or_used_peer_is_not_mislabelled_fresh(self):
        run=self.begin()['run_id']
        self.attach(run,code=5)
        self.assertEqual(self.rows('SELECT count(*) AS n FROM messages')[0]['n'],0)
        self.receipt()
        # A previous ordinary exchange disqualifies this session, even with launch evidence.
        self.call('send','claude','prior Codex conversation',actor=A)
        error=self.attach(run,code=5)
        self.assertEqual(error['error']['code'],'FRESH_CONTEXT_REQUIRED')

    def test_both_initials_are_fixed_before_normal_discussion(self):
        run=self.begin()['run_id'];self.receipt();self.attach(run)
        local=self.take(self.actions(run,B)[0]['action_id'],B)
        peer=self.take(self.actions(run,A)[0]['action_id'],A)
        self.submit(peer,'PEER_INITIAL_ANSWER',A)
        self.assertNotIn('PEER_INITIAL_ANSWER',json.dumps(self.call('run','report',run,actor=B)))
        self.submit(local,'CALLER_INITIAL_ANSWER',B)
        compare=self.take(self.actions(run,B)[0]['action_id'],B)
        self.assertIn('PEER_INITIAL_ANSWER',json.dumps(compare['input']))
        self.assertIn('CALLER_INITIAL_ANSWER',json.dumps(compare['input']))
        self.decide(compare,actor=B)
        report=self.call('run','report',run,actor=B)['report']
        self.assertEqual(report['review_mode'],'independent')
        self.assertEqual(report['peer_context']['origin'],'new_cli_for_input')
        self.assertEqual(report['input_provenance'],'native_claude_human_transcript')

    def test_new_pane_reusing_known_codex_conversation_is_rejected(self):
        run=self.begin()['run_id'];self.receipt()
        with sqlite3.connect(self.state/'mailbox.sqlite3') as conn:
            conn.execute("INSERT INTO sessions(session_id,kind,cli_session_id,status,created_at) VALUES('old-codex','codex','new-codex-thread','unresolved','before')")
        error=self.attach(run,code=5)
        self.assertEqual(error['error']['code'],'FRESH_CONTEXT_REQUIRED')
        self.assertEqual(self.rows('SELECT count(*) AS n FROM messages')[0]['n'],0)

    def test_consumption_survives_postcommit_failure_and_retry_without_files(self):
        with patch.dict(os.environ,self.env|{'TEST_ACTOR':B}):
            conn=db.connect()
            try:
                actor=sessions.actor(conn)
                args=cli.parser().parse_args(['run','start','codex','--input-id',self.bundle['input_id'],
                                             '--review-mode','independent','--operation-id','postcommit'])
                with patch.object(service,'observe',side_effect=sqlite3.OperationalError('injected read failure')):
                    with self.assertRaises(Error) as failure:service.start(conn,actor,args,None)
                self.assertTrue(failure.exception.saved)
                self.assertFalse(intake.requires_engine(actor))
                (self.state/'inputs/captures'/(self.capture['capture_id']+'.json')).unlink()
                with patch.object(intake,'_write',side_effect=OSError('filesystem unavailable')):
                    repeated=service.start(conn,actor,args,None)
                self.assertEqual(repeated['run_id'],failure.exception.run_id)
                self.assertEqual(conn.execute('SELECT count(*) FROM discussion_runs').fetchone()[0],1)
            finally:conn.close()
        self.call('run','cancel',repeated['run_id'],'--operation-id','finish-fixture','--reason','fixture done',actor=B)
        self.call('send','codex','ordinary request after terminal run',actor=B)

    def test_rollback_does_not_consume_input(self):
        with patch.dict(os.environ,self.env|{'TEST_ACTOR':B}):
            conn=db.connect()
            try:
                actor=sessions.actor(conn)
                args=cli.parser().parse_args(['run','start','codex','--input-id',self.bundle['input_id'],
                                             '--review-mode','independent','--operation-id','rollback'])
                with patch.object(service,'_record',side_effect=sqlite3.OperationalError('rollback')):
                    with self.assertRaises(sqlite3.OperationalError):service.start(conn,actor,args,None)
                self.assertEqual(conn.execute('SELECT count(*) FROM discussion_runs').fetchone()[0],0)
                self.assertTrue(intake.requires_engine(actor))
            finally:conn.close()


if __name__=='__main__':
    unittest.main()
