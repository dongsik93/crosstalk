"""Logical participants and one-use, exact-surface binding challenges."""
from contextlib import closing
import hashlib
import json
import os
import re
import secrets
import shlex
from pathlib import Path
import time
import uuid
from . import db
from .delivery import bridge
from .protocol import KINDS, Error, now, require, valid_id

SURFACE = re.compile(r'ghostty:[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}')
BINDING = 'SELECT b.*,s.kind,s.cli_session_id,s.status FROM bindings b JOIN sessions s ON s.session_id=b.session_id '


def identity():
    raw = bridge('strict-identity')
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise Error('CALLER_UNBOUND', 'Terminal did not provide structured caller identity') from None
    require(isinstance(value,dict) and SURFACE.fullmatch(value.get('surface_id','')), 'CALLER_UNBOUND', 'Mailbox requires an exactly identified Ghostty caller')
    require(value.get('process_id') and value.get('process_start'), 'CALLER_UNBOUND', 'Caller process evidence is missing')
    return value


def surface():
    return identity()['surface_id']


def actor(conn):
    current = identity()
    address = current['surface_id']
    row = conn.execute(BINDING + 'WHERE b.surface_id=? AND b.active=1 AND s.status=?', (address,'ready')).fetchone()
    require(row, 'CALLER_UNBOUND', 'Complete a protocol 2 session binding handshake')
    try:
        evidence = json.loads(row['evidence'])
    except (ValueError, TypeError):
        raise Error('STALE_BINDING', 'Binding has no instance evidence; complete an explicit rebind') from None
    require(all(evidence.get(key)==current.get(key) for key in ('process_id','process_start')),
            'STALE_BINDING', 'Caller instance changed; complete an explicit rebind')
    require(not current.get('kind') or current['kind']==row['kind'], 'STALE_BINDING', 'Executing CLI kind changed; rebind explicitly')
    actual_cli = current.get('cli_session_id') or (os.environ.get('CODEX_THREAD_ID') if row['kind']=='codex' else None)
    require(not actual_cli or not row['cli_session_id'] or actual_cli == row['cli_session_id'],
            'STALE_BINDING', 'CLI session changed; complete an explicit rebind')
    return dict(row)


def peer(conn, kind, caller, session_id=None):
    kind = 'antigravity' if kind=='agy' else kind
    require(kind in KINDS, 'INVALID_ARGUMENT', 'Unknown peer kind')
    query = BINDING + 'WHERE b.active=1 AND s.status=? AND s.kind=? AND b.session_id<>?'
    params = ['ready',kind,caller['session_id']]
    if session_id:
        query += ' AND b.session_id=?'
        params.append(valid_id(session_id))
    rows = conn.execute(query,params).fetchall()
    require(len(rows)==1, 'AMBIGUOUS_PEER', 'Select exactly one verified peer session; labels and working directories do not transfer ownership')
    return dict(rows[0])


def challenge(conn, address, kind, *, session_id=None, expected_generation=0):
    require(SURFACE.fullmatch(address), 'INVALID_ARGUMENT', 'Use an exact Ghostty surface ID')
    require(kind in KINDS, 'INVALID_ARGUMENT', 'Unknown CLI kind')
    require(isinstance(expected_generation,int) and expected_generation>=0, 'INVALID_ARGUMENT', 'Expected generation must be nonnegative')
    if session_id: valid_id(session_id)
    nonce, expires = 'bind_' + secrets.token_urlsafe(32), time.time()+300
    with db.transaction(conn):
        if session_id:
            existing = conn.execute('SELECT * FROM sessions WHERE session_id=?', (session_id,)).fetchone()
            require(existing and existing['kind'] in (kind,'unknown'), 'BINDING_CONFLICT', 'Logical session does not match the selected kind')
            generation = conn.execute('SELECT COALESCE(MAX(generation),0) FROM bindings WHERE session_id=?', (session_id,)).fetchone()[0]
            require(generation==expected_generation, 'STALE_BINDING', 'Binding generation changed')
        else:
            require(expected_generation==0, 'INVALID_ARGUMENT', 'New sessions start at generation zero')
            session_id = uuid.uuid4().hex
            conn.execute('INSERT INTO sessions(session_id,kind,status,created_at) VALUES(?,?,?,?)', (session_id,kind,'unresolved',now()))
        conn.execute('INSERT INTO challenges(nonce_hash,session_id,surface_id,kind,protocol,expected_generation,expires_at) VALUES(?,?,?,?,?,?,?)',
                     (hashlib.sha256(nonce.encode()).hexdigest(),session_id,address,kind,2,expected_generation,expires))
        db.event(conn,'binding_challenge_created',session_id=session_id,generation=expected_generation)
    return {'challenge':nonce,'session_id':session_id,'surface_id':address,'expected_generation':expected_generation,'expires_at':expires,'protocol_version':2}


def bind(conn, nonce, kind, *, protocol=2, cli_session_id=None, confirm_transfer=False):
    require(protocol==2, 'PROTOCOL_MISMATCH', 'Reload protocol 2 instructions before binding')
    require(kind in KINDS, 'INVALID_ARGUMENT', 'Unknown CLI kind')
    current = identity()
    address = current['surface_id']
    require(not current.get('kind') or current['kind']==kind, 'BINDING_CONFLICT', 'Executing CLI kind differs from the challenge')
    digest = hashlib.sha256(nonce.encode()).hexdigest()
    initial = conn.execute('SELECT * FROM challenges WHERE nonce_hash=?', (digest,)).fetchone()
    require(initial, 'BINDING_CONFLICT', 'Unknown binding challenge')
    sid = initial['session_id']
    with db.lock('session-' + valid_id(sid)[:48]), db.transaction(conn):
        request = conn.execute('SELECT * FROM challenges WHERE nonce_hash=?', (digest,)).fetchone()
        require(not request['used'] and request['expires_at']>time.time(), 'BINDING_CONFLICT', 'Challenge is expired or already used')
        require(request['surface_id']==address and request['kind']==kind and request['protocol']==protocol,
                'BINDING_CONFLICT', 'Challenge belongs to a different pane, kind, or protocol')
        previous = conn.execute('SELECT * FROM bindings WHERE session_id=? ORDER BY generation DESC LIMIT 1',(sid,)).fetchone()
        generation = previous['generation'] if previous else 0
        require(generation==request['expected_generation'], 'STALE_BINDING', 'Binding generation changed')
        require(not previous or confirm_transfer, 'BINDING_CONFLICT', 'Existing session requires explicit --confirm-transfer')
        occupant = conn.execute('SELECT session_id FROM bindings WHERE surface_id=? AND active=1', (address,)).fetchone()
        require(not occupant or occupant['session_id']==sid, 'BINDING_CONFLICT', 'Pane already belongs to another logical participant')
        existing = conn.execute('SELECT * FROM sessions WHERE session_id=?',(sid,)).fetchone()
        actual_cli = current.get('cli_session_id') or (os.environ.get('CODEX_THREAD_ID') if kind=='codex' else None)
        require(not cli_session_id or actual_cli==cli_session_id, 'BINDING_CONFLICT', 'CLI session ID must be confirmed by the executing CLI')
        cli_session_id = actual_cli or cli_session_id
        require(not existing['cli_session_id'] or not cli_session_id or existing['cli_session_id']==cli_session_id or confirm_transfer,
                'BINDING_CONFLICT', 'CLI identity changed without explicit transfer')
        instance, timestamp = uuid.uuid4().hex, now()
        conn.execute('UPDATE bindings SET active=0 WHERE session_id=?',(sid,))
        conn.execute('INSERT INTO bindings(session_id,instance_id,backend,surface_id,generation,evidence,bound_at,last_seen_at,active) VALUES(?,?,?,?,?,?,?,?,1)',
                     (sid,instance,'ghostty',address,generation+1,json.dumps({key: current.get(key) for key in ('process_id','process_start')}),timestamp,timestamp))
        conn.execute("UPDATE sessions SET kind=?,cli_session_id=?,status='ready' WHERE session_id=?", (kind,cli_session_id,sid))
        conn.execute('UPDATE challenges SET used=1 WHERE nonce_hash=?',(digest,))
        conn.execute("UPDATE messages SET processing_state='recovery_required',lease_token_hash=NULL,last_error_code='STALE_BINDING' WHERE recipient_session_id=? AND processing_state='processing'",(sid,))
        db.event(conn,'session_bound',session_id=sid,generation=generation+1)
    return {'session_id':sid,'instance_id':instance,'surface_id':address,'binding_generation':generation+1,'generation':generation+1,'protocol_version':2,'ready':True}


def add_parser(subparsers):
    parser = subparsers.add_parser('session',help='Inspect and explicitly bind logical participants')
    actions = parser.add_subparsers(dest='session_command',required=True)
    issue = actions.add_parser('challenge')
    issue.add_argument('--surface',required=True)
    issue.add_argument('--kind',choices=KINDS,required=True)
    issue.add_argument('--session-id')
    issue.add_argument('--expected-generation',type=int,default=0)
    issue.add_argument('--notify',action='store_true')
    issue.add_argument('--confirm-transfer',action='store_true',help='Include the user-authorized transfer in the target binding prompt')
    for action in ('bind','rebind'):
        answer = actions.add_parser(action)
        answer.add_argument('--challenge',required=True)
        answer.add_argument('--kind',choices=KINDS,required=True)
        answer.add_argument('--protocol',type=int,required=True)
        answer.add_argument('--cli-session-id')
        answer.add_argument('--confirm-transfer',action='store_true')
    actions.add_parser('status')


def run(args):
    with closing(db.connect(readonly=args.session_command=='status')) as conn:
        if args.session_command=='status':
            return [dict(row) for row in conn.execute(BINDING + 'WHERE b.active=1 ORDER BY b.session_id')]
        if args.session_command=='challenge':
            result = challenge(conn,args.surface,args.kind,session_id=args.session_id,expected_generation=args.expected_generation)
            if args.notify:
                # Nonce is deliberately sent only to the exact selected pane; never to logs/events.
                scripts = Path(__file__).resolve().parents[1]
                runtime = str(scripts / 'crosstalk')
                bridge_path = os.environ.get('CROSSTALK_BRIDGE',str(scripts / 'crosstalk_bridge.sh'))
                environment = ['env',f'CROSSTALK_CONFIG_DIR={db.root()}',f'CROSSTALK_SURFACE_ID={args.surface}']
                location = shlex.join([*environment,bridge_path,'bind',args.surface])
                capabilities = shlex.join([*environment,runtime,'capabilities','--json'])
                command = [*environment,runtime,'session','bind','--challenge',result['challenge'],'--kind',args.kind,'--protocol','2']
                if args.confirm_transfer: command.append('--confirm-transfer')
                bridge('send',args.surface, f'[Crosstalk] In this CLI, run {location}, then {capabilities}; read mailbox_instructions from that result, then run {shlex.join(command)}. Retain this explicitly selected CROSSTALK_SURFACE_ID for commands in this pane; on resume, select the current pane again rather than inheriting an old address. Do not start a discussion until ready=true.')
            return result
        return bind(conn,args.challenge,args.kind,protocol=args.protocol,cli_session_id=args.cli_session_id,confirm_transfer=args.confirm_transfer)
