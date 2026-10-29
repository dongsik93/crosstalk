"""Isolated executable fixtures; no real terminals or personal state."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'assets/scripts/crosstalk'
A='ghostty:00000000-0000-0000-0000-000000000001'
B='ghostty:00000000-0000-0000-0000-000000000002'
C='ghostty:00000000-0000-0000-0000-000000000003'


class EngineCase(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.state=self.root/'state';self.log=self.root/'input.log'
        bridge=self.root/'bridge'
        bridge.write_text('''#!/usr/bin/env python3
import json,os,sys
cmd=sys.argv[1];target=sys.argv[2] if cmd=='target-identity' else os.environ.get('TEST_ACTOR','')
kinds={'ghostty:00000000-0000-0000-0000-000000000001':'codex','ghostty:00000000-0000-0000-0000-000000000002':'claude','ghostty:00000000-0000-0000-0000-000000000003':'antigravity'}
if cmd in ('strict-identity','target-identity'):
 print(json.dumps(dict(surface_id=target,kind=kinds[target],process_id=target,process_start='fixture',cli_session_id='')))
elif cmd=='capabilities':print(json.dumps({'backend':'ghostty','features':{'exact_addressing':'supported','input_submission':'supported'},'observed_at':'fixture','evidence':['explicit fixture driver']}))
elif cmd=='get-language':print('en')
elif cmd=='send':
 with open(os.environ['TEST_LOG'],'a') as f:f.write(json.dumps(sys.argv[2:])+'\\n')
else:sys.exit(1)
''');bridge.chmod(0o700)
        self.env=dict(os.environ,CROSSTALK_CONFIG_DIR=str(self.state),CROSSTALK_BRIDGE=str(bridge),TEST_LOG=str(self.log),CODEX_THREAD_ID='')
        self.call('migrate')
        self.logical={}
        for surface,kind in ((A,'codex'),(B,'claude'),(C,'antigravity')):
            issued=self.call('session','challenge','--surface',surface,'--kind',kind,'--protocol','3','--engine-version','1',actor=surface)
            bound=self.call('session','bind','--challenge',issued['challenge'],'--kind',kind,'--protocol','3','--engine-version','1',actor=surface)
            self.logical[surface]=bound['session_id']

    def call(self,*args,actor=A,payload=None,text=None,code=0):
        proc=subprocess.run([sys.executable,str(CLI),*args],env=self.env|{'TEST_ACTOR':actor},
                            input=json.dumps(payload) if payload is not None else text,capture_output=True,text=True)
        self.assertEqual(proc.returncode,code,(args,proc.stdout,proc.stderr))
        return json.loads(proc.stdout)

    def start(self,mode='analyze',max_rounds=10,actor=A,peer='claude',op='start'):
        result=self.call('run','start',peer,'Exact original topic\n한글','--operation-id',op,'--mode',mode,'--max-rounds',str(max_rounds),actor=actor)
        return result['run_id']

    def actions(self,run,actor=A):
        return self.call('run','next',run,actor=actor)['actions']

    def take(self,action,actor=A,**kwargs):
        return self.call('run','take',action,actor=actor,**kwargs)

    def submit(self,handle,body='analysis',actor=A,op=None,**kwargs):
        flags=['--action-epoch',str(handle['action_epoch']),'--input-digest',handle['input_digest']]
        if handle.get('lease_token'):
            flags+=['--lease-token',handle['lease_token'],'--claim-version',str(handle['claim_version']),'--binding-generation',str(handle['binding_generation'])]
        return self.call('run','submit',handle['action_id'],'--operation-id',op or 'submit-'+handle['action_id'],*flags,'--result-stdin',payload={'body':body},actor=actor,**kwargs)

    def compare(self,run):
        return self.take(next(a['action_id'] for a in self.actions(run) if a['kind']=='compare'))

    def decide(self,handle,decision='finish',outcome='concluded',op=None,**kwargs):
        payload={'decision':decision,'comparison_summary':'Compare both stored results','caller_position':'My fixed position','cited_result_ids':handle['input']['cited_result_ids'],'unresolved_questions':[], 'closing_summary':'Stored final conclusion'}
        if decision=='finish':payload['requested_outcome']=outcome
        else:payload.update(followup_body='Examine this counterexample',continuation_reason='Resolve the discrepancy')
        flags=['--action-epoch',str(handle['action_epoch']),'--input-digest',handle['input_digest'],'--lease-token',handle['lease_token'],'--claim-version',str(handle['claim_version']),'--binding-generation',str(handle['binding_generation'])]
        return self.call('run','decide',handle['action_id'],'--operation-id',op or 'decide-'+handle['action_id'],*flags,'--result-stdin',payload=payload,**kwargs)

    def both(self,run):
        local=self.take(self.actions(run)[0]['action_id']);peer=self.take(self.actions(run,B)[0]['action_id'],B)
        self.submit(local,'caller initial');self.submit(peer,'peer initial',B)
        return local,peer

    def rows(self,sql,*params):
        conn=sqlite3.connect(self.state/'mailbox.sqlite3');conn.row_factory=sqlite3.Row
        try:return [dict(row) for row in conn.execute(sql,params)]
        finally:conn.close()
