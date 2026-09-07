# Ghostty integration verification

Verified locally on 2026-09-08 with Ghostty 1.3.1 on macOS.

## Actual interactive CLI checks

- Started from the existing Codex terminal, without tmux or cmux.
- Native Ghostty right split launched Claude in the repository directory.
- Claude executed the startup acknowledgement before the first task was sent.
- Codex caller → Claude peer → Codex callback: `run-MbfLr2Jq`.
- Claude caller → existing Codex peer → Claude callback: `run-MwNtHkZS`.
- Claude verified the reverse response and wrote `BOTH_DIRECTIONS_OK`.
- The reverse direction reused the same two terminals; it did not launch a second Codex instance.

Local evidence (runtime files are not part of the repository):

- `/tmp/crosstalk/run-MbfLr2Jq/responses/claude-r01.md`: `CODEX_TO_CLAUDE_OK`.
- `/tmp/crosstalk/run-MwNtHkZS/responses/codex-r01.md`: `CLAUDE_TO_CODEX_OK`.
- Both manifests record different moderator kinds and their exact Ghostty terminal IDs.
- `/tmp/crosstalk/run-MbfLr2Jq/reverse-verified.txt`: `BOTH_DIRECTIONS_OK`.

## Repeatable checks

`python3 tests/test_bridge.py` passes with fake terminals. It checks literal Unicode/quote/newline transmission, file-backed triggers, callback routing in both directions independent of the caller environment, closed/invalid terminal rejection, pending startup handling without duplicate launch, and cmux command compatibility.

`bash -n` passes for both bridge scripts; `git diff --check` passes.

## Boundaries

This verifies native Claude launch and two-way transport with the existing Codex instance. It does not establish reliability during every CLI busy/authentication state, test a fresh Codex launch, or exercise the advanced cowork/review workflows. The initial existing-terminal binding requires a unique working directory; ambiguous bindings require an explicit ID. Ghostty 1.3 AppleScript provides input and layout operations but no direct screen-read operation.

## Why file-backed messages remain

Gajae-Code's current managed launch path allocates tmux/psmux sessions (with headless fallback); its own harness accepts messages through SDK `turn.prompt`, checks acknowledgement and agent-start events, and supports idempotency keys. That is a useful model if Crosstalk eventually owns the agent runtime. It is a larger change than connecting existing interactive Claude/Codex CLIs.

Sources inspected:

- [Ghostty AppleScript API](https://ghostty.org/docs/features/applescript)
- [Gajae managed launch](https://github.com/Yeachan-Heo/gajae-code/blob/main/packages/coding-agent/src/gjc-runtime/launch-tmux.ts)
- [Gajae spawn substrate](https://github.com/Yeachan-Heo/gajae-code/blob/main/packages/coding-agent/src/sdk/broker/spawn-substrate.ts)
- [Gajae SDK prompt transport](https://github.com/Yeachan-Heo/gajae-code/blob/main/packages/coding-agent/src/harness-control-plane/sdk-transport.ts)
- [Gajae acceptance checks](https://github.com/Yeachan-Heo/gajae-code/blob/main/packages/coding-agent/src/harness-control-plane/session-transport.ts)
