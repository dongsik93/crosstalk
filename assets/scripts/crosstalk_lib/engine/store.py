"""Discussion persistence; callers own every transaction and commit."""
import json
from ..protocol import Error, require

SCHEMA = '''
CREATE TABLE discussion_runs (
 run_id TEXT PRIMARY KEY, thread_id TEXT UNIQUE REFERENCES threads(thread_id),
 mode TEXT NOT NULL CHECK(mode IN ('analyze','ask')),
 caller_session_id TEXT NOT NULL REFERENCES sessions(session_id), peer_session_id TEXT REFERENCES sessions(session_id),
 requested_peer_kind TEXT NOT NULL CHECK(requested_peer_kind IN ('claude','codex','antigravity')),
 requested_peer_session TEXT, pending_surface_id TEXT, lifecycle TEXT NOT NULL CHECK(lifecycle IN ('active','paused','completed','cancelled','failed')),
 phase TEXT NOT NULL CHECK(phase IN ('preparing','collecting','comparing','finalizing','terminal')),
 current_round INTEGER NOT NULL DEFAULT 0 CHECK(current_round BETWEEN 0 AND 10),
 max_rounds INTEGER NOT NULL CHECK(max_rounds BETWEEN 1 AND 10), revision INTEGER NOT NULL DEFAULT 0,
 engine_version INTEGER NOT NULL, protocol_version INTEGER NOT NULL, prompt_bundle_version INTEGER NOT NULL,
 execution_driver TEXT NOT NULL CHECK(execution_driver='discussion-v1'),
 raw_topic TEXT NOT NULL, config_snapshot TEXT NOT NULL, final_report_json TEXT, final_report_markdown TEXT,
 outcome TEXT, pause_reason TEXT, terminal_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX discussion_active_caller ON discussion_runs(caller_session_id)
 WHERE mode='analyze' AND lifecycle IN ('active','paused');
CREATE TABLE discussion_actions (
 action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES discussion_runs(run_id),
 round_no INTEGER NOT NULL CHECK(round_no BETWEEN 1 AND 10),
 kind TEXT NOT NULL CHECK(kind IN ('local_initial','peer_analysis','compare')),
 actor_session_id TEXT NOT NULL REFERENCES sessions(session_id), instance_id TEXT NOT NULL,
 binding_generation INTEGER NOT NULL, action_epoch INTEGER NOT NULL DEFAULT 1,
 input_manifest TEXT NOT NULL, input_digest TEXT NOT NULL, source_message_id TEXT UNIQUE REFERENCES messages(id),
 result_ref TEXT UNIQUE REFERENCES messages(id), result_json TEXT, result_metadata TEXT, result_hash TEXT,
 status TEXT NOT NULL CHECK(status IN ('pending','completed','cancelled')), created_at TEXT NOT NULL,
 UNIQUE(run_id,round_no,kind,actor_session_id), CHECK(result_ref IS NULL OR result_json IS NULL)
);
CREATE TABLE discussion_rounds (
 run_id TEXT NOT NULL REFERENCES discussion_runs(run_id), round_no INTEGER NOT NULL CHECK(round_no BETWEEN 1 AND 10),
 peer_request_id TEXT NOT NULL UNIQUE REFERENCES messages(id), peer_reply_id TEXT UNIQUE REFERENCES messages(id),
 caller_position_ref TEXT NOT NULL REFERENCES discussion_actions(action_id),
 compare_action_id TEXT UNIQUE REFERENCES discussion_actions(action_id), closing_decision_ref TEXT REFERENCES discussion_actions(action_id),
 PRIMARY KEY(run_id,round_no)
);
CREATE TABLE discussion_operations (
 actor_session_id TEXT NOT NULL REFERENCES sessions(session_id), operation_id TEXT NOT NULL,
 operation_kind TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES discussion_runs(run_id),
 semantic_hash TEXT NOT NULL, response_metadata TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(actor_session_id,operation_kind,operation_id)
);
'''


def run(conn, run_id, actor=None):
    row = conn.execute('SELECT * FROM discussion_runs WHERE run_id=?', (run_id,)).fetchone()
    require(row is not None and (actor is None or actor['session_id'] in (row['caller_session_id'],row['peer_session_id'])),
            'NOT_FOUND', 'Discussion run not found for this participant')
    require(row['engine_version']==1 and row['protocol_version']==3, 'ENGINE_VERSION_UNSUPPORTED', 'This run requires a compatible engine runtime')
    return row


def action(conn, action_id, actor=None):
    row = conn.execute('SELECT * FROM discussion_actions WHERE action_id=?', (action_id,)).fetchone()
    require(row is not None, 'NOT_FOUND', 'Discussion action not found')
    parent = run(conn, row['run_id'], actor)
    if actor is not None:
        require(row['actor_session_id']==actor['session_id'], 'STATE_CONFLICT', 'Only the assigned participant may execute this action')
    return row, parent


def operation(conn, actor, kind, operation_id, semantic_hash):
    row = conn.execute('SELECT * FROM discussion_operations WHERE actor_session_id=? AND operation_kind=? AND operation_id=?',
                       (actor['session_id'],kind,operation_id)).fetchone()
    if row:
        run(conn,row['run_id'],actor)
        require(row['semantic_hash']==semantic_hash, 'IDEMPOTENCY_CONFLICT', 'Operation ID already belongs to different content')
        return json.loads(row['response_metadata'])
    return None
