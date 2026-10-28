"""Static release and instruction contracts; no user state or terminal access."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/scripts'))


class ReleaseContractTests(unittest.TestCase):
    def test_versions_match(self):
        from crosstalk_lib import RUNTIME_VERSION
        version = (ROOT / 'VERSION').read_text().strip()
        self.assertEqual(RUNTIME_VERSION, version)
        marketplace = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text())
        plugin = json.loads((ROOT / 'plugins/crosstalk/.claude-plugin/plugin.json').read_text())
        self.assertEqual(marketplace['metadata']['version'], version)
        self.assertEqual(marketplace['plugins'][0]['version'], version)
        self.assertEqual(plugin['version'], version)

    def test_command_help_is_available_without_binding(self):
        for command in ('capabilities', 'send', 'receive', 'reply', 'ack', 'renew', 'retry',
                        'recover', 'cancel', 'session', 'status', 'history', 'doctor',
                        'review', 'migrate'):
            result = subprocess.run([sys.executable, str(ROOT / 'assets/scripts/crosstalk'),
                                     command, '--help'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, (command, result.stderr))

    def test_no_response_eval_or_destructive_review_instructions(self):
        analyze = (ROOT / 'plugins/crosstalk/commands/analyze.md').read_text()
        self.assertNotIn('eval ', analyze)
        review = (ROOT / 'plugins/crosstalk/commands/review.md').read_text()
        for command in ('git stash push', 'git stash pop', 'gh pr checkout', 'git reset --hard'):
            self.assertNotIn(command, review)
        self.assertNotIn('worktree remove --force',
                         (ROOT / 'assets/scripts/crosstalk_bridge.sh').read_text())


if __name__ == '__main__':
    unittest.main()
