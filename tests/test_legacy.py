"""Exercise legacy text as data and conservative cowork cleanup on real Git repos."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'assets/scripts/crosstalk_lib/legacy.py'
spec = importlib.util.spec_from_file_location('legacy', SCRIPT)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


class LegacyTests(unittest.TestCase):
    def test_custom_config_roots_isolate_topics_language_and_presets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            home = root / 'home'
            home.mkdir()
            roots = [root / 'state-a', root / 'state-b']
            bridge = ROOT / 'assets/scripts/crosstalk_bridge.sh'
            def run(state, *args, code=0):
                env = dict(os.environ, HOME=str(home), CROSSTALK_CONFIG_DIR=str(state))
                env.pop('CROSSTALK_CONFIG', None)
                result = subprocess.run(['bash', str(bridge), *args], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stderr)
                return result.stdout.strip()
            for index, state in enumerate(roots):
                run(state, 'pending-save', f'topic-{index}')
                (state / 'config.json').write_text(json.dumps({'language': 'ko' if index == 0 else 'en'}))
            self.assertEqual(run(roots[0], 'pending-load'), 'topic-0')
            self.assertEqual(run(roots[1], 'pending-load'), 'topic-1')
            self.assertEqual(run(roots[0], 'get-language'), 'ko')
            self.assertEqual(run(roots[1], 'get-language'), 'en')
            run(roots[0], 'pending-clear')
            run(roots[0], 'pending-load', code=1)
            self.assertEqual(run(roots[1], 'pending-load'), 'topic-1')
            self.assertEqual((roots[1] / 'pending.json').stat().st_mode & 0o077, 0)
            run(roots[0], 'ensure-presets', 'ko')
            self.assertTrue((roots[0] / 'rules/ko').is_dir())
            self.assertTrue((roots[0] / 'personas/ko').is_dir())
            self.assertFalse((home / '.claude/crosstalk').exists())

    def test_markers_are_control_lines_not_examples(self):
        for text in ('Example [AGREE]', '> [AGREE]', '```\n[AGREE]\n```',
                     '[AGREE]\n[DISAGREE: no]', '[DISAGREE: ]', '[AGREE]\nmore prose'):
            self.assertEqual(legacy.verdict(text)['verdict'], 'NONE', text)
        self.assertEqual(legacy.verdict('analysis\n[AGREE]\nconfidence: high'),
                         dict(verdict='AGREE', reason='', confidence='high'))

    def test_shell_reason_is_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            sentinel = path / 'EXECUTED'
            reason = f'$(touch {sentinel}); `touch {sentinel}` " quote'
            response = path / 'response.md'
            response.write_text(f'[DISAGREE: {reason}]')
            result = subprocess.run(['bash', str(ROOT / 'assets/scripts/crosstalk_bridge.sh'),
                                     'extract-verdict', str(response), '--json'],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)['reason'], reason)
            self.assertFalse(sentinel.exists())

    def test_cowork_preserves_dirty_ignored_commit_and_unowned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return legacy.git(repo, *args)
            git('init')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'user.name', 'Fixture')
            (repo / 'tracked').write_text('original')
            (repo / '.gitignore').write_text('ignored\n')
            git('add', '.')
            git('commit', '-m', 'fixture')
            before = git('rev-parse', 'HEAD')
            (repo / 'tracked').write_text('user staged')
            git('add', 'tracked')
            (repo / 'tracked').write_text('user unstaged')
            index = git('ls-files', '--stage')
            env = dict(os.environ, CROSSTALK_ROOT=str(root / 'state'))
            def run(*args, success=True):
                proc = subprocess.run(['python3', str(SCRIPT), *args], cwd=repo, env=env,
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode == 0, success, proc.stderr)
                return proc.stdout.strip()
            work = Path(run('start-worktree', 'test', 'codex'))
            self.assertIn('retained_active', run('cleanup-worktrees', 'test'))
            (work / 'ignored').write_text('valuable')
            self.assertIn('retained_dirty', run('cleanup-worktrees', 'test', '--confirm-stopped'))
            (work / 'ignored').unlink()
            (work / 'untracked').write_text('valuable')
            self.assertIn('retained_dirty', run('cleanup-worktrees', 'test', '--confirm-stopped'))
            (work / 'untracked').unlink()
            (work / 'tracked').write_text('peer change')
            self.assertIn('retained_dirty', run('cleanup-worktrees', 'test', '--confirm-stopped'))
            legacy.git(work, 'add', 'tracked')
            legacy.git(work, 'commit', '-m', 'peer commit')
            self.assertIn('retained_dirty', run('cleanup-worktrees', 'test', '--confirm-stopped'))
            other = Path(run('start-worktree', 'clean', 'claude'))
            self.assertIn('removed:', run('cleanup-worktrees', 'clean', '--confirm-stopped'))
            self.assertFalse(other.exists())
            old = root / 'state/worktrees/run-old/claude'
            old.mkdir(parents=True)
            (old / 'valuable').write_text('old data')
            self.assertIn('retained_unowned', run('cleanup-worktrees', 'old', '--confirm-stopped'))
            self.assertEqual(git('rev-parse', 'HEAD'), before)
            self.assertEqual(git('ls-files', '--stage'), index)
            self.assertEqual((repo / 'tracked').read_text(), 'user unstaged')
            run('cleanup-worktrees', '../escape', success=False)


if __name__ == '__main__':
    unittest.main()
