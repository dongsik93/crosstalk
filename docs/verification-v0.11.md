# v0.11 verification record

## Scope of this commit

On 2026-10-29 the user narrowed live acceptance to actual agy ↔ Claude round trips in splits beside the existing Ghostty pane. The user explicitly excluded cmux live testing and requested a short startup message. This record verifies that scope; it does not certify the complete release matrix from the original reliability plan.

## Actual Ghostty results

Environment: macOS 26.5 arm64, Ghostty 1.4.0, Claude Code 2.1.312, local agy CLI, Python 3.14.6. The current source was installed into an isolated test home/state directory. Existing user installation, conversation DB and original pane were preserved. Each peer used that installed runtime and exact test state/surface context.

| Scenario | Result |
| --- | --- |
| Split placement | New peers were split beside the existing Crosstalk pane. The earlier separate test window was discarded after user correction. |
| Startup display | Both native CLI process arguments show `Crosstalk startup check. Read /tmp/ct-startup.<id>.`; no raw handshake or config-path wall in the initial message. |
| Protocol handshake | Claude and antigravity each completed protocol-2 binding with generation 1 and observed foreground process identity. |
| Claude → agy | Request `17+25` was received; agy stored `42`; Claude received it and stored a concluded ack. Request and reply both completed. |
| agy → Claude | Request `9*7` was received; Claude stored `63`; agy received it and stored a concluded ack. Request and reply both completed. |
| agy startup permissions | The initial default-permission attempt waited for approval. Following the user's instruction, the final agy launch used `--auto-approve`, mapping to `--dangerously-skip-permissions`, for that execution only. Global settings were not changed. |

The local run evidence is under `.dsgoal/artifacts/live-agy-claude-short/`: `install.json`, `sessions.json`, `cli-processes.txt`, launch transcripts and `exchange.json`. Only synthetic arithmetic was exchanged. Tokens, credentials and conversation databases are not committed. Native AI responses and completed acknowledgements, rather than terminal submission alone, establish the round trips.

## Automated verification

All 12 `tests/test_*.py` scripts passed on the final implementation before the verification-document update: 123 unittest cases plus the original bridge and mailbox integration scripts. The local transcript is `.dsgoal/artifacts/precommit-tests.txt`.

Coverage includes explicit legacy migration and old-writer rejection; FIFO and reply relations; claim/rebind fencing; saved-result and delivery uncertainty boundaries; original Git-worktree preservation; safe cleanup; literal response/verdict handling; installed-wrapper diagnosis; missing/corrupt runtime repair; preserved DB/config and user files; interrupted staging/activation; and rejection of incomplete or unhealthy replacement runtimes before activation.

The bridge tests also execute the generated launcher for Claude, Codex and agy, checking the short prompt, private startup-file permissions and deletion on success, retention on failure, explicit approval flags and pending-pane reuse. Earlier macOS Python 3.11–3.14 matrix runs are preserved locally but are not a claim that the final bytes ran on Ubuntu or every Python version.

## Remaining release verification

Not certified by this commit: production-home upgrade/reload; installed slash-command/skill entrypoints; four-pane ambiguity; real restart/rebind/recovery; the full Ubuntu/macOS CI matrix; and real cmux callback/deep-review workflows. cmux was deliberately not exercised in this live run, as requested. The CI workflow is configured, not reported as remotely executed.

The earlier [v0.10 Ghostty record](ghostty-verification.md) and direct-source Claude↔Codex exchanges are historical evidence, not substitutes for these remaining checks. This is an unreleased implementation commit with the user-requested live scope verified, not a claim that all original release gates passed.
