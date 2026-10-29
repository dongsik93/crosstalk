"""Durable message ownership; external work is never automatically replayed."""
import hashlib
import hmac
import json
from contextlib import contextmanager
import secrets
import sqlite3
import time
import uuid
from . import db, delivery, sessions
from .protocol import CONFIDENCES, OUTCOMES, VERDICTS, Error, now, require, valid_id

LEASE_SECONDS = 900
MAX_ATTEMPTS = 3


@contextmanager
def saved_result(mid):
    """Once commit returned, reporting and notification failures cannot unsave it."""
    try:
        yield
    except Error as exc:
        if exc.saved:
            raise
        raise Error(exc.code, str(exc), saved=True, message_id=mid, next_action=f'status {mid}') from exc
    except (OSError, sqlite3.Error) as exc:
        code = 'DB_BUSY' if isinstance(exc, sqlite3.OperationalError) and 'locked' in str(exc) else 'OPERATION_FAILED'
        raise Error(code, 'Message saved; result could not be read or reported', saved=True,
                    message_id=mid, next_action=f'status {mid}') from exc


def message(conn, mid, actor):
    valid_id(mid)
    row = conn.execute('SELECT m.*,t.mode,t.state AS thread_state,t.execution_owner FROM messages m JOIN threads t USING(thread_id) WHERE id=?', (mid,)).fetchone()
    require(row is not None and actor['session_id'] in (row['sender_session_id'],row['recipient_session_id']), 'NOT_FOUND', 'Message not found for this session')
    return row


def effective_state(row, clock=None):
    if row['processing_state']=='processing' and (row['lease_expires_at'] is None or row['lease_expires_at'] <= (time.time() if clock is None else clock)):
        return 'recovery_required'
    return row['processing_state']


def envelope(row, *, body=True):
    result = {key: row[key] for key in row.keys() if key != 'lease_token_hash' and (body or key not in ('body','completion_result'))}
    result['effective_state'] = effective_state(row)
    if result.get('completion_result') is not None:
        result['completion_result'] = json.loads(result['completion_result'])
    return result


def current_binding(conn, actor):
    binding = conn.execute('SELECT * FROM bindings WHERE session_id=? AND active=1', (actor['session_id'],)).fetchone()
    require(binding and binding['generation']==actor['generation'] and binding['instance_id']==actor['instance_id'], 'STALE_BINDING', 'Session binding changed; inspect status and recover explicitly')
    return binding


def lease(conn, row, actor, token):
    require(row['recipient_session_id']==actor['session_id'], 'STATE_CONFLICT', 'Only the recipient can process this message')
    current_binding(conn,actor)
    require(row['processing_state']=='processing', 'STALE_LEASE', 'Message is not processing')
    require(row['claim_binding_generation']==actor['generation'] and row['claim_instance_id']==actor['instance_id'], 'STALE_BINDING', 'Claim belongs to a prior session binding')
    require(token and row['lease_token_hash'] and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),row['lease_token_hash']), 'STALE_LEASE', 'A current lease token is required')
    require(row['lease_expires_at']>time.time(), 'LEASE_EXPIRED', 'Lease expired; inspect recover before explicit reclaim')


def complete(conn, row, result):
    conn.execute("UPDATE messages SET processing_state='completed',lease_token_hash=NULL,lease_expires_at=NULL,completed_at=?,completion_result=? WHERE id=?", (now(),json.dumps(result,ensure_ascii=False),row['id']))
    db.event(conn,'completed',message_id=row['id'])


def claim(conn, row, actor):
    current_binding(conn,actor)
    token = 'lease_' + secrets.token_urlsafe(32)
    conn.execute("""UPDATE messages SET processing_state='processing',claim_version=claim_version+1,
                 lease_token_hash=?,lease_expires_at=?,claim_binding_generation=?,claim_instance_id=?,
                 attempt_count=attempt_count+1,received_at=COALESCE(received_at,?),last_error_code=NULL WHERE id=?""",
                 (hashlib.sha256(token.encode()).hexdigest(),time.time()+LEASE_SECONDS,actor['generation'],actor['instance_id'],now(),row['id']))
    db.event(conn,'claimed',message_id=row['id'],session_id=actor['session_id'],claim_version=row['claim_version']+1)
    result=envelope(message(conn,row['id'],actor))
    result.update(actionable=True,lease_token=token,binding_generation=actor['generation'])
    return result



def unmanaged(conn, row):
    owner = conn.execute('SELECT execution_owner FROM threads WHERE thread_id=?', (row['thread_id'],)).fetchone()
    require(owner and owner['execution_owner']=='mailbox-v2', 'RUN_MANAGED_BY_ENGINE', 'Use run take/submit/decide for this discussion message')


def create_request(conn, actor, recipient, *, mid, body, summary='', mode='analyze', thread_id=None,
                   round_no=1, caused_by=None, owner='mailbox-v2', run_id=None):
    require(conn.in_transaction, 'STATE_CONFLICT', 'Mailbox mutations require the service transaction')
    current_binding(conn,actor)
    current_binding(conn,recipient)
    reservations = conn.execute("""SELECT r.run_id,r.config_snapshot FROM discussion_runs r
        JOIN discussion_actions a ON a.run_id=r.run_id
        WHERE r.peer_session_id=? AND r.lifecycle IN ('active','paused')
        AND a.kind='peer_analysis' AND a.round_no=1 AND a.status='pending'""",
        (recipient['session_id'],)).fetchall()
    require(not any(row['run_id']!=run_id and json.loads(row['config_snapshot']).get('review_mode')=='independent'
                    for row in reservations), 'FRESH_CONTEXT_REQUIRED',
            'This peer is completing an independent first analysis; do not inject another request')
    if thread_id is None:
        thread_id=mid
        conn.execute('INSERT INTO threads(thread_id,caller_session_id,peer_session_id,mode,execution_owner,run_id) VALUES(?,?,?,?,?,?)',
                     (thread_id,actor['session_id'],recipient['session_id'],mode,owner,run_id))
    conn.execute("""INSERT INTO messages(id,thread_id,kind,sender_session_id,recipient_session_id,caused_by_reply_id,body,summary,round,created_at,run_id)
                    VALUES(?,?,'request',?,?,?,?,?,?,?,?)""",
                 (mid,thread_id,actor['session_id'],recipient['session_id'],caused_by,body,summary,round_no,now(),run_id))
    delivery.seed(conn,mid)
    db.event(conn,'saved',message_id=mid,session_id=actor['session_id'])
    return mid


def create_reply(conn, actor, original, *, body, summary='', verdict='none', reason='', confidence='unknown', token=None):
    require(conn.in_transaction, 'STATE_CONFLICT', 'Mailbox mutations require the service transaction')
    lease(conn,original,actor,token)
    require(original['kind']=='request' and original['thread_state']=='open', 'STATE_CONFLICT', 'Request is not open')
    mid=uuid.uuid4().hex
    conn.execute("""INSERT INTO messages(id,thread_id,kind,sender_session_id,recipient_session_id,reply_to,body,summary,round,created_at,verdict,verdict_reason,confidence,verdict_source,run_id)
                    VALUES(?,?,'reply',?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (mid,original['thread_id'],actor['session_id'],original['sender_session_id'],original['id'],body,summary,original['round'],now(),verdict,reason,confidence,'explicit' if verdict!='none' else 'none',original['run_id']))
    delivery.seed(conn,mid,suppressed=original['mode']=='ask')
    complete(conn,original,{'reply_id':mid})
    db.event(conn,'reply_saved',message_id=mid,session_id=actor['session_id'])
    return mid


def send(conn, actor, args, body):
    from . import intake
    require(not intake.requires_engine(actor),
            'RUN_MANAGED_BY_ENGINE','Independent review must use captured input and engine actions, not a rewritten mailbox message')
    mid=valid_id(args.id or uuid.uuid4().hex)
    recipient=sessions.peer(conn,args.peer,actor,session_id=args.peer_session)
    notify=False
    with db.transaction(conn):
        active = conn.execute("SELECT config_snapshot FROM discussion_runs WHERE caller_session_id=? AND lifecycle IN ('active','paused')",
                              (actor['session_id'],)).fetchall()
        require(not any(json.loads(row['config_snapshot']).get('review_mode')=='independent' for row in active),
                'RUN_MANAGED_BY_ENGINE','Use the independent run actions instead of a separate mailbox message')
        if args.thread:
            thread=conn.execute('SELECT execution_owner FROM threads WHERE thread_id=?',(args.thread,)).fetchone()
            require(not thread or thread['execution_owner']=='mailbox-v2','RUN_MANAGED_BY_ENGINE','Use run decide for managed follow-ups')
        current_binding(conn,actor)
        current_binding(conn,recipient)
        existing=conn.execute('SELECT * FROM messages WHERE id=?',(mid,)).fetchone()
        if existing:
            unmanaged(conn,existing)
            root=conn.execute('SELECT * FROM threads WHERE thread_id=?',(existing['thread_id'],)).fetchone()
            require((existing['sender_session_id'],existing['recipient_session_id'],existing['body'],root['mode'],existing['thread_id'],existing['kind'],existing['caused_by_reply_id']) ==
                    (actor['session_id'],recipient['session_id'],body,args.mode,args.thread or mid,'request',args.after_reply),
                    'IDEMPOTENCY_CONFLICT','Message ID already belongs to different content or routing')
        else:
            round_number=1
            if args.thread:
                require(args.after_reply, 'INVALID_ARGUMENT','Follow-up requires --after-reply and --lease-token')
                prior=message(conn,args.after_reply,actor)
                require(prior['kind']=='reply' and prior['thread_id']==args.thread, 'STATE_CONFLICT','Follow-up must refer to a reply in this thread')
                thread=conn.execute('SELECT * FROM threads WHERE thread_id=?',(args.thread,)).fetchone()
                require((thread['caller_session_id'],thread['peer_session_id'],thread['mode'])==(actor['session_id'],recipient['session_id'],args.mode), 'STATE_CONFLICT','Follow-up must retain caller, peer, and mode')
                linked=conn.execute('SELECT * FROM messages WHERE caused_by_reply_id=?',(prior['id'],)).fetchone()
                if linked:
                    require(linked['body']==body, 'IDEMPOTENCY_CONFLICT','Reply already caused a different follow-up')
                    return output(conn,linked['id'],actor)
                require(thread['mode']=='analyze' and thread['state']=='open', 'STATE_CONFLICT','Thread is not open for another round')
                lease(conn,prior,actor,args.lease_token)
                latest=conn.execute("SELECT MAX(round) FROM messages WHERE thread_id=? AND kind='request'",(args.thread,)).fetchone()[0]
                require(latest==prior['round'], 'STATE_CONFLICT','Follow-up must use the latest reply')
                round_number=latest+1
                require(round_number<=thread['max_rounds'], 'STATE_CONFLICT','Conversation reached its round limit')
            else:
                require(not args.after_reply and not args.lease_token, 'INVALID_ARGUMENT','--after-reply and --lease-token require --thread')
            create_request(conn,actor,recipient,mid=mid,body=body,summary=args.summary,mode=args.mode,thread_id=args.thread,round_no=round_number,caused_by=args.after_reply)
            if args.thread: complete(conn,prior,{'next_request_id':mid})
            notify=True
    with saved_result(mid):
        row=message(conn,mid,actor)
        result=output(conn,mid,actor)
        if notify: result.update(delivery.notify(conn,row))
        return result


def output(conn, mid, actor):
    row=message(conn,mid,actor)
    return {'id':row['id'],'message_id':row['id'],'thread_id':row['thread_id'],'reply_to':row['reply_to'],
            'processing_state':row['processing_state'],'saved':True,'notification_error':None}


def receive(conn, actor, args):
    require(not args.replay, 'INVALID_ARGUMENT','--replay is deprecated; inspect recover ID and explicitly reclaim')
    from .engine import service
    with db.transaction(conn):
        current_binding(conn,actor)
        rows=([message(conn,args.id,actor)] if args.id else conn.execute("SELECT m.*,t.mode,t.state AS thread_state,t.execution_owner FROM messages m JOIN threads t USING(thread_id) WHERE recipient_session_id=? AND processing_state='queued' AND t.state='open' ORDER BY seq",(actor['session_id'],)).fetchall())
        for row in rows:
            require(row['recipient_session_id']==actor['session_id'], 'STATE_CONFLICT','Only the recipient can receive this message')
            if row['execution_owner']=='discussion-v1':
                dispatched=service.dispatch_message(conn,row,actor)
                if dispatched: return dispatched
                if args.id: return {'id':row['id'],'actionable':False,'handler':'discussion','run_id':row['run_id'],'reason':'action_not_ready'}
                continue
            if row['processing_state']!='queued': return {'id':row['id'],'actionable':False,'processing_state':row['processing_state'],'effective_state':effective_state(row)}
            require(row['thread_state']=='open', 'STATE_CONFLICT','Thread is closed')
            return claim(conn,row,actor)
        return {'actionable':False,'reason':'empty'}


def reply(conn, actor, args, body):
    require(args.verdict in VERDICTS and args.confidence in CONFIDENCES, 'INVALID_ARGUMENT','Invalid verdict or confidence')
    require(args.verdict not in ('disagree','respect_disagree') or args.reason.strip(), 'INVALID_ARGUMENT','Disagreement requires a reason')
    notify=False
    with db.transaction(conn):
        original=message(conn,args.id,actor)
        unmanaged(conn,original)
        require(original['kind']=='request' and original['recipient_session_id']==actor['session_id'], 'STATE_CONFLICT','Only the request recipient can reply')
        current_binding(conn,actor)
        existing=conn.execute('SELECT * FROM messages WHERE reply_to=?',(args.id,)).fetchone()
        if existing:
            require((existing['body'],existing['verdict'],existing['verdict_reason'],existing['confidence']) == (body,args.verdict,args.reason,args.confidence), 'REPLY_CONFLICT','This request already has a different confirmed reply')
            mid=existing['id']
        else:
            mid=create_reply(conn,actor,original,body=body,summary=args.summary,verdict=args.verdict,reason=args.reason,confidence=args.confidence,token=args.lease_token)
            notify=True
    with saved_result(mid):
        result=output(conn,mid,actor)
        if notify: result.update(delivery.notify(conn,message(conn,mid,actor)))
        return result


def ack(conn, actor, args, result):
    payload={'outcome':args.outcome,'result':result}
    with db.transaction(conn):
        row=message(conn,args.id,actor)
        unmanaged(conn,row)
        require(row['kind']=='reply' and row['recipient_session_id']==actor['session_id'], 'STATE_CONFLICT','Only a reply recipient can ack')
        require(args.outcome in OUTCOMES and (args.outcome=='observed')==(row['mode']=='ask'), 'INVALID_ARGUMENT','Ask uses observed; analyze uses concluded, diverged, or unresolved')
        current_binding(conn,actor)
        if row['processing_state']=='completed':
            require(json.loads(row['completion_result'])==payload, 'STATE_CONFLICT','Reply already completed with a different result')
        else:
            lease(conn,row,actor,args.lease_token)
            later=conn.execute("SELECT 1 FROM messages WHERE thread_id=? AND kind='request' AND round>? LIMIT 1",
                               (row['thread_id'],row['round'])).fetchone()
            require(not later, 'STATE_CONFLICT', 'A later request already exists; inspect its saved result instead of closing this thread')
            complete(conn,row,payload)
            conn.execute("UPDATE threads SET state='closed' WHERE thread_id=?",(row['thread_id'],))
        return {'id':row['id'],'message_id':row['id'],'saved':True,'processing_state':'completed','completion_result':payload}


def renew(conn, actor, args):
    with db.transaction(conn):
        row=message(conn,args.id,actor)
        lease(conn,row,actor,args.lease_token)
        deadline=max(row['lease_expires_at'],time.time()+LEASE_SECONDS)
        conn.execute('UPDATE messages SET lease_expires_at=? WHERE id=?',(deadline,row['id']))
        db.event(conn,'renewed',message_id=row['id'],session_id=actor['session_id'])
        return {'id':row['id'],'lease_expires_at':deadline,'claim_version':row['claim_version']}


def recover(conn, actor, args):
    if not args.reclaim:
        row=message(conn,args.id,actor)
        return {'message':public_envelope(conn,row,actor,body=False),'reclaimable':effective_state(row)=='recovery_required',
                'warning':'Prior processing may have changed external files. Inspect history and external effects before reclaiming.',
                'next_action':f'recover {row["id"]} --reclaim --expected-claim-version {row["claim_version"]} --confirm-external-effects'}
    require(args.confirm_external_effects, 'INVALID_ARGUMENT','Explicit confirmation of external effects is required')
    require(args.expected_claim_version is not None, 'INVALID_ARGUMENT','--expected-claim-version is required')
    with db.transaction(conn):
        row=message(conn,args.id,actor)
        require(row['recipient_session_id']==actor['session_id'], 'STATE_CONFLICT','Only the recipient can reclaim')
        require(row['claim_version']==args.expected_claim_version, 'STALE_LEASE','Claim changed since inspection')
        require(effective_state(row)=='recovery_required', 'STATE_CONFLICT','Only expired or recovery-required work may be reclaimed')
        require(row['thread_state']=='open', 'STATE_CONFLICT','Thread is closed')
        if row['run_id']:
            from .engine.service import recovery_allowed
            recovery_allowed(conn,row,actor)
        if row['attempt_count']>=MAX_ATTEMPTS:
            conn.execute("UPDATE messages SET processing_state='failed',lease_token_hash=NULL,lease_expires_at=NULL,last_error_code='ATTEMPT_LIMIT' WHERE id=?",(row['id'],))
            db.event(conn,'failed',message_id=row['id'],error_code='ATTEMPT_LIMIT')
            return {'id':row['id'],'actionable':False,'processing_state':'failed','error':{'code':'ATTEMPT_LIMIT','message':'Inspect saved work before starting a new thread','retryable':False}}
        return claim(conn,row,actor)


def cancel(conn, actor, args):
    require(args.reason.strip(), 'INVALID_ARGUMENT','Cancellation requires a reason')
    with db.transaction(conn):
        row=message(conn,args.id,actor)
        unmanaged(conn,row)
        require(row['sender_session_id']==actor['session_id'], 'STATE_CONFLICT','Only the message sender can cancel')
        current_binding(conn,actor)
        require(row['processing_state'] in ('queued','processing','recovery_required','cancelled'), 'STATE_CONFLICT','Completed or failed messages cannot be cancelled')
        conn.execute("UPDATE messages SET processing_state='cancelled',lease_token_hash=NULL,lease_expires_at=NULL,last_error_code='CANCELLED',completion_result=COALESCE(completion_result,?) WHERE id=?",(json.dumps({'reason':args.reason}),row['id']))
        db.event(conn,'cancelled',message_id=row['id'],session_id=actor['session_id'])
        return {'id':row['id'],'processing_state':'cancelled','process_stopped':False}


def query(conn, actor, args):
    if args.command=='history':
        row=message(conn,args.id,actor)
        rows=conn.execute('SELECT * FROM messages WHERE thread_id=? ORDER BY seq LIMIT ? OFFSET ?',(row['thread_id'],args.limit,args.offset)).fetchall()
        result=[]
        for row in rows:
            item=public_envelope(conn,row,actor)
            item['delivery_attempts']=[delivery.attempt_view(attempt) for attempt in conn.execute(
                'SELECT * FROM delivery_attempts WHERE message_id=? ORDER BY rowid', (row['id'],))]
            result.append(item)
        return result
    rows=([message(conn,args.id,actor)] if args.id else conn.execute(
        'SELECT * FROM messages WHERE sender_session_id=? OR recipient_session_id=? ORDER BY seq DESC LIMIT ? OFFSET ?',
        (actor['session_id'],actor['session_id'],args.limit,args.offset)).fetchall())
    result=[]
    for row in rows:
        item=public_envelope(conn,row,actor,body=False)
        item['latest_delivery']=delivery.attempt_view(delivery.latest(conn,row['id']))
        result.append(item)
    return result


def public_envelope(conn,row,actor,*,body=True):
    value=envelope(row,body=body)
    if row['run_id']:
        from .engine.service import hidden_reply
        if hidden_reply(conn,row,actor):
            for key in ('body','summary','completion_result','verdict','verdict_reason','confidence','verdict_source'):
                value.pop(key,None)
            value['redacted']=True
    return value
