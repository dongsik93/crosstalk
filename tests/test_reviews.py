#!/usr/bin/env python3
"""Real Git worktrees and CLI contracts, with no user repository mutations."""
import argparse
from contextlib import closing, redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'assets/scripts'
sys.path.insert(0, str(SCRIPTS))
from crosstalk_lib import db, reviews
from crosstalk_lib.protocol import Error


class ReviewsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.environment = patch.dict(os.environ, {
            'CROSSTALK_CONFIG_DIR': str(self.root / 'state'),
            'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
            'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid',
        })
        self.environment.start()
        self.git('init', '-q')
        (self.repo / 'tracked').write_text('base\n')
        (self.repo / '.gitignore').write_text('ignored\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').strip()
        (self.repo / 'tracked').write_text('head\n')
        self.git('commit', '-qam', 'head')
        self.head = self.git('rev-parse', 'HEAD').strip()
        # Fixture includes every category that review preparation used to destroy.
        (self.repo / 'tracked').write_text('stash\n')
        self.git('stash', 'push', '-qm', 'existing user stash')
        (self.repo / 'tracked').write_text('staged\n')
        self.git('add', 'tracked')
        (self.repo / 'tracked').write_text('unstaged\n')
        (self.repo / 'untracked').write_text('do not delete\n')
        (self.repo / 'ignored').write_text('also preserve\n')
        with closing(db.connect(initialize=True)):
            pass
        self.before = self.snapshot()

    def tearDown(self):
        self.environment.stop()
        self.tmp.cleanup()

    def git(self, *args, repo=None):
        return subprocess.check_output(['git', '-C', str(repo or self.repo), *args], text=True, stderr=subprocess.PIPE)

    def snapshot(self):
        return {command: self.git(*command) for command in (
            ('rev-parse', 'HEAD'), ('symbolic-ref', 'HEAD'), ('show-ref', '--heads'),
            ('ls-files', '--stage'), ('rev-parse', 'refs/stash'))} | {
                name: (self.repo / name).read_bytes() for name in ('tracked', 'untracked', 'ignored')}

    def parse(self, *args):
        parser = argparse.ArgumentParser()
        reviews.add_parser(parser.add_subparsers(dest='command'))
        return parser.parse_args(['review', *args])

    def prepare(self):
        return reviews.run(self.parse('prepare', '--repo', str(self.repo), '--peer', 'codex',
                                      '--base', self.base, '--head', self.head))

    def finish(self, run, outcome='completed'):
        with patch('sys.stdin', io.StringIO('Reviewed commit: ' + self.head + '\nNo blockers.\n')):
            return reviews.run(self.parse('finish', run['run_id'], '--outcome', outcome,
                                          '--result-stdin', '--confirm-stopped'))

    def cleanup(self, run):
        return reviews.run(self.parse('cleanup', run['run_id']))

    def test_original_preserved_and_cleanup_idempotent(self):
        run = self.prepare()
        worktree = Path(run['review_root'])
        self.assertEqual(self.git('rev-parse', 'HEAD', repo=worktree).strip(), self.head)
        self.assertIn('+head', Path(run['diff_path']).read_text())
        self.assertEqual(self.cleanup(run)['cleanup_state'], 'retained_active')
        self.finish(run)
        self.assertEqual(self.cleanup(run)['cleanup_state'], 'removed')
        self.assertEqual(self.cleanup(run)['cleanup_state'], 'removed')
        self.assertTrue(Path(run['artifact_path']).exists())
        self.assertEqual(self.before, self.snapshot())

    def test_dirty_untracked_ignored_and_staged_preserved(self):
        for category in ('tracked', 'untracked', 'ignored', 'staged'):
            with self.subTest(category=category):
                run = self.prepare()
                worktree = Path(run['review_root'])
                target = worktree / ('tracked' if category == 'staged' else category)
                target.write_text('reviewer material\n')
                if category == 'staged':
                    self.git('add', 'tracked', repo=worktree)
                self.finish(run)
                self.assertEqual(self.cleanup(run)['cleanup_state'], 'retained_dirty')
                self.assertTrue(target.exists())
        self.assertEqual(self.before, self.snapshot())

    def test_new_commit_preserved_even_clean(self):
        run = self.prepare()
        worktree = Path(run['review_root'])
        self.finish(run)
        (worktree / 'tracked').write_text('new commit\n')
        self.git('commit', '-qam', 'new review work', repo=worktree)
        with self.assertRaisesRegex(Error, 'snapshot'):
            self.cleanup(run)
        self.assertTrue(worktree.exists())
        self.assertEqual(self.before, self.snapshot())

    def test_owner_nonce_mismatch(self):
        run = self.prepare()
        self.finish(run)
        owner_path = Path(run['artifact_path']).with_name('owner.json')
        owner = json.loads(owner_path.read_text())
        owner['owner_nonce'] = 'not-owned'
        owner_path.write_text(json.dumps(owner))
        with self.assertRaisesRegex(Error, 'ownership'):
            self.cleanup(run)
        self.assertTrue(Path(run['review_root']).exists())

    def test_symlink_and_path_tampering_refused(self):
        run = self.prepare()
        self.finish(run)
        worktree = Path(run['review_root'])
        moved = worktree.with_name('moved')
        worktree.rename(moved)
        worktree.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(Error, 'symlink'):
            self.cleanup(run)
        self.assertTrue(moved.exists())
        with self.assertRaises(Error):
            reviews.run(self.parse('cleanup', '../repo'))

    def test_missing_owner_and_unknown_run_refused(self):
        run = self.prepare()
        self.finish(run)
        Path(run['artifact_path']).with_name('owner.json').unlink()
        with self.assertRaisesRegex(Error, 'ownership'):
            self.cleanup(run)
        with self.assertRaises(Error):
            reviews.run(self.parse('cleanup', 'unknown'))

    def test_cleanup_failure_preserves_state_and_checkout(self):
        run = self.prepare()
        self.finish(run)
        original = reviews.git
        def fail_remove(repo, *args, **kwargs):
            if args[:2] == ('worktree', 'remove'):
                raise Error('REVIEW_COMMAND_FAILED', 'injected removal failure')
            return original(repo, *args, **kwargs)
        with patch.object(reviews, 'git', fail_remove), self.assertRaises(Error):
            self.cleanup(run)
        self.assertTrue(Path(run['review_root']).exists())
        with closing(db.connect(readonly=True)) as conn:
            row = reviews.row_for(conn, run['run_id'])
            self.assertEqual(row['last_error'], 'REVIEW_COMMAND_FAILED')
            self.assertEqual(row['state'], 'completed')
        self.assertEqual(self.before, self.snapshot())

    def test_failed_finish_resumes_after_artifact_before_stopped_record(self):
        run = self.prepare()
        with closing(db.connect()) as conn:
            reviews.set_state(conn, run['run_id'], 'failed', 'REVIEW_PREPARE_FAILED')
        original_write = reviews.write_private

        def interrupt_owner_write(path, content):
            if path.name == 'owner.json':
                raise OSError('interrupted before stopped confirmation was saved')
            original_write(path, content)

        with patch.object(reviews, 'write_private', interrupt_owner_write), self.assertRaises(OSError):
            self.finish(run, 'failed')
        artifact = Path(run['artifact_path'])
        saved_result = artifact.read_bytes()
        owner_path = artifact.with_name('owner.json')
        self.assertFalse(json.loads(owner_path.read_text()).get('stopped'))
        self.assertEqual(self.cleanup(run)['cleanup_state'], 'retained_active')
        with patch('sys.stdin', io.StringIO('different result')), self.assertRaisesRegex(Error, 'differs'):
            reviews.run(self.parse('finish', run['run_id'], '--outcome', 'failed',
                                  '--result-stdin', '--confirm-stopped'))
        self.assertFalse(json.loads(owner_path.read_text()).get('stopped'))
        self.finish(run, 'failed')
        self.assertEqual(artifact.read_bytes(), saved_result)
        self.assertTrue(json.loads(owner_path.read_text())['stopped'])
        self.assertEqual(self.cleanup(run)['cleanup_state'], 'removed')
        self.assertEqual(self.before, self.snapshot())

    def test_bad_commit_records_failed_run_preserves_origin(self):
        with self.assertRaises(Error):
            reviews.run(self.parse('prepare', '--repo', str(self.repo), '--peer', 'codex',
                                   '--base', self.base, '--head', 'missing-commit'))
        with closing(db.connect(readonly=True)) as conn:
            row = conn.execute('SELECT * FROM review_runs').fetchone()
            self.assertEqual(row['state'], 'failed')
            self.assertIsNotNone(row['worktree_path'])
        self.assertEqual(self.before, self.snapshot())

    def test_process_death_after_creation_is_diagnosable(self):
        script = '''import os, sys
sys.path.insert(0, sys.argv[1])
from crosstalk_lib import reviews
from argparse import Namespace
original=reviews.set_state
def stopped(conn, run_id, state, error=None):
    if state == 'ready': os._exit(91)
    return original(conn, run_id, state, error)
reviews.set_state=stopped
reviews.prepare(Namespace(repo=sys.argv[2], peer='codex', pr=None, base=sys.argv[3], head=sys.argv[4]))
'''
        completed = subprocess.run([sys.executable, '-c', script, str(SCRIPTS), str(self.repo), self.base, self.head])
        self.assertEqual(completed.returncode, 91)
        result = reviews.run(self.parse('status'))['runs'][0]
        self.assertEqual(result['state'], 'preparing')
        self.assertTrue(result['registered'])
        self.assertIn('Verified checkout', result['next_action'])
        self.assertEqual(self.cleanup(result)['cleanup_state'], 'retained_active')
        self.finish(result, 'failed')
        self.assertEqual(self.cleanup(result)['cleanup_state'], 'removed')
        self.assertEqual(self.before, self.snapshot())

    def test_hooks_and_checkout_filters_are_not_run(self):
        marker = self.root / 'hook-ran'
        hook = self.repo / '.git/hooks/post-checkout'
        hook.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        hook.chmod(0o700)
        self.git('config', 'filter.evil.smudge', 'touch ' + str(marker))
        self.git('config', 'filter.evil.required', 'true')
        # Attributes are untracked in the original and must not enter the snapshot.
        (self.repo / '.git/info/attributes').write_text('tracked filter=evil\n')
        run = self.prepare()
        self.assertFalse(marker.exists())
        self.assertEqual((Path(run['review_root']) / 'tracked').read_text(), 'head\n')

    def test_status_is_readonly_and_excludes_nonce(self):
        run = self.prepare()
        state = Path(os.environ['CROSSTALK_CONFIG_DIR']) / 'mailbox.sqlite3'
        before = state.read_bytes()
        result = reviews.run(self.parse('status', run['run_id']))
        self.assertEqual(before, state.read_bytes())
        self.assertNotIn('owner_nonce', json.dumps(result))
        self.assertEqual(result['runs'][0]['head_sha'], self.head)

    def test_cli_help_and_finish_require_stopped_confirmation(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse('finish', 'id', '--outcome', 'completed', '--result-stdin')

    def test_recreated_removed_path_never_deleted(self):
        run = self.prepare()
        self.finish(run)
        self.cleanup(run)
        path = Path(run['review_root'])
        path.mkdir()
        (path / 'valuable').write_text('preserve')
        with self.assertRaisesRegex(Error, 'recreated'):
            self.cleanup(run)
        self.assertTrue((path / 'valuable').exists())

    def test_pr_fetch_uses_fixed_shas_and_dedicated_refs(self):
        remote = self.root / 'remote.git'
        subprocess.check_call(['git', 'clone', '-q', '--bare', str(self.repo), str(remote)])
        self.git('remote', 'add', 'origin', str(remote))
        binary = self.root / 'bin'
        binary.mkdir()
        gh = binary / 'gh'
        gh.write_text('#!' + sys.executable + '\nimport json,sys\n'
                      + 'print(json.dumps(' + repr({'nameWithOwner': 'example/repository'})
                      + ' if sys.argv[1] == "repo" else '
                      + repr({'baseRefOid': self.base, 'headRefOid': self.head}) + '))\n')
        gh.chmod(0o700)
        with patch.dict(os.environ, {'PATH': str(binary) + os.pathsep + os.environ['PATH']}):
            run = reviews.run(self.parse('prepare', '42', '--repo', str(self.repo), '--peer', 'codex'))
        self.assertEqual(run['head_sha'], self.head)
        self.assertEqual(run['repository_identity'], 'example/repository')
        self.assertEqual(self.git('rev-parse', 'refs/crosstalk/reviews/' + run['run_id'] + '/head').strip(), self.head)
        self.assertFalse((self.repo / '.git/FETCH_HEAD').exists())
        # Even after a new commit exists remotely, the review stays on its recorded object.
        self.git('update-ref', 'refs/heads/moved-remote', self.base, repo=remote)
        self.assertEqual(self.git('rev-parse', 'HEAD', repo=Path(run['review_root'])).strip(), self.head)
        self.assertEqual(self.before, self.snapshot())

    def test_real_cli_prepare_finish_cleanup(self):
        def cli(*args, text=None):
            process = subprocess.run([str(SCRIPTS / 'crosstalk'), 'review', *args], input=text,
                                     text=True, capture_output=True,
                                     env=dict(os.environ, CROSSTALK_BRIDGE='/nonexistent-unused-bridge'))
            self.assertEqual(process.returncode, 0, (process.stdout, process.stderr))
            return json.loads(process.stdout)
        run = cli('prepare', '--repo', str(self.repo), '--peer', 'codex', '--base', self.base, '--head', self.head)
        self.assertEqual(cli('status', run['run_id'])['runs'][0]['head_sha'], self.head)
        cli('finish', run['run_id'], '--outcome', 'completed', '--confirm-stopped', '--result-stdin',
            text='reviewed_commit=' + self.head + '\nComplete review response.\n')
        self.assertEqual(cli('cleanup', run['run_id'])['cleanup_state'], 'removed')
        self.assertEqual(self.before, self.snapshot())

    def test_timeout_is_bounded(self):
        with self.assertRaisesRegex(Error, 'timed out'):
            reviews.command([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=0.05)


if __name__ == '__main__':
    unittest.main()
