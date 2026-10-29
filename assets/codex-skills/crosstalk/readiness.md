# Crosstalk v0.12.1 readiness

For status/empty invocation, inspect only. Do not launch, label, challenge, bind, receive, retry or recover merely to display state.

```bash
CT="$HOME/.claude/scripts/crosstalk"
BRIDGE="$HOME/.claude/scripts/crosstalk_bridge.sh"
CONFIG_ROOT="${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}"
"$CT" capabilities --json
"$CT" doctor --offline
"$BRIDGE" backend
```

On Ghostty require runtime protocol 3, supported schema and a healthy installation. For an engine run require engine 1 and read `discussion_instructions`; ordinary `mailbox-v2` threads use `mailbox_instructions`. General engine creation remains explicit opt-in until the live gates pass. A natural independent-review request to Claude is the separate automatic protected route: read `independent_instructions` first and use its fresh-input-bound launch, rather than reusing an existing peer. A schema migration or partial installation is an explicit upgrade task, not a side effect of readiness. Use the same `CROSSTALK_CONFIG_DIR` in both participants. On cmux retain the existing launch/setup and RUN_ID file/ping flows.

## Bind the Ghostty caller

Use `bridge strict-self`, which accepts exact caller evidence and refuses label/cwd fallback. Claude/agy first match their exact TTY to Ghostty’s TTY enumeration; an older API may need the OSC 7 compatibility probe. A successful enumeration with zero or multiple matches stops instead of guessing. Codex tool shells use a shared daemon, so process ancestry is not pane proof. If strict identity is unavailable, show candidates and have the user select the intended pane; never guess focus, title, cwd or kind. Inspect candidates with:

```bash
osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'
```

From the selected CLI itself, `bridge bind ghostty:<UUID>` records legacy transport cache only. Complete a protocol-3/engine-1 session challenge/bind in that same CLI; the exact setup sequence is below (Claude also exposes `/crosstalk:setup`). A transport bind or label alone does not create a logical session. Do not execute another participant's bind for it. An existing verified logical binding may be reused only with fresh exact current-invocation surface context. A resumed CLI needs explicit rebind of the intended logical session, expected generation, and a fresh target challenge; do not silently adopt its old work.

Codex requires exact current-invocation surface context on **every** protocol-3/engine-1 tool call. Its shared tool daemon may omit parent environment, and `CODEX_THREAD_ID` plus a saved bridge binding cannot distinguish the same thread resumed in another live pane. Prefix each invocation (or explicitly export in that same tool shell):

```bash
env CROSSTALK_CONFIG_DIR="<SHARED_CONFIG_ROOT>" CROSSTALK_SURFACE_ID="ghostty:<CURRENT_SELECTED_UUID>" \
  <ABSOLUTE_CROSSTALK_RUNTIME> receive
```

The UUID must come from this execution's targeted launch/handshake or explicit user selection. Do not reconstruct it from a thread cache, kind, cwd, or an old resumed conversation. After restart/resume, reselect and complete the new target handshake before acting; do not reuse an inherited stale surface value. Replace `receive` with the needed send/reply/ack/renew/status command and preserve these same per-call environment arguments. A plain `bridge bind` only updates legacy transport cache and does not satisfy strict Codex identity by itself.

For a new participant without an existing verified binding, execute in that participant's own CLI:

```bash
# SELF is the current execution's exact selected/probed address, never an old cache.
# Repeat these exports in every new Codex tool shell; KIND is the actual CLI kind.
export CROSSTALK_CONFIG_DIR="$CONFIG_ROOT" CROSSTALK_SURFACE_ID="$SELF"
"$BRIDGE" bind "$SELF"
CHALLENGE=$("$CT" session challenge --surface "$SELF" --kind "$KIND" --protocol 3 --engine-version 1) || exit 1
NONCE=$(printf '%s' "$CHALLENGE" | jq -er '.challenge') || exit 1
"$CT" session bind --challenge "$NONCE" --kind "$KIND" --protocol 3 --engine-version 1
"$CT" session status
```

For an existing peer, create `session challenge --surface <EXACT_SURFACE> --kind <KIND> --protocol 3 --engine-version 1 --notify` and let that target execute its own transport/protocol bind. Check session status before sending. For an authorized transfer, include `--session-id <LOGICAL_ID> --expected-generation <N>` on challenge, then the target uses `session rebind --challenge <NONCE> --kind <KIND> --protocol 3 --engine-version 1 --confirm-transfer`. If using `--notify` for that transfer, also supply challenge's `--confirm-transfer` only after user authorization. Keep nonce/token values out of ordinary conversation.

## Prepare a peer for a requested topic

For independent review, follow `independent.md`: use `launch codex --fresh-for-input <INPUT_ID>` and keep its saved run/input IDs. The ordinary `ensure-peer` reuse below is not a fresh-context guarantee.

After the caller is bound, use its actual kind (Codex=`codex`, Claude=`claude`) and the requested peer (other kind by default, `antigravity` only when requested):

```bash
PEER=$("$BRIDGE" ensure-peer codex "${PEER_KIND:-claude}")
```

The bridge reuses an existing candidate or opens an exact native split and waits for startup. A new launch completes its protocol-3/engine-1 bind before readiness. Existing labelled panes and protocol-2-only bindings still need explicit protocol-3/engine-1 readiness for new engine runs: use the setup challenge flow and wait for the target CLI to complete it. Check the registry before sending a topic. More than one matching peer requires explicit selection, never a first-pane fallback.

On timeout retain the pending pane; show login/trust/busy state only when observed, otherwise report it as a possible cause. Do not launch another copy, increase permissions, or send a topic before handshake. Use default CLI permissions unless the user already explicitly selected the per-launch auto-approval option in mailbox.md.

If preparation fails, preserve the supplied topic with bridge `pending-save`. Resume that topic after readiness; message recovery is a separate `recover` operation. Do not move users to cmux because Ghostty identity failed. Do not use screen capture, `wait-ready` or `wait-turn` for Ghostty; those are legacy cmux paths.

A protocol-2 binding may continue an ordinary stored mailbox-v2 thread; it does not prove engine readiness. Confirm both `protocol_version=3` and `engine_version=1` in session status before `run start`. Agy is not a caller role; use the kind `antigravity` only for its peer binding.

New peers appear in native splits, not new windows or tabs. The short visible startup message points at a private instruction file; do not paste the full bootstrap command into normal conversation. Startup success removes that file; failed preparation retains it and the pending pane for retry. `--auto-approve` remains an explicit per-launch user choice, never an inferred response to a stalled permission prompt.

For an engine run already in preparing, retain the exact pending surface returned by launch and attach it with `run continue <RUN_ID> --operation-id <ID> --peer-surface <EXACT_SURFACE>` (or an intended `--peer-session`). This records selection, not ownership: the target still completes its own protocol-3/engine-1 handshake before a request is created. Repeat only the same stored selection. Once the first request fixes the participant, selection flags cannot replace it; use validated rebinding of that logical session instead.
