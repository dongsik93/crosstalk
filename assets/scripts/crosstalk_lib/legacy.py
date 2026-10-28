"""Conservative adapters for the cmux file protocol and cowork worktrees."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


def verdict(text):
    controls = []
    confidence = 'unknown'
    fence = None
    last = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(('```', '~~~')):
            marker = stripped[:3]
            fence = None if fence == marker else marker if fence is None else fence
            continue
        if fence or line.startswith((' ', '\t', '>')):
            continue
        match = re.fullmatch(r'\[(AGREE|DISAGREE|RESPECT_DISAGREE)(?::\s*(.*))?\]', line)
        conf = re.fullmatch(r'(?:confidence|신뢰도):\s*(high|medium|low|unknown)', line, re.I)
        if match:
            kind, reason = match.groups()
            controls.append((kind, reason or ''))
            last = 'verdict'
        elif conf:
            confidence = conf[1].lower()
        elif stripped:
            last = 'prose'
    result = {'verdict': 'NONE', 'reason': '', 'confidence': confidence}
    if controls and last == 'verdict' and len(set(controls)) == 1:
        kind, reason = controls[-1]
        if (kind == 'AGREE' and not reason) or (kind != 'AGREE' and reason.strip()):
            result.update(verdict=kind, reason=reason)
    return result


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null', *args],
                          check=True, capture_output=True, text=True, timeout=60).stdout.strip()


def safe_path(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Refusing symlink worktree/state path')


def worktrees(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id):
        raise ValueError('Invalid run ID')
    root = Path(os.environ['CROSSTALK_ROOT']).absolute() if 'CROSSTALK_ROOT' in os.environ else Path('/tmp').resolve() / 'crosstalk'
    workroot = root / 'worktrees' / ('run-' + args.run_id)
    records = root / 'worktree-owners' / ('run-' + args.run_id)
    safe_path(workroot)
    safe_path(records)
    repo = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel')).resolve()
    if args.operation == 'start-worktree':
        if args.agent not in ('claude', 'codex', 'antigravity', 'agy'):
            raise ValueError('Invalid agent')
        path = workroot / args.agent
        record = records / (args.agent + '.json')
        safe_path(path)
        safe_path(record)
        if path.exists() or record.exists():
            raise ValueError('Worktree already exists; inspect it before reuse')
        records.mkdir(parents=True, exist_ok=True, mode=0o700)
        workroot.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = dict(path=str(path), repository=str(repo), head=git(repo, 'rev-parse', 'HEAD'),
                    nonce=uuid.uuid4().hex, state='preparing')
        def save():
            temporary = record.with_suffix('.tmp')
            temporary.write_text(json.dumps(info))
            temporary.chmod(0o600)
            temporary.replace(record)
        save()
        git(repo, 'worktree', 'add', '-b', f'cowork/{args.run_id}-{args.agent}', str(path))
        info['state'] = 'active'
        save()
        print(path)
        return
    if not args.confirm_stopped:
        print('retained_active: verify every peer has stopped, then use --confirm-stopped')
        return
    if not workroot.exists():
        print('no worktrees')
        return
    for path in sorted(workroot.iterdir()):
        record = records / (path.name + '.json')
        safe_path(path)
        safe_path(record)
        if not record.is_file():
            print(f'retained_unowned: {path}')
            continue
        info = json.loads(record.read_text())
        if (info.get('path') != str(path) or info.get('repository') != str(repo)
                or not info.get('nonce') or info.get('state') != 'active'):
            print(f'retained_unowned: {path}')
            continue
        registered = git(repo, 'worktree', 'list', '--porcelain').splitlines()
        if f'worktree {path}' not in registered:
            print(f'retained_unowned: {path}')
            continue
        if (git(path, 'rev-parse', 'HEAD') != info['head']
                or git(path, 'status', '--porcelain', '--untracked-files=all', '--ignored')):
            print(f'retained_dirty: {path}')
            continue
        git(repo, 'worktree', 'remove', str(path))
        info['state'] = 'removed'
        record.write_text(json.dumps(info))
        print(f'removed: {path}')


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='operation', required=True)
    extract = commands.add_parser('extract-verdict')
    extract.add_argument('file')
    extract.add_argument('--json', action='store_true')
    start = commands.add_parser('start-worktree')
    start.add_argument('run_id')
    start.add_argument('agent')
    cleanup = commands.add_parser('cleanup-worktrees')
    cleanup.add_argument('run_id')
    cleanup.add_argument('--confirm-stopped', action='store_true')
    args = parser.parse_args()
    if args.operation == 'extract-verdict':
        result = verdict(Path(args.file).read_text())
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            for key, value in result.items():
                print(f'{key}={value}')
    else:
        worktrees(args)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
