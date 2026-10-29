"""Selection of built-in adapters and compatibility calls, never dynamic imports."""
import json
import os
from pathlib import Path
import tempfile
from .cli import build_launch_spec, identify_cli_context, normalize
from .contracts import SurfaceRef
from .terminal import TerminalAdapter, invoke, wait_ready
from ..protocol import Error, require


def terminal(backend):
    return TerminalAdapter(backend)


def _config():
    return Path(os.environ.get('CROSSTALK_CONFIG_DIR', Path.home() / '.claude/crosstalk')).absolute()


def launch(kind, *, auto_approve=False, anchor=None):
    kind = normalize(kind)
    anchor = anchor or invoke('self')
    require(SurfaceRef.parse(anchor).backend == 'ghostty', 'CAPABILITY_UNSUPPORTED', 'Native launch requires a Ghostty anchor')
    try:
        max_wait = int(os.environ.get('READY_MAX_WAIT', '60'))
    except ValueError:
        raise Error('INVALID_ARGUMENT', 'READY_MAX_WAIT must be a positive integer') from None
    require(max_wait > 0, 'INVALID_ARGUMENT', 'READY_MAX_WAIT must be positive')
    fd, ready_name = tempfile.mkstemp(prefix='crosstalk-ready.', dir=os.environ.get('TMPDIR') or None)
    os.close(fd)
    fd, startup_name = tempfile.mkstemp(prefix='ct-startup.', dir='/tmp')
    os.close(fd)
    ready, startup = Path(ready_name), Path(startup_name)
    runtime = Path(__file__).resolve().parents[2] / 'crosstalk'
    try:
        spec = build_launch_spec(kind, cwd=Path.cwd(), runtime=runtime, config=_config(),
                                 ready=ready, startup=startup, auto_approve=auto_approve)
    except BaseException:
        ready.unlink(missing_ok=True)
        startup.unlink(missing_ok=True)
        raise
    return terminal('ghostty').launch_peer(anchor, spec, ready=ready, startup=startup,
                                         label=kind, max_wait=max_wait).address()


def call_terminal(*args, timeout=10):
    """Compatibility facade used by mailbox delivery; production calls only the restricted driver."""
    require(args, 'INVALID_ARGUMENT', 'A terminal operation is required')
    override = os.environ.get('CROSSTALK_BRIDGE')
    if override:
        return invoke(*args, timeout=timeout, driver=override)
    operation, *values = args
    if operation == 'get-language':
        path = Path(os.environ.get('CROSSTALK_CONFIG', _config() / 'config.json'))
        try:
            language = json.loads(path.read_text()).get('language', 'en')
        except (OSError, ValueError, AttributeError):
            language = 'en'
        return language if language in ('en', 'ko') else 'en'
    if operation in ('strict-identity', 'target-identity'):
        own = operation == 'strict-identity'
        address = invoke('strict-self', timeout=timeout) if own else SurfaceRef.parse(values[0]).address()
        context = json.loads(invoke('context', address, timeout=timeout))
        return json.dumps(identify_cli_context(context, cli_session_id=os.environ.get('CODEX_THREAD_ID', '') if own else ''))
    if operation == 'launch':
        require(1 <= len(values) <= 2 and (len(values) == 1 or values[1] == '--auto-approve'),
                'INVALID_ARGUMENT', 'Use launch kind [--auto-approve]')
        return launch(values[0], auto_approve=len(values) == 2)
    if operation in ('list-peers', 'list-all'):
        anchor = invoke('self', timeout=timeout)
        entries = []
        for address in invoke('list-surfaces', anchor, timeout=timeout).splitlines():
            if not address or (operation == 'list-peers' and address == anchor):
                continue
            label = invoke('get-label', address, timeout=timeout)
            kind = label if label in ('claude', 'codex', 'antigravity', 'shell') else 'unknown'
            entry = f'{address}\t{kind}'
            if operation == 'list-all':
                entry += '\t' + ('self' if address == anchor else 'peer')
            entries.append(entry)
        return '\n'.join(entries)
    if operation == 'ensure-peer':
        require(1 <= len(values) <= 3, 'INVALID_ARGUMENT', 'Use ensure-peer caller [peer] [--auto-approve]')
        caller = normalize(values[0])
        require(caller in ('claude', 'codex'), 'CAPABILITY_UNSUPPORTED', 'Only Claude and Codex are callers')
        kind = normalize(values[1] if len(values) > 1 else ('claude' if caller == 'codex' else 'codex'))
        approve = len(values) == 3
        require(not approve or values[2] == '--auto-approve', 'INVALID_ARGUMENT', 'Unknown permission flag')
        require(caller != kind, 'CAPABILITY_UNSUPPORTED', 'Choose a different peer kind')
        anchor = invoke('self', timeout=timeout)
        invoke('label', anchor, caller, timeout=timeout)
        peers = [line.split('\t')[0] for line in call_terminal('list-peers', timeout=timeout).splitlines()
                 if line.split('\t')[1:] == [kind]]
        require(len(peers) <= 1, 'AMBIGUOUS_PEER', 'Select one exact peer explicitly')
        if peers:
            require(not approve, 'INVALID_ARGUMENT', 'Existing peer permissions cannot be changed')
            wait_ready(peers[0], _config(), int(os.environ.get('READY_MAX_WAIT', '60')))
            return peers[0]
        return launch(kind, auto_approve=approve, anchor=anchor)
    allowed = {'self', 'strict-self', 'backend', 'send', 'text', 'key', 'exists', 'bind',
               'label', 'get-label', 'capture', 'list-surfaces'}
    require(operation in allowed, 'CAPABILITY_UNSUPPORTED', 'Operation is not part of the terminal adapter contract')
    if operation in ('send', 'text', 'key', 'exists', 'bind', 'label', 'get-label', 'capture', 'list-surfaces'):
        require(values, 'INVALID_ARGUMENT', 'Exact target surface required')
        SurfaceRef.parse(values[0])
    return invoke(operation, *values, timeout=timeout)
