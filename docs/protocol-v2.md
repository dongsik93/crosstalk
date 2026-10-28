# Mailbox protocol 2

Runtime 0.11.0, mailbox protocol 2, and SQLite schema 2 are separate version contracts. `crosstalk capabilities --json` reports each, installation health, supported commands and the actual `mailbox_instructions` path. The source checkout is not a claim of successful installed or live integration verification; see [verification](verification-v0.11.md).

All machine-readable command output is JSON on stdout; human diagnostics use stderr. `CROSSTALK_CONFIG_DIR` selects the shared state root. Both participants must use the same root. Ordinary receive/send calls never migrate older data: explicitly run `migrate` using the [upgrade procedure](upgrade-v0.11.md).

## Identity and ownership

`session_id` is a logical participant; `cli_session_id` is an independently observed CLI identity where available; `instance_id` identifies the current execution. `surface_id` is a physical Ghostty delivery address and `generation` is its monotonically increasing binding generation. A CLI session ID does not prove its current pane. Labels, cwd and titles are candidate discovery only. One logical session and one physical pane have at most one active binding each.

Codex requires exact current-invocation surface context on **every** protocol-2 tool call. Its shared tool daemon may omit parent environment, and `CODEX_THREAD_ID` plus a saved bridge binding cannot distinguish the same thread resumed in another live pane. Prefix each invocation (or explicitly export in that same tool shell):

```bash
env CROSSTALK_CONFIG_DIR="<SHARED_CONFIG_ROOT>" CROSSTALK_SURFACE_ID="ghostty:<CURRENT_SELECTED_UUID>" \
  <ABSOLUTE_CROSSTALK_RUNTIME> receive
```

The UUID must come from this execution's targeted launch/handshake or explicit user selection. Do not reconstruct it from a thread cache, kind, cwd, or an old resumed conversation. After restart/resume, reselect and complete the new target handshake before acting; do not reuse an inherited stale surface value. Replace `receive` with the needed send/reply/ack/renew/status command and preserve these same per-call environment arguments. A plain `bridge bind` only updates legacy transport cache and does not satisfy strict Codex identity by itself.

A new participant uses an exact selected/probed surface, a short-lived one-use challenge and a bind executed by that participant. The examples use placeholders; quote real argument values rather than interpolating user text into shell code:

```sh
crosstalk session status
crosstalk session challenge --surface <EXACT_SURFACE> --kind codex
crosstalk session bind --challenge <RETURNED_NONCE> --kind codex --protocol 2
```

`bridge bind <EXACT_SURFACE>` in that CLI records legacy transport cache; it neither replaces the protocol handshake nor proves a later Codex invocation's surface. `session challenge --notify` sends a challenge to the selected pane. Do not report ready until `session status` confirms binding. Existing verified instances may reuse their logical binding only with exact current-invocation surface context. Neither another pane nor a stale nonce may complete the challenge.

For explicit transfer, inspect the intended logical session and generation and obtain the user's authorization. Create `session challenge --surface <NEW_SURFACE> --kind <KIND> --session-id <LOGICAL_ID> --expected-generation <N>`, then execute `session rebind --challenge <NONCE> --kind <KIND> --protocol 2 --confirm-transfer` inside the selected new CLI. With `--notify`, add challenge's `--confirm-transfer` only after that user authorization. A new binding invalidates old claims; it does not change queued logical recipients or supply the old conversation context. Read history before continuing. Unknown CLI identity and changed repository context require explicit confirmation. This is local coordination, not protection against malicious processes owned by the same OS user.

## Message and delivery states

`message_id` (CLI `id`) and body/routing are immutable. `thread_id` is a 1:1 discussion. Requests and replies are different message kinds; both have processing state:

```text
queued -> processing -> completed
             |
             +-> effective recovery_required -> explicit new claim
queued / processing / recovery_required -> cancelled
recovery_required at claim limit -> failed
```

No daemon writes a transition at lease expiry. Read-only status/doctor can report `effective_state=recovery_required` while stored state remains processing. `receive` claims one queued message in integer `seq` FIFO order, never an expired claim. A claim has a private token, `claim_version`, binding generation, expiry and attempt count. The initial policy is 900 seconds and at most three claims including the first. Renew only extends a currently valid claim. Expiry is not permission to run the task again.

Delivery attempts are separate: `not_attempted`, `in_flight`, `submitted`, `failed`, `unknown`, or `suppressed`. Submitted means terminal input submission, not AI receipt or completion. A crash after submission but before recording the result is unknown; inspect/retry the same saved message rather than creating a replacement. Ask replies are saved with callback suppressed. Short terminal operations have bounded waits and execute outside SQLite write transactions.

## Command contracts

| Command | Effect |
| --- | --- |
| `capabilities --json` | Read runtime/protocol/schema and instruction location. |
| `send PEER BODY --id KEY` | Save a request before notification; same ID with changed semantic payload conflicts. |
| `send PEER --stdin --summary TEXT` | Read body as data from stdin; summary is display-only. |
| `send PEER --peer-session ID` | Select a particular verified logical recipient if kind alone is ambiguous. |
| `receive [ID]` | Atomically claim one queued message for this bound recipient. |
| `reply ID --lease-token TOKEN --stdin` | Store at most one reply and complete the request atomically. |
| `ack ID --lease-token TOKEN --outcome OUTCOME --result-stdin` | Persist processing of a reply; outcomes concluded/diverged/unresolved/observed. |
| `send PEER --thread THREAD --after-reply REPLY --lease-token TOKEN --stdin` | Create one follow-up and complete its source reply atomically. |
| `renew ID --lease-token TOKEN` | Extend a valid active claim, never revive expiry. |
| `retry ID` | Resubmit notification, without increasing rounds or claim attempts. |
| `recover ID` | Read-only diagnosis. |
| `recover ID --reclaim --expected-claim-version N --confirm-external-effects` | Authorized reclaim of the same interrupted message with a new token/version. |
| `cancel ID --reason TEXT` | Invalidate a claim/result acceptance; does not terminate external work. |
| `status [ID] --limit N --offset N` | Read processing/delivery state without consuming messages. |
| `history ID --limit N --offset N` | Read a thread in pages without claiming it. |
| `doctor --offline` | Inspect DB/install/recovery state without terminal UI or repairs. |

`receive ID --replay` is deprecated; it does not grant recovery ownership. `resume` is an agent command for a topic saved during failed preparation, not message reclaim. Ten request rounds is the thread maximum. Notification retries and reply reprocessing do not add rounds.

Reply verdicts are explicit `--verdict agree|disagree|respect_disagree|none`, optional `--reason`, and `--confidence high|medium|low|unknown`. Disagreement requires a reason; omitted verdict is none and omitted confidence is unknown. Body markers do not set v2 verdicts. A verdict is a peer position, not the caller's comparison outcome or truth certification. Legacy cmux markers use `extract-verdict FILE --json` and safe JSON field parsing, never eval.

After a reply commit, submitting exactly the same body/verdict/reason/confidence returns the saved reply even if the original lease has expired. A different result conflicts. This confirms a saved result; it does not issue a new claim or repeat notification. Summary keeps its first saved value. Follow-up idempotency likewise returns its saved causal link rather than duplicating a round.

## Errors and guarantees

Errors carry `error.code`, `error.message`, `error.retryable`, `saved`, `message_id` and `next_action`. After saving a request, notification failure reports that saved ID. If the process cannot print at all, use status/history. Exit codes: 0 success, 2 invalid arguments, 3 identity/target, 4 saved with notification unconfirmed, 5 state conflict, 6 schema/protocol/migration, 7 other operation failure. Use `error.code` for the recovery decision.

Typical codes include `AMBIGUOUS_PEER`, `CALLER_UNBOUND`, `BINDING_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `REPLY_CONFLICT`, `LEASE_EXPIRED`, `STALE_LEASE`, `STALE_BINDING`, `NOTIFICATION_UNKNOWN`, `DB_BUSY`, `MIGRATION_REQUIRED`, `PROTOCOL_MISMATCH` and `INSTALLATION_INCOMPLETE`.

Crosstalk preserves requests/replies and rejects stale result commits. It does not guarantee exactly-once file edits, network calls or other external actions. Token hashes and state are local DB data; tokens, bodies and credentials must not appear in default diagnostic events. DB and backups contain plaintext conversation data with private file permissions, not encrypted storage. A rebind or cancellation does not stop an already running AI. [Recovery](recovery.md) describes explicit next steps.
