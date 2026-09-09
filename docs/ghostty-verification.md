# Ghostty integration verification

The original v0.9.0 file-transport checks are recorded below. The v0.10.0 SQLite mailbox checks are in the final section.

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

## v0.10.0 — SQLite mailbox (2026-09-08)

Actual existing Ghostty Codex and Claude panes exchanged requests and replies using the installed `crosstalk send`, `receive`, and `reply` commands. No per-message MD file or bridge ping was used for these checks.

| Direction | Root request ID | Reply marker | Final states |
| --- | --- | --- | --- |
| Codex → Claude → Codex | `mailbox-smoke-codex-20260908` | `MAILBOX_CODEX_TO_CLAUDE_OK` | request replied; reply received |
| Claude → Codex → Claude | `mailbox-smoke-claude-20260908` | `MAILBOX_CLAUDE_TO_CODEX_OK` | request replied; reply received |

Runtime evidence is retained in the local user's `~/.claude/crosstalk/mailbox.sqlite3`. From a participating pane, `crosstalk history <root request ID>` displays the stored messages and receipt timestamps. The database is not committed.

`python3 tests/test_mailbox.py` additionally checks concurrent receipt (one actionable result), explicit replay, stable send IDs, duplicate/conflicting replies, notification failures after durable storage, retries without duplicate inserts, participant-scoped reads, the 10-round cap, muted ask replies, invalid terminal IDs, and SQLite integrity. `python3 tests/test_bridge.py` retains legacy transport coverage.

These tests do not establish unattended recovery from all permission dialogs, pane closure, or interrupted AI computation. The tool records receipt when the AI calls receive; replay after interrupted processing remains explicit.

## v0.10.2 — startup command and PATH (2026-09-09)

A diagnostic Ghostty command inherited a PATH without `/opt/homebrew/bin`; the installed Codex launcher uses `#!/usr/bin/env node` and failed with `env: node: No such file or directory`. This is direct evidence of the missing-runtime path. The printed command alone does not establish how Ghostty grouped the original argv.

The launcher now gives Ghostty `/bin/bash <private-script-path>` instead of a nested `bash -c` program, and passes the caller PATH through surface configuration. The script still waits for its exact terminal ID before starting the CLI.

The regression test executes the generated startup script with fake Claude/Codex launchers whose interpreter is available only on the supplied PATH. It covers paths with spaces and apostrophes, exact binding propagation, acknowledgement, and temporary-file cleanup. The automated regression test opens no Ghostty windows. After the user explicitly requested an adjacent-pane test, the production launcher opened Codex beside the existing caller in the same tab. Codex executed the readiness acknowledgement successfully. The owned test pane was then closed; no additional standalone window was created for this live test.
