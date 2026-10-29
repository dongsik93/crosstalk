"""Exact terminal operations and private launcher lifecycle; no discussion state."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from ..contracts import CapabilitySet, LaunchSpec, SubmissionOutcome, SurfaceRef
from ...protocol import Error, require

DRIVER = Path(__file__).resolve().parents[3] / 'crosstalk_terminal.sh'
GHOSTTY_DICTIONARY = Path('/Applications/Ghostty.app/Contents/Resources/Ghostty.sdef')


def invoke(*args, timeout=10, driver=None):
    process = subprocess.Popen([str(driver or DRIVER), *map(str, args)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        for sig, grace in ((signal.SIGTERM, 1), (signal.SIGKILL, 1)):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=grace)
                break
            except subprocess.TimeoutExpired:
                continue
        raise Error('TERMINAL_TIMEOUT', 'Terminal helper timed out') from None
    if process.returncode:
        code = 'NOTIFICATION_UNKNOWN' if args and args[0] in ('send', 'text', 'key') else 'NOTIFICATION_FAILED'
        raise Error(code, 'Terminal helper did not confirm completion')
    return output.strip()


class TerminalAdapter:
    def __init__(self, backend):
        require(backend in ('ghostty', 'cmux'), 'CAPABILITY_UNSUPPORTED', 'Unsupported terminal backend')
        self.backend = backend

    def capabilities(self):
        import shutil
        observed_at = datetime.now(timezone.utc).isoformat()
        names = ('exact_addressing', 'input_submission', 'native_split', 'screen_capture')
        provider = os.environ.get('CROSSTALK_BRIDGE')
        if provider:
            features = {name: 'unknown' for name in names}
            evidence = ['Configured transport provider: ' + provider]
            try:
                result = json.loads(invoke('capabilities', driver=provider))
                require(isinstance(result, dict) and result.get('backend') == self.backend
                        and isinstance(result.get('features'), dict),
                        'CAPABILITY_UNSUPPORTED', 'Provider capability response is malformed')
                declared = result['features']
                require(all(name in names and value in ('supported', 'unsupported', 'unknown')
                            for name, value in declared.items()),
                        'CAPABILITY_UNSUPPORTED', 'Provider capabilities must use known names and states')
                features.update(declared)
                evidence.append('Capabilities explicitly advertised by configured provider')
            except (Error, OSError, ValueError, TypeError):
                evidence.append('Provider did not advertise a valid capability contract')
            return CapabilitySet(features, observed_at, tuple(evidence))
        tool = 'osascript' if self.backend == 'ghostty' else 'cmux'
        installed = bool(shutil.which(tool))
        features = {name: 'unknown' for name in ('exact_addressing', 'input_submission', 'native_split')}
        features['screen_capture'] = 'unsupported' if self.backend == 'ghostty' else 'unknown'
        evidence = [f'{tool}: {"available, live target not probed" if installed else "missing"}']
        if not installed:
            features = {name: 'unsupported' for name in features}
        elif self.backend == 'ghostty':
            try:
                dictionary = ET.parse(GHOSTTY_DICTIONARY)
                commands = {node.get('name') for node in dictionary.findall('.//command')}
                properties = {node.get('name') for node in dictionary.findall(".//class[@name='terminal']/property")}
                for feature, supported in (
                    ('exact_addressing', {'id', 'tty'} <= properties),
                    ('input_submission', {'input text', 'send key'} <= commands),
                    ('native_split', 'split' in commands),
                ):
                    features[feature] = 'supported' if supported else 'unsupported'
                evidence.append('Installed scripting dictionary: ' + str(GHOSTTY_DICTIONARY))
            except (OSError, ET.ParseError):
                evidence.append('Installed scripting dictionary not readable; capabilities remain unknown')
        return CapabilitySet(features, observed_at,
                             tuple(evidence))

    def _surface(self, surface):
        ref = surface if isinstance(surface, SurfaceRef) else SurfaceRef.parse(surface)
        require(ref.backend == self.backend, 'CAPABILITY_UNSUPPORTED', 'Mixed terminal addressing is not supported')
        return ref.address()

    def inspect_self_evidence(self):
        address = invoke('strict-self' if self.backend == 'ghostty' else 'self')
        return SurfaceRef.parse(self._surface(address))

    def list_surfaces(self, anchor):
        return [SurfaceRef.parse(value) for value in invoke('list-surfaces', self._surface(anchor)).splitlines() if value]

    def exists(self, surface):
        invoke('exists', self._surface(surface))
        return True

    def submit_input(self, surface, text):
        require(isinstance(text, str), 'INVALID_ARGUMENT', 'Input must be text')
        try:
            invoke('send', self._surface(surface), text, '2')
            return SubmissionOutcome('submitted')
        except Error as exc:
            return SubmissionOutcome('unknown' if exc.code in ('TERMINAL_TIMEOUT', 'NOTIFICATION_UNKNOWN') else 'failed', exc.code)

    def capture(self, surface, lines=200):
        require(self.backend == 'cmux', 'CAPABILITY_UNSUPPORTED', 'Ghostty screen capture is not supported')
        require(type(lines) is int and lines > 0, 'INVALID_ARGUMENT', 'Line count must be positive')
        return invoke('capture', self._surface(surface), lines)

    def launch_peer(self, anchor, spec, *, ready, startup, label, max_wait=60):
        require(self.backend == 'ghostty', 'CAPABILITY_UNSUPPORTED', 'Use the legacy cmux launch workflow')
        require(isinstance(spec, LaunchSpec), 'INVALID_ARGUMENT', 'A validated LaunchSpec is required')
        address = self._surface(anchor)
        binding = Path(str(ready) + '.surface')
        launcher = Path(str(ready) + '.launch')
        q = shlex.quote
        environment = ''.join(f'export {key}={q(value)}\n' for key, value in spec.env_delta.items())
        script = ('#!/bin/bash\nset -euo pipefail\nunset CODEX_THREAD_ID\n' + environment +
                  'p=' + q(spec.bootstrap_instruction) + '\n' +
                  f'for i in {{1..100}}; do if [ -s {q(str(binding))} ]; then\n' +
                  f'export CROSSTALK_SURFACE_ID="$(cat {q(str(binding))})"\n' +
                  f'printf "%s\\n" "${{p//__SID__/$CROSSTALK_SURFACE_ID}}" > {q(str(startup))}\n' +
                  f'rm -f {q(str(binding))} "$0"\nexec ' +
                  shlex.join([spec.executable, *spec.argv, f'Crosstalk startup check. Read {startup}.']) + '\n' +
                  f'fi; sleep 0.1; done; rm -f {q(str(startup))} "$0"; exit 1\n')
        fd = os.open(launcher, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write(script)
        try:
            child = invoke('split', address, spec.cwd, '/bin/bash ' + q(str(launcher)), spec.env_delta['PATH'])
            child = SurfaceRef('ghostty', child).address()
        except BaseException:
            for path in (launcher, ready, startup):
                Path(path).unlink(missing_ok=True)
            raise
        invoke('label', child, label)
        state = Path(spec.env_delta['CROSSTALK_CONFIG_DIR']) / 'ghostty' / (child.removeprefix('ghostty:') + '.kind.ready')
        state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        state.write_text(str(ready))
        state.chmod(0o600)
        binding.write_text(child + '\n')
        binding.chmod(0o600)
        import sys
        print(f'STATE: launched surface={child} kind={label}', file=sys.stderr)
        wait_ready(child, spec.env_delta['CROSSTALK_CONFIG_DIR'], max_wait)
        return SurfaceRef.parse(child)


def wait_ready(surface, config, max_wait):
    require(type(max_wait) is int and max_wait > 0, 'INVALID_ARGUMENT', 'READY_MAX_WAIT must be positive')
    ref = SurfaceRef.parse(surface)
    require(ref.backend == 'ghostty', 'CAPABILITY_UNSUPPORTED', 'Protocol readiness uses Ghostty bindings')
    state = Path(config) / 'ghostty' / (ref.native_id + '.kind.ready')
    if not state.exists():
        return
    ready = Path(state.read_text().strip())
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            if ready.read_text() == 'ready':
                ready.unlink()
                state.unlink()
                return
        except FileNotFoundError:
            pass
        time.sleep(0.1)
    raise Error('PEER_NOT_READY', 'Peer has not acknowledged startup; inspect login or permission prompts in the existing pane')
