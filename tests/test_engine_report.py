"""Stored result rendering and non-destructive export paths."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'assets/scripts'))
from crosstalk_lib.engine import report
from crosstalk_lib.protocol import Error


class ReportTests(unittest.TestCase):
    def data(self, mode='analyze', lifecycle='completed'):
        run=dict(run_id='test',raw_topic='topic\n```quoted```',mode=mode,lifecycle=lifecycle,phase='terminal',
                 outcome='sampled' if mode=='ask' else 'concluded',caller_session_id='a',peer_session_id='b',requested_peer_kind='claude',
                 engine_version=1,protocol_version=3,prompt_bundle_version=1)
        actions=[dict(action_id='initial',kind='local_initial',round_no=1,result_json=json.dumps({'body':'my answer','assumptions':['assumption']})),
                 dict(action_id='peer',kind='peer_analysis',round_no=1,result_ref='reply',result_metadata=json.dumps({'evidence_refs':[{'kind':'claim','value':'test passed','status':'reported'}]}))]
        rounds=[dict(round_no=1,caller_position_ref='initial',peer_reply_id='reply',peer_request_id='request')]
        messages={'reply':{'body':'peer answer','summary':'short','lease_token_hash':'MUST NOT EXPORT'}}
        if mode=='analyze':
            actions.append(dict(action_id='compare',kind='compare',round_no=1,result_json=json.dumps({'comparison_summary':'comparison','closing_summary':'conclusion','caller_position':'revised','unresolved_questions':[]})))
            rounds[0]['compare_action_id']='compare'
        return report.build(run,rounds,actions,messages)

    def test_report_contains_stored_text_not_credentials(self):
        data=self.data()
        self.assertEqual(data['initial_position']['body'],'my answer')
        self.assertEqual(data['rounds'][0]['peer_result']['body'],'peer answer')
        self.assertEqual(data['decision']['closing_summary'],'conclusion')
        self.assertEqual(data['evidence_refs'][0]['status'],'reported')
        self.assertNotIn('MUST NOT EXPORT',json.dumps(data))
        self.assertIn('````\ntopic\n```quoted```\n````',report.markdown(data))

    def test_ask_only_individual_answers(self):
        data=self.data('ask')
        self.assertIsNone(data['decision'])
        self.assertEqual(data['individual_answers']['peer']['body'],'peer answer')
        self.assertNotIn('Caller comparison',report.markdown(data))
        self.assertEqual(data['outcome'],'sampled')

    def test_partial_report_preserves_missing_answers(self):
        data=report.build(dict(run_id='p',raw_topic='t',mode='analyze',lifecycle='cancelled',phase='terminal',caller_session_id='a'),
                          [dict(round_no=1)],[],{})
        self.assertTrue(data['partial'])
        self.assertEqual(data['outcome'],'cancelled')
        self.assertIn('peer_result',data['rounds'][0]['missing'])
        self.assertIsNone(data['rounds'][0]['peer_result'])

    def test_export_idempotent_collision_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()/'exports'
            payload=json.dumps(self.data());md=report.markdown(self.data())
            first=report.export(root,'test',payload,md)
            self.assertEqual(first,report.export(root,'test',payload,md))
            self.assertEqual((root/'test.json').stat().st_mode & 0o077,0)
            (root/'test.md').write_text('user content')
            with self.assertRaises(Error):report.export(root,'test',payload,md)
            self.assertEqual((root/'test.md').read_text(),'user content')
            report.export(root,'test',payload,md,overwrite=True)
            with self.assertRaises(Error):report.export(root,'../escape',payload,md)
            (root/'link.json').symlink_to(root/'test.json')
            with self.assertRaises(Error):report.export(root,'link',payload,md,overwrite=True)

    def test_export_failure_can_resume_without_reanalysis(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()/'exports'
            original=os.link
            def fail_second(src,dst):
                if str(dst).endswith('.md'):raise OSError('disk full')
                return original(src,dst)
            with patch.object(report.os,'link',side_effect=fail_second):
                with self.assertRaises(OSError):report.export(root,'test','{}','stored report')
            self.assertTrue((root/'test.json').is_file())
            self.assertFalse((root/'test.md').exists())
            result=report.export(root,'test','{}','stored report')
            self.assertEqual(Path(result['md']['path']).read_text(),'stored report')


if __name__=='__main__':
    unittest.main()
