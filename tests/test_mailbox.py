#!/usr/bin/env python3
"""python3 tests/test_mailbox.py — isolated SQLite/CLI integration, no real pane input."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

CLI = Path(__file__).resolve().parents[1] / 'assets/scripts/crosstalk'
A = 'ghostty:00000000-0000-0000-0000-000000000001'
B = 'ghostty:00000000-0000-0000-0000-000000000002'
C = 'ghostty:00000000-0000-0000-0000-000000000003'

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp).resolve()
    fake = root / 'bridge'
    fake.write_text(f'''#!/usr/bin/env python3
import json, os, sys
actor=os.environ['TEST_ACTOR']
cmd=sys.argv[1]
if cmd=='target-identity': actor=sys.argv[2]
if cmd=='get-language': print(os.environ.get('TEST_LANGUAGE','en'))
elif cmd in ('self','strict-self'): print(actor)
elif cmd in ('strict-identity','target-identity'): print(json.dumps(dict(surface_id=actor,kind='codex' if actor=={A!r} else 'claude' if actor=={B!r} else 'antigravity',process_id=actor,process_start='test',cli_session_id='')))
elif cmd=='list-peers':
    print({B!r}+'\\tclaude' if actor=={A!r} else {A!r}+'\\tcodex')
    if actor!={C!r}: print({C!r}+'\\tantigravity')
elif cmd=='send':
    if os.environ.get('TEST_FAIL')=='1':
        print('terminal closed or busy',file=sys.stderr);sys.exit(1)
    with open(os.environ['TEST_LOG'],'a') as f: f.write(json.dumps(sys.argv[2:])+'\\n')
else: sys.exit(1)
''')
    fake.chmod(0o755)
    log = root / 'notifications'
    env = dict(os.environ, CROSSTALK_BRIDGE=str(fake), CROSSTALK_CONFIG_DIR=str(root / 'state'), TEST_LOG=str(log))

    tokens = {}
    logical = {}
    def call(actor, *args, text=None, ok=True, **extra):
        if args[0] in ('reply','renew') and (actor,args[1]) in tokens and '--lease-token' not in args:
            args = (*args, '--lease-token', tokens[actor,args[1]])
        result = subprocess.run([str(CLI), *args], input=text, env=env | {'TEST_ACTOR': actor} | extra,
                                text=True, capture_output=True)
        assert (result.returncode == 0) == ok, (args, result.stdout, result.stderr)
        data = json.loads(result.stdout) if result.stdout else None
        if isinstance(data,dict) and data.get('lease_token'):
            tokens[actor,data['id']] = data['lease_token']
        return data

    # Migrate an existing database without losing an unread legacy message.
    state = root / 'state'
    state.mkdir(mode=0o700)
    database = state / 'mailbox.sqlite3'
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, reply_to TEXT UNIQUE REFERENCES messages(id), sender TEXT NOT NULL, recipient TEXT NOT NULL, body TEXT NOT NULL, mode TEXT NOT NULL, round INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, received_at TEXT, notify_error TEXT)")
        conn.execute("INSERT INTO messages(id,thread_id,sender,recipient,body,mode,round,created_at) VALUES(?,?,?,?,?,'analyze',1,'2026-09-01')", ('legacy','legacy',A,B,'preserved legacy body'))
    database.chmod(0o600)
    call(B,'receive',ok=False)  # ordinary commands never migrate
    call(A,'migrate')
    unresolved = call(A,'doctor','--offline')['unresolved_sessions']
    for surface,kind in ((A,'codex'),(B,'claude'),(C,'antigravity')):
        prior = next((item for item in unresolved if item['legacy_surface']==surface),None)
        flags = ('--session-id',prior['session_id']) if prior else ()
        challenge = call(surface,'session','challenge','--surface',surface,'--kind',kind,*flags)
        bound = call(surface,'session','bind','--challenge',challenge['challenge'],'--kind',kind,'--protocol','2')
        logical[surface] = bound['session_id']
    legacy = call(B,'receive')
    assert legacy['id']=='legacy' and legacy['body']=='preserved legacy body' and legacy['summary']==''
    payload = '한글 "quotes" \\ $HOME $(touch NEVER) `echo nope`\n' * 5000
    first = call(A, 'send', 'claude', '--stdin', '--id', 'test-first', '--summary', 'Long question summary', text=payload)
    mid = first['id']
    assert first['saved'] and first['processing_state'] == 'queued'
    assert json.loads(log.read_text().splitlines()[-1]) == [B, '[Crosstalk] Question: Long question summary']
    assert payload not in log.read_text()
    assert call(A, 'send', 'claude', '--stdin', '--id', mid, text=payload)['id'] == mid
    call(A, 'send', 'claude', 'changed', '--id', mid, ok=False)
    call(B, 'reply', mid, 'too early', ok=False)
    call(C, 'receive', mid, ok=False)
    call(A, 'receive', mid, ok=False)
    # Atomic receipt: concurrent notification handlers get the body exactly once.
    procs = [subprocess.Popen([str(CLI), 'receive'], env=env | {'TEST_ACTOR': B},
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    results=[]
    for proc in procs:
        out, err=proc.communicate();assert proc.returncode==0, err;results.append(json.loads(out))
    assert sum(r['actionable'] for r in results) == 1
    assert next(r for r in results if r['actionable'])['body'] == payload
    assert not call(B, 'receive', mid)['actionable']
    call(B, 'receive', mid, '--replay',ok=False)
    tokens[B,mid] = next(r for r in results if r['actionable'])['lease_token']
    call(A, 'send', 'claude', 'premature', '--thread', mid, ok=False)
    response=call(B, 'reply', mid, '동의합니다. confidence: high [AGREE]', '--verdict','agree','--confidence','high')
    assert call(B, 'reply', mid, '동의합니다. confidence: high [AGREE]', '--verdict','agree','--confidence','high')['id']==response['id']
    call(B, 'reply', mid, 'different answer', ok=False)
    assert call(A, 'status', mid)[0]['processing_state']=='completed'
    call(B, 'receive', mid, '--replay',ok=False)
    received=call(A, 'receive', response['id'])
    assert received['verdict']=='agree' and received['reply_to']==mid and received['kind']=='reply'
    call(A, 'reply', response['id'], 'no reply loops', ok=False)
    # Continue a thread and enforce the bound in code, not just in AI instructions.
    for number in range(2,11):
        follow=call(A,'send','claude',f'round {number}','--thread',mid,'--after-reply',received['id'],'--lease-token',received['lease_token'])
        assert call(B,'receive',follow['id'])['round']==number
        answered=call(B,'reply',follow['id'],'[AGREE]')
        received=call(A,'receive',answered['id'])
    call(A,'send','claude','round 11','--thread',mid,'--after-reply',received['id'],'--lease-token',received['lease_token'],ok=False)
    assert len(call(A,'history',mid))==20
    call(C,'history',mid,ok=False)
    # Store before failed notification; retry never inserts another request.
    failed=call(A,'send','claude','survives failure',ok=False,TEST_FAIL='1')
    assert failed['saved'] and failed['error']['code']=='NOTIFICATION_UNKNOWN'
    assert call(A,'retry',failed['message_id'])['notification_error'] is None
    assert len(call(A,'history',failed['message_id']))==1
    assert call(B,'receive',failed['message_id'])['body']=='survives failure'
    call(B,'retry',failed['message_id'],ok=False)
    reply_failed=call(B,'reply',failed['message_id'],'durable reply',ok=False,TEST_FAIL='1')
    assert reply_failed['saved']
    assert call(A,'status',failed['message_id'])[0]['processing_state']=='completed'
    call(B,'retry',reply_failed['message_id'])
    call(A,'receive',reply_failed['message_id'])
    # Reverse caller, and fire-and-forget ask storage without reply notification.
    reverse=call(B,'send','codex','reverse caller','--mode','ask')
    assert call(A,'receive')['id']==reverse['id']
    before=len(log.read_text().splitlines())
    ask_reply=call(A,'reply',reverse['id'],'ask answer')
    assert len(log.read_text().splitlines())==before
    assert call(B,'receive',ask_reply['id'])['body']=='ask answer'
    assert not call(B,'receive')['actionable']
    # All wake-ups look alike: choose the correct recipient's rows in insertion order.
    other = call(B, 'send', 'codex', 'other recipient', '--id', 'queue-other')
    queued = []
    for mid, body in [('queue-z','첫 번째 질문'), ('queue-a','second "quoted" question'), ('queue-m','third\nquestion')]:
        queued.append((call(A,'send','claude',body,'--id',mid, TEST_LANGUAGE='ko')['id'], body))
    assert json.loads(log.read_text().splitlines()[-1]) == [B, '[Crosstalk] 질문: third question']
    # Equal or regressing wall-clock timestamps must not reorder queued messages.
    with sqlite3.connect(root/'state/mailbox.sqlite3') as conn:
        conn.execute("UPDATE messages SET created_at='2000-01-01' WHERE id LIKE 'queue-%'")
    for mid, body in queued:
        item = call(B, 'receive')
        assert item['id']==mid and item['body']==body and item['thread_id']==mid
        assert item['sender_session_id']==logical[A] and item['recipient_session_id']==logical[B] and item['actionable']
        assert not call(B,'receive',mid)['actionable']  # old ID-bearing wake-ups remain safe
    assert not call(B,'receive')['actionable']  # duplicate generic wake-up
    assert call(A,'receive')['id']==other['id']
    answer = call(B,'reply',queued[1][0],'answer to the second question')
    received = call(A,'receive')
    assert received['id']==answer['id'] and received['reply_to']==queued[1][0]
    assert received['thread_id']==queued[1][0] and received['body']=='answer to the second question'
    # Identical display summaries still route two distinct requests and exact bodies.
    summary = '같은 요약'
    one = call(A,'send','claude','body one','--summary',summary)
    two = call(A,'send','claude','body two','--summary',summary)
    assert call(B,'receive')['id']==one['id']
    assert call(B,'receive')['id']==two['id']
    assert call(A,'history',one['id'])[0]['body']=='body one'
    assert call(A,'history',two['id'])[0]['body']=='body two'
    control = call(A,'send','claude','full body remains intact','--summary','line 1\n\x1b[31m' + '긴' * 200)
    assert call(B,'receive')['body']=='full body remains intact'
    for caller, destination in [(A,'agy'), (B,'antigravity')]:
        request=call(caller,'send',destination,'Agy peer question','--summary','Agy question summary')
        item=call(C,'receive')
        assert item['id']==request['id'] and item['recipient_session_id']==logical[C] and item['sender_session_id']==logical[caller]
        answer=call(C,'reply',item['id'],'Agy answer','--summary','Agy answer summary')
        item=call(caller,'receive')
        assert item['id']==answer['id'] and item['reply_to']==request['id'] and item['body']=='Agy answer'
    for target, text in map(json.loads,log.read_text().splitlines()):
        assert text.startswith('[Crosstalk] ') and len(text) < 200
        assert ' — Run ' not in text and str(CLI) not in text
        assert all(c.isprintable() for c in text)
    call(A,'send','claude','   ',ok=False)
    call(A,'send','claude','body','--id','../../bad',ok=False)
    call(A,'receive','--replay',ok=False)
    call('surface:1','status',ok=False)
    call('ghostty:' + '-' * 36,'status',ok=False)
    db=root/'state/mailbox.sqlite3'
    assert db.stat().st_mode & 0o077 == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT summary FROM messages WHERE id=?',('test-first',)).fetchone()[0]=='Long question summary'
print('PASS: mailbox persistence, concurrent receipt, idempotency, authorization, replies, retry, 10 rounds, ask, reverse caller')
