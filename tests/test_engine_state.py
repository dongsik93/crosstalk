"""Pure engine contracts and input snapshot guarantees."""
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/scripts'))
from crosstalk_lib.engine import contracts, context, state
from crosstalk_lib.protocol import Error


class ContractTests(unittest.TestCase):
    def assertCode(self, code, callback, *args):
        with self.assertRaises(Error) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)

    def test_json_refuses_duplicate_keys_and_nonfinite_values(self):
        for value in ('{"body":"a","body":"b"}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"a":{"a":1,"a":2}}', '{bad'):
            self.assertCode('INVALID_ARGUMENT', contracts.loads, value)
        self.assertEqual(contracts.loads('{"body":"한글\\r\\n text"}')['body'], '한글\r\n text')

    def test_analysis_preserves_raw_body_and_rejects_wrong_types(self):
        body = '  e\u0301\r\n한글 $(not-code)  '
        value = contracts.analysis({'body': body})
        self.assertEqual(value['body'], body)
        self.assertEqual(value['verdict'], 'none')
        for payload in ({'body': 1}, {'body':'x','confidence':0.85}, {'body':'x','schema_version':True},
                        {'body':'x','verdict':'agree!'}, {'body':'x','assumptions':'one'},
                        {'body':'x','unknown':'field'}, {'body':'x','verdict':'disagree'}):
            self.assertCode('INVALID_ARGUMENT', contracts.analysis, payload)
        self.assertCode('CONTEXT_TOO_LARGE', contracts.analysis, {'body':'가' * (contracts.BODY_LIMIT // 3 + 1)})

    def decision(self, **extra):
        return dict(decision='finish', requested_outcome='concluded', comparison_summary='Compare',
                    caller_position='Position', cited_result_ids=['caller', 'reply'], unresolved_questions=[],
                    closing_summary='Conclusion', **extra)

    def test_decisions_have_required_evidence_and_no_ambiguous_fields(self):
        value = contracts.decision(self.decision())
        self.assertEqual(value['requested_outcome'], 'concluded')
        for field in ('comparison_summary', 'caller_position', 'cited_result_ids', 'unresolved_questions', 'closing_summary'):
            payload = self.decision();payload.pop(field)
            self.assertCode('DECISION_INVALID', contracts.decision, payload)
        self.assertCode('DECISION_INVALID', contracts.decision, self.decision(followup_body='secret next question'))
        payload=self.decision();payload.update(decision='continue',followup_body='next',continuation_reason='reason');payload.pop('requested_outcome')
        self.assertEqual(contracts.decision(payload)['decision'], 'continue')
        payload['cited_result_ids']=['same','same']
        self.assertCode('DECISION_INVALID', contracts.decision, payload)

    def test_external_evidence_is_reported_not_verified(self):
        value=contracts.analysis({'body':'x','evidence_refs':[{'kind':'url','value':'https://example.invalid'}]})
        self.assertEqual(value['evidence_refs'][0]['status'],'reported')
        self.assertCode('INVALID_ARGUMENT',contracts.analysis,{'body':'x','evidence_refs':[{'kind':'claim','value':'tests passed','status':'verified'}]})

    def test_snapshot_is_pinned_and_preset_path_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            preset=root/'rules/ko/custom.md';preset.parent.mkdir(parents=True)
            preset.write_bytes('원문\r\nsecond\r\n'.encode())
            (root/'config.json').write_text(json.dumps({'language':'ko','active_rules':'custom','active_persona':'none'}))
            with patch.dict(os.environ, CROSSTALK_CONFIG_DIR=str(root)):
                snap=context.snapshot('topic\r\n', 'analyze')
                before=context.render('local_initial',snap,1)
                preset.write_text('changed')
                self.assertEqual(context.render('local_initial',snap,1),before)
                self.assertEqual(snap['rules']['content'],'원문\r\nsecond\r\n')
                self.assertCode('INVALID_ARGUMENT',context.snapshot,'topic','analyze','../escape')
                self.assertCode('INITIAL_POSITION_REQUIRED',context.render,'peer_analysis',snap,1,'hidden caller')

    def test_pure_state_sequences_keep_terminal_and_ask_distinct(self):
        randomizer=random.Random(120)
        for _ in range(100):
            caller,peer=randomizer.choice([False,True]),randomizer.choice([False,True])
            for mode in ('analyze','ask'):
                actual=state.next_phase(mode,caller,peer,'collecting')
                expected=('comparing' if mode=='analyze' else 'finalizing') if caller and peer else 'collecting'
                self.assertEqual(actual,expected)
                self.assertEqual(state.next_phase(mode,caller,peer,'terminal'),'terminal')
        cap=state.applied_decision({'decision':'continue'},10,10)
        self.assertEqual(cap['outcome'],'round_limit')
        self.assertEqual(cap['requested_decision'],'continue')
        self.assertEqual(cap['applied_decision'],'finish')


if __name__=='__main__':
    unittest.main()
