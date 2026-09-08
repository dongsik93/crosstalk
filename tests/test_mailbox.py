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
    root = Path(tmp)
    fake = root / 'bridge'
    fake.write_text(f'''#!/usr/bin/env python3
import json, os, sys
actor=os.environ['TEST_ACTOR']
cmd=sys.argv[1]
if cmd=='get-language': print(os.environ.get('TEST_LANGUAGE','en'))
elif cmd=='self': print(actor)
elif cmd=='list-peers':
    print({B!r}+'\\tclaude' if actor=={A!r} else {A!r}+'\\tcodex')
elif cmd=='send':
    if os.environ.get('TEST_FAIL')=='1':
        print('terminal closed or busy',file=sys.stderr);sys.exit(1)
    with open(os.environ['TEST_LOG'],'a') as f: f.write(json.dumps(sys.argv[2:])+'\\n')
else: sys.exit(1)
''')
    fake.chmod(0o755)
    log = root / 'notifications'
    env = dict(os.environ, CROSSTALK_BRIDGE=str(fake), CROSSTALK_CONFIG_DIR=str(root / 'state'), TEST_LOG=str(log))

    def call(actor, *args, text=None, ok=True, **extra):
        result = subprocess.run([str(CLI), *args], input=text, env=env | {'TEST_ACTOR': actor} | extra,
                                text=True, capture_output=True)
        assert (result.returncode == 0) == ok, (args, result.stdout, result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    # Migrate an existing database without losing an unread legacy message.
    state = root / 'state'
    state.mkdir()
    database = state / 'mailbox.sqlite3'
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, reply_to TEXT UNIQUE REFERENCES messages(id), sender TEXT NOT NULL, recipient TEXT NOT NULL, body TEXT NOT NULL, mode TEXT NOT NULL, round INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, received_at TEXT, notify_error TEXT)")
        conn.execute("INSERT INTO messages(id,thread_id,sender,recipient,body,mode,round,created_at) VALUES(?,?,?,?,?,'analyze',1,'2026-09-01')", ('legacy','legacy',A,B,'preserved legacy body'))
    database.chmod(0o600)
    legacy = call(B,'receive')
    assert legacy['id']=='legacy' and legacy['body']=='preserved legacy body' and legacy['summary']==''
    payload = '한글 "quotes" \\ $HOME $(touch NEVER) `echo nope`\n' * 5000
    first = call(A, 'send', 'claude', '--stdin', '--id', 'test-first', '--summary', 'Long question summary', text=payload)
    mid = first['id']
    assert first['saved'] and first['status'] == 'pending'
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
    assert call(B, 'receive', mid, '--replay')['body'] == payload
    call(A, 'send', 'claude', 'premature', '--thread', mid, ok=False)
    response=call(B, 'reply', mid, '동의합니다. confidence: high [AGREE]')
    assert call(B, 'reply', mid, '동의합니다. confidence: high [AGREE]')['id']==response['id']
    call(B, 'reply', mid, 'different answer', ok=False)
    assert call(A, 'status', mid)[0]['status']=='replied'
    assert not call(B, 'receive', mid, '--replay')['actionable']
    received=call(A, 'receive', response['id'])
    assert received['verdict']=='AGREE' and received['reply_to']==mid and received['kind']=='reply'
    call(A, 'reply', response['id'], 'no reply loops', ok=False)
    # Continue a thread and enforce the bound in code, not just in AI instructions.
    for number in range(2,11):
        follow=call(A,'send','claude',f'round {number}','--thread',mid)
        assert call(B,'receive',follow['id'])['round']==number
        answered=call(B,'reply',follow['id'],'[AGREE]')
        call(A,'receive',answered['id'])
    call(A,'send','claude','round 11','--thread',mid,ok=False)
    assert len(call(A,'history',mid))==20
    call(C,'history',mid,ok=False)
    # Store before failed notification; retry never inserts another request.
    failed=call(A,'send','claude','survives failure',ok=False,TEST_FAIL='1')
    assert failed['saved'] and failed['notification_error']
    assert call(A,'retry',failed['id'])['notification_error'] is None
    assert len(call(A,'history',failed['id']))==1
    assert call(B,'receive',failed['id'])['body']=='survives failure'
    call(B,'retry',failed['id'],ok=False)
    reply_failed=call(B,'reply',failed['id'],'durable reply',ok=False,TEST_FAIL='1')
    assert reply_failed['saved']
    assert call(A,'status',failed['id'])[0]['status']=='replied'
    call(B,'retry',reply_failed['id'])
    call(A,'receive',reply_failed['id'])
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
        assert item['sender']==A and item['recipient']==B and item['actionable']
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
