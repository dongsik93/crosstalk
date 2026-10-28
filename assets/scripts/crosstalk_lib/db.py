"""Short SQLite transactions and restrictive state paths."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time
from .protocol import Error, now, require, valid_id

SCHEMA = '''
CREATE TABLE sessions (
 session_id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('claude','codex','antigravity','unknown')),
 cli_session_id TEXT, status TEXT NOT NULL CHECK(status IN ('unresolved','ready')), created_at TEXT NOT NULL,
 legacy_surface TEXT
);
CREATE TABLE bindings (
 session_id TEXT NOT NULL REFERENCES sessions(session_id), instance_id TEXT NOT NULL,
 backend TEXT NOT NULL CHECK(backend IN ('ghostty','cmux')), surface_id TEXT NOT NULL,
 generation INTEGER NOT NULL CHECK(generation>0), evidence TEXT NOT NULL, bound_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)),
 PRIMARY KEY(session_id,generation)
);
CREATE UNIQUE INDEX binding_session ON bindings(session_id) WHERE active=1;
CREATE UNIQUE INDEX binding_surface ON bindings(backend,surface_id) WHERE active=1;
CREATE TABLE challenges (
 nonce_hash TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(session_id), surface_id TEXT NOT NULL,
 kind TEXT NOT NULL, protocol INTEGER NOT NULL, expected_generation INTEGER NOT NULL,
 expires_at REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0 CHECK(used IN (0,1))
);
CREATE TABLE threads (
 thread_id TEXT PRIMARY KEY, caller_session_id TEXT NOT NULL REFERENCES sessions(session_id),
 peer_session_id TEXT NOT NULL REFERENCES sessions(session_id), mode TEXT NOT NULL CHECK(mode IN ('ask','analyze')),
 max_rounds INTEGER NOT NULL DEFAULT 10 CHECK(max_rounds BETWEEN 1 AND 10),
 state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open','closed'))
);
CREATE TABLE messages (
 seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, thread_id TEXT NOT NULL REFERENCES threads(thread_id),
 kind TEXT NOT NULL CHECK(kind IN ('request','reply')), sender_session_id TEXT NOT NULL REFERENCES sessions(session_id),
 recipient_session_id TEXT NOT NULL REFERENCES sessions(session_id), reply_to TEXT UNIQUE REFERENCES messages(id),
 caused_by_reply_id TEXT UNIQUE REFERENCES messages(id), body TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
 round INTEGER NOT NULL CHECK(round BETWEEN 1 AND 10),
 processing_state TEXT NOT NULL DEFAULT 'queued' CHECK(processing_state IN ('queued','processing','completed','recovery_required','failed','cancelled')),
 created_at TEXT NOT NULL, received_at TEXT, claim_version INTEGER NOT NULL DEFAULT 0,
 lease_token_hash TEXT, lease_expires_at REAL, claim_binding_generation INTEGER, claim_instance_id TEXT,
 attempt_count INTEGER NOT NULL DEFAULT 0, last_error_code TEXT, completed_at TEXT, completion_result TEXT,
 verdict TEXT NOT NULL DEFAULT 'none' CHECK(verdict IN ('agree','disagree','respect_disagree','none')),
 verdict_reason TEXT NOT NULL DEFAULT '', confidence TEXT NOT NULL DEFAULT 'unknown' CHECK(confidence IN ('high','medium','low','unknown')),
 verdict_source TEXT NOT NULL DEFAULT 'none' CHECK(verdict_source IN ('explicit','legacy_marker','none')),
 CHECK((kind='request' AND reply_to IS NULL) OR (kind='reply' AND reply_to IS NOT NULL))
);
CREATE UNIQUE INDEX request_round ON messages(thread_id,round) WHERE kind='request';
CREATE INDEX inbox_v2 ON messages(recipient_session_id,processing_state,seq);
CREATE TABLE delivery_attempts (
 attempt_id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id), target_surface_id TEXT,
 target_binding_generation INTEGER, state TEXT NOT NULL CHECK(state IN ('not_attempted','in_flight','submitted','failed','unknown','suppressed')),
 started_at TEXT NOT NULL, finished_at TEXT, error_code TEXT
);
CREATE TABLE events (
 seq INTEGER PRIMARY KEY, event_type TEXT NOT NULL, message_id TEXT, session_id TEXT,
 metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE review_runs (
 run_id TEXT PRIMARY KEY, repository_identity TEXT, origin_path TEXT, base_sha TEXT, head_sha TEXT,
 worktree_path TEXT, owner_nonce TEXT, state TEXT, artifact_path TEXT, last_error TEXT
);
'''


def root():
    return Path(os.environ.get('CROSSTALK_CONFIG_DIR', Path.home() / '.claude/crosstalk')).absolute()


def secure_path(path, *, directory=False, create=False):
    path = Path(path)
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'UNSAFE_PATH', 'State path must not traverse symlinks')
    if create and directory:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.exists():
        stat = path.stat()
        require(stat.st_uid == os.getuid(), 'UNSAFE_PATH', 'State path belongs to another user')
        require(stat.st_mode & 0o077 == 0, 'UNSAFE_PERMISSIONS', f'User-only permissions required: {path}')
    return path


def schema_version(conn):
    version = conn.execute('PRAGMA user_version').fetchone()[0]
    columns = {row[1] for row in conn.execute('PRAGMA table_info(messages)')}
    if version > 2: raise Error('SCHEMA_TOO_NEW', 'Database schema is newer than this runtime')
    if not columns:
        require(not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall(), 'UNSUPPORTED_SCHEMA', 'Database contains unknown tables')
        return 0
    if 'sender' in columns: return 1
    require(version == 2 and {'seq','sender_session_id','processing_state','lease_token_hash'} <= columns,
            'UNSUPPORTED_SCHEMA', 'Unrecognized database structure')
    for table in ('sessions','bindings','threads','challenges','delivery_attempts','events','review_runs'):
        require(conn.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table',table)).fetchone(), 'UNSUPPORTED_SCHEMA', f'Missing table: {table}')
    return 2


def connect(*, readonly=False, initialize=False):
    state = secure_path(root(), directory=True, create=initialize)
    path = state / 'mailbox.sqlite3'
    secure_path(path)
    if not path.exists() and not initialize:
        raise Error('MIGRATION_REQUIRED', 'No mailbox database; run migrate to initialize it')
    if readonly:
        conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)
    else:
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    version = schema_version(conn)
    if version == 0 and initialize:
        conn.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nPRAGMA user_version=2; COMMIT;')
        os.chmod(path, 0o600)
    elif version != 2:
        conn.close()
        raise Error('MIGRATION_REQUIRED', 'Run migrate explicitly before using protocol 2')
    return conn


@contextmanager
def transaction(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def event(conn, kind, *, message_id=None, session_id=None, **metadata):
    conn.execute('INSERT INTO events(event_type,message_id,session_id,metadata,created_at) VALUES(?,?,?,?,?)',
                 (kind,message_id,session_id,json.dumps(metadata),now()))


@contextmanager
def lock(name, timeout=10):
    valid_id(name)
    directory = secure_path(root() / 'locks', directory=True, create=True)
    path = secure_path(directory / name)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline: raise Error('DB_BUSY', 'Timed out waiting for Crosstalk operation lock')
                time.sleep(0.02)
        yield
    finally:
        os.close(fd)
