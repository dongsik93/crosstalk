"""Check the shared workflow against real CLI parsing and result validators."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/scripts'))
from crosstalk_lib import cli
from crosstalk_lib.engine import contracts

WORKFLOW = ROOT / 'assets/codex-skills/crosstalk/discussion.md'
CLI = ROOT / 'assets/scripts/crosstalk'


def example_args(text):
    replacements = {'<EPOCH>': '1', '<CLAIM_VERSION>': '1', '<GENERATION>': '1'}
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r'<[^>]+>', 'example-id', text)
    return shlex.split(text)


class WorkflowContractTests(unittest.TestCase):
    def test_shared_workflow_command_examples_parse(self):
        parser = cli.parser()
        examples = []
        for block in re.findall(r'```bash\n(.*?)```', WORKFLOW.read_text(), re.S):
            for line in block.replace('\\\n', ' ').splitlines():
                if line.strip().startswith('"$CT" '):
                    command = line.strip().split('<<', 1)[0]
                    args = example_args(command)[1:]
                    parsed = parser.parse_args(args)
                    examples.append((parsed.command, getattr(parsed, 'run_command', None)))
        self.assertIn(('run', 'start'), examples)
        self.assertIn(('run', 'take'), examples)
        self.assertIn(('run', 'submit'), examples)
        self.assertIn(('run', 'decide'), examples)
        self.assertIn(('receive', None), examples)

    def test_documented_payloads_use_actual_result_schema(self):
        payloads = [json.loads(line) for line in WORKFLOW.read_text().splitlines()
                    if line.startswith('{"schema_version":')]
        self.assertEqual(len(payloads), 2)
        analysis, decision = payloads
        self.assertEqual(contracts.analysis(analysis)['verdict'], 'none')
        self.assertEqual(contracts.decision(decision)['requested_outcome'], 'concluded')
        continuation = dict(decision)
        continuation.pop('requested_outcome')
        continuation.update(decision='continue', followup_body='Check this unresolved premise.',
                            continuation_reason='A material premise still needs a response.')
        self.assertEqual(contracts.decision(continuation)['decision'], 'continue')

    def test_documented_control_and_recovery_arguments_parse(self):
        examples = [
            ['run', 'start', 'antigravity', '--operation-id', 'op', '--mode', 'ask', '--stdin',
             '--max-rounds', '1', '--rules', 'none', '--persona', 'none', '--peer-session', 'peer'],
            ['run', 'next', 'run'], ['run', 'status', 'run'], ['run', 'report', 'run', '--json'],
            ['run', 'pause', 'run', '--operation-id', 'pause-op', '--reason', 'user pause'],
            ['run', 'continue', 'run', '--operation-id', 'continue-op', '--confirm-rebind'],
            ['run', 'continue', 'run', '--operation-id', 'prepare-op',
             '--peer-surface', 'ghostty:00000000-0000-0000-0000-000000000002', '--peer-session', 'peer'],
            ['run', 'cancel', 'run', '--operation-id', 'cancel-op', '--reason', 'scope changed'],
            ['run', 'advance', 'run'], ['run', 'export', 'run', '--overwrite'],
            ['run', 'take', 'action', '--lease-token', 'lease_recovered'],
            ['recover', 'message', '--reclaim', '--expected-claim-version', '2', '--confirm-external-effects'],
            ['retry', 'message'], ['renew', 'message', '--lease-token', 'lease_current'],
        ]
        parser = cli.parser()
        for args in examples:
            with self.subTest(args=args):
                parser.parse_args(args)

    def test_setup_and_readiness_have_executable_engine_handshakes(self):
        parser = cli.parser()
        for relative in ('assets/codex-skills/crosstalk/readiness.md',
                         'plugins/crosstalk/commands/setup.md'):
            text = (ROOT / relative).read_text()
            for verb in ('challenge', 'bind'):
                match = re.search(r'session ' + verb + r'[^\n]*--protocol 3 --engine-version 1', text)
                self.assertIsNotNone(match, (relative, verb))
                command = match[0].replace('"$SELF"', 'ghostty:00000000-0000-0000-0000-000000000001')
                command = command.replace('"$KIND"', 'claude').replace('"$NONCE"', 'bind_example')
                args = parser.parse_args(shlex.split(command))
                self.assertEqual((args.protocol, args.engine_version), (3, 1))

    def test_instruction_routes_share_the_canonical_path(self):
        paths = ['assets/user-commands/crosstalk.md', 'assets/agy-commands/crosstalk-peer.toml']
        paths += [f'assets/codex-skills/crosstalk/{name}.md' for name in ('SKILL', 'mailbox', 'readiness', 'analyze', 'ask', 'callback')]
        paths += [f'plugins/crosstalk/commands/{name}.md' for name in ('analyze', 'ask', 'setup', 'launch')]
        for relative in paths:
            with self.subTest(path=relative):
                self.assertIn('discussion_instructions', (ROOT / relative).read_text())
        peer = tomllib.loads((ROOT / 'assets/agy-commands/crosstalk-peer.toml').read_text())
        self.assertIn('peer-only', peer['prompt'])
        self.assertIn('handler=discussion', peer['prompt'])

    def test_help_and_capabilities_are_safe_without_state_or_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve() / 'must-not-be-created'
            env = dict(os.environ, CROSSTALK_CONFIG_DIR=str(state), CROSSTALK_BRIDGE='/missing-test-bridge')
            verbs = ('start', 'next', 'take', 'submit', 'decide', 'advance', 'status',
                     'pause', 'continue', 'cancel', 'report', 'export')
            for verb in verbs:
                result = subprocess.run([sys.executable, str(CLI), 'run', verb, '--help'], cwd='/',
                                        env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, (verb, result.stdout, result.stderr))
            result = subprocess.run([sys.executable, str(CLI), 'capabilities', '--json'], cwd='/',
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            capabilities = json.loads(result.stdout)
            self.assertEqual((capabilities['protocol_version'], capabilities['engine_version']), (3, 1))
            self.assertTrue(capabilities['engine_available'])
            self.assertFalse(capabilities['engine_default'])
            self.assertEqual(Path(capabilities['discussion_instructions']).resolve(), WORKFLOW.resolve())
            self.assertFalse(state.exists())


if __name__ == '__main__':
    unittest.main()
