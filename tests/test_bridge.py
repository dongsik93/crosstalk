#!/usr/bin/env python3
"""Run with python3 tests/test_bridge.py. Uses fake terminals; sends no real UI input."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

BRIDGE = Path(__file__).resolve().parents[1] / 'assets/scripts/crosstalk_bridge.sh'
A = '00000000-0000-0000-0000-000000000001'
B = '00000000-0000-0000-0000-000000000002'

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    log = root / 'calls.jsonl'
    fake = root / 'osascript'
    fake.write_text('''#!/usr/bin/env python3
import json, os, sys, subprocess
from pathlib import Path
args = sys.argv[2:]
with open(os.environ['TEST_LOG'], 'a') as out:
    out.write(json.dumps(args) + '\\n')
op, tid = args[:2]
alive = json.loads(Path(os.environ['TEST_ALIVE']).read_text())
if op == 'find-cwd': sys.exit(1)
if tid not in alive: sys.exit(1)
if op == 'exists': print(tid)
elif op == 'list': print('\\n'.join(alive))
elif op == 'split':
    if os.environ.get('TEST_LAUNCH') == '1':
        child_env = dict(os.environ, PATH=args[4] if len(args)>4 else '/usr/bin:/bin')
        subprocess.Popen(['/bin/bash', '--noprofile', '--norc', '-c', args[3]], env=child_env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(alive[-1])
''')
    fake.chmod(0o755)
    cmux = root / 'cmux'
    cmux.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_LOG'], 'a') as out:
    out.write(json.dumps(['cmux'] + sys.argv[1:]) + '\\n')
if os.environ.get('TEST_CMUX_DOWN') == '1': sys.exit(1)
if sys.argv[1] == 'identify': print('{"caller": {\\n"surface_ref": "surface:1"}}')
elif sys.argv[1] == 'list-panes': print('pane:1')
elif sys.argv[1] == 'list-pane-surfaces': print('surface:1 ct-codex\\nsurface:2 ct-claude')
elif sys.argv[1] == 'read-screen': print('screen text')
''')
    cmux.chmod(0o755)
    ps = root / 'ps'
    ps.write_text('''#!/usr/bin/env python3
import os, sys
name = os.environ.get('TEST_PARENT_TERMINAL', 'other')
if 'ppid=,tty=' in sys.argv:
    print('1 ttys555' if sys.argv[-1]=='4242' else '4242 ??')
elif 'lstart=' in sys.argv: print(os.environ.get('TEST_START', 'Mon Sep 7 22:58:00 2026'))
else: print('1 /Applications/' + name + '.app/Contents/MacOS/' + name)
''')
    ps.chmod(0o755)
    alive = root / 'alive.json'
    alive.write_text(json.dumps([A, B]))
    env = dict(os.environ, PATH=f'{root}:{os.environ["PATH"]}', TEST_LOG=str(log),
               TEST_ALIVE=str(alive), CROSSTALK_CONFIG_DIR=str(root / 'config'),
               CROSSTALK_ROOT=str(root / 'runs'), CROSSTALK_BACKEND='ghostty',
               CROSSTALK_SURFACE_ID=f'ghostty:{A}')

    def run(*args, ok=True, **extra):
        result = subprocess.run(['bash', str(BRIDGE), *args], env=env | extra,
                                capture_output=True, text=True)
        assert (result.returncode == 0) == ok, (args, result.stdout, result.stderr)
        return result.stdout.strip()

    def events():
        return [json.loads(line) for line in log.read_text().splitlines()]

    auto = dict(CROSSTALK_BACKEND='', CROSSTALK_SURFACE_ID='', TERM_PROGRAM='',
                GHOSTTY_RESOURCES_DIR='', GHOSTTY_BIN_DIR='', CMUX_SURFACE_ID='', CMUX_WORKSPACE_ID='')
    assert run('backend', **(auto | {'TEST_PARENT_TERMINAL': 'ghostty'})) == 'ghostty'
    assert run('backend', **(auto | {'GHOSTTY_RESOURCES_DIR': '/Applications/Ghostty.app/Contents/Resources'})) == 'ghostty'
    assert run('backend', **(auto | {'GHOSTTY_BIN_DIR': '/Applications/Ghostty.app/Contents/MacOS'})) == 'ghostty'
    assert run('backend', **(auto | {'TERM_PROGRAM': 'ghostty', 'CMUX_SURFACE_ID': 'stale', 'TEST_CMUX_DOWN': '1'})) == 'ghostty'
    assert run('backend', **(auto | {'TEST_PARENT_TERMINAL': 'ghostty', 'CMUX_SURFACE_ID': 'stale'})) == 'ghostty'
    assert run('backend', **(auto | {'TEST_PARENT_TERMINAL': 'cmux', 'GHOSTTY_BIN_DIR': 'inherited'})) == 'cmux'
    assert run('backend', **(auto | {'CMUX_SURFACE_ID': 'surface:1'})) == 'cmux'
    run('backend', ok=False, **(auto | {'CMUX_SURFACE_ID': 'stale', 'TEST_CMUX_DOWN': '1'}))
    run('backend', ok=False, **auto)
    assert run('self') == f'ghostty:{A}'
    run('self', ok=False, CROSSTALK_BACKEND='invalid')
    run('label', f'ghostty:{A}', 'codex')
    run('label', f'ghostty:{B}', 'claude')
    assert run('list-peers') == f'ghostty:{B}\tclaude'
    assert run('ensure-peer', 'codex') == f'ghostty:{B}'
    assert not any(e[0] == 'split' for e in events())
    # Explicit selection is remembered for this caller, without changing parent environment.
    run('self', ok=False, CROSSTALK_SURFACE_ID='')  # ambiguous/missing cwd lookup
    assert run('bind', f'ghostty:{A}') == f'ghostty:{A}'
    assert run('self', CROSSTALK_SURFACE_ID='') == f'ghostty:{A}'
    run('self', ok=False, CROSSTALK_SURFACE_ID='', TEST_START='a different process start')
    run('bind', 'ghostty:invalid', ok=False)
    # Untrusted text is a single argv value, never AppleScript or shell code.
    payload = '한글 "quote" \\ backslash\n$HOME $(touch NEVER) `echo nope`'
    run('send', f'ghostty:{B}', payload)
    assert ['text', B, payload] in events()
    assert ['key', B, 'enter'] in events()
    before = len(events())
    run('send', 'ghostty:../../invalid', 'ignored', ok=False)
    assert len(events()) == before
    body = root / 'task with spaces.md'
    body.write_text('large body\n' * 10000)
    run('send-via-file', f'ghostty:{B}', str(body), '[crosstalk] preamble claude RUN_ID=test')
    sent = [e[2] for e in events() if e[0] == 'text'][-1]
    assert 'Read the task file' in sent and 'large body' not in sent and len(sent) < 500
    run('send-via-file', f'ghostty:{B}', str(root / 'missing'), 'trigger', ok=False)
    # Callback uses manifest ID and kind, independent of the peer's environment.
    for kind, moderator, peer in [('codex', A, B), ('claude', B, A)]:
        rid = run('start-run', CROSSTALK_MODERATOR_KIND=kind, CROSSTALK_SURFACE_ID=f'ghostty:{moderator}')
        manifest = root / 'runs' / f'run-{rid}' / 'manifest.json'
        assert json.loads(manifest.read_text())['moderator_surface'] == f'ghostty:{moderator}'
        run('ping', rid, 'claude' if kind == 'codex' else 'codex', '1',
            CROSSTALK_SURFACE_ID=f'ghostty:{peer}', CROSSTALK_BACKEND='cmux')
        callback = [e for e in events() if e[0] == 'text'][-1]
        assert callback[1] == moderator
        assert ('$crosstalk callback' in callback[2]) == (kind == 'codex')
    # Pending startup must not pass or create another pane merely because labelled.
    state = root / 'config' / 'ghostty' / f'{B}.kind.ready'
    ready = root / 'ready'
    ready.write_text('')
    state.write_text(str(ready))
    run('ensure-peer', 'codex', ok=False, READY_MAX_WAIT='1')
    assert not any(e[0] == 'split' for e in events())
    ready.write_text('ready')
    assert run('ensure-peer', 'codex') == f'ghostty:{B}'
    assert not state.exists()
    run('capture', f'ghostty:{A}', ok=False)
    run('wait-turn', f'ghostty:{A}', 'test', 'run-test-r01-claude-a1', ok=False)
    # Execute the actual generated launcher, but use a fake CLI and never open a UI.
    runtime = root / 'ct-test-runtime'
    runtime.write_text('#!/bin/sh\nexec ' + subprocess.check_output(['which', 'python3'], text=True).strip() + ' "$@"\n')
    runtime.chmod(0o755)
    for kind in ('codex', 'claude'):
        cli = root / kind
        cli.write_text('''#!/usr/bin/env ct-test-runtime
import json, os, re, subprocess, sys
from pathlib import Path
assert os.environ['CROSSTALK_SURFACE_ID'].startswith('ghostty:')
assert len(sys.argv)==2
prompt = sys.argv[1]
ack = re.search(r'Run exactly: (.*?) [.] Then say', prompt).group(1)
Path(os.environ['TEST_LAUNCH_RESULT']).write_text(json.dumps({'id': os.environ['CROSSTALK_SURFACE_ID'], 'prompt': prompt}))
subprocess.run(['/bin/bash', '-c', ack], check=True)
''')
        cli.chmod(0o755)
        scratch = root / "temp dir ' with spaces"
        scratch.mkdir(exist_ok=True)
        result = root / 'launch-result'
        assert run('launch', kind, TEST_LAUNCH='1', READY_MAX_WAIT='10', TMPDIR=str(scratch), TEST_LAUNCH_RESULT=str(result)) == f'ghostty:{B}'
        data = json.loads(result.read_text())
        assert data['id'] == f'ghostty:{B}' and 'Crosstalk startup check' in data['prompt']
        split = [e for e in events() if e[0]=='split'][-1]
        assert split[3].startswith('/bin/bash ') and '/bin/bash -c ' not in split[3]
        assert split[4] == env['PATH']
        assert not list(scratch.glob('crosstalk-ready.*'))
    alive.write_text(json.dumps([A]))
    run('send', f'ghostty:{B}', 'closed', ok=False)
    run('self', CROSSTALK_SURFACE_ID=f'ghostty:{B}', ok=False)
    assert run('list-peers', CROSSTALK_BACKEND='cmux') == 'surface:2\tclaude'
    run('send', 'surface:2', payload, CROSSTALK_BACKEND='cmux')
    assert ['cmux', 'send', '--surface', 'surface:2', payload] in events()
    assert run('capture', 'surface:2') == 'screen text'
    assert ['cmux', 'read-screen', '--surface', 'surface:2', '--lines', '200'] in events()
print('PASS: Ghostty identity, routing both ways, literal input, file triggers, readiness, closed panes, cmux regression')
