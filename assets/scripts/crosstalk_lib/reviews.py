"""Fixed-commit review worktrees; never restore or clean the caller's checkout."""
from contextlib import closing
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid

from . import db
from .protocol import Error, require, valid_id


def add_parser(subparsers):
    parser = subparsers.add_parser('review', help='Prepare and preserve isolated cmux review worktrees')
    commands = parser.add_subparsers(dest='review_command', required=True)
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('pr', nargs='?', type=int)
    prepare_parser.add_argument('--repo', default='.')
    prepare_parser.add_argument('--peer', required=True, choices=['claude', 'codex', 'antigravity', 'agy'])
    prepare_parser.add_argument('--base', help='Local commit, together with --head instead of a PR')
    prepare_parser.add_argument('--head', help='Local commit, together with --base instead of a PR')
    finish_parser = commands.add_parser('finish')
    finish_parser.add_argument('id')
    finish_parser.add_argument('--outcome', choices=['completed', 'failed'], required=True)
    finish_parser.add_argument('--result-stdin', action='store_true', required=True)
    finish_parser.add_argument('--confirm-stopped', action='store_true', required=True,
                               help='Confirm all review peers and commands have stopped using the worktree')
    commands.add_parser('cleanup').add_argument('id')
    status_parser = commands.add_parser('status')
    status_parser.add_argument('id', nargs='?')
    status_parser.add_argument('--limit', type=int, default=50)
    status_parser.add_argument('--offset', type=int, default=0)


def command(argv, *, cwd=None, timeout=60):
    # Git's inherited location overrides would otherwise defeat explicit -C paths.
    env = {key: value for key, value in os.environ.items()
           if key not in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                          'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')}
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        except ProcessLookupError:
            process.communicate()
        raise Error('REVIEW_TIMEOUT', 'Review helper timed out; inspect review status before retrying') from exc
    if process.returncode:
        raise Error('REVIEW_COMMAND_FAILED', stderr.decode('utf-8', 'replace').strip() or 'Review helper failed')
    return stdout


def git(repo, *args, timeout=60):
    return command(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                    '-C', str(repo), *args], timeout=timeout)


def text_git(repo, *args):
    return git(repo, *args).decode('utf-8', 'surrogateescape').removesuffix('\n')


def safe_dir(path):
    return db.secure_path(path, directory=True, create=True)


def write_private(path, content):
    db.secure_path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def paths(run_id):
    valid_id(run_id)
    root = db.root() / 'reviews'
    return root / 'runs' / run_id, root / 'worktrees' / run_id


def row_for(conn, run_id):
    valid_id(run_id)
    row = conn.execute('SELECT * FROM review_runs WHERE run_id=?', (run_id,)).fetchone()
    require(row is not None, 'REVIEW_NOT_FOUND', 'Unknown review run')
    return dict(row)


def set_state(conn, run_id, state, error=None):
    with db.transaction(conn):
        conn.execute('UPDATE review_runs SET state=?,last_error=? WHERE run_id=?', (state, error, run_id))
        db.event(conn, 'review_' + state, run_id=run_id, error_code=error)


def ownership(row):
    run_path, worktree = paths(row['run_id'])
    db.secure_path(run_path)
    owner_file = db.secure_path(run_path / 'owner.json')
    require(owner_file.is_file(), 'WORKTREE_NOT_OWNED', 'Review ownership record is missing')
    try:
        owner = json.loads(owner_file.read_text())
    except (ValueError, OSError) as exc:
        raise Error('WORKTREE_NOT_OWNED', 'Unreadable review ownership record') from exc
    require(row['worktree_path'] == str(worktree) and
            owner.get('worktree_path') == str(worktree) and
            owner.get('owner_nonce') == row['owner_nonce'] and
            owner.get('origin_path') == row['origin_path'] and
            owner.get('head_sha') == row['head_sha'] and
            owner.get('base_sha') == row['base_sha'],
            'WORKTREE_NOT_OWNED', 'Review path, snapshot or ownership nonce does not match')
    # The checkout can contain public source files; only its path must be symlink-free.
    for part in (worktree, *worktree.parents):
        require(not part.is_symlink(), 'WORKTREE_NOT_OWNED', 'Review path traverses a symlink')
    require(worktree.resolve() == worktree, 'WORKTREE_NOT_OWNED', 'Review path is not canonical')
    require(row['artifact_path'] == str(run_path / 'discussion.md'), 'WORKTREE_NOT_OWNED', 'Unexpected artifact path')
    return owner, run_path, worktree


def registered_worktree(row, owner, worktree):
    origin = Path(row['origin_path'])
    common = text_git(origin, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    require(common == owner['common_dir'], 'WORKTREE_NOT_OWNED', 'Origin repository identity changed')
    records = git(origin, 'worktree', 'list', '--porcelain', '-z').split(b'\0\0')
    for record in records:
        fields = dict(field.split(b' ', 1) if b' ' in field else (field, b'')
                      for field in record.split(b'\0') if field)
        if fields.get(b'worktree', b'').decode('utf-8', 'surrogateescape') == str(worktree):
            require(b'detached' in fields and fields.get(b'HEAD', b'').decode() == row['head_sha'],
                    'REVIEW_SHA_MISMATCH', 'Worktree is no longer at the detached review snapshot')
            if worktree.exists():
                require(text_git(worktree, 'rev-parse', '--path-format=absolute', '--git-common-dir') == common,
                        'WORKTREE_NOT_OWNED', 'Worktree belongs to a different repository')
                require(text_git(worktree, 'rev-parse', 'HEAD') == row['head_sha'],
                        'REVIEW_SHA_MISMATCH', 'Review HEAD changed')
            return True
    return False


def public_row(row):
    return {key: value for key, value in row.items() if key != 'owner_nonce'}


def prepare(args):
    require((args.base is None) == (args.head is None), 'INVALID_ARGUMENT', '--base and --head must be paired')
    require(bool(args.pr) != bool(args.base), 'INVALID_ARGUMENT', 'Choose a positive PR number or local --base/--head')
    require(args.pr is None or args.pr > 0, 'INVALID_ARGUMENT', 'PR number must be positive')
    origin = Path(text_git(Path(args.repo).resolve(), 'rev-parse', '--show-toplevel')).resolve()
    common = text_git(origin, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    run_id = uuid.uuid4().hex
    run_path, worktree = paths(run_id)
    with closing(db.connect()) as conn:
        for directory in (db.root() / 'reviews', run_path.parent, run_path, worktree.parent):
            safe_dir(directory)
        require(not worktree.exists(), 'WORKTREE_NOT_OWNED', 'Review path already exists')
        with db.transaction(conn):
            conn.execute('INSERT INTO review_runs(run_id,repository_identity,origin_path,worktree_path,owner_nonce,state,artifact_path) VALUES(?,?,?,?,?,?,?)',
                         (run_id, common, str(origin), str(worktree), uuid.uuid4().hex, 'preparing', str(run_path / 'discussion.md')))
            db.event(conn, 'review_preparing', run_id=run_id)
        try:
            identity = common
            if args.pr:
                remote = text_git(origin, 'remote', 'get-url', 'origin')
                repository = json.loads(command(['gh', 'repo', 'view', remote, '--json', 'nameWithOwner'], cwd=origin))
                identity = repository['nameWithOwner']
                require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', identity),
                        'INVALID_ARGUMENT', 'Invalid GitHub repository identity')
                metadata = json.loads(command(['gh', 'pr', 'view', str(args.pr), '--repo', identity,
                                               '--json', 'baseRefOid,headRefOid'], cwd=origin))
                base, head = metadata['baseRefOid'], metadata['headRefOid']
                for label, sha in (('base', base), ('head', head)):
                    require(re.fullmatch(r'[0-9a-f]{40,64}', sha), 'INVALID_ARGUMENT', 'Invalid PR commit SHA')
                    git(origin, 'fetch', '--no-tags', '--no-write-fetch-head', 'origin',
                        f'{sha}:refs/crosstalk/reviews/{run_id}/{label}', timeout=120)
            else:
                base = text_git(origin, 'rev-parse', '--verify', '--end-of-options', args.base + '^{commit}')
                head = text_git(origin, 'rev-parse', '--verify', '--end-of-options', args.head + '^{commit}')
            merge_base = text_git(origin, 'merge-base', base, head)
            with db.transaction(conn):
                conn.execute('UPDATE review_runs SET repository_identity=?,base_sha=?,head_sha=? WHERE run_id=?',
                             (identity, base, head, run_id))
            row = row_for(conn, run_id)
            owner = dict(row, common_dir=common, merge_base_sha=merge_base, peer=args.peer, pr=args.pr)
            write_private(run_path / 'owner.json', json.dumps(owner, ensure_ascii=False).encode())
            write_private(run_path / 'pr.diff', git(origin, 'diff', '--no-ext-diff', '--no-textconv', merge_base, head, '--'))
            # Disable configured checkout filters; a review must not run repository commands.
            config = git(origin, 'config', '--null', '--list')
            filter_names = set()
            for entry in config.split(b'\0'):
                key = entry.split(b'\n', 1)[0].decode('utf-8', 'replace')
                if key.startswith('filter.') and key.rsplit('.', 1)[-1] in ('smudge', 'process', 'required'):
                    filter_names.add(key.rsplit('.', 1)[0])
            overrides = []
            for name in sorted(filter_names):
                overrides.extend(['-c', name + '.smudge=', '-c', name + '.process=', '-c', name + '.required=false'])
            git(origin, *overrides, 'worktree', 'add', '--detach', str(worktree), head)
            require(registered_worktree(row, owner, worktree), 'WORKTREE_NOT_OWNED', 'Git did not register review worktree')
            set_state(conn, run_id, 'ready')
            return dict(public_row(row_for(conn, run_id)), review_root=str(worktree),
                        merge_base_sha=merge_base, diff_path=str(run_path / 'pr.diff'))
        except BaseException as exc:
            # Preserve both the intended location and any partially created checkout.
            code = getattr(exc, 'code', 'REVIEW_PREPARE_FAILED')
            set_state(conn, run_id, 'failed', code)
            if isinstance(exc, Exception):
                raise Error(code, f'Review prepare failed; inspect review status {run_id}: {exc}', next_action=f'review status {run_id}') from exc
            raise


def finish(args):
    require(args.confirm_stopped, 'STATE_CONFLICT', 'Confirm all review processes have stopped before finishing')
    result = sys.stdin.read()
    require(result.strip(), 'INVALID_ARGUMENT', 'A nonempty review result is required')
    with db.lock('review-' + valid_id(args.id)), closing(db.connect()) as conn:
        row = row_for(conn, args.id)
        owner, run_path, worktree = ownership(row)
        artifact = run_path / 'discussion.md'
        if artifact.exists():
            require(artifact.read_text() == result, 'STATE_CONFLICT', 'Stored review result differs; preserve it before continuing')
            if row['state'] in ('completed', 'failed'):
                require(row['state'] == args.outcome, 'STATE_CONFLICT', 'Review already finished with a different outcome')
                if owner.get('stopped'):
                    return public_row(row)
        require(row['state'] != 'removed', 'STATE_CONFLICT', 'Review worktree was already removed')
        if args.outcome == 'completed':
            require(registered_worktree(row, owner, worktree) and worktree.exists(),
                    'REVIEW_SHA_MISMATCH', 'Cannot complete a review without the fixed snapshot')
        write_private(artifact, result.encode())
        owner['stopped'] = True
        write_private(run_path / 'owner.json', json.dumps(owner, ensure_ascii=False).encode())
        set_state(conn, args.id, args.outcome)
        return public_row(row_for(conn, args.id))


def cleanup(args):
    with db.lock('review-' + valid_id(args.id)), closing(db.connect()) as conn:
        row = row_for(conn, args.id)
        owner, run_path, worktree = ownership(row)
        if row['state'] == 'removed':
            require(not worktree.exists(), 'WORKTREE_NOT_OWNED', 'Removed review path was recreated; it is not owned')
            return dict(public_row(row), cleanup_state='removed')
        if row['state'] not in ('completed', 'failed') or not owner.get('stopped'):
            with db.transaction(conn):
                db.event(conn, 'review_retained_active', run_id=args.id)
            return dict(public_row(row), cleanup_state='retained_active')
        try:
            registered = registered_worktree(row, owner, worktree)
            if not worktree.exists():
                require(not registered, 'WORKTREE_NOT_OWNED', 'Checkout is missing but Git registration remains; inspect manually')
                set_state(conn, args.id, 'removed')
                return dict(public_row(row_for(conn, args.id)), cleanup_state='removed')
            require(registered, 'WORKTREE_NOT_OWNED', 'Review is not registered with Git')
            changes = git(worktree, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignored=matching')
            if changes:
                with db.transaction(conn):
                    db.event(conn, 'review_retained_dirty', run_id=args.id)
                return dict(public_row(row), cleanup_state='retained_dirty',
                            changes=changes.decode('utf-8', 'replace').split('\0'))
            git(row['origin_path'], 'worktree', 'remove', str(worktree))
            set_state(conn, args.id, 'removed')
            return dict(public_row(row_for(conn, args.id)), cleanup_state='removed')
        except Error as exc:
            with db.transaction(conn):
                conn.execute('UPDATE review_runs SET last_error=? WHERE run_id=?', (exc.code, args.id))
                db.event(conn, 'review_cleanup_failed', run_id=args.id, error_code=exc.code)
            raise


def status(args):
    require(args.limit > 0 and args.limit <= 1000 and args.offset >= 0, 'INVALID_ARGUMENT', 'Invalid pagination')
    with closing(db.connect(readonly=True)) as conn:
        rows = [row_for(conn, args.id)] if args.id else [dict(row) for row in conn.execute(
            'SELECT * FROM review_runs ORDER BY rowid DESC LIMIT ? OFFSET ?', (args.limit, args.offset))]
        result = []
        for row in rows:
            item = public_row(row)
            try:
                owner, run_path, worktree = ownership(row)
                item['registered'] = registered_worktree(row, owner, worktree)
                item['review_root'] = str(worktree)
                item['diff_path'] = str(run_path / 'pr.diff')
                item['merge_base_sha'] = owner.get('merge_base_sha')
                item['stopped'] = bool(owner.get('stopped'))
                if item['registered'] and row['state'] == 'preparing':
                    item['next_action'] = 'Verified checkout exists; inspect retained work before continuing or finish --outcome failed --confirm-stopped'
            except Error as exc:
                item['diagnostic'] = exc.code
            result.append(item)
        return {'runs': result, 'limit': args.limit, 'offset': args.offset}


def run(args):
    return {'prepare': prepare, 'finish': finish, 'cleanup': cleanup, 'status': status}[args.review_command](args)
