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
import json, os, sys
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
elif op == 'split': print(alive[-1])
''')
    fake.chmod(0o755)
    cmux = root / 'cmux'
    cmux.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_LOG'], 'a') as out:
    out.write(json.dumps(['cmux'] + sys.argv[1:]) + '\\n')
if sys.argv[1] == 'identify': print('{"caller": {\\n"surface_ref": "surface:1"}}')
elif sys.argv[1] == 'list-panes': print('pane:1')
elif sys.argv[1] == 'list-pane-surfaces': print('surface:1 ct-codex\\nsurface:2 ct-claude')
elif sys.argv[1] == 'read-screen': print('screen text')
''')
    cmux.chmod(0o755)
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

    assert run('self') == f'ghostty:{A}'
    run('self', ok=False, CROSSTALK_BACKEND='invalid')
    run('label', f'ghostty:{A}', 'codex')
    run('label', f'ghostty:{B}', 'claude')
    assert run('list-peers') == f'ghostty:{B}\tclaude'
    assert run('ensure-peer', 'codex') == f'ghostty:{B}'
    assert not any(e[0] == 'split' for e in events())
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
    alive.write_text(json.dumps([A]))
    run('send', f'ghostty:{B}', 'closed', ok=False)
    run('self', CROSSTALK_SURFACE_ID=f'ghostty:{B}', ok=False)
    assert run('list-peers', CROSSTALK_BACKEND='cmux') == 'surface:2\tclaude'
    run('send', 'surface:2', payload, CROSSTALK_BACKEND='cmux')
    assert ['cmux', 'send', '--surface', 'surface:2', payload] in events()
    assert run('capture', 'surface:2') == 'screen text'
    assert ['cmux', 'read-screen', '--surface', 'surface:2', '--lines', '200'] in events()
print('PASS: Ghostty identity, routing both ways, literal input, file triggers, readiness, closed panes, cmux regression')
