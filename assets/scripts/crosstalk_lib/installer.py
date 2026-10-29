"""Resumable user installation; user state and changed files are never deleted."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid


MANIFEST = 'installation.json'
SCRIPTS = ('crosstalk', 'crosstalk_bridge.sh', 'crosstalk_ghostty.sh', 'crosstalk_terminal.sh')
RUNTIME_MODULES = ('__init__', 'cli', 'db', 'delivery', 'doctor', 'installer', 'legacy',
                   'mailbox', 'migrations', 'protocol', 'reviews', 'sessions', 'intake',
                   'engine/__init__', 'engine/contracts', 'engine/state', 'engine/store',
                   'engine/context', 'engine/report', 'engine/service',
                   'adapters/__init__', 'adapters/__main__', 'adapters/contracts', 'adapters/registry',
                   'adapters/cli/__init__', 'adapters/terminal/__init__')
RUNTIME_TEMPLATES = ('local_initial.md', 'peer_analysis.md', 'compare.md')


def _safe(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f'Refusing symlink in installation path: {item}')
    if path.exists() and path.stat().st_uid != os.getuid():
        raise ValueError(f'Installation path belongs to another user: {path}')
    return path


def _json(path, default=None):
    _safe(path)
    if not path.exists():
        return default
    if not path.is_file():
        raise ValueError(f'Expected a regular file: {path}')
    return json.loads(path.read_text())


def _manifest(root):
    value = _json(root / MANIFEST)
    if value is None:
        return None
    fields = ('phase', 'release_path', 'release_version', 'install_id', 'home', 'config_root')
    maps = ('release_files', 'installed_files', 'owned_symlinks')
    if (not isinstance(value, dict) or
            any(not isinstance(value.get(key), str) for key in fields) or
            any(not isinstance(value.get(key), dict) or
                any(not isinstance(k, str) or not isinstance(v, str) for k, v in value[key].items())
                for key in maps) or not isinstance(value.get('backups'), list)):
        raise ValueError('Malformed installation manifest; preserve it and repair the installation')
    if value['phase'] not in ('staging', 'maintenance', 'migrated', 'activated', 'verifying', 'complete', 'uninstalling', 'uninstalled'):
        raise ValueError('Unknown installation phase')
    if Path(value['release_path']).parent != root / 'releases':
        raise ValueError('Invalid release path in installation manifest')
    if any(Path(rel).is_absolute() or '..' in Path(rel).parts for rel in value['release_files']):
        raise ValueError('Invalid release file in installation manifest')
    return value


def _write(path, data, mode=0o600):
    _safe(path)
    _safe(path.parent).mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _save(root, manifest):
    _write(root / MANIFEST, (json.dumps(manifest, indent=2) + '\n').encode())


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _lock(root):
    _safe(root).mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise ValueError('State directory must be private (mode 0700); inspect and correct permissions explicitly')
    path = _safe(root / 'install.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Installation already running; retry after it finishes') from exc
        yield
    finally:
        os.close(fd)


def _invoke(argv, root, home):
    env = dict(os.environ, HOME=str(home), CROSSTALK_CONFIG_DIR=str(root), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=30, umask=0o077)
    if result.returncode:
        raise ValueError(f'Installation check failed ({Path(argv[0]).name}): {result.stderr.strip() or result.stdout.strip()}')
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError('Installation check did not return JSON') from exc


def _sources(source):
    required = ['VERSION', 'assets/scripts/crosstalk', 'assets/scripts/crosstalk_bridge.sh',
                'assets/scripts/crosstalk_ghostty.sh', 'assets/scripts/crosstalk_terminal.sh', 'assets/scripts/crosstalk_lib/__init__.py',
                'assets/scripts/crosstalk_lib/cli.py', 'assets/codex-skills/crosstalk/SKILL.md',
                'assets/codex-skills/crosstalk/mailbox.md', 'assets/codex-skills/crosstalk/discussion.md',
                'assets/codex-skills/crosstalk/independent.md', 'assets/user-commands/crosstalk.md',
                'assets/agy-commands/crosstalk-peer.toml',
                'plugins/crosstalk/hooks/hooks.json', 'plugins/crosstalk/hooks/capture.py']
    required.extend(f'assets/scripts/crosstalk_lib/{name}.py' for name in RUNTIME_MODULES)
    required.extend(f'assets/scripts/crosstalk_lib/engine/templates/{name}' for name in RUNTIME_TEMPLATES)
    for rel in required:
        if not _safe(source / rel).is_file():
            raise ValueError(f'Incomplete release: {rel}')
    paths = [source / 'VERSION']
    for rel in ('assets/scripts', 'assets/codex-skills/crosstalk', 'assets/user-commands',
                'assets/agy-commands', 'assets/rules', 'assets/personas', 'plugins/crosstalk/commands', 'plugins/crosstalk/hooks'):
        for path in sorted((source / rel).rglob('*')):
            _safe(path)
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                paths.append(path)
    for path in paths:
        if path.suffix == '.py' or path.name == 'crosstalk':
            compile(path.read_bytes(), str(path), 'exec')
        elif path.suffix == '.sh':
            subprocess.run(['/bin/bash', '-n', str(path)], check=True, capture_output=True, timeout=10)
    return {str(path.relative_to(source)): _hash(path) for path in paths}


def _check_runtime(executable, root, home):
    report = _invoke([sys.executable, executable, 'doctor', '--offline'], root, home)
    # Pending installation and message notifications do not establish runtime/DB health.
    if not isinstance(report, dict) or report.get('runtime_healthy') is not True:
        raise ValueError('Staged runtime/database diagnosis failed: ' + json.dumps(report, ensure_ascii=False))


def _release_matches(release, files):
    _safe(release)
    for rel, digest in files.items():
        try:
            path = _safe(release / rel)
        except ValueError:
            return False
        if not path.is_file() or _hash(path) != digest:
            return False
        if path.name in SCRIPTS and not path.stat().st_mode & 0o111:
            return False
    return True


def _stage(source, release, files):
    release.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=release.parent))
    try:
        for rel, digest in files.items():
            src = _safe(source / rel)
            content = src.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError('Release source changed during staging')
            _write(staging / rel, content, 0o700 if src.name in SCRIPTS else 0o600)
        if not _release_matches(staging, files):
            raise ValueError('Staged release checksum mismatch')
        os.replace(staging, release)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _active_work(root):
    path = root / 'mailbox.sqlite3'
    if not path.exists():
        return False
    _safe(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(messages)')}
        if 'processing_state' in columns:
            return bool(conn.execute("SELECT 1 FROM messages WHERE processing_state='processing' LIMIT 1").fetchone())
        if 'status' in columns:
            return bool(conn.execute("SELECT 1 FROM messages WHERE status='received' AND reply_to IS NULL LIMIT 1").fetchone())
    return False


def _migration_backup(root):
    path = root / 'mailbox.sqlite3'
    if not path.exists():
        return None
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone():
            return None
        event = conn.execute("SELECT metadata FROM events WHERE event_type='migrated' ORDER BY seq DESC LIMIT 1").fetchone()
        if event:
            backup = Path(json.loads(event[0])['backup_path'])
            if backup.parent != root / 'backups' or not _safe(backup).is_file():
                raise ValueError('Migration backup recorded in DB is unavailable')
            return str(backup)
    return None


def _destination_files(release, home, root):
    result = {home / '.claude/commands/crosstalk.md': release / 'assets/user-commands/crosstalk.md',
              root / 'mailbox.md': release / 'assets/codex-skills/crosstalk/mailbox.md',
              root / 'VERSION': release / 'VERSION'}
    for file in (release / 'assets/codex-skills/crosstalk').rglob('*'):
        if file.is_file():
            result[home / '.codex/skills/crosstalk' / file.relative_to(release / 'assets/codex-skills/crosstalk')] = file
    if (home / '.gemini').exists():
        result[home / '.gemini/commands/crosstalk-peer.toml'] = release / 'assets/agy-commands/crosstalk-peer.toml'
    return result


def _backup(root, manifest, path):
    _safe(path)
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f'Expected a regular installation target: {path}')
    digest = _hash(path)
    key = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    target = root / 'install-backups' / manifest['install_id'] / (key + '-' + digest)
    if not target.exists():
        _write(target, path.read_bytes())
    entry = {'path': str(path), 'backup': str(target), 'checksum': digest}
    if entry not in manifest['backups']:
        manifest['backups'].append(entry)
        _save(root, manifest)


def _put(root, manifest, path, data, mode=0o600):
    _safe(path)
    digest = hashlib.sha256(data).hexdigest()
    if not path.exists() or _hash(path) != digest:
        _backup(root, manifest, path)
        _write(path, data, mode)
    manifest['installed_files'][str(path)] = digest
    _save(root, manifest)


def _pointer(root, release):
    current = root / 'current'
    _safe(current.parent)
    if current.exists() or current.is_symlink():
        if not current.is_symlink() or current.resolve().parent != root / 'releases':
            raise ValueError('Active runtime pointer is not Crosstalk-owned')
    temp = root / ('.current-' + uuid.uuid4().hex)
    try:
        temp.symlink_to(release)
        os.replace(temp, current)
    finally:
        if temp.is_symlink():
            temp.unlink()


def _wrapper(root, script):
    target = root / 'current/assets/scripts' / script
    guard = '' if script == 'crosstalk' else (
        'if [ -f "$CROSSTALK_CONFIG_DIR/maintenance.json" ]; then\n'
        '  echo "Crosstalk installation is incomplete; resume install or run doctor --offline." >&2\n'
        '  exit 6\nfi\n')
    return ('#!/bin/sh\nexport PYTHONDONTWRITEBYTECODE=1\nexport CROSSTALK_CONFIG_DIR="${CROSSTALK_CONFIG_DIR:-' +
            str(root).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`') + '}"\n' + guard +
            'exec ' + shlex.quote(str(target)) + ' "$@"\n').encode()


def inspect(root=None):
    root = Path(root or os.environ.get('CROSSTALK_CONFIG_DIR', Path.home() / '.claude/crosstalk')).absolute()
    manifest = _manifest(root)
    if manifest is None:
        return {'status': 'unmanaged', 'issues': []}
    if manifest['phase'] == 'uninstalled':
        return {'status': 'uninstalled', 'phase': 'uninstalled', 'issues': []}
    issues = []
    if (root / 'maintenance.json').exists() and manifest['phase'] == 'complete':
        issues.append('installation_incomplete')
    if manifest['phase'] not in ('complete', 'uninstalled'):
        issues.append('installation_incomplete')
    current = root / 'current'
    if manifest['phase'] in ('activated', 'verifying', 'complete') and (not current.is_symlink() or current.resolve() != Path(manifest['release_path'])):
        issues.append('runtime_pointer_mismatch')
    for path, digest in manifest.get('installed_files', {}).items():
        file = Path(path)
        if file.is_symlink() or not file.is_file() or _hash(file) != digest:
            issues.append('modified_or_missing:' + path)
    release = Path(manifest['release_path'])
    for rel, digest in manifest['release_files'].items():
        file = release / rel
        if file.is_symlink() or not file.is_file() or _hash(file) != digest:
            issues.append('runtime_modified_or_missing:' + rel)
    return {'status': 'healthy' if not issues else 'incomplete', 'phase': manifest['phase'],
            'issues': issues, 'release_version': manifest['release_version'],
            'mailbox_instructions': str(release / 'assets/codex-skills/crosstalk/mailbox.md')}


def _presets(source, root, language):
    for kind in ('rules', 'personas'):
        for src in (source / 'assets' / kind).rglob('*.md'):
            _safe(src)
            dst = root / kind / src.relative_to(source / 'assets' / kind)
            _safe(dst)
            if not dst.exists():
                _write(dst, src.read_bytes())
    config = _json(root / 'config.json', {})
    if not isinstance(config, dict):
        raise ValueError('Configuration must be a JSON object')
    original = dict(config)
    config.setdefault('language', 'en')
    config.setdefault('active_rules', 'default')
    config.setdefault('active_persona', 'default')
    if language:
        config['language'] = language
    if config != original or not (root / 'config.json').exists():
        _write(root / 'config.json', (json.dumps(config, indent=2) + '\n').encode())


def refresh_presets(source, home=None, language=None):
    source = _safe(Path(source).absolute())
    home = _safe(Path(home or Path.home()).absolute())
    root = _safe(Path(os.environ.get('CROSSTALK_CONFIG_DIR', home / '.claude/crosstalk')).absolute())
    if not (source / 'assets/rules').is_dir() or not (source / 'assets/personas').is_dir():
        raise ValueError('Missing preset source directories')
    with _lock(root):
        _presets(source, root, language)
    return {'presets_refreshed': True, 'config_root': str(root)}


def install(source, home=None, language=None, quiesced=False):
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11 or newer is required')
    source = _safe(Path(source).absolute())
    home = _safe(Path(home or Path.home()).absolute())
    root = _safe(Path(os.environ.get('CROSSTALK_CONFIG_DIR', home / '.claude/crosstalk')).absolute())
    files = _sources(source)
    version = (source / 'VERSION').read_text().strip()
    if not re.fullmatch(r'0\.12\.\d+(?:[-.][A-Za-z0-9]+)*', version):
        raise ValueError('Installer only accepts protocol-3 v0.12 releases; down-migration is unsupported')
    content_id = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    canonical_release = root / 'releases' / f'{version}-{content_id}'
    with _lock(root):
        previous = _manifest(root)
        resume = previous and previous['phase'] not in ('complete', 'uninstalled')
        if resume and (previous['release_files'] != files or previous['release_version'] != version):
            raise ValueError('Resume the exact interrupted release before installing another release')
        if previous and (previous['home'] != str(home) or previous['config_root'] != str(root)):
            raise ValueError('Installation manifest belongs to a different home or state directory')
        if _active_work(root) and not quiesced:
            raise ValueError('Active claims exist. Finish or explicitly stop workers, then install --quiesced')
        if resume:
            manifest = previous
            release = Path(manifest['release_path'])
        else:
            release = (Path(previous['release_path']) if previous and previous['release_files'] == files
                       else canonical_release)
            retained = None
            if release.exists() and not _release_matches(release, files):
                retained = str(release)
                release = root / 'releases' / f'{version}-{content_id}-{uuid.uuid4().hex}'
            manifest = {
                'release_version': version, 'protocol_version': 3, 'schema_version': 3, 'engine_version': 1,
                'release_path': str(release), 'release_files': files,
                'previous_release': previous.get('release_path') if previous else None,
                'install_id': uuid.uuid4().hex, 'phase': 'staging',
                'backups': list(previous.get('backups', [])) if previous else [],
                'installed_files': dict(previous.get('installed_files', {})) if previous else {},
                'owned_symlinks': dict(previous.get('owned_symlinks', {})) if previous else {},
                'migration_backup': None, 'home': str(home), 'config_root': str(root),
                'retained_release': retained}
        # Preflight destination ownership before changing DB or active runtime.
        for path in _destination_files(source, home, root):
            _safe(path)
        for script in SCRIPTS:
            _safe(home / '.claude/scripts' / script)
        local_bin = home / '.local/bin/crosstalk'
        _safe(local_bin.parent)
        if local_bin.is_symlink() and str(local_bin) not in manifest['owned_symlinks']:
            expected_legacy = home / '.claude/scripts/crosstalk'
            if os.readlink(local_bin) != str(expected_legacy):
                raise ValueError('Unrelated crosstalk symlink exists; preserved without changes')
        elif local_bin.exists() and not local_bin.is_symlink():
            raise ValueError('Unrelated crosstalk executable exists; preserved without changes')
        _safe(release)
        # Record the replacement before staging, while the active runtime stays untouched.
        _save(root, manifest)
        if not release.exists():
            _stage(source, release, files)
        if not _release_matches(release, files):
            raise ValueError('Staged release checksum mismatch; preserve it and repair the installation')
        for path, src in _destination_files(release, home, root).items():
            if path.exists() and _hash(path) != _hash(src):
                _backup(root, manifest, path)
        for script in SCRIPTS:
            path = home / '.claude/scripts' / script
            if path.exists() and path.read_bytes() != _wrapper(root, script):
                _backup(root, manifest, path)
        manifest['phase'] = 'maintenance'
        _save(root, manifest)
        _write(root / 'maintenance.json', json.dumps({'release': str(release)}).encode())
        try:
            executable = str(release / 'assets/scripts/crosstalk')
            result = _invoke([sys.executable, executable, 'migrate'], root, home)
            manifest['migration_backup'] = result.get('backup_path', result.get('backup', manifest['migration_backup'])) or _migration_backup(root)
            manifest['phase'] = 'migrated'
            _save(root, manifest)
            capabilities = _invoke([sys.executable, executable, 'capabilities', '--json'], root, home)
            if capabilities.get('protocol_version') != 3 or capabilities.get('runtime_version') != version or capabilities.get('schema_version') != 3 or capabilities.get('engine_version') != 1:
                raise ValueError('Runtime/protocol version mismatch')
            _check_runtime(executable, root, home)
            _pointer(root, release)
            manifest['phase'] = 'activated'
            _save(root, manifest)
            for script in SCRIPTS:
                _put(root, manifest, home / '.claude/scripts' / script, _wrapper(root, script), 0o700)
            for path, src in _destination_files(release, home, root).items():
                _put(root, manifest, path, src.read_bytes())
            local_bin.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            expected = str(home / '.claude/scripts/crosstalk')
            if local_bin.is_symlink():
                if os.readlink(local_bin) != expected:
                    raise ValueError('Owned symlink target changed; refusing overwrite')
            else:
                local_bin.symlink_to(expected)
            manifest['owned_symlinks'][str(local_bin)] = expected
            _save(root, manifest)
            _presets(release, root, language)
            manifest['phase'] = 'verifying'
            _save(root, manifest)
            _check_runtime(executable, root, home)
            # Validate our files independently of doctor's incomplete-install diagnosis.
            health = inspect(root)
            if any(issue != 'installation_incomplete' for issue in health['issues']):
                raise ValueError('Installed file validation failed: ' + ', '.join(health['issues']))
            manifest['phase'] = 'complete'
            _save(root, manifest)
            (root / 'maintenance.json').unlink()
        except BaseException:
            # Migration commits its backup path in events, even if its stdout was lost.
            backup = _migration_backup(root)
            if backup:
                manifest['migration_backup'] = backup
                _save(root, manifest)
            raise
    return {'installed': True, 'release_version': version, 'manifest': str(root / MANIFEST),
            'migration_backup': manifest['migration_backup'], 'backups': manifest['backups'],
            'retained_release': manifest.get('retained_release'),
            'next_action': 'Reload Crosstalk instructions and complete protocol-3 / engine-1 session handshake.'}


def uninstall(home=None):
    home = _safe(Path(home or Path.home()).absolute())
    root = _safe(Path(os.environ.get('CROSSTALK_CONFIG_DIR', home / '.claude/crosstalk')).absolute())
    with _lock(root):
        manifest = _manifest(root)
        if manifest is None:
            raise ValueError('No installation manifest; refusing to guess ownership of legacy files')
        if manifest.get('home') != str(home) or manifest.get('config_root') != str(root):
            raise ValueError('Installation manifest belongs to a different home or state directory')
        if _active_work(root):
            raise ValueError('Active claims exist; finish or cancel work before uninstall')
        manifest['phase'] = 'uninstalling'
        _save(root, manifest)
        _write(root / 'maintenance.json', json.dumps({'action': 'uninstall'}).encode())
        removed, retained = [], []
        for filename, target in manifest['owned_symlinks'].items():
            path = Path(filename)
            if path.parent != home / '.local/bin' or path.name != 'crosstalk':
                raise ValueError('Invalid owned symlink in manifest')
            _safe(path.parent)
            if path.is_symlink() and os.readlink(path) == target:
                path.unlink()
                removed.append(filename)
            elif path.exists() or path.is_symlink():
                retained.append(filename)
        allowed = [home / '.claude/scripts', home / '.claude/commands', home / '.codex/skills/crosstalk', home / '.gemini/commands']
        for filename, digest in manifest['installed_files'].items():
            path = Path(filename)
            if path not in (root / 'mailbox.md', root / 'VERSION') and not any(path.is_relative_to(parent) for parent in allowed):
                raise ValueError('Invalid installed path in manifest')
            _safe(path)
            if path.exists():
                if path.is_file() and _hash(path) == digest:
                    path.unlink()
                    removed.append(filename)
                else:
                    retained.append(filename)
        release = Path(manifest['release_path'])
        if release.parent != root / 'releases':
            raise ValueError('Invalid release path in manifest')
        for rel, digest in manifest['release_files'].items():
            path = release / rel
            if not path.is_relative_to(release) or '..' in Path(rel).parts:
                raise ValueError('Invalid release entry in manifest')
            _safe(path)
            if path.is_file() and _hash(path) == digest:
                path.unlink()
                removed.append(str(path))
            elif path.exists():
                retained.append(str(path))
        current = root / 'current'
        if current.is_symlink() and current.resolve() == release:
            current.unlink()
        manifest['phase'] = 'uninstalled'
        manifest['installed_files'] = {p: h for p, h in manifest['installed_files'].items() if p in retained}
        manifest['owned_symlinks'] = {p: h for p, h in manifest['owned_symlinks'].items() if p in retained}
        _save(root, manifest)
        sentinel = _safe(root / 'maintenance.json')
        if sentinel.exists():
            sentinel.unlink()
    return {'uninstalled': True, 'removed': removed, 'retained_modified': retained,
            'preserved': ['database', 'configuration', 'presets', 'backups', 'logs', 'review worktrees']}


def add_parser(subparsers):
    install_parser = subparsers.add_parser('install', help='Stage, migrate and activate a verified release')
    install_parser.add_argument('--source', required=True)
    install_parser.add_argument('--home')
    install_parser.add_argument('--presets-only', action='store_true')
    install_parser.add_argument('--language', choices=('en', 'ko'))
    install_parser.add_argument('--quiesced', action='store_true', help='Confirm active workers were explicitly stopped')
    remove = subparsers.add_parser('uninstall', help='Remove only manifest-owned unchanged files')
    remove.add_argument('--home')


def run(args):
    if args.command == 'install':
        if args.presets_only:
            return refresh_presets(args.source, args.home, args.language)
        return install(args.source, args.home, args.language, args.quiesced)
    return uninstall(args.home)
