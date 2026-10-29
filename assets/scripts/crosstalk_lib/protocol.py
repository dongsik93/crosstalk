"""Protocol values and errors shared by the CLI and state managers."""
import re
from datetime import datetime, timezone

KINDS = ('claude', 'codex', 'antigravity')
VERDICTS = ('agree', 'disagree', 'respect_disagree', 'none')
CONFIDENCES = ('high', 'medium', 'low', 'unknown')
OUTCOMES = ('concluded', 'diverged', 'unresolved', 'observed')


class Error(ValueError):
    def __init__(self, code, message, *, saved=False, message_id=None, next_action=None):
        super().__init__(message)
        self.code, self.saved, self.message_id = code, saved, message_id
        self.next_action = next_action

    @property
    def exit_code(self):
        if self.saved: return 4
        if self.code in ('INVALID_ARGUMENT', 'INVALID_ID'): return 2
        if self.code in ('CALLER_UNBOUND', 'AMBIGUOUS_PEER', 'BINDING_CONFLICT'): return 3
        if self.code in ('MIGRATION_REQUIRED', 'SCHEMA_TOO_NEW', 'PROTOCOL_MISMATCH'): return 6
        if self.code in ('INPUT_SOURCE_REQUIRED','INPUT_SOURCE_UNVERIFIED','INPUT_SOURCE_UNAVAILABLE','INPUT_SCOPE_REQUIRED',
                         'FRESH_PEER_REQUIRED','FRESH_PEER_CONFLICT','FRESH_CONTEXT_REQUIRED'): return 5
        if self.code in ('LEASE_EXPIRED', 'STALE_LEASE', 'STALE_BINDING', 'IDEMPOTENCY_CONFLICT', 'REPLY_CONFLICT', 'STATE_CONFLICT','RUN_ALREADY_ACTIVE','RUN_MANAGED_BY_ENGINE','INITIAL_POSITION_REQUIRED','ACTION_NOT_READY','STALE_ACTION','RESULT_CONFLICT','INPUT_DIGEST_MISMATCH','DECISION_INVALID','RUN_PAUSED','RUN_TERMINAL'): return 5
        return 7

    def result(self):
        value = {'error': {'code': self.code, 'message': str(self), 'retryable': self.code in ('DB_BUSY', 'TERMINAL_TIMEOUT')},
                 'saved': self.saved, 'message_id': self.message_id, 'next_action': self.next_action}
        if getattr(self,'engine',False):
            value.update(protocol_version=3,ok=False,run_id=getattr(self,'run_id',None),action_id=getattr(self,'action_id',None),
                         lifecycle=None,phase=None,round=None)
        return value


def require(value, code, message):
    if not value:
        raise Error(code, message)


def valid_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value), 'INVALID_ID', 'ID must contain 1..64 letters, digits, underscores or hyphens')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()
