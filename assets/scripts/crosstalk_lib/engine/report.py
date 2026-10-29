"""Deterministic rendering of stored facts; never calls a model or the database."""
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from ..protocol import Error, require, valid_id

LABELS = {'concluded': "Caller's comparison conclusion", 'diverged': 'Ended with differences preserved',
          'unresolved': 'Ended with insufficient information', 'round_limit': 'Round limit reached',
          'sampled': 'Individual answers collected', 'cancelled': 'Cancelled: partial transcript',
          'failed': 'Failed: partial transcript'}


def _json(value, default=None):
    return json.loads(value) if isinstance(value, str) else default if value is None else value


def _result(action, messages):
    if action.get('result_ref'):
        source = messages.get(action['result_ref'])
        if source is None:
            return None
        source = dict(source)
        result = dict(_json(action.get('result_metadata'), {}) or {})
        result.update(body=source['body'], summary=source.get('summary', ''),
                      verdict=source.get('verdict', 'none'), confidence=source.get('confidence', 'unknown'))
        return result
    return _json(action.get('result_json'))


def build(run, rounds, actions, messages):
    run = dict(run)
    rounds = [dict(row) for row in rounds]
    actions = [dict(row) for row in actions]
    messages = {key: dict(value) for key, value in messages.items()}
    by_id = {action['action_id']: action for action in actions}
    initial = next((action for action in actions if action['kind'] == 'local_initial'), None)
    snapshot = _json(run.get('config_snapshot'), {}) or {}
    outcome = run.get('outcome')
    if outcome is None and run.get('lifecycle') in ('cancelled', 'failed'):
        outcome = run['lifecycle']
    result = {'original_topic': run['raw_topic'], 'run_id': run['run_id'], 'mode': run['mode'],
              'participants': {'caller': {'session_id': run['caller_session_id'], 'role': 'caller'},
                               'peer': {'session_id': run.get('peer_session_id'), 'kind': run.get('requested_peer_kind'), 'role': 'peer'}},
              'lifecycle': run['lifecycle'], 'phase': run['phase'], 'outcome': outcome,
              'outcome_label': LABELS.get(outcome, 'Discussion in progress'), 'rounds': [],
              'initial_position': _result(initial, messages) if initial else None,
              'decision': None, 'unresolved_questions': [], 'assumptions': [], 'evidence_refs': [],
              'execution_driver': run.get('execution_driver'),
              'configuration': {key: snapshot[key] for key in ('language', 'rules', 'persona', 'prompt_bundle_version') if key in snapshot},
              'versions': {field: run.get(field) for field in ('engine_version', 'protocol_version', 'prompt_bundle_version')},
              'limitations': ['Conclusions are reported judgments, not engine-certified truth.',
                              'External evidence claims are reported unless independently verified.',
                              'Shared CLI context and the repository are not isolated snapshots.']}
    for round_row in sorted(rounds, key=lambda row: row['round_no']):
        number = round_row['round_no']
        peer = next((a for a in actions if a['kind'] == 'peer_analysis' and a['round_no'] == number), None)
        comparison = by_id.get(round_row.get('compare_action_id'))
        position_action = by_id.get(round_row.get('caller_position_ref'))
        position = _result(position_action, messages) if position_action else None
        if position_action and position_action['kind'] == 'compare' and position:
            position = {'body': position['caller_position']}
        peer_result = _result(peer, messages) if peer else None
        decision = _result(comparison, messages) if comparison else None
        entry = {'round': number, 'caller_position': position, 'peer_result': peer_result,
                 'peer_request_id': round_row.get('peer_request_id'), 'peer_reply_id': round_row.get('peer_reply_id'),
                 'decision': decision, 'missing': []}
        if position is None:
            entry['missing'].append('caller_position')
        if peer_result is None:
            entry['missing'].append('peer_result')
        if run['mode'] == 'analyze' and decision is None:
            entry['missing'].append('comparison')
        result['rounds'].append(entry)
        if decision:
            result['decision'] = decision
            result['unresolved_questions'] = decision.get('unresolved_questions', [])
        for payload in (position, peer_result, decision):
            if not payload:
                continue
            result['assumptions'].extend(payload.get('assumptions', []))
            result['evidence_refs'].extend(payload.get('evidence_refs', payload.get('new_evidence_refs', [])))
    result['partial'] = run['lifecycle'] in ('cancelled', 'failed') or outcome is None
    result['missing_participants'] = []
    if result['initial_position'] is None:
        result['missing_participants'].append('caller')
    if not any(row['peer_result'] is not None for row in result['rounds']):
        result['missing_participants'].append('peer')
    if run['mode'] == 'ask':
        result['decision'] = None
        result['individual_answers'] = {'caller': result['initial_position'],
                                        'peer': result['rounds'][0]['peer_result'] if result['rounds'] else None}
    return result


def markdown(data):
    # Use a fence longer than any user fence so stored text cannot escape its section.
    def quote(value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        longest = max((len(part) for part in re.findall(r'`+', text)), default=0)
        fence = '`' * max(3, longest + 1)
        return fence + '\n' + text + '\n' + fence
    lines = ['# Discussion result', '', data['outcome_label'], '', '## Original topic', '', quote(data['original_topic'])]
    if data.get('missing_participants'):
        lines.extend(['', 'Missing participant results: ' + ', '.join(data['missing_participants'])])
    for row in data['rounds']:
        lines.extend(['', f"## Round {row['round']}", '', '### Caller position', '', quote(row['caller_position']),
                      '', '### Peer answer', '', quote(row['peer_result'])])
        if data['mode'] == 'analyze':
            lines.extend(['', '### Caller comparison', '', quote(row['decision'])])
        if row['missing']:
            lines.extend(['', 'Missing: ' + ', '.join(row['missing'])])
    lines.extend(['', '## Limitations', '', *('- ' + item for item in data['limitations']), ''])
    return '\n'.join(lines)


def export(root, run_id, json_text, markdown_text, overwrite=False):
    valid_id(run_id)
    require(type(overwrite) is bool, 'INVALID_ARGUMENT', 'Overwrite must be explicit boolean')
    root = Path(root).absolute()
    for part in (root, *root.parents):
        require(not part.is_symlink(), 'UNSAFE_PATH', 'Export paths must not traverse symlinks')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(root.is_dir() and root.stat().st_uid == os.getuid(), 'UNSAFE_PATH', 'Export directory must belong to this user')
    require(not root.stat().st_mode & 0o077, 'UNSAFE_PERMISSIONS', 'Export directory must be private')
    targets = {root / (run_id + '.json'): json_text, root / (run_id + '.md'): markdown_text}
    for path, text in targets.items():
        require(type(text) is str, 'INVALID_ARGUMENT', 'Export content must be stored text')
        require(not path.is_symlink(), 'UNSAFE_PATH', 'Do not replace a symlink')
        require(not path.exists() or (path.is_file() and path.stat().st_uid == os.getuid()
                and (overwrite or path.read_bytes() == text.encode('utf-8'))),
                'EXPORT_CONFLICT', 'Different existing export requires explicit overwrite')
    output = {}
    for path, text in targets.items():
        require(type(text) is str, 'INVALID_ARGUMENT', 'Export content must be stored text')
        if path.is_file() and not path.is_symlink() and path.read_bytes() == text.encode('utf-8'):
            output[path.suffix[1:]] = {'path': str(path), 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
            continue
        fd, temp = tempfile.mkstemp(prefix='.' + run_id + '-', dir=root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                content = text.encode('utf-8')
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if overwrite:
                # Explicit overwrite grants replacement of this regular owned destination only.
                require(not path.is_symlink(), 'UNSAFE_PATH', 'Do not replace a symlink')
                os.replace(temp, path)
            else:
                try:
                    os.link(temp, path)
                except FileExistsError as exc:
                    raise Error('EXPORT_CONFLICT', 'Export appeared concurrently; existing file preserved') from exc
            output[path.suffix[1:]] = {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest()}
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return output
