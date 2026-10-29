"""Selection of built-in adapters and compatibility calls, never dynamic imports."""
import json
import fcntl
import os
from pathlib import Path
import tempfile
import uuid
from datetime import datetime, timezone
from .cli import build_launch_spec, identify_cli_context, normalize
from .contracts import SurfaceRef
from .terminal import TerminalAdapter, invoke, wait_ready
from ..protocol import Error, require, valid_id


def terminal(backend):
    return TerminalAdapter(backend)


def _config():
    return Path(os.environ.get('CROSSTALK_CONFIG_DIR', Path.home() / '.claude/crosstalk')).absolute()


def launch(kind, *, auto_approve=False, anchor=None, fresh_for_input=None):
    kind = normalize(kind)
    require(type(auto_approve) is bool, 'INVALID_ARGUMENT', 'Permission selection must be boolean')
    anchor = anchor or invoke('self')
    require(SurfaceRef.parse(anchor).backend == 'ghostty', 'CAPABILITY_UNSUPPORTED', 'Native launch requires a Ghostty anchor')
    try:
        max_wait = int(os.environ.get('READY_MAX_WAIT', '60'))
    except ValueError:
        raise Error('INVALID_ARGUMENT', 'READY_MAX_WAIT must be a positive integer') from None
    require(max_wait > 0, 'INVALID_ARGUMENT', 'READY_MAX_WAIT must be positive')
    if fresh_for_input is not None:
        valid_id(fresh_for_input)
        require(kind == 'codex', 'CAPABILITY_UNSUPPORTED', 'Independent first analysis currently requires a new Codex peer')
        return _fresh_launch(kind, auto_approve, anchor, max_wait, fresh_for_input)
    return _launch_new(kind, auto_approve, anchor, max_wait)


def _launch_new(kind, auto_approve, anchor, max_wait, on_created=None, before_launch=None):
    fd, ready_name = tempfile.mkstemp(prefix='crosstalk-ready.', dir=os.environ.get('TMPDIR') or None)
    os.close(fd)
    fd, startup_name = tempfile.mkstemp(prefix='ct-startup.', dir='/tmp')
    os.close(fd)
    ready, startup = Path(ready_name), Path(startup_name)
    runtime = Path(__file__).resolve().parents[2] / 'crosstalk'
    try:
        spec = build_launch_spec(kind, cwd=Path.cwd(), runtime=runtime, config=_config(),
                                 ready=ready, startup=startup, auto_approve=auto_approve)
        if before_launch is not None:
            before_launch()
    except BaseException:
        ready.unlink(missing_ok=True)
        startup.unlink(missing_ok=True)
        raise
    return terminal('ghostty').launch_peer(anchor, spec, ready=ready, startup=startup,
                                         label=kind, max_wait=max_wait, on_created=on_created).address()


def _private(path, directory=False):
    path = Path(path).absolute()
    require(not any(item.is_symlink() for item in (path, *path.parents)), 'UNSAFE_PATH', 'Launch evidence cannot traverse symlinks')
    if directory:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        info = path.stat()
        require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
                'UNSAFE_PATH', 'Launch evidence must be private to its owner')
    return path


def _read(path):
    path = _private(path)
    require(path.is_file(), 'FRESH_PEER_REQUIRED', 'No verified new-conversation launch is recorded')
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        raise Error('FRESH_PEER_REQUIRED', 'Launch evidence is unreadable') from None
    require(isinstance(value, dict), 'FRESH_PEER_REQUIRED', 'Invalid launch evidence')
    return value


def _write(path, value, *, replace=True):
    path = _private(path)
    fd, name = tempfile.mkstemp(prefix='.launch-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(name, path)
        else:
            os.link(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def fresh_receipt(config, surface, input_id):
    """Read recorded launch provenance; engine additionally checks binding and prior use."""
    valid_id(input_id)
    ref = SurfaceRef.parse(surface)
    require(ref.backend == 'ghostty', 'FRESH_PEER_REQUIRED', 'Fresh conversation requires an exact Ghostty surface')
    value = _read(Path(config) / 'inputs/launches' / (ref.native_id + '.json'))
    require(value.get('input_id') == input_id and value.get('surface_id') == surface
            and value.get('kind') == 'codex' and value.get('origin') == 'new_cli_process'
            and value.get('process_id') and value.get('process_start') and value.get('launch_id')
            and value.get('cli_options') in ([], ['--yolo'])
            and isinstance(value.get('startup_prompt'), str)
            and value['startup_prompt'].startswith('Crosstalk startup check. Read /tmp/ct-startup.')
            and value.get('argv') == [*value['cli_options'], value['startup_prompt']],
            'FRESH_PEER_REQUIRED', 'The selected peer is not the recorded new conversation for this input')
    return value


def _fresh_launch(kind, auto_approve, anchor, max_wait, input_id):
    config = _config()
    _private(config, directory=True)
    _private(config / 'inputs', directory=True)
    folder = _private(config / 'inputs/launches', directory=True)
    intent_path = folder / ('input-' + input_id + '.json')
    lock_path = _private(folder / ('input-' + input_id + '.lock'))
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Error('PEER_NOT_READY', 'This input already has a launch in progress; retry that same input') from None
        if intent_path.exists():
            intent = _read(intent_path)
            require(intent.get('input_id') == input_id and intent.get('kind') == kind
                    and intent.get('anchor') == anchor and intent.get('auto_approve') == auto_approve
                    and intent.get('cwd') == str(Path.cwd()),
                    'FRESH_PEER_CONFLICT', 'A launch already exists for this input with different context or permissions')
            surface = intent.get('surface_id')
            require(surface, 'PEER_NOT_READY', 'A prior launch was interrupted before its address was recorded; do not create another pane')
            invoke('exists', SurfaceRef.parse(surface).address())
            wait_ready(surface, config, max_wait)
        else:
            # Keep an intent even if split succeeded but its response was lost.
            intent = {'input_id': input_id, 'kind': kind, 'anchor': anchor,
                      'auto_approve': auto_approve, 'cwd': str(Path.cwd()),
                      'launch_id': uuid.uuid4().hex,
                      'created_at': datetime.now(timezone.utc).isoformat(), 'state': 'creating'}
            def created(surface, spec, ready, startup):
                prompt = f'Crosstalk startup check. Read {startup}.'
                intent.update(surface_id=surface, executable=spec.executable, cli_options=list(spec.argv),
                              argv=[*spec.argv, prompt], startup_prompt=prompt,
                              ready_path=str(ready), startup_path=str(startup), state='pending')
                _write(intent_path, intent)
            surface = _launch_new(kind, auto_approve, anchor, max_wait, on_created=created,
                                  before_launch=lambda: _write(intent_path, intent))
        context = json.loads(invoke('context', surface))
        identity = identify_cli_context(context)
        require(identity['surface_id'] == surface and identity['kind'] == kind,
                'FRESH_PEER_REQUIRED', 'The new pane no longer contains its expected CLI')
        receipt = {key: intent[key] for key in ('input_id', 'kind', 'surface_id', 'executable', 'argv', 'cli_options', 'startup_prompt', 'launch_id', 'created_at')}
        receipt.update(origin='new_cli_process', process_id=identity['process_id'], process_start=identity['process_start'])
        path = _private(folder / (SurfaceRef.parse(surface).native_id + '.json'))
        if path.exists():
            require(_read(path) == receipt, 'FRESH_PEER_REQUIRED', 'The recorded CLI process has changed; it is not a fresh peer')
        else:
            _write(path, receipt, replace=False)
        intent['state'] = 'ready'
        _write(intent_path, intent)
        return surface
    finally:
        os.close(fd)


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
        require(values, 'INVALID_ARGUMENT', 'Use launch kind [--auto-approve] [--fresh-for-input ID]')
        kind, *options = values
        approve, fresh = False, None
        while options:
            option = options.pop(0)
            if option == '--auto-approve' and not approve:
                approve = True
            elif option == '--fresh-for-input' and fresh is None and options:
                fresh = valid_id(options.pop(0))
            else:
                raise Error('INVALID_ARGUMENT', 'Invalid launch option')
        return launch(kind, auto_approve=approve, fresh_for_input=fresh)
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
