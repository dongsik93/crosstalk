"""Pure workflow decisions; semantics of an answer remain the caller's judgment."""
from ..protocol import require

LIFECYCLES = ('active', 'paused', 'completed', 'cancelled', 'failed')
PHASES = ('preparing', 'collecting', 'comparing', 'finalizing', 'terminal')


def next_phase(mode, caller_ready, peer_ready, current_phase):
    require(mode in ('analyze', 'ask') and current_phase in PHASES, 'STATE_CONFLICT', 'Unknown engine state')
    require(type(caller_ready) is bool and type(peer_ready) is bool, 'STATE_CONFLICT', 'Readiness must be boolean')
    if current_phase == 'collecting' and caller_ready and peer_ready:
        return 'finalizing' if mode == 'ask' else 'comparing'
    return current_phase


def applied_decision(payload, round_no, max_rounds):
    require(type(round_no) is int and type(max_rounds) is int and 1 <= round_no <= max_rounds <= 10,
            'STATE_CONFLICT', 'Round policy is invalid')
    requested = payload['decision']
    require(requested in ('continue', 'finish'), 'DECISION_INVALID', 'Unknown decision')
    if requested == 'continue' and round_no == max_rounds:
        return {'requested_decision': 'continue', 'applied_decision': 'finish',
                'override_reason': 'round_limit', 'outcome': 'round_limit'}
    return {'requested_decision': requested, 'applied_decision': requested,
            'override_reason': None, 'outcome': payload.get('requested_outcome') if requested == 'finish' else None}
