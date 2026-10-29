"""Read-only installation and mailbox diagnostics; no terminal or repair actions."""
import sqlite3
from . import db, delivery, installer
from .protocol import Error


def inspect():
    result={'database_exists':(db.root()/'mailbox.sqlite3').exists(),'runtime_healthy':False,'issues':[]}
    try:
        result['installation_health']=installer.inspect(db.root())
        for issue in result['installation_health']['issues']:
            result['issues'].append({'code':'INSTALLATION_INCOMPLETE','detail':issue,
                                     'next_action':'Re-run install from the same verified release to repair the installation'})
        if result['installation_health']['status']=='uninstalled':
            result['issues'].append({'code':'INSTALLATION_INCOMPLETE','detail':'uninstalled',
                                     'next_action':'Install a compatible runtime before starting new mailbox work'})
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        result['installation_health']={'status':'incomplete'}
        result['issues'].append({'code':'INSTALLATION_INCOMPLETE','detail':str(exc),
                                 'next_action':'Inspect the installation manifest and re-run the same release installer'})
    if (db.root()/'maintenance.json').exists() and not any(issue.get('detail')=='installation_incomplete' for issue in result['issues']):
        result['issues'].append({'code':'INSTALLATION_INCOMPLETE','detail':'installation_incomplete',
                                 'next_action':'Resume installation before starting new mailbox work'})
    result['probe_traces']=[str(path) for path in (db.root()/'ghostty').glob('probe-*.json')]
    if not result['database_exists']:
        result['issues'].append({'code':'MIGRATION_REQUIRED','detail':'No mailbox database',
                                 'next_action':'Run migrate explicitly to initialize the mailbox'})
        return result
    try:
        from .mailbox import effective_state
        conn=db.connect(readonly=True)
        try:
            result['schema_version']=2
            result['messages']=[{'id':row['id'],'processing_state':row['processing_state'],'effective_state':effective_state(row),
                                 'attempt_count':row['attempt_count'],'claim_version':row['claim_version'],
                                 'recipient_session_id':row['recipient_session_id'],'lease_expires_at':row['lease_expires_at']}
                                for row in conn.execute("SELECT * FROM messages WHERE processing_state NOT IN ('completed','cancelled') AND NOT (kind='reply' AND run_id IN (SELECT run_id FROM discussion_runs WHERE mode='ask' AND lifecycle='completed')) ORDER BY seq")]
            result['unresolved_sessions']=[dict(row) for row in conn.execute("SELECT session_id,kind,legacy_surface FROM sessions WHERE status='unresolved'")]
            result['delivery']=[delivery.attempt_view(row) for row in conn.execute('''
                SELECT a.*,m.processing_state FROM delivery_attempts a JOIN messages m ON m.id=a.message_id
                WHERE a.rowid=(SELECT MAX(b.rowid) FROM delivery_attempts b WHERE b.message_id=a.message_id)
                ORDER BY a.rowid''')]
            for attempt in result['delivery']:
                if attempt['processing_state']=='queued' and attempt['effective_state'] in ('not_attempted','failed','unknown'):
                    result['issues'].append({'code':attempt['error_code'] or 'NOTIFICATION_PENDING',
                                             'message_id':attempt['message_id'],'delivery_state':attempt['effective_state'],
                                             'next_action':f"Inspect status {attempt['message_id']} and recipient binding, then retry {attempt['message_id']} if appropriate"})
            result['reviews']=[dict(row) for row in conn.execute("SELECT run_id,worktree_path,state,last_error FROM review_runs WHERE state IS NOT NULL AND state!='removed'")]
            result['discussion_runs']=[dict(row) for row in conn.execute('SELECT run_id,mode,lifecycle,phase,current_round,caller_session_id,peer_session_id,outcome FROM discussion_runs ORDER BY created_at')]
            result['runtime_healthy']=True
        finally: conn.close()
    except (Error,sqlite3.Error,OSError) as exc:
        result['runtime_healthy']=False
        result['issues'].append({'code':getattr(exc,'code','DB_ERROR'),'message':str(exc),
                                 'next_action':'Inspect database permissions/schema; use migrate only for a supported upgrade'})
    return result


def add_parser(subparsers):
    parser=subparsers.add_parser('doctor',help='Read-only diagnostics; never launches or retries work')
    parser.add_argument('--offline',action='store_true',help='Do not contact terminal applications')
    parser.add_argument('--json',action='store_true')


def run(args):
    return inspect()
