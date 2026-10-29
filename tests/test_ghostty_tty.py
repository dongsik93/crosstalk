"""Exact caller lookup must not depend on Ghostty reporting working directories."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'assets/scripts/crosstalk_ghostty.sh'
A = '00000000-0000-0000-0000-000000000001'
B = '00000000-0000-0000-0000-000000000002'


class CallerTTYTests(unittest.TestCase):
    def lookup(self, rows, available=True):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CROSSTALK_CONFIG_DIR=str(Path(tmp).resolve()),
                       CROSSTALK_SURFACE_ID='', CODEX_THREAD_ID='',
                       CROSSTALK_STRICT_IDENTITY='1', TEST_ROWS=rows,
                       TEST_AVAILABLE='yes' if available else 'no')
            return subprocess.run(['/bin/bash', '-c', '''
source "$1"
ghostty_caller() { printf '123\tttys001\tfixture\n'; }
ghostty_rpc() {
  case "$1" in
    tty-list) [ "$TEST_AVAILABLE" = yes ] || return 1; printf '%s\n' "$TEST_ROWS" ;;
    exists) return 0 ;;
    *) echo 'unexpected directory/probe call' >&2; return 9 ;;
  esac
}
ghostty_probe() { echo 'probe must not run' >&2; return 8; }
ghostty_self
''', 'tty-test', str(SCRIPT)], env=env, capture_output=True, text=True)

    def test_unique_tty_works_without_directory_or_probe(self):
        result = self.lookup(f'{A}\t/dev/ttys000\n{B}\t/dev/ttys001')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'ghostty:' + B)
        self.assertEqual(result.stderr, '')

    def test_absent_or_ambiguous_tty_never_guesses_or_probes(self):
        for rows in (f'{A}\t/dev/ttys002', f'{A}\t/dev/ttys001\n{B}\t/dev/ttys001'):
            with self.subTest(rows=rows):
                result = self.lookup(rows)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('exactly one', result.stderr)
                self.assertNotIn('probe must not run', result.stderr)
                self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
