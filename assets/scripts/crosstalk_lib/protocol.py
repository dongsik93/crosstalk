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
        if self.code in ('LEASE_EXPIRED', 'STALE_LEASE', 'STALE_BINDING', 'IDEMPOTENCY_CONFLICT', 'REPLY_CONFLICT', 'STATE_CONFLICT'): return 5
        return 7

    def result(self):
        return {'error': {'code': self.code, 'message': str(self), 'retryable': self.code in ('DB_BUSY', 'TERMINAL_TIMEOUT')},
                'saved': self.saved, 'message_id': self.message_id, 'next_action': self.next_action}


def require(value, code, message):
    if not value:
        raise Error(code, message)


def valid_id(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value), 'INVALID_ID', 'ID must contain 1..64 letters, digits, underscores or hyphens')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()
