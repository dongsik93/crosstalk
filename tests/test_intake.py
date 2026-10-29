"""Synthetic native transcript fixtures; no personal conversation access."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import io
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/scripts'))
from crosstalk_lib import intake, db
from crosstalk_lib.protocol import Error


class IntakeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / 'state'
        self.state.mkdir(mode=0o700)
        self.claude = self.root / 'claude'
        self.transcript = self.claude / 'projects/project/session-1.jsonl'
        self.transcript.parent.mkdir(parents=True)
        self.transcript.touch()
        env = patch.dict(os.environ, {'CROSSTALK_CONFIG_DIR': str(self.state), 'CLAUDE_CONFIG_DIR': str(self.claude)})
        env.start(); self.addCleanup(env.stop)
        self.identity = {'kind': 'claude', 'surface_id': 'ghostty:00000000-0000-0000-0000-000000000001',
                         'process_id': '123', 'process_start': 'fixture'}
        identity = patch.object(intake.sessions, 'identity', return_value=self.identity)
        identity.start(); self.addCleanup(identity.stop)
        self.actor = {'session_id': 'caller', 'kind': 'claude', 'surface_id': self.identity['surface_id'],
                      'evidence': json.dumps({'process_id': '123', 'process_start': 'fixture'})}

    def human(self, mid, text, **changes):
        row = {'type': 'user', 'sessionId': 'session-1', 'uuid': mid, 'promptId': mid,
               'origin': {'kind': 'human'}, 'turnOrigin': 'human', 'promptSource': 'typed',
               'isSidechain': False, 'message': {'content': text}}
        row.update(changes)
        self.append(row)

    def append(self, row):
        with self.transcript.open('a') as out:
            out.write(json.dumps(row, ensure_ascii=False) + '\n')

    def capture(self, prompt, prompt_id=None):
        # Synthetic native hook IDs, independent of body matching in production code.
        if prompt_id is None:
            records=[json.loads(line) for line in self.transcript.read_text().splitlines()]
            prompt_id=records[-1]['uuid'] if records else 'pending'
        return intake.capture({'hook_event_name': 'UserPromptSubmit', 'session_id': 'session-1',
                               'transcript_path': str(self.transcript), 'prompt': prompt, 'prompt_id': prompt_id})

    def consume(self, bundle, run_id):
        conn=db.connect(initialize=True)
        try:
            with conn:
                conn.execute("INSERT OR IGNORE INTO sessions(session_id,kind,status,created_at) VALUES('caller','claude','ready','now')")
                captured=intake.load_bundle(bundle['input_id'],self.actor)
                snapshot=json.dumps({'input_id':bundle['input_id'],'capture_id':captured['capture_id'],
                                     'request_capture_id':captured['request_capture_id']})
                conn.execute("""INSERT INTO discussion_runs(run_id,mode,caller_session_id,requested_peer_kind,lifecycle,phase,max_rounds,
                    engine_version,protocol_version,prompt_bundle_version,execution_driver,raw_topic,config_snapshot,created_at,updated_at)
                    VALUES(?,'analyze','caller','codex','completed','terminal',10,1,3,2,'discussion-v1',?,?,'now','now')""",
                    (run_id,bundle['raw_topic'],snapshot))
        finally:conn.close()

    def test_private_assistant_opinions_never_enter_bundle(self):
        self.human('question', 'Compose와 XML 중 현재 화면에 적합한 것을 검토해줘.')
        self.append({'type': 'assistant', 'message': {'content': 'PRIVATE_CLAUDE_OPINION_A'}})
        self.human('constraint', '사용자 조건: 기존 접근성 동작을 유지해야 해.')
        self.append({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'content': 'PRIVATE_TOOL_OPINION'}]}})
        trigger = '야 옆에 애랑 독립적으로 검토해줘'
        self.human('trigger', trigger)
        capture = self.capture(trigger)
        sources = intake.list_sources(capture['capture_id'], self.actor)
        self.assertEqual([s['message_id'] for s in sources['sources']], ['question', 'constraint', 'trigger'])
        bundle = intake.prepare(capture['capture_id'], self.actor, 'question')
        self.assertNotIn('PRIVATE_', bundle['raw_topic'])
        self.assertIn('Compose와 XML', bundle['raw_topic'])
        self.assertIn('접근성', bundle['raw_topic'])
        self.assertEqual(intake.prepare(capture['capture_id'], self.actor, 'question'), bundle)
        self.assertEqual(intake.load_bundle(bundle['input_id'], self.actor)['raw_topic'], bundle['raw_topic'])
        data = self.transcript.read_text().replace('PRIVATE_CLAUDE_OPINION_A', 'PRIVATE_CLAUDE_OPINION_B')
        self.transcript.write_text(data)
        self.assertEqual(intake.prepare(capture['capture_id'], self.actor, 'question'), bundle)
        stored = self.state / 'inputs/bundles' / (bundle['input_id'] + '.json')
        self.assertEqual(stored.stat().st_mode & 0o077, 0)

    def test_hook_capture_does_not_self_certify_human_origin(self):
        prompt = '독립적으로 Compose 구현을 검토해줘'
        self.human('unknown', prompt, origin={'kind': 'automation'}, turnOrigin='automation')
        captured = self.capture(prompt)
        with self.assertRaises(Error) as failure:
            intake.prepare(captured['capture_id'], self.actor)
        self.assertEqual(failure.exception.code, 'INPUT_SOURCE_UNVERIFIED')
        self.assertFalse(intake.requires_engine(self.actor))

    def test_capture_before_transcript_can_be_resolved_after_recording(self):
        prompt = '이 API의 캐시 정책을 독립적으로 검토해줘'
        captured = self.capture(prompt, prompt_id='actual')
        with self.assertRaises(Error):
            intake.prepare(captured['capture_id'], self.actor)
        self.human('actual', prompt)
        bundle = intake.prepare(captured['capture_id'], self.actor)
        self.assertEqual(bundle['raw_topic'], prompt)
        metadata = json.loads((self.state / 'inputs/captures' / (captured['capture_id'] + '.json')).read_text())
        self.assertNotIn('prompt', metadata)

    def test_vague_topic_requires_real_context(self):
        prompt = '옆에 애랑 독립적으로 검토해줘'
        self.human('trigger', prompt)
        capture = self.capture(prompt)
        with self.assertRaises(Error) as failure:
            intake.prepare(capture['capture_id'], self.actor)
        self.assertEqual(failure.exception.code, 'INPUT_SCOPE_REQUIRED')
        with self.assertRaises(Error) as failure:
            intake.prepare(capture['capture_id'], self.actor, 'trigger')
        self.assertEqual(failure.exception.code, 'INPUT_SCOPE_REQUIRED')

    def test_repeated_prompt_waits_for_its_own_native_event(self):
        prompt='옆에 애랑 독립적으로 검토해줘'
        self.human('old-question','이전 UI 구조를 검토해야 해')
        self.human('old-trigger',prompt)
        self.human('new-question','이번에는 캐시 만료 정책을 검토해야 해')
        captured=self.capture(prompt,prompt_id='current-trigger')
        with self.assertRaises(Error) as failure:
            intake.list_sources(captured['capture_id'],self.actor)
        self.assertEqual(failure.exception.code,'INPUT_SOURCE_UNAVAILABLE')
        self.human('current-trigger',prompt)
        rows=intake.list_sources(captured['capture_id'],self.actor)['sources']
        self.assertEqual(rows[-1]['message_id'],'current-trigger')
        self.assertIn('new-question',[row['message_id'] for row in rows])

    def test_delayed_old_capture_never_selects_future_identical_prompt(self):
        prompt='캐시 정책을 독립적으로 검토해줘'
        self.human('original',prompt);captured=self.capture(prompt,prompt_id='original')
        self.human('future-question','새 화면의 접근성을 검토해야 해')
        self.human('future-trigger',prompt)
        self.assertEqual(intake.list_sources(captured['capture_id'],self.actor)['sources'][-1]['message_id'],'original')

    def test_unrecorded_old_event_does_not_adopt_next_repeated_prompt(self):
        prompt='캐시 정책을 독립적으로 검토해줘'
        old=self.capture(prompt,prompt_id='never-recorded')
        self.human('new',prompt);self.capture(prompt,prompt_id='new')
        with self.assertRaises(Error):intake.list_sources(old['capture_id'],self.actor)

    def test_event_content_mismatch_and_duplicate_events_are_rejected(self):
        prompt='독립적으로 캐시 정책을 검토해줘'
        captured=self.capture(prompt,prompt_id='event')
        self.human('message','different user content',promptId='event')
        with self.assertRaises(Error):intake.list_sources(captured['capture_id'],self.actor)
        self.transcript.write_text('')
        self.human('message-one',prompt,promptId='event');self.human('message-two',prompt,promptId='event')
        with self.assertRaises(Error):intake.list_sources(captured['capture_id'],self.actor)

    def test_default_scope_never_discards_question_in_favor_of_constraint(self):
        self.human('question','Compose와 XML 중 어떤 것이 적절할까?')
        self.human('constraint','기존 접근성 동작은 유지해야 해')
        prompt='옆에 애랑 독립적으로 검토해줘';self.human('trigger',prompt)
        captured=self.capture(prompt)
        with self.assertRaises(Error) as failure:intake.prepare(captured['capture_id'],self.actor)
        self.assertEqual(failure.exception.code,'INPUT_SCOPE_REQUIRED')
        bundle=intake.prepare(captured['capture_id'],self.actor,'question')
        self.assertEqual([row['message_id'] for row in bundle['sources']],['question','constraint','trigger'])

    def test_quoted_example_is_candidate_without_mailbox_block(self):
        for prompt in ['README에 “독립적으로 검토해줘”라는 사용 예시를 추가해주세요.',
                       'README에 독립적으로 검토해줘라는 사용 예시를 추가해주세요.',
                       '독립적으로 검토한다는 것이 무엇인지 궁금합니다.',
                       'Independent review is part of this discussion.']:
            with self.subTest(prompt=prompt):
                mid='example-'+str(len(self.transcript.read_text()))
                self.human(mid,prompt);captured=self.capture(prompt)
                self.assertEqual(captured['request_state'],'candidate')
                self.assertFalse(intake.requires_engine(self.actor))
                with self.assertRaises(Error):intake.prepare(captured['capture_id'],self.actor,mid)

    def test_pending_request_does_not_promote_a_later_example(self):
        prompt='캐시 정책을 독립적으로 검토해줘';self.human('request',prompt);self.capture(prompt)
        example='README에 “독립적으로 검토해줘”라는 예시를 추가해줘'
        self.human('example',example);captured=self.capture(example)
        self.assertTrue(intake.requires_engine(self.actor))  # Earlier real request is still pending.
        with self.assertRaises(Error):intake.prepare(captured['capture_id'],self.actor,'example')

    def test_failed_capture_blocks_native_prompt_instead_of_only_warning(self):
        prompt='캐시 정책을 독립적으로 검토해줘'
        payload=dict(hook_event_name='UserPromptSubmit',session_id='session-1',prompt_id='new',
                     transcript_path=str(self.transcript),prompt=prompt)
        output=io.StringIO()
        with patch('sys.stdin',io.StringIO(json.dumps(payload))), patch.object(intake,'_write',side_effect=OSError('disk full')), redirect_stdout(output), redirect_stderr(io.StringIO()):
            intake.hook_main()
        self.assertEqual(json.loads(output.getvalue())['decision'],'block')
        self.assertFalse((self.state/'inputs/heads').exists())

    def test_clarification_capture_failure_keeps_confirmed_request_blocked(self):
        prompt='독립적으로 캐시 정책을 검토해줘';self.human('request',prompt);self.capture(prompt)
        payload=dict(hook_event_name='UserPromptSubmit',session_id='session-1',prompt_id='clarification',
                     transcript_path=str(self.transcript),prompt='접근성은 유지해야 해')
        output=io.StringIO()
        with patch('sys.stdin',io.StringIO(json.dumps(payload))), patch.object(intake,'_write',side_effect=OSError('disk full')), redirect_stdout(output), redirect_stderr(io.StringIO()):
            intake.hook_main()
        self.assertEqual(json.loads(output.getvalue())['decision'],'block')
        self.assertTrue(intake.requires_engine(self.actor))

    def test_long_ordinary_conversation_does_not_create_request_obligation(self):
        for number in range(40):
            text=f'일반 작업 메모 {number}';self.human('note-'+str(number),text);self.capture(text)
        self.assertFalse(intake.requires_engine(self.actor))

    def test_missing_native_event_id_does_not_fall_back_to_hash(self):
        prompt='キャッシュ方針を independent review してください'
        self.human('past',prompt)
        with self.assertRaises(Error):
            intake.capture(dict(hook_event_name='UserPromptSubmit',session_id='session-1',
                                transcript_path=str(self.transcript),prompt=prompt))

    def test_legacy_committed_run_consumes_without_its_marker(self):
        prompt='캐시 정책을 독립적으로 검토해줘';self.human('request',prompt)
        captured=self.capture(prompt);bundle=intake.prepare(captured['capture_id'],self.actor)
        self.consume(bundle,'old-run')
        conn=db.connect()
        try:
            with conn:
                conn.execute('UPDATE discussion_runs SET config_snapshot=? WHERE run_id=?',
                             (json.dumps({'input_id':bundle['input_id']}),'old-run'))
        finally:conn.close()
        self.assertFalse((self.state/'inputs/consumed').exists())
        self.assertFalse(intake.requires_engine(self.actor))

    def test_marker_without_committed_run_does_not_consume(self):
        prompt='캐시 정책을 독립적으로 검토해줘';self.human('request',prompt)
        captured=self.capture(prompt);bundle=intake.prepare(captured['capture_id'],self.actor)
        folder=self.state/'inputs/consumed';folder.mkdir(mode=0o700)
        (folder/(captured['capture_id']+'.json')).write_text(json.dumps({'input_id':bundle['input_id'],'run_id':'not-committed'}))
        self.assertTrue(intake.requires_engine(self.actor))

    def test_old_producer_bundle_cannot_claim_new_event_binding(self):
        prompt='캐시 정책을 독립적으로 검토해줘';self.human('request',prompt)
        captured=self.capture(prompt);bundle=intake.prepare(captured['capture_id'],self.actor)
        path=self.state/'inputs/bundles'/(bundle['input_id']+'.json')
        old=json.loads(path.read_text());old.pop('event_binding');old.pop('content_hash')
        old['content_hash']=intake._hash(intake._canonical(old))
        path.write_text(json.dumps(old))
        with self.assertRaises(Error):intake.load_bundle(bundle['input_id'],self.actor)

    def test_other_actor_and_modified_bundle_are_rejected(self):
        prompt = '캐시 만료 정책을 독립적으로 검토해줘'
        self.human('trigger', prompt)
        capture = self.capture(prompt)
        bundle = intake.prepare(capture['capture_id'], self.actor)
        other = dict(self.actor, evidence=json.dumps({'process_id': '456', 'process_start': 'fixture'}))
        with self.assertRaises(Error): intake.load_bundle(bundle['input_id'], other)
        path = self.state / 'inputs/bundles' / (bundle['input_id'] + '.json')
        data = json.loads(path.read_text()); data['raw_topic'] = 'Claude rewrote it'
        path.write_text(json.dumps(data))
        with self.assertRaises(Error): intake.load_bundle(bundle['input_id'], self.actor)

    def test_notification_does_not_clear_guard_and_consumption_is_explicit(self):
        prompt = '캐시 정책을 독립적으로 검토해줘'
        self.human('trigger', prompt)
        capture = self.capture(prompt)
        self.assertTrue(intake.requires_engine(self.actor))
        self.assertTrue(self.capture('[Crosstalk] Discussion work is available')['ignored'])
        self.assertTrue(intake.requires_engine(self.actor))
        bundle = intake.prepare(capture['capture_id'], self.actor)
        self.consume(bundle, 'run-1')
        self.assertFalse(intake.requires_engine(self.actor))
        (self.state/'inputs/captures'/ (capture['capture_id']+'.json')).unlink()
        self.assertFalse(intake.requires_engine(self.actor))

    def test_normal_human_turn_can_supersede_but_unknown_turn_cannot(self):
        first = '캐시 정책을 독립적으로 검토해줘'
        self.human('one', first); self.capture(first)
        self.human('robot', '그냥 실행해', origin={'kind': 'agent'}, turnOrigin='agent')
        self.capture('그냥 실행해')
        self.assertTrue(intake.requires_engine(self.actor))
        self.human('two', '독립 검토 말고 현재 파일만 보여줘')
        self.capture('독립 검토 말고 현재 파일만 보여줘')
        self.assertFalse(intake.requires_engine(self.actor))

    def test_clarification_keeps_independent_guard_until_run_consumes_it(self):
        self.human('topic','이 화면의 UI 구현 방식을 정해야 해')
        prompt='옆에 애랑 독립적으로 검토해줘'
        self.human('one',prompt);self.capture(prompt)
        clarification='Compose와 XML 중 고르되 접근성을 유지해야 해'
        self.human('two',clarification);captured=self.capture(clarification)
        self.assertTrue(intake.requires_engine(self.actor))
        bundle=intake.prepare(captured['capture_id'],self.actor,'topic')
        self.consume(bundle, 'run-clarified')
        self.assertFalse(intake.requires_engine(self.actor))
        self.human('next','이제 다른 일반 작업을 하자');self.capture('이제 다른 일반 작업을 하자')
        self.assertFalse(intake.requires_engine(self.actor))

    def test_arbitrary_transcript_and_symlink_not_accepted(self):
        payload = {'hook_event_name': 'UserPromptSubmit', 'session_id': 'session-1',
                   'transcript_path': str(self.root / 'model-file.jsonl'), 'prompt': '독립적으로 검토해줘', 'prompt_id':'native-event'}
        with self.assertRaises(Error): intake.capture(payload)
        link = self.transcript.parent / 'session-2.jsonl'
        link.symlink_to(self.transcript)
        payload.update(session_id='session-2', transcript_path=str(link))
        with self.assertRaises(Error): intake.capture(payload)

    def test_malformed_capture_and_storage_fail_closed(self):
        with self.assertRaises(Error):
            intake.capture({'hook_event_name': 'UserPromptSubmit', 'prompt': 'hello',
                            'session_id': 'session-1', 'transcript_path': None})
        self.assertFalse(intake.independent_intent(None))
        prompt = 'API 조건을 독립적으로 검토해줘'
        self.human('trigger', prompt)
        captured = self.capture(prompt)
        path = self.state / 'inputs/captures' / (captured['capture_id'] + '.json')
        path.write_text('[]')
        with self.assertRaises(Error): intake.prepare(captured['capture_id'], self.actor)


if __name__ == '__main__':
    unittest.main()
