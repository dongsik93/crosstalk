"""Strict data contracts for model results; no model or storage access."""
import hashlib
import json
from ..protocol import CONFIDENCES, VERDICTS, Error, require

BODY_LIMIT = 1024 * 1024
DECISION_LIMIT = 256 * 1024
TASK_LIMIT = 4 * 1024 * 1024


def canonical(value):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        text.encode('utf-8')
        return text
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise Error('INVALID_ARGUMENT', 'Expected finite JSON data') from exc


def digest(value):
    text = canonical(value)
    try:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    except UnicodeError as exc:
        raise Error('INVALID_ARGUMENT', 'Expected valid Unicode data') from exc


def sized(text, limit, name='Input'):
    require(isinstance(text, str), 'INVALID_ARGUMENT', f'{name} must be a string')
    try:
        size = len(text.encode('utf-8'))
    except UnicodeError as exc:
        raise Error('INVALID_ARGUMENT', f'{name} must contain valid Unicode') from exc
    require(size <= limit, 'CONTEXT_TOO_LARGE', f'{name} exceeds {limit} UTF-8 bytes')
    return text


def loads(text, limit=TASK_LIMIT):
    sized(text, limit, 'JSON input')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'INVALID_ARGUMENT', 'Duplicate JSON keys are not accepted')
            result[key] = value
        return result
    def constant(_):
        raise Error('INVALID_ARGUMENT', 'NaN and Infinity are not accepted')
    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
        canonical(value)
        return value
    except (json.JSONDecodeError, RecursionError) as exc:
        raise Error('INVALID_ARGUMENT', 'Malformed JSON input') from exc


def _object(payload, allowed, code):
    require(type(payload) is dict, code, 'Result must be a JSON object')
    require(all(type(key) is str for key in payload), code, 'Object keys must be strings')
    require(not set(payload) - allowed, code, 'Unknown result fields are not accepted')
    version = payload.get('schema_version', 1)
    require(type(version) is int and version == 1, code, 'Result schema_version must be integer 1')
    return {'schema_version': 1}


def _text(value, field, code, *, nonempty=True, limit=BODY_LIMIT):
    require(type(value) is str, code, f'{field} must be a string')
    sized(value, limit, field)
    require(not nonempty or bool(value.strip()), code, f'{field} must not be empty')
    return value


def _strings(value, field, code):
    require(type(value) is list, code, f'{field} must be a list')
    return [_text(item, field, code) for item in value]


def evidence(value, code='INVALID_ARGUMENT'):
    require(type(value) is list, code, 'Evidence references must be a list')
    result = []
    for ref in value:
        require(type(ref) is dict and not set(ref) - {'kind', 'value', 'status'}, code, 'Invalid evidence reference')
        kind = ref.get('kind')
        require(type(kind) is str and kind in ('message', 'action', 'url', 'file', 'claim'), code, 'Unknown evidence kind')
        item = {'kind': kind, 'value': _text(ref.get('value'), 'evidence value', code)}
        if kind in ('message', 'action'):
            require('status' not in ref, code, 'Internal reference validation belongs to the engine')
        else:
            require(ref.get('status', 'reported') == 'reported', code, 'External evidence is reported, not verified')
            item['status'] = 'reported'
        result.append(item)
    return result


def analysis(payload):
    code = 'INVALID_ARGUMENT'
    fields = {'schema_version', 'body', 'summary', 'confidence', 'assumptions', 'unresolved_questions', 'evidence_refs', 'verdict', 'reason'}
    result = _object(payload, fields, code)
    result['body'] = _text(payload.get('body'), 'body', code)
    result['summary'] = _text(payload.get('summary', ''), 'summary', code, nonempty=False)
    confidence, verdict = payload.get('confidence', 'unknown'), payload.get('verdict', 'none')
    require(type(confidence) is str and confidence in CONFIDENCES, code, 'Invalid confidence')
    require(type(verdict) is str and verdict in VERDICTS, code, 'Invalid verdict')
    result.update(confidence=confidence, verdict=verdict)
    result['reason'] = _text(payload.get('reason', ''), 'reason', code, nonempty=verdict in ('disagree', 'respect_disagree'))
    for field in ('assumptions', 'unresolved_questions'):
        result[field] = _strings(payload.get(field, []), field, code)
    result['evidence_refs'] = evidence(payload.get('evidence_refs', []), code)
    sized(canonical(result), TASK_LIMIT, 'Analysis result')
    return result


def decision(payload):
    code = 'DECISION_INVALID'
    fields = {'schema_version', 'decision', 'requested_outcome', 'comparison_summary', 'caller_position', 'cited_result_ids',
              'unresolved_questions', 'followup_body', 'continuation_reason', 'new_evidence_refs', 'closing_summary'}
    result = _object(payload, fields, code)
    sized(canonical(payload), DECISION_LIMIT, 'Decision')
    requested = payload.get('decision')
    require(type(requested) is str and requested in ('continue', 'finish'), code, 'decision must be continue or finish')
    result['decision'] = requested
    for field in ('comparison_summary', 'caller_position', 'closing_summary'):
        result[field] = _text(payload.get(field), field, code, limit=DECISION_LIMIT)
    for field in ('cited_result_ids', 'unresolved_questions'):
        result[field] = _strings(payload.get(field), field, code)
    require(len(result['cited_result_ids']) >= 2 and len(set(result['cited_result_ids'])) == len(result['cited_result_ids']),
            code, 'Cite distinct current caller and peer results')
    result['new_evidence_refs'] = evidence(payload.get('new_evidence_refs', []), code)
    if requested == 'finish':
        outcome = payload.get('requested_outcome')
        require(type(outcome) is str and outcome in ('concluded', 'diverged', 'unresolved'), code, 'Invalid finish outcome')
        require('followup_body' not in payload and 'continuation_reason' not in payload, code, 'Finish cannot contain a follow-up')
        result['requested_outcome'] = outcome
    else:
        require('requested_outcome' not in payload, code, 'Continue cannot request a terminal outcome')
        for field in ('followup_body', 'continuation_reason'):
            result[field] = _text(payload.get(field), field, code, limit=DECISION_LIMIT)
    return result
