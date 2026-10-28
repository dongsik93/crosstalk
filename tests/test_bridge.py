#!/usr/bin/env python3
"""Run with python3 tests/test_bridge.py. Uses fake terminals; sends no real UI input."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil
import sys

BRIDGE = Path(__file__).resolve().parents[1] / 'assets/scripts/crosstalk_bridge.sh'
A = '00000000-0000-0000-0000-000000000001'
B = '00000000-0000-0000-0000-000000000002'

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    # Test an isolated installation: generated startup prompts use its sibling runtime.
    scripts = root / 'scripts'
    shutil.copytree(BRIDGE.parent, scripts, ignore=shutil.ignore_patterns('__pycache__'))
    BRIDGE = scripts / 'crosstalk_bridge.sh'
    (scripts / 'crosstalk').write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['TEST_LOG'], 'a') as out:
    out.write(json.dumps(['mailbox', *args, os.environ['CROSSTALK_CONFIG_DIR']]) + '\\n')
if args[:2] == ['session', 'challenge']:
    assert args[args.index('--surface') + 1] == os.environ['CROSSTALK_SURFACE_ID']
    print(json.dumps({'challenge': 'startup-test-nonce'}))
elif args[:2] == ['session', 'bind']:
    assert args[args.index('--challenge') + 1] == 'startup-test-nonce'
    assert args[args.index('--protocol') + 1] == '2'
    if os.environ.get('TEST_BIND_FAIL') == '1': sys.exit(1)
    print(json.dumps({'bound': True}))
else:
    sys.exit(2)
''')
    (scripts / 'crosstalk').chmod(0o755)
    log = root / 'calls.jsonl'
    fake = root / 'osascript'
    fake.write_text('''#!/usr/bin/env python3
import json, os, re, sys, subprocess, urllib.parse
from pathlib import Path
args = sys.argv[2:]
with open(os.environ['TEST_LOG'], 'a') as out:
    out.write(json.dumps(args) + '\\n')
if args[0] == 'wd-list':
    # A reports whatever OSC 7 path its TTY last carried (the probe's or the restored one).
    seen = Path(os.environ['TEST_OSC']).read_text(errors='replace') if os.environ.get('TEST_OSC') else ''
    paths = re.findall(r'\x1b]7;file://[^/]*([^\x1b]*)\x1b\\\\', seen)
    wd = urllib.parse.unquote(paths[-1]) if paths and os.environ.get('TEST_PROBE_MATCH') == '1' else os.environ.get('TEST_WD', '/work/한글 dir')
    if wd.startswith('/crosstalk-probe-') and os.environ.get('TEST_PROBE_DELAY'):
        import time
        Path(os.environ['TEST_PROBE_ACTIVE']).touch()
        time.sleep(float(os.environ['TEST_PROBE_DELAY']))
    print(f'{os.environ.get("TEST_PROBE_ID", "x")}\\t{wd}\\nother\\t/elsewhere'); sys.exit(0)
op, tid = args[:2]
alive = json.loads(Path(os.environ['TEST_ALIVE']).read_text())
if op == 'find-cwd': sys.exit(1)
if op == 'cwd-list': print('\\n'.join(alive)); sys.exit(0)
if tid not in alive: sys.exit(1)
if op == 'exists': print(tid)
elif op == 'tty': print('/dev/ttys555')
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
    # TEST_INNER_TTY: the tool shell sits on a CLI-owned inner pty (agy), the CLI on the pane's TTY.
    inner = os.environ.get('TEST_INNER_TTY')
    if sys.argv[-1] == '4242': print('1 ' + os.environ.get('TEST_TTY', 'ttys555'))
    elif sys.argv[-1] == '4241': print('4242 ' + inner)  # second shell on the inner pty
    else: print(('4241 ' + inner) if inner else '4242 ??')
elif 'lstart=' in sys.argv: print(os.environ.get('TEST_START', 'Mon Sep 7 22:58:00 2026'))
elif 'pid=,pgid=,tpgid=,stat=,comm=' in sys.argv:
    name = os.environ.get('TEST_FOREGROUND_KIND', 'codex')
    pid = os.environ.get('TEST_FOREGROUND_PID', '4242')
    if name == 'node':
        print('4141 4242 4242 S+ node')
        name, pid = os.environ.get('TEST_CHILD_KIND', 'codex'), '4343'
    group = '5555' if os.environ.get('TEST_BACKGROUND') else '4242'
    print(pid + ' ' + group + ' 4242 S+ /usr/local/bin/' + name)
    print('8888 7777 4242 S /usr/local/bin/codex')
    print('4240 4242 4242 Ss+ /usr/bin/login')
else: print('1 /Applications/' + name + '.app/Contents/MacOS/' + name)
''')
    ps.chmod(0o755)
    alive = root / 'alive.json'
    alive.write_text(json.dumps([A, B]))
    env = dict(os.environ, PATH=f'{root}:{os.environ["PATH"]}', TEST_LOG=str(log),
               TEST_ALIVE=str(alive), CROSSTALK_CONFIG_DIR=str(root / 'config'),
               CROSSTALK_ROOT=str(root / 'runs'), CROSSTALK_BACKEND='ghostty',
               CROSSTALK_SURFACE_ID=f'ghostty:{A}', CODEX_THREAD_ID='')

    def run(*args, ok=True, **extra):
        result = subprocess.run(['bash', str(BRIDGE), *args], env=env | extra,
                                capture_output=True, text=True, timeout=20)
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
    assert run('strict-self') == f'ghostty:{A}'
    run('self', ok=False, CROSSTALK_BACKEND='invalid')
    run('label', f'ghostty:{A}', 'codex')
    run('label', f'ghostty:{B}', 'claude')
    exact = json.loads(run('strict-identity'))
    assert exact['surface_id'] == f'ghostty:{A}' and exact['kind'] == 'codex'
    assert exact['process_id'] == '4242' and exact['process_start']
    assert json.loads(run('strict-identity', TEST_FOREGROUND_KIND='claude'))['kind'] == 'claude'
    assert json.loads(run('strict-identity', TEST_FOREGROUND_KIND='claude.exe'))['kind'] == 'claude'
    run('strict-identity', TEST_FOREGROUND_KIND='zsh', ok=False)
    run('strict-identity', TEST_BACKGROUND='1', ok=False)
    wrapped = json.loads(run('strict-identity', TEST_FOREGROUND_KIND='node'))
    assert wrapped['kind'] == 'codex' and wrapped['process_id'] == '4343'
    target = json.loads(run('target-identity', f'ghostty:{B}', CODEX_THREAD_ID='sender-thread', TEST_FOREGROUND_KIND='claude'))
    assert target['surface_id'] == f'ghostty:{B}' and target['kind'] == 'claude'
    assert target['cli_session_id'] == ''
    run('target-identity', 'ghostty:invalid', ok=False)
    run('strict-identity', TEST_FOREGROUND_KIND='node', TEST_CHILD_KIND='other', ok=False)
    assert json.loads(run('strict-identity', TEST_FOREGROUND_PID='9999', TEST_START='new instance'))['process_start'] == 'new instance'
    assert run('list-peers') == f'ghostty:{B}\tclaude'
    assert run('ensure-peer', 'codex') == f'ghostty:{B}'
    assert not any(e[0] == 'split' for e in events())
    # Explicit selection is remembered for this caller, without changing parent environment.
    run('self', ok=False, CROSSTALK_SURFACE_ID='')  # ambiguous/missing cwd lookup
    assert run('bind', f'ghostty:{A}') == f'ghostty:{A}'
    assert run('self', CROSSTALK_SURFACE_ID='') == f'ghostty:{A}'
    run('self', ok=False, CROSSTALK_SURFACE_ID='', TEST_START='a different process start')
    # Labels written once (by setup in any pane) let each CLI find its own pane by kind.
    assert run('self', CROSSTALK_SURFACE_ID='', TEST_START='other start', TEST_PARENT_TERMINAL='codex') == f'ghostty:{A}'
    assert run('self', CROSSTALK_SURFACE_ID='', TEST_START='third start', TEST_PARENT_TERMINAL='claude') == f'ghostty:{B}'
    # Codex tool shells share a daemon: identity follows CODEX_THREAD_ID, not the process tree.
    assert run('self', CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t1') == f'ghostty:{A}'
    run('strict-self', ok=False, CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t1')
    assert run('bind', f'ghostty:{B}', CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t2') == f'ghostty:{B}'
    assert run('self', CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t2') == f'ghostty:{B}'
    run('strict-self', ok=False, CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t2')
    assert run('self', CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t1') == f'ghostty:{A}'
    # A thread resumed in A must not inherit its B cache while both panes are still live.
    assert json.loads(alive.read_text()) == [A, B]
    before = len(events())
    run('strict-identity', ok=False, CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t2')
    assert not any(e[0] in ('tty', 'text', 'key') for e in events()[before:])
    current = json.loads(run('strict-identity', CROSSTALK_SURFACE_ID=f'ghostty:{A}', CODEX_THREAD_ID='t2'))
    assert current['surface_id'] == f'ghostty:{A}' and current['cli_session_id'] == 't2'
    assert json.loads((root / 'config/ghostty/bind-codex-t2.json').read_text())['id'] == B
    # Resume in a new pane: the cached pane is gone, so it is re-resolved by kind.
    dead = '00000000-0000-0000-0000-00000000dead'
    (root / 'config/ghostty/bind-codex-t3.json').write_text(json.dumps({'id': dead, 'stamp': 'session', 'tty': 'codex'}))
    assert run('self', CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t3') == f'ghostty:{A}'
    run('strict-self', ok=False, CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='t3')
    run('bind', f'ghostty:{A}', ok=False, CODEX_THREAD_ID='../../escape')
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
    for kind in ('codex', 'claude', 'antigravity', 'agy'):
        cli = root / ('agy' if kind in ('antigravity','agy') else kind)
        cli.write_text('''#!/usr/bin/env ct-test-runtime
import json, os, re, subprocess, sys
from pathlib import Path
assert os.environ['CROSSTALK_SURFACE_ID'].startswith('ghostty:')
if Path(sys.argv[0]).name == 'agy':
    expected = ['--dangerously-skip-permissions','--prompt-interactive'] if os.environ.get('TEST_AUTO_APPROVE')=='1' else ['--prompt-interactive']
    assert sys.argv[1:-1]==expected
else:
    flag = '--yolo' if Path(sys.argv[0]).name=='codex' else '--dangerously-skip-permissions'
    assert sys.argv[1:-1] == ([flag] if os.environ.get('TEST_AUTO_APPROVE')=='1' else [])
prompt = sys.argv[-1]
assert len(prompt) < 90 and 'session bind' not in prompt and 'CROSSTALK_' not in prompt
startup = Path(re.fullmatch(r'Crosstalk startup check[.] Read (/tmp/ct-startup[.][A-Za-z0-9]+)[.]', prompt).group(1))
assert startup.stat().st_mode & 0o777 == 0o600
instructions = startup.read_text()
assert '__SID__' not in instructions and os.environ['CROSSTALK_SURFACE_ID'] in instructions
ack = re.search(r'Run exactly: (.*?) [.] Then say', instructions).group(1)
Path(os.environ['TEST_LAUNCH_RESULT']).write_text(json.dumps({'id': os.environ['CROSSTALK_SURFACE_ID'], 'prompt': prompt, 'instructions': instructions, 'startup': str(startup)}))
subprocess.run(['/bin/bash', '-c', ack], check=True)
''')
        cli.chmod(0o755)
        scratch = root / "temp dir ' with spaces"
        scratch.mkdir(exist_ok=True)
        result = root / 'launch-result'
        assert run('launch', kind, TEST_LAUNCH='1', READY_MAX_WAIT='10', TMPDIR=str(scratch), TEST_LAUNCH_RESULT=str(result)) == f'ghostty:{B}'
        data = json.loads(result.read_text())
        assert data['id'] == f'ghostty:{B}' and 'Crosstalk startup check' in data['prompt']
        assert 'session challenge' in data['instructions'] and '--protocol 2' in data['instructions']
        assert not Path(data['startup']).exists()
        bound = [e for e in events() if e[:3] == ['mailbox', 'session', 'bind']][-1]
        assert bound[-1] == env['CROSSTALK_CONFIG_DIR']
        split = [e for e in events() if e[0]=='split'][-1]
        assert split[3].startswith('/bin/bash ') and '/bin/bash -c ' not in split[3]
        assert split[4] == env['PATH']
        assert not list(scratch.glob('crosstalk-ready.*'))
    # A failed protocol handshake leaves the existing pending pane; it never reports ready.
    run('launch', 'claude', ok=False, TEST_LAUNCH='1', TEST_BIND_FAIL='1', READY_MAX_WAIT='1',
        TMPDIR=str(scratch), TEST_LAUNCH_RESULT=str(result))
    pending_startup = Path(json.loads(result.read_text())['startup'])
    assert pending_startup.is_file()
    pending_splits = len([e for e in events() if e[0] == 'split'])
    run('ensure-peer', 'codex', 'claude', ok=False, READY_MAX_WAIT='1')
    assert len([e for e in events() if e[0] == 'split']) == pending_splits
    pending_ready = Path(state.read_text().strip())
    assert pending_startup.is_file()
    pending_ready.unlink()
    pending_startup.unlink()
    state.unlink()
    run('label', f'ghostty:{B}', 'antigravity')
    run('launch','agy','--unknown',ok=False)
    run('ensure-peer','codex','agy','--auto-approve',ok=False)  # cannot upgrade an existing peer
    # Ghostty's TTY discovery is macOS-only; the remaining transport tests run on Linux too.
    if sys.platform == 'darwin':
        # TTY probe: a real pty stands in for the caller's terminal; its OSC 7 output is captured.
        import re, threading, urllib.parse
        master, slave = os.openpty()
        osc = root / 'osc.bin'
        osc.write_bytes(b'')
        def pump():
            while True:
                try: chunk = os.read(master, 4096)
                except OSError: return
                if not chunk: return
                with open(osc, 'ab') as out: out.write(chunk)
        threading.Thread(target=pump, daemon=True).start()
        probe = dict(CROSSTALK_SURFACE_ID='', TEST_TTY=os.path.basename(os.ttyname(slave)), TEST_OSC=str(osc),
                     TEST_PROBE_ID=A, TEST_PROBE_MATCH='1')
        def last_osc_path():
            found = re.findall(rb'\x1b]7;file://[^/]*([^\x1b]*)\x1b\\', osc.read_bytes())
            return urllib.parse.unquote(found[-1].decode()) if found else None
        # Found exactly, cached, and the pane's original (non-ASCII) directory is restored.
        assert run('self', CROSSTALK_CONFIG_DIR=str(root / 'probe1'), **probe) == f'ghostty:{A}'
        assert last_osc_path() == '/work/한글 dir'
        assert len(list((root / 'probe1/ghostty').glob('bind-4242.json'))) == 1
        before = osc.read_bytes()
        assert run('self', CROSSTALK_CONFIG_DIR=str(root / 'probe1'), **probe) == f'ghostty:{A}'
        assert osc.read_bytes() == before  # cached: no second probe
        # Concurrent probes cannot snapshot one another's temporary directory.
        import signal, time
        concurrent_root = root / 'probe-concurrent'
        concurrent_env = env | probe | {'CROSSTALK_CONFIG_DIR': str(concurrent_root),
            'TEST_PROBE_DELAY': '.2', 'TEST_PROBE_ACTIVE': str(root / 'probe-active')}
        offset = len(osc.read_bytes())
        children = [subprocess.Popen(['bash', str(BRIDGE), 'strict-self'], env=concurrent_env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        for child in children:
            output, error = child.communicate(timeout=15)
            assert child.returncode == 0 and output.strip() == f'ghostty:{A}', (output, error)
        paths = re.findall(rb'\x1b]7;file://[^/]*([^\x1b]*)\x1b\\', osc.read_bytes()[offset:])
        assert len(paths) in (2, 4), paths
        for index in range(0, len(paths), 2):
            assert paths[index].startswith(b'/crosstalk-probe-')
            assert urllib.parse.unquote(paths[index + 1].decode()) == '/work/한글 dir'
        assert not list((concurrent_root / 'ghostty').glob('probe-*.json'))
        # SIGTERM during RPC restores the original directory and never binds an interrupted probe.
        signal_root = root / 'probe-signal'
        active = root / 'signal-active'
        signal_env = env | probe | {'CROSSTALK_CONFIG_DIR': str(signal_root),
            'TEST_PROBE_DELAY': '.4', 'TEST_PROBE_ACTIVE': str(active)}
        child = subprocess.Popen(['bash', str(BRIDGE), 'strict-self'], env=signal_env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 10
        while not active.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert active.exists(), 'probe did not reach cancellable RPC'
        record = next((signal_root / 'ghostty').glob('probe-*.json'))
        os.kill(json.loads(record.read_text())['pid'], signal.SIGTERM)
        output, error = child.communicate(timeout=10)
        assert child.returncode != 0 and not output, (output, error)
        assert last_osc_path() == '/work/한글 dir'
        assert not list((signal_root / 'ghostty').glob('bind-*.json'))
        assert not record.exists()
        # A SIGKILL orphan's pre-probe mapping must survive the next attempted probe.
        orphan_root = root / 'probe-orphan'
        (orphan_root / 'ghostty').mkdir(parents=True)
        orphan = orphan_root / 'ghostty' / ('probe-' + probe['TEST_TTY'] + '.json')
        orphan.write_text('{"before": "preserve this diagnostic snapshot"}')
        prior = osc.read_bytes()
        run('strict-self', ok=False, CROSSTALK_CONFIG_DIR=str(orphan_root), **probe)
        assert orphan.read_text() == '{"before": "preserve this diagnostic snapshot"}'
        assert osc.read_bytes() == prior
        # agy: the tool shell is on an inner pty, so probe and cache follow the CLI on the pane's TTY.
        assert run('self', CROSSTALK_CONFIG_DIR=str(root / 'probe3'), TEST_INNER_TTY='ttys900', **probe) == f'ghostty:{A}'
        assert [p.name for p in (root / 'probe3/ghostty').glob('bind-*.json')] == ['bind-4242.json']
        # No pane reports the probe: fail closed, but still restore (here to the caller's cwd).
        assert run('self', ok=False, CROSSTALK_CONFIG_DIR=str(root / 'probe2'), **(probe | {'TEST_PROBE_MATCH': '0'})) == ''
        assert last_osc_path() == os.getcwd()
        os.close(slave); os.close(master)
    for kind in ('codex','claude','agy'):
        assert run('launch',kind,'--auto-approve',TEST_LAUNCH='1',TEST_AUTO_APPROVE='1',READY_MAX_WAIT='10',TMPDIR=str(scratch),TEST_LAUNCH_RESULT=str(result)) == f'ghostty:{B}'
    run('launch','agy','--auto-approve','extra',ok=False)
    assert run('detect', f'ghostty:{B}') == 'antigravity'
    assert run('ensure-peer', 'codex', 'agy') == f'ghostty:{B}'
    assert run('ensure-peer', 'claude', 'antigravity') == f'ghostty:{B}'
    alive.write_text(json.dumps([A]))
    run('send', f'ghostty:{B}', 'closed', ok=False)
    run('self', CROSSTALK_SURFACE_ID=f'ghostty:{B}', ok=False)
    assert run('list-peers', CROSSTALK_BACKEND='cmux') == 'surface:2\tclaude'
    run('send', 'surface:2', payload, CROSSTALK_BACKEND='cmux')
    assert ['cmux', 'send', '--surface', 'surface:2', payload] in events()
    assert run('capture', 'surface:2') == 'screen text'
    assert ['cmux', 'read-screen', '--surface', 'surface:2', '--lines', '200'] in events()
print('PASS: Ghostty identity, routing both ways, literal input, file triggers, readiness, closed panes, cmux regression')
