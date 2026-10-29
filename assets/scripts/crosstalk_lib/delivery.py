"""Persisted notification attempts; submission never implies AI receipt."""
import os
import json
from pathlib import Path
import signal
import sqlite3
import subprocess
import uuid
from . import db
from .protocol import Error, now, require, valid_id

BRIDGE_TIMEOUT = 10


def bridge(*args):
    from .adapters.registry import call_terminal
    timeout = BRIDGE_TIMEOUT
    if args and args[0] in ('launch','ensure-peer','wait-ready'):
        timeout = max(10, int(os.environ.get('READY_MAX_WAIT','120'))) + 10
    return call_terminal(*args, timeout=timeout)


def verify_target(binding):
    raw = bridge('target-identity', binding['surface_id'])
    try:
        evidence = json.loads(binding['evidence'])
        current = json.loads(raw)
    except (ValueError, TypeError):
        raise Error('STALE_BINDING', 'Cannot verify the foreground recipient instance') from None
    require(isinstance(evidence,dict) and isinstance(current,dict), 'STALE_BINDING', 'Recipient identity evidence is malformed')
    require(current.get('surface_id')==binding['surface_id'] and current.get('kind')==binding['kind']
            and all(evidence.get(key) and str(evidence[key])==str(current.get(key,'')) for key in ('process_id','process_start')),
            'STALE_BINDING', 'Recipient foreground instance changed; rebind before retrying')


def seed(conn, message_id, suppressed=False):
    attempt = uuid.uuid4().hex
    conn.execute('INSERT INTO delivery_attempts(attempt_id,message_id,state,started_at,finished_at) VALUES(?,?,?,?,?)',
                 (attempt,message_id,'suppressed' if suppressed else 'not_attempted',now(),now() if suppressed else None))
    return attempt


def latest(conn, message_id):
    row = conn.execute('SELECT * FROM delivery_attempts WHERE message_id=? ORDER BY rowid DESC LIMIT 1', (message_id,)).fetchone()
    return dict(row) if row else None


def result(attempt):
    state = attempt['state'] if attempt else 'not_attempted'
    return {'notification_error': attempt['error_code'] if attempt else None,
            'delivery_state': 'unknown' if state == 'in_flight' else state}


def attempt_view(attempt):
    if not attempt:
        return None
    value=dict(attempt)
    value['effective_state']='unknown' if value['state']=='in_flight' else value['state']
    return value


def notify(conn, row, *, retry=False):
    mid, recipient = valid_id(row['id']), valid_id(row['recipient_session_id'])
    try:
        observed = latest(conn, mid)
        observed_key = (observed['attempt_id'], observed['state'], observed['finished_at']) if observed else None
        require(not conn.in_transaction, 'STATE_CONFLICT', 'Commit the message before notifying')
        with db.lock('message-' + mid[:48]), db.lock('session-' + recipient[:48]):
            current = latest(conn, mid)
            # A retry that waited behind another delivery adopts its result instead of typing twice.
            current_key = (current['attempt_id'], current['state'], current['finished_at']) if current else None
            if current and current_key != observed_key:
                return result(current)
            fresh = conn.execute('SELECT * FROM messages WHERE id=?', (mid,)).fetchone()
            require(fresh, 'STATE_CONFLICT', 'Message no longer exists')
            from .engine.service import delivery_allowed, notification_preview
            if not delivery_allowed(conn,fresh): return result(current)
            if fresh['processing_state'] != 'queued' or (current and current['state'] == 'suppressed'):
                return result(current)
            if current and current['state'] != 'not_attempted' and not retry:
                return result(current)
            binding = conn.execute('SELECT b.*,s.kind FROM bindings b JOIN sessions s USING(session_id) WHERE b.session_id=? AND b.active=1', (recipient,)).fetchone()
            require(binding, 'CALLER_UNBOUND', 'Recipient must complete a binding handshake')
            attempt = current['attempt_id'] if current and current['state'] == 'not_attempted' else uuid.uuid4().hex
            with db.transaction(conn):
                if not delivery_allowed(conn,fresh): return result(current)
                if current and current['state'] == 'in_flight':
                    conn.execute("UPDATE delivery_attempts SET state='unknown',finished_at=?,error_code='NOTIFICATION_UNKNOWN' WHERE attempt_id=?", (now(),current['attempt_id']))
                conn.execute('INSERT INTO delivery_attempts(attempt_id,message_id,target_surface_id,target_binding_generation,state,started_at) VALUES(?,?,?,?,?,?) ON CONFLICT(attempt_id) DO UPDATE SET target_surface_id=excluded.target_surface_id,target_binding_generation=excluded.target_binding_generation,state=excluded.state,started_at=excluded.started_at',
                             (attempt,mid,binding['surface_id'],binding['generation'],'in_flight',now()))
                db.event(conn,'notification_started',message_id=mid,session_id=recipient,generation=binding['generation'])
            state, error_code = 'submitted', None
            try:
                korean = bridge('get-language') == 'ko'
                kind = ('답변' if row['kind']=='reply' else '질문') if korean else ('Reply' if row['kind']=='reply' else 'Question')
                preview = notification_preview(conn,fresh) or ' '.join((row['summary'].strip() or row['body']).split())
                preview = ''.join(c for c in preview if c.isprintable())
                if len(preview) > 160: preview = preview[:159] + '…'
                verify_target(binding)
                bridge('send', binding['surface_id'], f'[Crosstalk] {kind}: {preview}')
            except Error as exc:
                state = 'unknown' if exc.code in ('TERMINAL_TIMEOUT','NOTIFICATION_UNKNOWN') else 'failed'
                error_code = 'NOTIFICATION_UNKNOWN' if state == 'unknown' else ('STALE_BINDING' if exc.code=='STALE_BINDING' else 'NOTIFICATION_FAILED')
            except OSError:
                state, error_code = 'failed', 'NOTIFICATION_FAILED'
            with db.transaction(conn):
                conn.execute('UPDATE delivery_attempts SET state=?,finished_at=?,error_code=? WHERE attempt_id=?', (state,now(),error_code,attempt))
                db.event(conn,'notification_finished',message_id=mid,session_id=recipient,state=state,error_code=error_code)
            if error_code:
                raise Error(error_code, 'Message saved; inspect status and retry this notification', saved=True, message_id=mid, next_action=f'retry {mid}')
            return {'notification_error': None, 'delivery_state': state}
    except Error as exc:
        if exc.saved: raise
        raise Error(exc.code,str(exc),saved=True,message_id=mid,next_action=f'status {mid}') from None
    except (OSError, sqlite3.Error) as exc:
        raise Error('NOTIFICATION_UNKNOWN', 'Message saved; notification outcome could not be recorded',
                    saved=True, message_id=mid, next_action=f'status {mid}') from exc
