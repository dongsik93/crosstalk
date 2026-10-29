"""Verbatim Claude input bundles. Normal API provenance, not an OS-user sandbox."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import uuid

from . import db, sessions
from .protocol import Error, require, valid_id

LIMIT = 1024 * 1024
_AUTOMATED = ('[crosstalk]', 'crosstalk startup check.', 'crosstalk test.',
              'crosstalk reverse test.', '<task-notification', '<teammate-message',
              '<local-command', '<system-reminder')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _safe(path):
    path = Path(path).absolute()
    require(not any(item.is_symlink() for item in (path, *path.parents)),
            'INPUT_SOURCE_UNVERIFIED', 'Input storage and transcript paths must not traverse symlinks')
    if path.exists():
        require(path.stat().st_uid == os.getuid(), 'INPUT_SOURCE_UNVERIFIED', 'Input path belongs to another user')
    return path


def _root():
    return _safe(db.root() / 'inputs')


def _write(path, value, *, replace=False):
    path = _safe(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = (_canonical(value) + '\n').encode('utf-8')
    if not replace:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as out:
            out.write(content)
        return
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read(path):
    path = _safe(path)
    require(path.is_file(), 'INPUT_SOURCE_UNAVAILABLE', 'Captured input is unavailable; submit the request in Claude again')
    require(path.stat().st_size <= 4 * LIMIT, 'CONTEXT_TOO_LARGE', 'Stored input exceeds its size limit')
    try:
        value = json.loads(path.read_text())
    except (ValueError, UnicodeError) as exc:
        raise Error('INPUT_SOURCE_UNVERIFIED', 'Stored input is invalid') from exc
    require(isinstance(value, dict), 'INPUT_SOURCE_UNVERIFIED', 'Stored input must be an object')
    return value


def _automated(text):
    return text.lstrip().lower().startswith(_AUTOMATED)


def independent_intent(text):
    if not isinstance(text, str):
        return False
    if _automated(text):
        return False
    if re.search(r'독립.{0,12}(?:하지\s*마|안\s*해|말고)|(?:not|don.t)\s+(?:an?\s+)?(?:independent|blind)', text, re.I):
        return False
    return bool(re.search(r'독립.{0,40}(?:검토|분석|토론)|(?:independent(?:ly)?|blind).{0,40}(?:review|analysis|analy[sz]e|discuss)', text, re.I))


def _cancel_independent(text):
    return bool(re.search(r'독립.{0,25}(?:취소|중단|말고|대신|하지\s*마)|(?:cancel|stop|not).{0,25}(?:independent|blind)', text, re.I)
                or re.fullmatch(r'(?:취소|그만|그만해|cancel|stop)[.!\s]*', text.strip(), re.I))


def request_state(text):
    """A mention is only a candidate; quoted examples never establish a request."""
    if not isinstance(text, str) or _automated(text):
        return 'none'
    plain = re.sub(r'''```[\s\S]*?```|`[^`]*`|“[^”]*”|‘[^’]*’|「[^」]*」|"[^"\n]*"|(?<!\w)'[^'\n]+'(?!\w)''', ' ', text)
    if _cancel_independent(plain):
        return 'cancelled'
    if re.match(r'^\s*/crosstalk(?::independent|\s+independent)\b', plain):
        return 'requested'
    if not independent_intent(text):
        return 'none'
    if not independent_intent(plain) or re.search(r'예시|예문|문구|사용법|기능.{0,12}(?:구현|추가|설명)|\bexample\b|\bdocument(?:ation)?\b', plain, re.I):
        return 'candidate'
    korean_request = re.search(r'(?:검토|분석|토론)\s*(?:좀\s*)?(?:해\s*(?:줘|봐|주세요|줄래|라)?|하자|부탁해)(?:[.!?\s]*$|[.!?])', plain, re.M)
    english_request = re.search(r'^\s*(?:(?:please|hey)\s+|(?:can|could|would)\s+you\s+)?(?:independently\s+(?:review|analy[sz]e|discuss)|(?:do|perform|run|start)\b.{0,35}(?:independent|blind))', plain, re.I|re.M)
    return 'requested' if korean_request or english_request else 'candidate'


def _identity(actor):
    require(actor.get('kind') == 'claude', 'CAPABILITY_UNSUPPORTED', 'Captured independent input currently supports Claude callers')
    evidence = actor.get('evidence', actor)
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except ValueError:
            evidence = {}
    result = {'surface_id': actor.get('surface_id'),
              'process_id': evidence.get('process_id'), 'process_start': evidence.get('process_start')}
    require(all(isinstance(v, str) and v for v in result.values()),
            'INPUT_SOURCE_UNVERIFIED', 'Exact caller process evidence is required for captured input')
    return result


def _actor_key(actor):
    return _hash(_canonical(_identity(actor)))


def _transcript(session_id, path):
    valid_id(session_id)
    require(isinstance(path, str) and Path(path).is_absolute(),
            'INPUT_SOURCE_UNVERIFIED', 'A native absolute transcript path is required')
    path = _safe(path)
    projects = _safe(Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude')) / 'projects')
    require(path.is_relative_to(projects) and path.name == session_id + '.jsonl',
            'INPUT_SOURCE_UNVERIFIED', 'Transcript must be the native Claude session file')
    return path


def capture(payload):
    require(isinstance(payload, dict) and payload.get('hook_event_name') == 'UserPromptSubmit',
            'INPUT_SOURCE_UNVERIFIED', 'Input capture requires the native prompt hook event')
    prompt = payload.get('prompt')
    require(isinstance(prompt, str) and len(prompt.encode('utf-8')) <= LIMIT,
            'INVALID_ARGUMENT', 'Prompt must be a string within the input limit')
    if _automated(prompt) or payload.get('agent_id') or payload.get('isMeta') or payload.get('isSidechain'):
        return {'ignored': True}
    session_id = payload.get('session_id')
    prompt_id = payload.get('prompt_id')
    require(isinstance(prompt_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', prompt_id),
            'INPUT_SOURCE_UNVERIFIED', 'Native prompt_id is required; reload or update the capture integration')
    path = _transcript(session_id, payload.get('transcript_path', ''))
    current = sessions.identity()
    owner = _identity(current)
    key = _actor_key(current)
    head_path = _root() / 'heads' / (key + '.json')
    head = _read(head_path) if head_path.exists() else {}
    previous = head.get('capture_id')
    previous_control = head.get('control_capture_id')
    capture_id = uuid.uuid4().hex
    record = {'capture_id': capture_id, 'capture_version': 2, 'prompt_id': prompt_id,
              'request_state': request_state(prompt), 'session_id': session_id, 'transcript_path': str(path),
              'prompt_hash': _hash(prompt), 'identity': owner, 'independent_intent': independent_intent(prompt),
              'previous_capture_id': previous, 'previous_control_id': previous_control,
              'created_at': datetime.now(timezone.utc).isoformat()}
    try:
        _write(_root() / 'captures' / (capture_id + '.json'), record)
        _write(head_path, {'capture_id': capture_id,
                          'control_capture_id':capture_id if record['request_state'] in ('requested','cancelled') else previous_control}, replace=True)
    except (Error, OSError) as exc:
        exc.capture_identity=current
        raise
    return {'capture_id': capture_id, 'independent_intent': record['independent_intent'],
            'request_state': record['request_state']}


def _capture(capture_id, actor):
    if capture_id is None:
        capture_id = _read(_root() / 'heads' / (_actor_key(actor) + '.json')).get('capture_id')
    valid_id(capture_id)
    record = _read(_root() / 'captures' / (capture_id + '.json'))
    require(record.get('capture_id') == capture_id and record.get('identity') == _identity(actor),
            'INPUT_SOURCE_UNVERIFIED', 'Captured input belongs to a different Claude instance')
    return record


def _human(record, session_id):
    text = record.get('message', {}).get('content')
    return (record.get('type') == 'user' and record.get('sessionId') == session_id
            and record.get('origin') == {'kind': 'human'} and record.get('turnOrigin') == 'human'
            and record.get('promptSource') in ('typed', 'queued') and record.get('isSidechain') is False
            and not any(record.get(key) for key in ('isMeta', 'isCompactSummary', 'isSynthetic', 'sourceToolAssistantUUID'))
            and isinstance(text, str) and not _automated(text))


def _sources(record):
    require(record.get('capture_version') == 2 and record.get('prompt_id'),
            'INPUT_SOURCE_UNVERIFIED', 'This older capture has no native event binding; submit a new request')
    path = _transcript(record['session_id'], record['transcript_path'])
    require(path.is_file(), 'INPUT_SOURCE_UNAVAILABLE', 'Wait for the native user message to be recorded, then retry')
    rows, matches, event_seen, nonhuman_event = [], [], False, False
    seen = set()
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            event_matches = entry.get('sessionId') == record['session_id'] and entry.get('promptId') == record['prompt_id']
            if event_matches and entry.get('type') == 'user':
                event_seen = True
                text = entry.get('message', {}).get('content')
                origin = entry.get('origin', {})
                if (isinstance(text,str) and _hash(text)==record['prompt_hash'] and isinstance(origin,dict)
                        and origin.get('kind') not in (None,'human')):
                    nonhuman_event = True
            if not _human(entry, record['session_id']):
                continue
            mid = entry.get('uuid')
            if not isinstance(mid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', mid):
                continue
            require(mid not in seen, 'INPUT_SOURCE_UNVERIFIED', 'Transcript has duplicate message identities')
            seen.add(mid)
            text = entry['message']['content']
            require(len(text.encode('utf-8')) <= LIMIT, 'CONTEXT_TOO_LARGE', 'User source message exceeds the input limit')
            digest = _hash(text)
            rows.append({'message_id': mid, 'text': text, 'sha256': digest})
            if event_matches:
                require(digest == record['prompt_hash'], 'INPUT_SOURCE_UNVERIFIED', 'Native event content differs from the captured prompt')
                matches.append(len(rows) - 1)
    require(event_seen, 'INPUT_SOURCE_UNAVAILABLE', 'This prompt event is not recorded yet; retry the same capture later')
    if not matches and nonhuman_event:
        error=Error('INPUT_SOURCE_UNVERIFIED','This native event is not a human request')
        error.source_not_human=True
        raise error
    require(len(matches) == 1, 'INPUT_SOURCE_UNVERIFIED', 'The native event does not identify exactly one human message')
    return rows[:matches[0] + 1]


def list_sources(capture_id, actor):
    record = _capture(capture_id, actor)
    rows = _sources(record)
    require(sum(len(row['text'].encode('utf-8')) for row in rows) <= 4 * LIMIT,
            'CONTEXT_TOO_LARGE', 'Session input history is too large; ask the user for a concise review topic')
    return {'capture_id': record['capture_id'], 'sources': rows,
            'provenance': 'native_claude_human_transcript', 'independent_intent': record['independent_intent'],
            'request_state': record['request_state']}


def _substantive(text):
    # Only recognize obvious directives/acknowledgements; semantic uncertainty stays with the caller.
    stripped = text.strip()
    if re.fullmatch(r'(?:ㅇㅇ|응|네|넵|좋아|그래|해줘|진행해|ㄱㄱ|ok|okay|yes|go)[.!\s]*', stripped, re.I):
        return False
    residue = re.sub(r'독립적으로|독립적|독립|검토해줘|검토해|검토|분석해줘|분석해|분석|토론해줘|토론해|토론|해\s*주세요|해봐|해주세요|부탁해|해줘|해라|옆에|옆|애랑|걔랑|이거|이것|그거|그것|저거|둘이|너네|한번|다시|야|좀|codex|claude|코덱스|클로드|independently|independent|blind|review|analy[sz]e|analysis|discuss|this|that|please|with|peer', '', stripped, flags=re.I)
    residue = re.sub(r'[\W_]+', '', residue)
    return len(residue) >= 4


def prepare(capture_id, actor, from_message=None):
    record = _capture(capture_id, actor)
    rows = _sources(record)
    request_id = _pending_request(record, actor)
    require(record['request_state'] in ('requested','none') and request_id,
            'INPUT_SCOPE_REQUIRED', 'This is only a mention or example; ask the user whether independent review is intended')
    if request_id != record['capture_id']:
        _sources(_capture(request_id, actor))
    if from_message is not None:
        matches = [index for index, item in enumerate(rows) if item['message_id'] == from_message]
        require(len(matches) == 1, 'INPUT_SOURCE_UNVERIFIED', 'Scope must begin at a recorded human source message')
        start = matches[0]
    else:
        starts = [index for index, item in enumerate(rows) if _substantive(item['text'])]
        require(len(starts) == 1, 'INPUT_SCOPE_REQUIRED', 'Select the explicit user-message range; do not guess which question or constraint is the subject')
        start = starts[0]
    selected = rows[start:]
    require(any(_substantive(item['text']) for item in selected),
            'INPUT_SCOPE_REQUIRED', 'Selected input contains no review subject; ask one focused question')
    raw_topic = '\n\n'.join(item['text'] for item in selected)
    require(len(raw_topic.encode('utf-8')) <= LIMIT, 'CONTEXT_TOO_LARGE', 'Selected source input exceeds the topic limit')
    source_refs = [{'message_id': item['message_id'], 'sha256': item['sha256']} for item in selected]
    public = {'raw_topic': raw_topic, 'sources': source_refs, 'provenance': 'native_claude_human_transcript',
              'request_capture_id': request_id,
              'event_binding': {'version': 2, 'prompt_id': record['prompt_id'], 'message_id': rows[-1]['message_id']}}
    input_id = _hash(_canonical({'capture_id': record['capture_id'], **public}))
    bundle = {'input_id': input_id, 'capture_id': record['capture_id'], 'identity': record['identity'],
              'source_records': selected, **public}
    bundle['content_hash'] = _hash(_canonical(bundle))
    path = _root() / 'bundles' / (input_id + '.json')
    try:
        _write(path, bundle)
    except FileExistsError:
        require(_read(path) == bundle, 'INPUT_SOURCE_UNVERIFIED', 'Existing input bundle differs')
    return {'input_id': input_id, **public}


def load_bundle(input_id, actor):
    valid_id(input_id)
    bundle = _read(_root() / 'bundles' / (input_id + '.json'))
    expected = bundle.pop('content_hash', None)
    require(bundle.get('input_id') == input_id and expected == _hash(_canonical(bundle)),
            'INPUT_SOURCE_UNVERIFIED', 'Stored input bundle changed')
    require(bundle.get('identity') == _identity(actor), 'INPUT_SOURCE_UNVERIFIED', 'Input belongs to another Claude instance')
    require(bundle.get('provenance') == 'native_claude_human_transcript', 'INPUT_SOURCE_UNVERIFIED', 'Unknown input provenance')
    record = _capture(bundle['capture_id'], actor)
    require(record.get('capture_version') == 2 and record.get('prompt_id'),
            'INPUT_SOURCE_UNVERIFIED', 'Prepare a new event-bound input; older unstarted bundles are not trusted')
    binding = bundle.get('event_binding', {})
    require(isinstance(binding,dict) and binding.get('version')==2 and binding.get('prompt_id')==record['prompt_id']
            and bundle.get('sources') and binding.get('message_id')==bundle['sources'][-1]['message_id'],
            'INPUT_SOURCE_UNVERIFIED', 'This bundle was not prepared against the captured native event; prepare it again')
    return {key: bundle[key] for key in ('input_id', 'capture_id', 'request_capture_id', 'raw_topic', 'sources', 'provenance')}


def _consumed(capture_id, actor):
    """The committed run is authoritative; old marker files are not consumption state."""
    path = db.root() / 'mailbox.sqlite3'
    if not path.exists():
        return False
    with closing(db.connect(readonly=True)) as conn:
        sid = actor.get('session_id')
        if not sid:
            row=conn.execute(sessions.BINDING+'WHERE b.surface_id=? AND b.active=1',(actor.get('surface_id'),)).fetchone()
            if row and _identity(dict(row))==_identity(actor):sid=row['session_id']
        if not sid:return False
        rows = conn.execute('SELECT config_snapshot FROM discussion_runs WHERE caller_session_id=?',
                            (sid,)).fetchall()
    for row in rows:
        snapshot = json.loads(row['config_snapshot'])
        if capture_id in (snapshot.get('capture_id'), snapshot.get('request_capture_id')):
            return True
        # Read-only compatibility with committed v0.12.1 runs, never trust their marker alone.
        if snapshot.get('input_id') and 'capture_id' not in snapshot:
            try:
                bundle = _read(_root() / 'bundles' / (valid_id(snapshot['input_id']) + '.json'))
                digest = bundle.pop('content_hash', None)
                if digest == _hash(_canonical(bundle)) and bundle.get('capture_id') == capture_id and bundle.get('identity') == _identity(actor):
                    return True
            except (Error, OSError):
                continue
    return False


def _pending_request(record, actor):
    capture_id = record['capture_id'] if record.get('request_state') in ('requested','cancelled') else record.get('previous_control_id')
    for _ in range(32):
        if not capture_id:return None
        if _consumed(capture_id, actor):
            return None
        record = _capture(capture_id, actor)
        state = record.get('request_state', 'legacy_unverified')
        if state == 'legacy_unverified':
            return None  # Older captures cannot identify a current event; new runs must recapture.
        try:
            sources = _sources(record)
        except Error as exc:
            if exc.code not in ('INPUT_SOURCE_UNVERIFIED', 'INPUT_SOURCE_UNAVAILABLE'):
                raise
            if state == 'requested' and not getattr(exc,'source_not_human',False):
                return capture_id
            capture_id = record.get('previous_control_id')
            continue
        return capture_id if state=='requested' else None
    raise Error('INPUT_SOURCE_UNVERIFIED', 'Input provenance chain needs a new direct user request')


def requires_engine(actor):
    if actor.get('kind') != 'claude':return False
    head = _root() / 'heads' / (_actor_key(actor) + '.json')
    if not head.exists():return False
    capture_id = _read(head).get('capture_id')
    if _consumed(capture_id, actor):return False
    return _pending_request(_capture(capture_id, actor), actor) is not None


def add_parser(subparsers):
    parser = subparsers.add_parser('input', help='Use captured user messages without model rewriting')
    actions = parser.add_subparsers(dest='input_command', required=True)
    actions.add_parser('capture')
    sources = actions.add_parser('sources')
    sources.add_argument('capture_id', nargs='?')
    prepare_parser = actions.add_parser('prepare')
    prepare_parser.add_argument('capture_id')
    prepare_parser.add_argument('--from-message')
    actions.add_parser('show').add_argument('input_id')


def run(args):
    if args.input_command == 'capture':
        return capture(json.load(sys.stdin))
    with closing(db.connect(readonly=True)) as conn:
        actor = sessions.actor(conn)
    if args.input_command == 'sources':
        return list_sources(args.capture_id, actor)
    if args.input_command == 'prepare':
        return prepare(args.capture_id, actor, args.from_message)
    return load_bundle(args.input_id, actor)


def hook_main():
    try:
        payload = json.load(sys.stdin)
        result = capture(payload)
        if result.get('independent_intent'):
            runtime = Path(__file__).resolve().parents[1] / 'crosstalk'
            instruction = ('This prompt may request independent review. If the user is only describing the feature or quoting an example, do not start a discussion. '
                           'For an actual independent-review request, do not compose a peer message or use raw send. '
                           f'Use the Crosstalk executable at {runtime} to read capabilities --json and its independent_instructions file. '
                           'Use input sources and input prepare with '
                           f'capture ID {result["capture_id"]}. Reuse verbatim recorded user messages, not assistant opinions. '
                           'If the subject is unclear, ask one focused question. Never claim an unverified source is user approved.')
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': instruction}}))
    except (Error, OSError, ValueError, TypeError) as exc:
        pending=False
        if getattr(exc,'capture_identity',None):
            try:pending=requires_engine(exc.capture_identity)
            except (Error,OSError,ValueError):pending=True
        if pending or (isinstance(locals().get('payload'), dict) and request_state(payload.get('prompt', '')) == 'requested'):
            print(json.dumps({'decision': 'block', 'reason':
                'Crosstalk could not capture this independent-review request. Repair input capture and resubmit; no unprotected fallback was allowed.'}))
        print('Crosstalk input capture unavailable: ' + str(exc), file=sys.stderr)


if __name__ == '__main__':
    hook_main()
