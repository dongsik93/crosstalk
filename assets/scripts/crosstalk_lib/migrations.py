"""Explicit, backed-up, atomic migration of legacy mailboxes."""
from contextlib import closing
import json
import os
import sqlite3
import uuid
from . import db
from .protocol import Error, now, require


def _execute_schema(conn):
    # executescript commits an existing transaction; execute each DDL statement instead.
    for statement in db.SCHEMA.split(';'):
        if statement.strip(): conn.execute(statement)


def _backup(path, version):
    backup_dir = db.secure_path(path.parent / 'backups', directory=True, create=True)
    backup_path = backup_dir / (f'mailbox-v{version}-' + uuid.uuid4().hex + '.sqlite3')
    fd = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(path, timeout=10)) as reader, closing(sqlite3.connect(backup_path)) as backup:
        reader.backup(backup)
        require(backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok',
                'BACKUP_FAILED', 'Backup integrity check failed')
    return backup_path


def _upgrade_v2(conn, path):
    require(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'DB_CORRUPT', 'Mailbox integrity check failed')
    with db.transaction(conn):
        backup_path = _backup(path, 2)
        original = {}
        for table in ('sessions','bindings','challenges','threads','messages','delivery_attempts','events','review_runs'):
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]
            original[table] = (columns, [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY rowid')])
        for statement in db.ENGINE_SCHEMA.split(';'):
            if statement.strip(): conn.execute(statement)
        additions = {
            'threads': ["execution_owner TEXT NOT NULL DEFAULT 'mailbox-v2' CHECK(execution_owner IN ('mailbox-v2','discussion-v1'))",
                        'run_id TEXT REFERENCES discussion_runs(run_id)'],
            'messages': ['run_id TEXT REFERENCES discussion_runs(run_id)', 'action_id TEXT REFERENCES discussion_actions(action_id)'],
            'bindings': ['protocol_version INTEGER NOT NULL DEFAULT 2 CHECK(protocol_version IN (2,3))',
                         'engine_version INTEGER NOT NULL DEFAULT 0 CHECK(engine_version IN (0,1))'],
            'challenges': ['engine_version INTEGER NOT NULL DEFAULT 0 CHECK(engine_version IN (0,1))'],
        }
        for table, definitions in additions.items():
            for definition in definitions:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {definition}')
        conn.execute('CREATE UNIQUE INDEX thread_run ON threads(run_id) WHERE run_id IS NOT NULL')
        for table, (columns, rows) in original.items():
            projected = ','.join('"' + column.replace('"', '""') + '"' for column in columns)
            require(rows == [tuple(row) for row in conn.execute(f'SELECT {projected} FROM {table} ORDER BY rowid')],
                    'MIGRATION_FAILED', f'Existing {table} data changed during migration')
        require(not conn.execute('PRAGMA foreign_key_check').fetchall(), 'MIGRATION_FAILED', 'Migration foreign key check failed')
        require(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'MIGRATION_FAILED', 'Migration integrity check failed')
        conn.execute('PRAGMA user_version=3')
        count = len(original['messages'][1])
        db.event(conn, 'migrated', backup_path=str(backup_path), message_count=count, from_schema=2, to_schema=3)
    return {'schema_version': 3, 'migrated': True, 'backup_path': str(backup_path), 'message_count': count}



def _legacy_followups(rows):
    requests, replies = {}, {}
    for row in rows:
        if row['reply_to']:
            require(row['reply_to'] not in replies, 'UNSUPPORTED_SCHEMA', 'Legacy request has ambiguous replies')
            replies[row['reply_to']] = row
        else:
            key = (row['thread_id'], row['round'])
            require(key not in requests, 'UNSUPPORTED_SCHEMA', 'Legacy thread has ambiguous request rounds')
            requests[key] = row
    causes, successors = {}, {}
    for (thread_id, round_number), request in requests.items():
        if round_number == 1:
            require(request['id'] == thread_id, 'UNSUPPORTED_SCHEMA', 'Legacy first round is not its thread root')
            continue
        previous = requests.get((thread_id, round_number - 1))
        reply = replies.get(previous['id']) if previous else None
        require(previous and reply and previous['status'] == 'replied'
                and reply['thread_id'] == thread_id and reply['round'] == round_number - 1,
                'UNSUPPORTED_SCHEMA', 'Legacy follow-up has no unambiguous preceding reply')
        require(previous['legacy_seq'] < reply['legacy_seq'] < request['legacy_seq'],
                'UNSUPPORTED_SCHEMA', 'Legacy follow-up order does not establish causality')
        causes[request['id']] = reply['id']
        successors[reply['id']] = request['id']
    return replies, causes, successors


def migrate():
    state = db.secure_path(db.root(), directory=True, create=True)
    path = db.secure_path(state / 'mailbox.sqlite3')
    with db.lock('installation'):
        if not path.exists():
            conn = db.connect(initialize=True)
            conn.close()
            return {'schema_version': 3, 'created': True}
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            version = db.schema_version(conn)
            if version == 3:
                result = {'schema_version': 3, 'migrated': False}
                recorded = conn.execute("SELECT metadata FROM events WHERE event_type='migrated' ORDER BY seq DESC LIMIT 1").fetchone()
                if recorded:
                    metadata = json.loads(recorded['metadata'])
                    result.update(backup_path=metadata['backup_path'], message_count=metadata['message_count'])
                return result
            if version == 2:
                return _upgrade_v2(conn, path)
            if version == 0:
                require(not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone(),
                        'UNSUPPORTED_SCHEMA', 'Refusing to initialize a database containing unknown tables')
                conn.close()
                with closing(db.connect(initialize=True)):
                    pass
                return {'schema_version': 3, 'created': True}
            require(version == 1, 'UNSUPPORTED_SCHEMA', 'Only the legacy mailbox schema can migrate')
            require(conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'DB_CORRUPT', 'Mailbox integrity check failed')
            conn.execute('PRAGMA foreign_keys=OFF')
            with db.transaction(conn):
                # A separate reader snapshots committed data while the writer reservation is held.
                backup_path = _backup(path, 1)
                rows = [dict(row) for row in conn.execute('SELECT rowid AS legacy_seq,* FROM messages ORDER BY rowid')]
                conn.execute('ALTER TABLE messages RENAME TO legacy_messages')
                for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='legacy_messages' AND sql IS NOT NULL").fetchall():
                    conn.execute('DROP INDEX "' + name.replace('"','""') + '"')
                _execute_schema(conn)
                surface_sessions = {}
                for row in rows:
                    for field in ('sender','recipient'):
                        surface = row[field]
                        if surface not in surface_sessions:
                            sid = uuid.uuid4().hex
                            surface_sessions[surface] = sid
                            conn.execute('INSERT INTO sessions(session_id,kind,status,created_at,legacy_surface) VALUES(?,?,?,?,?)', (sid,'unknown','unresolved',now(),surface))
                by_id = {row['id']: row for row in rows}
                for tid in dict.fromkeys(row['thread_id'] for row in rows):
                    original = by_id.get(tid)
                    require(original and not original['reply_to'], 'UNSUPPORTED_SCHEMA', 'Legacy thread has no root request')
                    conn.execute('INSERT INTO threads(thread_id,caller_session_id,peer_session_id,mode) VALUES(?,?,?,?)',
                                 (tid,surface_sessions[original['sender']],surface_sessions[original['recipient']],original['mode']))
                replies, causes, successors = _legacy_followups(rows)
                for row in rows:
                    root = by_id[row['thread_id']]
                    expected_pair = (root['recipient'], root['sender']) if row['reply_to'] else (root['sender'], root['recipient'])
                    require((row['sender'], row['recipient']) == expected_pair and row['mode'] == root['mode'],
                            'UNSUPPORTED_SCHEMA', 'Legacy message does not match its thread participants or mode')
                    kind = 'reply' if row['reply_to'] else 'request'
                    status = ('queued' if row['status']=='pending' else
                              'completed' if kind=='request' and row['status']=='replied' else 'recovery_required')
                    if status == 'completed': require(row['id'] in replies, 'UNSUPPORTED_SCHEMA', 'Completed legacy request lacks a reply')
                    if kind == 'reply':
                        original = by_id.get(row['reply_to'])
                        require(original and not original['reply_to'] and original['status']=='replied' and original['thread_id']==row['thread_id'] and original['round']==row['round']
                                and original['sender']==row['recipient'] and original['recipient']==row['sender'], 'UNSUPPORTED_SCHEMA', 'Legacy reply relation is invalid')
                    completion_result = None
                    completed_at = None
                    if row['id'] in successors:
                        # A stored next request proves this reply was already used to continue the thread.
                        status = 'completed'
                        next_request = by_id[successors[row['id']]]
                        completion_result = json.dumps({'next_request_id': next_request['id']})
                        completed_at = next_request['created_at']
                    elif kind == 'request' and status == 'completed':
                        completion_result = json.dumps({'reply_id': replies[row['id']]['id']})
                        completed_at = replies[row['id']]['created_at']
                    conn.execute('''INSERT INTO messages(seq,id,thread_id,kind,sender_session_id,recipient_session_id,reply_to,
                                 body,summary,round,processing_state,created_at,received_at,verdict_source,
                                 caused_by_reply_id,completion_result,completed_at)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                 (row['legacy_seq'],row['id'],row['thread_id'],kind,surface_sessions[row['sender']],surface_sessions[row['recipient']],
                                  row['reply_to'],row['body'],row.get('summary',''),row['round'],status,row['created_at'],row.get('received_at'),
                                  'legacy_marker' if kind=='reply' and any(marker in row['body'] for marker in ('[AGREE','[DISAGREE','[RESPECT_DISAGREE')) else 'none',
                                  causes.get(row['id']),completion_result,completed_at))
                    conn.execute('INSERT INTO delivery_attempts(attempt_id,message_id,state,started_at,error_code) VALUES(?,?,?,?,?)',
                                 (uuid.uuid4().hex,row['id'],'suppressed' if kind=='reply' and row['mode']=='ask' else 'unknown',now(),None))
                migrated = conn.execute('SELECT * FROM messages ORDER BY seq').fetchall()
                require(len(migrated)==len(rows), 'MIGRATION_FAILED', 'Migration row count differs')
                for old, new in zip(rows,migrated):
                    for field in ('id','thread_id','body','reply_to','created_at'):
                        require(old[field]==new[field], 'MIGRATION_FAILED', 'Migration data mismatch')
                    require(old['legacy_seq']==new['seq'] and old.get('summary','')==new['summary'], 'MIGRATION_FAILED', 'Migration order or summary mismatch')
                conn.execute('DROP TABLE legacy_messages')
                require(not conn.execute('PRAGMA foreign_key_check').fetchall(), 'MIGRATION_FAILED', 'Migration foreign key check failed')
                require(conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok', 'MIGRATION_FAILED', 'Migration integrity check failed')
                conn.execute('PRAGMA user_version=3')
                db.event(conn,'migrated',backup_path=str(backup_path),message_count=len(rows))
            return {'schema_version': 3, 'migrated': True, 'backup_path': str(backup_path), 'message_count': len(rows)}
        finally:
            conn.close()


def add_parser(subparsers):
    subparsers.add_parser('migrate', help='Explicitly initialize or migrate the mailbox with a verified backup')


def run(args):
    return migrate()
