"""Synthetic native transcript fixtures; no personal conversation access."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/scripts'))
from crosstalk_lib import intake
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
        self.actor = {'kind': 'claude', 'surface_id': self.identity['surface_id'],
                      'evidence': json.dumps({'process_id': '123', 'process_start': 'fixture'})}

    def human(self, mid, text, **changes):
        row = {'type': 'user', 'sessionId': 'session-1', 'uuid': mid,
               'origin': {'kind': 'human'}, 'turnOrigin': 'human', 'promptSource': 'typed',
               'isSidechain': False, 'message': {'content': text}}
        row.update(changes)
        self.append(row)

    def append(self, row):
        with self.transcript.open('a') as out:
            out.write(json.dumps(row, ensure_ascii=False) + '\n')

    def capture(self, prompt):
        return intake.capture({'hook_event_name': 'UserPromptSubmit', 'session_id': 'session-1',
                               'transcript_path': str(self.transcript), 'prompt': prompt})

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
        self.assertTrue(intake.requires_engine(self.actor))

    def test_capture_before_transcript_can_be_resolved_after_recording(self):
        prompt = '이 API의 캐시 정책을 독립적으로 검토해줘'
        captured = self.capture(prompt)
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
        intake.mark_consumed(bundle['input_id'], self.actor, 'run-1')
        self.assertFalse(intake.requires_engine(self.actor))
        with self.assertRaises(Error): intake.mark_consumed(bundle['input_id'], self.actor, 'another-run')

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
        intake.mark_consumed(bundle['input_id'],self.actor,'run-clarified')
        self.assertFalse(intake.requires_engine(self.actor))

    def test_arbitrary_transcript_and_symlink_not_accepted(self):
        payload = {'hook_event_name': 'UserPromptSubmit', 'session_id': 'session-1',
                   'transcript_path': str(self.root / 'model-file.jsonl'), 'prompt': '독립적으로 검토해줘'}
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
