"""Transactional discussion workflow; model reasoning remains in the native CLIs."""
import argparse
from contextlib import contextmanager
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from .. import db, delivery, mailbox, sessions
from ..protocol import Error, now, require, valid_id
from . import contracts, context, report, state, store

ENGINE_VERSION = 1
PROMPT_VERSION = 1


def _id():
    return uuid.uuid4().hex


def _json(value):
    return contracts.canonical(value)


def _value(row, key, default=None):
    return row[key] if key in row.keys() else default


def compatible(actor, *, caller=False):
    require(actor['backend']=='ghostty' and (not caller or actor['kind'] in ('claude','codex')),
            'CAPABILITY_UNSUPPORTED', 'Discussion runs support Ghostty Claude/Codex callers and one supported peer')
    require(_value(actor,'protocol_version',0)==3 and _value(actor,'engine_version',0)==1,
            'PROTOCOL_MISMATCH', 'Reload discussion instructions and complete a protocol 3 / engine 1 handshake')


def _event(conn, event_type, run_id, action_id=None, **extra):
    db.event(conn,event_type,run_id=run_id,action_id=action_id,**extra)


def _touch(conn, run_id):
    conn.execute('UPDATE discussion_runs SET revision=revision+1,updated_at=? WHERE run_id=?',(now(),run_id))


def _operation(conn, actor, kind, operation_id, semantic):
    valid_id(operation_id)
    return store.operation(conn,actor,kind,operation_id,contracts.digest(semantic))


def _record(conn, actor, kind, operation_id, semantic, result):
    conn.execute('INSERT INTO discussion_operations(actor_session_id,operation_id,operation_kind,run_id,semantic_hash,response_metadata,created_at) VALUES(?,?,?,?,?,?,?)',
                 (actor['session_id'],operation_id,kind,result['run_id'],contracts.digest(semantic),_json(result),now()))


def _handle(action, actor):
    return {'action_id':action['action_id'],'kind':action['kind'],'action_epoch':action['action_epoch'],
            'input_digest':action['input_digest'],'binding_generation':actor['generation'],
            'message_id':action['source_message_id']}


def _caller(conn, run, actor):
    require(run['caller_session_id']==actor['session_id'],'STATE_CONFLICT','Only the run caller may control its workflow')
    mailbox.current_binding(conn,actor)


def _active(run):
    require(run['lifecycle'] not in ('completed','cancelled','failed'),'RUN_TERMINAL','Run is terminal; inspect its saved report')


def _not_paused(run):
    _active(run)
    require(run['lifecycle']=='active','RUN_PAUSED','Run is paused; explicitly continue it first')


def _create_action(conn, run, kind, actor, round_no, manifest, message_id=None):
    aid=_id()
    text=_json(manifest)
    require(len(text.encode('utf-8'))<=contracts.TASK_LIMIT,'CONTEXT_TOO_LARGE','Rendered task exceeds the byte limit')
    conn.execute('''INSERT INTO discussion_actions(action_id,run_id,round_no,kind,actor_session_id,instance_id,
                 binding_generation,input_manifest,input_digest,source_message_id,status,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?)''',
                 (aid,run['run_id'],round_no,kind,actor['session_id'],actor['instance_id'],actor['generation'],text,contracts.digest(manifest),message_id,now()))
    if message_id:
        conn.execute('UPDATE messages SET action_id=? WHERE id=?',(aid,message_id))
    _event(conn,'discussion_action_created',run['run_id'],aid,action_kind=kind,round_no=round_no)
    return aid


def _binding(conn, sid):
    row=conn.execute(sessions.BINDING+'WHERE b.session_id=? AND b.active=1',(sid,)).fetchone()
    require(row,'CALLER_UNBOUND','Run participant has no active verified binding')
    return dict(row)


def _resolve_peer(conn, run, caller, allow_discovery=False):
    if run['pending_surface_id']:
        query=sessions.BINDING+'WHERE b.surface_id=? AND b.active=1 AND s.kind=? AND s.status=?'
        values=[run['pending_surface_id'],run['requested_peer_kind'],'ready']
        if run['requested_peer_session']:
            query+=' AND b.session_id=?';values.append(run['requested_peer_session'])
        row=conn.execute(query,values).fetchone()
        return dict(row) if row else None
    if run['requested_peer_session'] or allow_discovery:
        return sessions.peer(conn,run['requested_peer_kind'],caller,session_id=run['requested_peer_session'])
    return None


def _validate_surface(value):
    if value is not None:
        require(isinstance(value,str) and sessions.SURFACE.fullmatch(value),'INVALID_ARGUMENT','Use an exact Ghostty peer surface')
    return value


def _analysis_result(conn, action):
    if action['result_ref']:
        row=conn.execute('SELECT body,summary,confidence,verdict,verdict_reason FROM messages WHERE id=?',(action['result_ref'],)).fetchone()
        require(row,'STATE_CONFLICT','Saved result reference is missing')
        value=json.loads(action['result_metadata'] or '{}')
        value.update(body=row['body'],summary=row['summary'],confidence=row['confidence'],verdict=row['verdict'],reason=row['verdict_reason'])
        return value
    return json.loads(action['result_json']) if action['result_json'] else None


def _position(conn, round_row):
    action=conn.execute('SELECT * FROM discussion_actions WHERE action_id=?',(round_row['caller_position_ref'],)).fetchone()
    value=_analysis_result(conn,action)
    require(value is not None,'ACTION_NOT_READY','Caller position is not yet stored')
    return value if action['kind']=='local_initial' else {'body':value['caller_position'],'summary':value['comparison_summary']}


def _finalize_tx(conn, run):
    rounds=[dict(x) for x in conn.execute('SELECT * FROM discussion_rounds WHERE run_id=? ORDER BY round_no',(run['run_id'],))]
    actions=[dict(x) for x in conn.execute('SELECT * FROM discussion_actions WHERE run_id=? ORDER BY round_no,created_at',(run['run_id'],))]
    messages={x['id']:dict(x) for x in conn.execute('SELECT * FROM messages WHERE run_id=? ORDER BY seq',(run['run_id'],))}
    data=report.build({**dict(run),'lifecycle':'completed','phase':'terminal'},rounds,actions,messages)
    conn.execute("UPDATE discussion_runs SET lifecycle='completed',phase='terminal',final_report_json=?,final_report_markdown=?,revision=revision+1,updated_at=? WHERE run_id=?",(_json(data),report.markdown(data),now(),run['run_id']))
    conn.execute("UPDATE threads SET state='closed' WHERE thread_id=?",(run['thread_id'],))
    _event(conn,'discussion_completed',run['run_id'],outcome=run['outcome'])


def _advance_tx(conn, run_id, *, allow_discovery=False):
    """At most a few bounded, deterministic transitions; never calls terminal/model APIs."""
    run=store.run(conn,run_id)
    if run['lifecycle']!='active': return []
    notifications=[]
    failed=conn.execute("SELECT last_error_code FROM messages WHERE run_id=? AND processing_state='failed' LIMIT 1",(run_id,)).fetchone()
    if failed:
        conn.execute("UPDATE discussion_runs SET lifecycle='failed',phase='terminal',outcome='failed',terminal_reason=? WHERE run_id=?",(failed['last_error_code'] or 'message_failed',run_id))
        conn.execute("UPDATE discussion_actions SET status='cancelled' WHERE run_id=? AND status='pending'",(run_id,))
        _touch(conn,run_id)
        _event(conn,'discussion_failed',run_id)
        return []
    if run['phase']=='preparing':
        caller=_binding(conn,run['caller_session_id'])
        compatible(caller,caller=True)
        try:
            peer=_resolve_peer(conn,run,caller,allow_discovery)
            if peer is None: return []
            require(peer['session_id']!=caller['session_id'],'CAPABILITY_UNSUPPORTED','A discussion requires a distinct peer')
            conn.execute('UPDATE discussion_runs SET requested_peer_session=? WHERE run_id=?',(peer['session_id'],run_id))
            compatible(peer)
        except Error as exc:
            if exc.code in ('CALLER_UNBOUND','AMBIGUOUS_PEER','PROTOCOL_MISMATCH'):
                return []
            raise
        snapshot=json.loads(run['config_snapshot'])
        if snapshot.get('review_mode') == 'independent':
            from ..adapters.registry import fresh_receipt
            receipt = fresh_receipt(db.root(), peer['surface_id'], snapshot['input_id'])
            evidence = json.loads(peer['evidence'])
            require(peer['kind']=='codex' and peer['generation']==1 and peer['cli_session_id']
                    and receipt.get('process_id')==evidence.get('process_id')
                    and receipt.get('process_start')==evidence.get('process_start'),
                    'FRESH_CONTEXT_REQUIRED','Independent analysis requires the newly launched Codex conversation')
            require(not conn.execute('SELECT 1 FROM sessions WHERE kind=? AND cli_session_id=? AND session_id<>? LIMIT 1',
                                     ('codex',peer['cli_session_id'],peer['session_id'])).fetchone(),
                    'FRESH_CONTEXT_REQUIRED','This Codex conversation ID is already known; a new pane is not a new conversation')
            require(not conn.execute('SELECT 1 FROM messages WHERE sender_session_id=? OR recipient_session_id=? LIMIT 1',
                                     (peer['session_id'],peer['session_id'])).fetchone(),
                    'FRESH_CONTEXT_REQUIRED','This peer already participated in Crosstalk; create a new conversation')
            snapshot['peer_context']={'origin':'new_cli_for_input','launch_id':receipt['launch_id'],
                                      'cli_session_id':peer['cli_session_id']}
            conn.execute('UPDATE discussion_runs SET config_snapshot=? WHERE run_id=?',(_json(snapshot),run_id))
        initial_manifest=context.render('local_initial',snapshot,1)
        initial=_create_action(conn,run,'local_initial',caller,1,initial_manifest)
        peer_manifest=context.render('peer_analysis',snapshot,1)
        mid=_id()
        mailbox.create_request(conn,caller,peer,mid=mid,body=peer_manifest['task_text'],mode=run['mode'],owner='discussion-v1',run_id=run_id)
        conn.execute('UPDATE threads SET max_rounds=? WHERE thread_id=?',(run['max_rounds'],mid))
        _create_action(conn,run,'peer_analysis',peer,1,peer_manifest,mid)
        conn.execute('INSERT INTO discussion_rounds(run_id,round_no,peer_request_id,caller_position_ref) VALUES(?,1,?,?)',(run_id,mid,initial))
        conn.execute("UPDATE discussion_runs SET thread_id=?,peer_session_id=?,phase='collecting',current_round=1 WHERE run_id=?",(mid,peer['session_id'],run_id))
        _touch(conn,run_id)
        notifications.append(mid)
        run=store.run(conn,run_id)
    if run['phase']=='collecting':
        round_row=conn.execute('SELECT * FROM discussion_rounds WHERE run_id=? AND round_no=?',(run_id,run['current_round'])).fetchone()
        position=conn.execute('SELECT * FROM discussion_actions WHERE action_id=?',(round_row['caller_position_ref'],)).fetchone()
        if position['status']=='completed' and round_row['peer_reply_id']:
            next_phase=state.next_phase(run['mode'],True,True,run['phase'])
            if next_phase=='finalizing':
                conn.execute("UPDATE discussion_runs SET phase='finalizing',outcome='sampled' WHERE run_id=?",(run_id,))
            else:
                peer_action=conn.execute("SELECT * FROM discussion_actions WHERE run_id=? AND round_no=? AND kind='peer_analysis'",(run_id,run['current_round'])).fetchone()
                manifest=context.render('compare',json.loads(run['config_snapshot']),run['current_round'],caller_position=_position(conn,round_row),peer_result=_analysis_result(conn,peer_action))
                manifest['cited_result_ids']=[round_row['caller_position_ref'],round_row['peer_reply_id']]
                aid=_create_action(conn,run,'compare',_binding(conn,run['caller_session_id']),run['current_round'],manifest,round_row['peer_reply_id'])
                conn.execute('UPDATE discussion_rounds SET compare_action_id=? WHERE run_id=? AND round_no=?',(aid,run_id,run['current_round']))
                conn.execute("UPDATE discussion_runs SET phase='comparing' WHERE run_id=?",(run_id,))
            _touch(conn,run_id)
            run=store.run(conn,run_id)
    if run['phase']=='finalizing':
        _finalize_tx(conn,run)
    return notifications


def hidden_reply(conn, message, actor):
    if not message['run_id'] or message['kind']!='reply': return False
    run=store.run(conn,message['run_id'],actor)
    if run['lifecycle']=='cancelled' or actor['session_id']!=run['caller_session_id']: return False
    initial=conn.execute("SELECT status FROM discussion_actions WHERE run_id=? AND kind='local_initial'",(run['run_id'],)).fetchone()
    return (not initial or initial['status']!='completed' or (run['lifecycle']=='paused' and run['phase']=='collecting'))


def dispatch_message(conn, message, actor):
    run=store.run(conn,message['run_id'],actor)
    if run['lifecycle']!='active' or message['processing_state']!='queued': return None
    compatible(actor)
    if hidden_reply(conn,message,actor) or (run['mode']=='ask' and message['kind']=='reply'): return None
    action=conn.execute('SELECT * FROM discussion_actions WHERE source_message_id=? AND status=?',(message['id'],'pending')).fetchone()
    if not action: return None
    return {'protocol_version':3,'handler':'discussion','actionable':True,'run_id':run['run_id'],
            'action_id':action['action_id'],'next_action':{'command':'run take','args':{'action_id':action['action_id']}}}


def recovery_allowed(conn, message, actor):
    run=store.run(conn,message['run_id'],actor)
    _not_paused(run)
    compatible(actor)
    require(not hidden_reply(conn,message,actor),'INITIAL_POSITION_REQUIRED','Submit the caller initial position first')
    require(not (run['mode']=='ask' and message['kind']=='reply'),'RUN_MANAGED_BY_ENGINE','Ask replies are informational; use run report')


def delivery_allowed(conn, message):
    if not _value(message,'run_id'): return True
    run=store.run(conn,message['run_id'])
    return run['lifecycle']=='active' and not (run['mode']=='ask' and message['kind']=='reply')


def notification_preview(conn,message):
    if not _value(message,'run_id'): return None
    # Never disclose a peer result through a wake-up, even before the first position is saved.
    return 'Discussion work is available. Run receive to inspect your next action.'


def _blockers(conn, run, actor):
    if run['lifecycle']=='paused': return ['user_paused']
    if run['lifecycle'] in ('completed','cancelled','failed'): return []
    if run['phase']=='preparing': return ['peer_not_bound_or_protocol_mismatch']
    pending=conn.execute('SELECT * FROM discussion_actions WHERE run_id=? AND actor_session_id=? AND status=? ORDER BY round_no,created_at',(run['run_id'],actor['session_id'],'pending')).fetchall()
    blockers=[]
    for action in pending:
        if action['kind']=='local_initial':
            if action['instance_id']!=actor['instance_id'] or action['binding_generation']!=actor['generation']: blockers.append('binding_changed')
            else: blockers.append('caller_initial_pending')
        elif action['source_message_id']:
            msg=conn.execute('SELECT * FROM messages WHERE id=?',(action['source_message_id'],)).fetchone()
            if mailbox.effective_state(msg)=='recovery_required': blockers.append('lease_recovery_required')
            elif action['kind']=='compare': blockers.append('comparison_pending')
            else: blockers.append('peer_analysis_pending')
    if run['phase']=='collecting' and actor['session_id']==run['caller_session_id']:
        row=conn.execute('SELECT peer_reply_id FROM discussion_rounds WHERE run_id=? AND round_no=?',(run['run_id'],run['current_round'])).fetchone()
        if row and not row['peer_reply_id']: blockers.append('peer_reply_pending')
    if run['phase']=='finalizing': blockers.append('finalization_pending')
    return list(dict.fromkeys(blockers))


def observe(conn, run_id, actor):
    run=store.run(conn,run_id,actor)
    actions=[]
    if run['lifecycle']=='active':
        for action in conn.execute('SELECT * FROM discussion_actions WHERE run_id=? AND actor_session_id=? AND status=? ORDER BY round_no,created_at',(run_id,actor['session_id'],'pending')):
            if action['kind']=='local_initial' or (action['round_no']==run['current_round'] and run['phase'] in ('collecting','comparing')):
                actions.append(_handle(action,actor))
    next_action={'command':'run take','args':{'action_id':actions[0]['action_id']}} if actions else None
    if run['lifecycle']=='active' and run['phase']=='finalizing' and actor['session_id']==run['caller_session_id']:
        next_action={'command':'run advance','args':{'run_id':run_id}}
    return {'protocol_version':3,'ok':True,'run_id':run_id,'action_id':actions[0]['action_id'] if actions else None,
            'lifecycle':run['lifecycle'],'phase':run['phase'],'round':run['current_round'],'revision':run['revision'],
            'mode':run['mode'],'outcome':run['outcome'],'caller_session_id':run['caller_session_id'],'peer_session_id':run['peer_session_id'],
            'pending_surface_id':run['pending_surface_id'],'requested_peer_kind':run['requested_peer_kind'],
            'saved':True,'error':None,'actions':actions,'blockers':_blockers(conn,run,actor),'next_action':next_action}


@contextmanager
def persisted(run_id, action_id=None, command='run status'):
    try:
        yield
    except (Error,OSError,sqlite3.Error) as exc:
        error=exc if isinstance(exc,Error) else Error('OPERATION_FAILED','Discussion saved; retry the requested read or deterministic operation')
        error.saved=True
        error.run_id=run_id
        error.action_id=action_id
        error.engine=True
        error.next_action={'command':command,'args':{'run_id':run_id}}
        raise error from exc


def _response(conn, actor, result, notifications=()):
    with persisted(result['run_id'],result.get('action_id')):
        value=dict(result)
        value['observed']=observe(conn,result['run_id'],actor)
        value.update({key:value['observed'][key] for key in ('protocol_version','ok','lifecycle','phase','round','next_action')})
        value.setdefault('saved',True)
        value.setdefault('error',None)
        for mid in notifications:
            with mailbox.saved_result(mid):
                delivery.notify(conn,mailbox.message(conn,mid,actor))
        return value


def start(conn, actor, args, body):
    compatible(actor,caller=True)
    require(args.peer in ('claude','codex','agy','antigravity'),'CAPABILITY_UNSUPPORTED','Unsupported discussion peer')
    peer_kind='antigravity' if args.peer=='agy' else args.peer
    require(peer_kind!=actor['kind'],'CAPABILITY_UNSUPPORTED','Choose the other caller kind or agy as peer')
    peer_surface=_validate_surface(getattr(args,'peer_surface',None))
    if args.peer_session: valid_id(args.peer_session)
    require(not peer_surface or peer_surface!=actor['surface_id'],'CAPABILITY_UNSUPPORTED','Caller cannot be its own peer')
    require(type(args.max_rounds) is int and 1<=args.max_rounds<=10,'INVALID_ARGUMENT','max-rounds must be 1..10')
    input_id=getattr(args,'input_id',None)
    review_mode=getattr(args,'review_mode',None) or ('independent' if input_id else 'discussion')
    if review_mode=='independent':
        require(actor['kind']=='claude' and peer_kind=='codex','CAPABILITY_UNSUPPORTED','Independent intake currently supports a Claude caller and a fresh Codex peer')
        require(input_id,'INPUT_SOURCE_REQUIRED','Use the captured user-input bundle, not a rewritten first question')
        require(body is None and not args.stdin and args.rules is None and args.persona is None,
                'INVALID_ARGUMENT','Independent input cannot accept a body, rules or persona override')
    else:
        require(not input_id,'INVALID_ARGUMENT','Captured input IDs are for independent review')
        require(body and body.strip(),'INVALID_ARGUMENT','A nonempty topic is required')
        require(len(body.encode('utf-8'))<=contracts.BODY_LIMIT,'CONTEXT_TOO_LARGE','Topic exceeds the byte limit')
    semantic={'topic':body,'mode':args.mode,'peer':peer_kind,'peer_session':args.peer_session,'peer_surface':peer_surface,'max_rounds':args.max_rounds,
              'rules':args.rules,'persona':args.persona,'language':args.language}
    if input_id or getattr(args,'review_mode',None):
        semantic.update(input_id=input_id,review_mode=review_mode)
    prior=_operation(conn,actor,'start',args.operation_id,semantic)
    if prior: return _response(conn,actor,prior)
    from .. import intake
    require(review_mode=='independent' or not intake.requires_engine(actor),
            'INPUT_SOURCE_REQUIRED','The current independent-review request must use captured input')
    from ..adapters.registry import terminal
    capabilities=terminal('ghostty').capabilities()
    try:
        capabilities.require('exact_addressing','input_submission')
    except ValueError as exc:
        raise Error('CAPABILITY_UNSUPPORTED','Exact addressing and input submission must be supported') from exc
    if review_mode=='independent':
        bundle=intake.load_bundle(input_id,actor)
        body=bundle['raw_topic']
        snapshot=context.independent_snapshot(bundle,args.mode,args.language)
    else:
        snapshot=context.snapshot(body,args.mode,rules=args.rules,persona=args.persona,language=args.language)
        if review_mode!='discussion':
            snapshot['review_mode']=review_mode
            snapshot['templates']['peer_analysis'] = (
                'Review the supplied proposal as an artifact. Its author positions are part of the proposal; '
                'this is proposal review, not blind alternatives analysis. Return analysis result schema 1.'
                if review_mode=='proposal_review' else
                'Give an additional opinion using the supplied topic and your existing context. '
                'Do not claim a fresh independent conversation. Return analysis result schema 1.')
    snapshot['terminal_capabilities']={'features':dict(capabilities.features),'observed_at':capabilities.observed_at,'evidence':list(capabilities.evidence)}
    with db.transaction(conn):
        mailbox.current_binding(conn,actor)
        prior=_operation(conn,actor,'start',args.operation_id,semantic)
        if prior: result=prior; notifications=[]
        else:
            if input_id:
                existing_inputs=conn.execute('SELECT config_snapshot FROM discussion_runs WHERE caller_session_id=?',
                                             (actor['session_id'],)).fetchall()
                require(not any(json.loads(row['config_snapshot']).get('input_id')==input_id for row in existing_inputs),
                        'RESULT_CONFLICT','This captured input already belongs to a run; reuse its start operation or capture a new user request')
            if review_mode!='independent':
                active_inputs=conn.execute("SELECT config_snapshot FROM discussion_runs WHERE caller_session_id=? AND lifecycle IN ('active','paused')",
                                           (actor['session_id'],)).fetchall()
                require(not any(json.loads(row['config_snapshot']).get('review_mode')=='independent' for row in active_inputs),
                        'RUN_MANAGED_BY_ENGINE','Complete the current independent run instead of sending a separate opinion')
            active=conn.execute("SELECT run_id FROM discussion_runs WHERE caller_session_id=? AND mode='analyze' AND lifecycle IN ('active','paused')",(actor['session_id'],)).fetchone()
            require(args.mode!='analyze' or not active,'RUN_ALREADY_ACTIVE','Caller already has an active analyze run: '+(active['run_id'] if active else ''))
            rid=_id()
            conn.execute('''INSERT INTO discussion_runs(run_id,mode,caller_session_id,requested_peer_kind,requested_peer_session,pending_surface_id,lifecycle,phase,max_rounds,
                         engine_version,protocol_version,prompt_bundle_version,execution_driver,raw_topic,config_snapshot,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,'active','preparing',?,1,3,?,'discussion-v1',?,?,?,?)''',
                         (rid,args.mode,actor['session_id'],peer_kind,args.peer_session,peer_surface,args.max_rounds,snapshot['prompt_bundle_version'],body,_json(snapshot),now(),now()))
            _event(conn,'discussion_started',rid,mode=args.mode)
            notifications=_advance_tx(conn,rid,allow_discovery=review_mode!='independent')
            result={'run_id':rid}
            _record(conn,actor,'start',args.operation_id,semantic,result)
    return _response(conn,actor,result,notifications)


def take(conn, actor, args):
    compatible(actor)
    with db.transaction(conn):
        action,run=store.action(conn,args.id,actor)
        _not_paused(run)
        mailbox.current_binding(conn,actor)
        require(action['status']=='pending','ACTION_NOT_READY','Action already has a result; inspect the report')
        handle=_handle(action,actor)
        if action['kind']=='local_initial':
            require(action['instance_id']==actor['instance_id'] and action['binding_generation']==actor['generation'], 'STALE_ACTION','Explicit run continue --confirm-rebind is required for local action handoff')
        else:
            row=mailbox.message(conn,action['source_message_id'],actor)
            recovery_allowed(conn,row,actor)
            if row['processing_state']=='queued': claim=mailbox.claim(conn,row,actor)
            else:
                require(args.lease_token,'ACTION_NOT_READY','Action was already claimed; use the saved lease or explicit recover')
                mailbox.lease(conn,row,actor,args.lease_token)
                claim={'lease_token':args.lease_token,'claim_version':row['claim_version'],'lease_expires_at':row['lease_expires_at']}
            handle.update({key:claim[key] for key in ('lease_token','claim_version','lease_expires_at')})
        return {'protocol_version':3,'ok':True,'run_id':run['run_id'],'lifecycle':run['lifecycle'],'phase':run['phase'],'round':action['round_no'],
                'saved':action['kind']!='local_initial','error':None,**handle,'input':json.loads(action['input_manifest']),
                'next_action':{'command':'run decide' if action['kind']=='compare' else 'run submit','args':{'action_id':action['action_id']}}}


def _validate_handle(conn, action, actor, args):
    mailbox.current_binding(conn,actor)
    require(args.action_epoch==action['action_epoch'],'STALE_ACTION','Action epoch changed; retrieve its current input')
    require(args.input_digest==action['input_digest'],'INPUT_DIGEST_MISMATCH','Result does not refer to this fixed input')
    if action['kind']=='local_initial':
        require(action['instance_id']==actor['instance_id'] and action['binding_generation']==actor['generation'],'STALE_ACTION','Local action binding changed; explicitly continue after rebind')
    else:
        row=mailbox.message(conn,action['source_message_id'],actor)
        require(args.claim_version==row['claim_version'],'STALE_LEASE','Claim generation differs')
        require(args.binding_generation==actor['generation'],'STALE_BINDING','Submitted binding generation differs')
        mailbox.lease(conn,row,actor,args.lease_token)


def _evidence(conn, run, values):
    for item in values:
        if item['kind']=='message':
            require(conn.execute('SELECT 1 FROM messages WHERE id=? AND run_id=?',(item['value'],run['run_id'])).fetchone(), 'DECISION_INVALID','Evidence message is not part of this run')
        elif item['kind']=='action':
            require(conn.execute('SELECT 1 FROM discussion_actions WHERE action_id=? AND run_id=? AND status=?',(item['value'],run['run_id'],'completed')).fetchone(), 'DECISION_INVALID','Evidence action is not a completed result in this run')


def _semantic_result(payload):
    return {key:value for key,value in payload.items() if key!='summary'}


def submit(conn, actor, args, payload):
    payload=contracts.analysis(payload)
    semantic={'action_id':args.id,'action_epoch':args.action_epoch,'input_digest':args.input_digest,'result':_semantic_result(payload)}
    with db.transaction(conn):
        action,run=store.action(conn,args.id,actor)
        prior=_operation(conn,actor,'submit',args.operation_id,semantic)
        if prior: result=prior; notifications=[]
        else:
            compatible(actor)
            require(action['kind'] in ('local_initial','peer_analysis'),'ACTION_NOT_READY','Compare actions use run decide')
            result_hash=contracts.digest(_semantic_result(payload))
            if action['status']=='completed':
                require(args.input_digest==action['input_digest'],'INPUT_DIGEST_MISMATCH','Result references a different input')
                require(args.action_epoch==action['action_epoch'],'STALE_ACTION','Result references a different action epoch')
                require(action['result_hash']==result_hash,'RESULT_CONFLICT','Action already has a different result')
                result={'run_id':run['run_id'],'action_id':action['action_id'],'result_id':action['result_ref'] or action['action_id']}
                _record(conn,actor,'submit',args.operation_id,semantic,result)
                notifications=[]
            else:
                _active(run)
                _validate_handle(conn,action,actor,args)
                _evidence(conn,run,payload['evidence_refs'])
                notifications=[]
                if action['kind']=='peer_analysis':
                    original=mailbox.message(conn,action['source_message_id'],actor)
                    mid=mailbox.create_reply(conn,actor,original,body=payload['body'],summary=payload['summary'],verdict=payload['verdict'],reason=payload['reason'],confidence=payload['confidence'],token=args.lease_token)
                    conn.execute("UPDATE discussion_actions SET result_ref=?,result_metadata=?,result_hash=?,status='completed' WHERE action_id=?",(mid,_json({k:v for k,v in payload.items() if k not in ('body','summary','verdict','reason','confidence')}),result_hash,action['action_id']))
                    conn.execute('UPDATE discussion_rounds SET peer_reply_id=? WHERE run_id=? AND round_no=?',(mid,run['run_id'],action['round_no']))
                    notifications.append(mid)
                    result_id=mid
                else:
                    conn.execute("UPDATE discussion_actions SET result_json=?,result_hash=?,status='completed' WHERE action_id=?",(_json(payload),result_hash,action['action_id']))
                    result_id=action['action_id']
                _touch(conn,run['run_id'])
                _event(conn,'discussion_result_saved',run['run_id'],action['action_id'])
                notifications.extend(_advance_tx(conn,run['run_id']))
                result={'run_id':run['run_id'],'action_id':action['action_id'],'result_id':result_id}
                _record(conn,actor,'submit',args.operation_id,semantic,result)
    return _response(conn,actor,result,notifications)


def decide(conn, actor, args, payload):
    payload=contracts.decision(payload)
    semantic={'action_id':args.id,'action_epoch':args.action_epoch,'input_digest':args.input_digest,'result':payload}
    with db.transaction(conn):
        action,run=store.action(conn,args.id,actor)
        _caller(conn,run,actor)
        prior=_operation(conn,actor,'decide',args.operation_id,semantic)
        if prior: result=prior; notifications=[]
        else:
            compatible(actor,caller=True)
            require(action['kind']=='compare','ACTION_NOT_READY','Only compare actions accept decisions')
            digest=contracts.digest(payload)
            if action['status']=='completed':
                require(args.input_digest==action['input_digest'],'INPUT_DIGEST_MISMATCH','Decision references a different input')
                require(args.action_epoch==action['action_epoch'],'STALE_ACTION','Decision references a different action epoch')
                previous=json.loads(action['result_json'])
                require(previous['submitted']==payload,'RESULT_CONFLICT','Compare action already has a different decision')
                result={'run_id':run['run_id'],'action_id':action['action_id'],'decision_id':action['action_id']}
                _record(conn,actor,'decide',args.operation_id,semantic,result)
                notifications=[]
            else:
                _not_paused(run)
                require(run['phase']=='comparing' and run['current_round']==action['round_no'],'ACTION_NOT_READY','Compare action is not current')
                _validate_handle(conn,action,actor,args)
                round_row=conn.execute('SELECT * FROM discussion_rounds WHERE run_id=? AND round_no=?',(run['run_id'],run['current_round'])).fetchone()
                require(set(payload['cited_result_ids'])=={round_row['caller_position_ref'],round_row['peer_reply_id']},'DECISION_INVALID','Cite exactly the fixed caller position and current peer reply')
                _evidence(conn,run,payload.get('new_evidence_refs',[]))
                policy=state.applied_decision(payload,run['current_round'],run['max_rounds'])
                capped=policy['override_reason']=='round_limit'
                applied=policy['applied_decision']
                result_payload={**payload,'submitted':payload,'requested_decision':payload['decision'],'applied_decision':applied,'override_reason':'round_limit' if capped else None}
                conn.execute("UPDATE discussion_actions SET result_json=?,result_hash=?,status='completed' WHERE action_id=?",(_json(result_payload),digest,action['action_id']))
                conn.execute('UPDATE discussion_rounds SET closing_decision_ref=? WHERE run_id=? AND round_no=?',(action['action_id'],run['run_id'],run['current_round']))
                reply=mailbox.message(conn,action['source_message_id'],actor)
                notifications=[]
                result={'run_id':run['run_id'],'action_id':action['action_id'],'decision_id':action['action_id']}
                if applied=='continue':
                    peer=_binding(conn,run['peer_session_id']);compatible(peer)
                    next_round=run['current_round']+1
                    manifest=context.render('peer_analysis',json.loads(run['config_snapshot']),next_round,caller_position={'body':payload['caller_position']},followup_body=payload['followup_body'])
                    mid=_id()
                    mailbox.create_request(conn,actor,peer,mid=mid,body=manifest['task_text'],mode=run['mode'],thread_id=run['thread_id'],round_no=next_round,caused_by=reply['id'],owner='discussion-v1',run_id=run['run_id'])
                    mailbox.complete(conn,reply,{'next_request_id':mid})
                    _create_action(conn,run,'peer_analysis',peer,next_round,manifest,mid)
                    conn.execute('INSERT INTO discussion_rounds(run_id,round_no,peer_request_id,caller_position_ref) VALUES(?,?,?,?)',(run['run_id'],next_round,mid,action['action_id']))
                    conn.execute("UPDATE discussion_runs SET phase='collecting',current_round=? WHERE run_id=?",(next_round,run['run_id']))
                    notifications.append(mid); result['message_id']=mid
                else:
                    outcome='round_limit' if capped else payload['requested_outcome']
                    mailbox.complete(conn,reply,{'outcome':outcome,'decision_id':action['action_id']})
                    conn.execute("UPDATE discussion_runs SET phase='finalizing',outcome=? WHERE run_id=?",(outcome,run['run_id']))
                _touch(conn,run['run_id'])
                _event(conn,'discussion_decided',run['run_id'],action['action_id'],applied_decision=applied)
                _record(conn,actor,'decide',args.operation_id,semantic,result)
    # Finalization is deliberately a separate deterministic transaction.
    if not prior:
        with persisted(result['run_id'],result.get('action_id'),'run advance'), db.transaction(conn):
            notifications.extend(_advance_tx(conn,result['run_id']))
    return _response(conn,actor,result,notifications)


def control(conn, actor, args):
    kind=args.run_command
    if kind in ('pause','cancel'):
        require(args.reason.strip(),'INVALID_ARGUMENT','A nonempty reason is required')
    semantic={'run_id':args.id,'reason':getattr(args,'reason',None),'confirm_rebind':getattr(args,'confirm_rebind',False),
              'peer_surface':getattr(args,'peer_surface',None),'peer_session':getattr(args,'peer_session',None)}
    notifications=[]
    with db.transaction(conn):
        run=store.run(conn,args.id,actor)
        _caller(conn,run,actor)
        prior=_operation(conn,actor,kind,args.operation_id,semantic)
        if prior: result=prior
        else:
            compatible(actor,caller=True)
            _active(run)
            if kind=='pause':
                conn.execute("UPDATE discussion_runs SET lifecycle='paused',pause_reason=? WHERE run_id=?",(args.reason,run['run_id']))
            elif kind=='continue':
                selected_surface=_validate_surface(getattr(args,'peer_surface',None))
                selected_session=getattr(args,'peer_session',None)
                if selected_session: valid_id(selected_session)
                if selected_surface or selected_session:
                    require(run['phase']=='preparing' and not run['peer_session_id'],'STATE_CONFLICT','Participants are fixed after preparation')
                    require(not selected_surface or not run['pending_surface_id'] or selected_surface==run['pending_surface_id'],'STATE_CONFLICT','A pending peer surface is already selected')
                    require(not selected_session or not run['requested_peer_session'] or selected_session==run['requested_peer_session'],'STATE_CONFLICT','A logical peer is already selected')
                    require(selected_surface!=actor['surface_id'] and selected_session!=actor['session_id'],'CAPABILITY_UNSUPPORTED','Caller cannot be its own peer')
                    conn.execute('UPDATE discussion_runs SET pending_surface_id=COALESCE(?,pending_surface_id),requested_peer_session=COALESCE(?,requested_peer_session) WHERE run_id=?',(selected_surface,selected_session,run['run_id']))
                local=conn.execute("SELECT * FROM discussion_actions WHERE run_id=? AND kind='local_initial' AND status='pending'",(run['run_id'],)).fetchone()
                if local and (local['instance_id']!=actor['instance_id'] or local['binding_generation']!=actor['generation']):
                    require(args.confirm_rebind,'STALE_ACTION','Explicit --confirm-rebind is required for local action handoff')
                    conn.execute('UPDATE discussion_actions SET instance_id=?,binding_generation=?,action_epoch=action_epoch+1 WHERE action_id=?',(actor['instance_id'],actor['generation'],local['action_id']))
                conn.execute("UPDATE discussion_runs SET lifecycle='active',pause_reason=NULL WHERE run_id=?",(run['run_id'],))
            elif kind=='cancel':
                conn.execute("UPDATE discussion_runs SET lifecycle='cancelled',phase='terminal',terminal_reason=?,outcome='cancelled' WHERE run_id=?",(args.reason,run['run_id']))
                conn.execute("UPDATE discussion_actions SET status='cancelled' WHERE run_id=? AND status='pending'",(run['run_id'],))
                conn.execute("UPDATE messages SET processing_state='cancelled',lease_token_hash=NULL,lease_expires_at=NULL,last_error_code='CANCELLED' WHERE run_id=? AND processing_state IN ('queued','processing','recovery_required')",(run['run_id'],))
                conn.execute("UPDATE threads SET state='closed' WHERE thread_id=?",(run['thread_id'],))
            _touch(conn,run['run_id']);_event(conn,'discussion_'+kind,run['run_id'])
            if kind=='continue': notifications=_advance_tx(conn,run['run_id'])
            result={'run_id':run['run_id'],'process_stopped':False} if kind=='cancel' else {'run_id':run['run_id']}
            _record(conn,actor,kind,args.operation_id,semantic,result)
    return _response(conn,actor,result,notifications)


def read_report(conn, actor, run_id):
    run=store.run(conn,run_id,actor)
    initial=conn.execute("SELECT status FROM discussion_actions WHERE run_id=? AND kind='local_initial'",(run_id,)).fetchone()
    if actor['session_id']==run['caller_session_id'] and run['lifecycle']!='cancelled' and (not initial or initial['status']!='completed' or (run['lifecycle']=='paused' and run['phase']=='collecting')):
        return {**observe(conn,run_id,actor),'redacted':True,'report':None,'reason':'INITIAL_POSITION_REQUIRED'}
    if actor['session_id']==run['peer_session_id'] and run['lifecycle'] not in ('completed','cancelled','failed'):
        own=conn.execute("SELECT status FROM discussion_actions WHERE run_id=? AND kind='peer_analysis' AND round_no=?",(run_id,run['current_round'])).fetchone()
        if own and own['status']!='completed':
            return {**observe(conn,run_id,actor),'redacted':True,'report':None,'reason':'INITIAL_POSITION_REQUIRED'}
    if run['final_report_json']:
        return {**observe(conn,run_id,actor),'report':json.loads(run['final_report_json']),'markdown':run['final_report_markdown']}
    rounds=[dict(x) for x in conn.execute('SELECT * FROM discussion_rounds WHERE run_id=? ORDER BY round_no',(run_id,))]
    actions=[dict(x) for x in conn.execute('SELECT * FROM discussion_actions WHERE run_id=? ORDER BY round_no,created_at',(run_id,))]
    messages={x['id']:dict(x) for x in conn.execute('SELECT * FROM messages WHERE run_id=? ORDER BY seq',(run_id,))}
    return {**observe(conn,run_id,actor),'report':report.build(dict(run),rounds,actions,messages)}


def add_parser(subparsers):
    parser=subparsers.add_parser('run',help='Explicit opt-in discussion engine commands')
    actions=parser.add_subparsers(dest='run_command',required=True)
    start_parser=actions.add_parser('start')
    start_parser.add_argument('peer',choices=('claude','codex','agy','antigravity'))
    start_parser.add_argument('text',nargs='?')
    start_parser.add_argument('--stdin',action='store_true')
    start_parser.add_argument('--operation-id',required=True)
    start_parser.add_argument('--mode',choices=('analyze','ask'),default='analyze')
    start_parser.add_argument('--peer-session')
    start_parser.add_argument('--peer-surface')
    start_parser.add_argument('--input-id')
    start_parser.add_argument('--review-mode',choices=('independent','proposal_review','additional_opinion'))
    start_parser.add_argument('--max-rounds',type=int,default=10)
    for field in ('rules','persona','language'): start_parser.add_argument('--'+field)
    for name in ('next','status','report','advance','pause','continue','cancel','export'):
        command=actions.add_parser(name);command.add_argument('id')
        if name in ('pause','continue','cancel'): command.add_argument('--operation-id',required=True)
        if name in ('pause','cancel'): command.add_argument('--reason',required=True)
        if name=='continue':
            command.add_argument('--confirm-rebind',action='store_true')
            command.add_argument('--peer-surface')
            command.add_argument('--peer-session')
        if name=='report': command.add_argument('--json',action='store_true')
        if name=='export': command.add_argument('--overwrite',action='store_true')
    take_parser=actions.add_parser('take');take_parser.add_argument('id');take_parser.add_argument('--lease-token')
    for name in ('submit','decide'):
        command=actions.add_parser(name);command.add_argument('id')
        command.add_argument('--operation-id',required=True)
        command.add_argument('--action-epoch',required=True,type=int)
        command.add_argument('--input-digest',required=True)
        command.add_argument('--lease-token')
        command.add_argument('--claim-version',type=int)
        command.add_argument('--binding-generation',type=int)
        command.add_argument('--result-stdin',action='store_true',required=True)


def run(args):
    readonly=args.run_command in ('next','status','report','export')
    conn=db.connect(readonly=readonly)
    try:
        actor=sessions.actor(conn)
        if args.run_command=='start':
            require(not (args.stdin and args.text is not None),'INVALID_ARGUMENT','Choose text or --stdin')
            return start(conn,actor,args,sys.stdin.read() if args.stdin else args.text)
        if args.run_command in ('next','status'): return observe(conn,args.id,actor)
        if args.run_command=='take': return take(conn,actor,args)
        if args.run_command in ('submit','decide'):
            payload=contracts.loads(sys.stdin.read(),limit=contracts.DECISION_LIMIT if args.run_command=='decide' else contracts.BODY_LIMIT+contracts.DECISION_LIMIT)
            return globals()[args.run_command](conn,actor,args,payload)
        if args.run_command=='advance':
            with db.transaction(conn):
                parent=store.run(conn,args.id,actor);_caller(conn,parent,actor);compatible(actor,caller=True)
                notifications=_advance_tx(conn,args.id)
            return _response(conn,actor,{'run_id':args.id},notifications)
        if args.run_command in ('pause','continue','cancel'): return control(conn,actor,args)
        value=read_report(conn,actor,args.id)
        if args.run_command=='report': return value
        require(not value.get('redacted'),'INITIAL_POSITION_REQUIRED','Submit your initial analysis before exporting peer results')
        parent=store.run(conn,args.id,actor)
        require(parent['lifecycle'] in ('completed','cancelled','failed'),'ACTION_NOT_READY','Export is available for terminal runs')
        data=value['report']; markdown=parent['final_report_markdown'] or report.markdown(data)
        with persisted(args.id,command='run export'):
            return {**observe(conn,args.id,actor),'export':report.export(db.root()/'exports',args.id,_json(data),markdown,overwrite=args.overwrite)}
    except Error as exc:
        exc.engine=True
        if not hasattr(exc,'run_id'):
            exc.run_id=getattr(args,'id',None) if args.run_command not in ('submit','decide','take') else None
        exc.action_id=getattr(args,'id',None) if args.run_command in ('submit','decide','take') else None
        raise
    finally:
        conn.close()
