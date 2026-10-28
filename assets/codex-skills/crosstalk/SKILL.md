---
name: crosstalk
description: Discuss with Claude from Codex using the Ghostty SQLite mailbox (send/receive/reply), with legacy cmux workflows available.
---

# Crosstalk for Codex

Use this skill when the user invokes `$crosstalk` or asks Codex to run Crosstalk as the caller/moderator.

## Protocol gate

Before Ghostty mailbox actions run `~/.claude/scripts/crosstalk capabilities --json`. Require protocol 2, supported schema and healthy installation; read the mailbox instruction path it returns. Reload instructions after upgrade. Do not rely on a cached v0.10 flow or bypass a missing token. For an empty/status call use read-only doctor/status, never preparation or message receipt. See `readiness.md` for exact caller/peer handshake.

Codex protocol-2 calls must include the current execution's exact `CROSSTALK_SURFACE_ID` and shared `CROSSTALK_CONFIG_DIR` on every invocation; see readiness.md. A CODEX_THREAD_ID/bridge cache alone is refused. After resume/restart reselect the current target and handshake, rather than copying a remembered old pane ID. Apply this before processing an incoming preview as well as when starting a discussion.

## Route first

- Incoming `[Crosstalk] 질문:/답변:/Question:/Reply:` summary: read `mailbox.md`, then use ID-less `receive`. The preview is display-only; process the returned DB row and drain pending messages one at a time.

- Incoming `[crosstalk] mailbox <ID>`: read `mailbox.md`. Call `~/.claude/scripts/crosstalk receive <ID>` and use `reply` for requests. Never call `start-run` or `ping` for mailbox messages.
- New topic, `analyze`, or `ask`: check `~/.claude/scripts/crosstalk_bridge.sh backend`. On Ghostty, read `mailbox.md` and use the protocol-2 send/receive/reply/ack flow. On cmux, use the legacy flow files below.
- No topic, launch, status, resume, cowork, or an explicit legacy `RUN_ID` trigger: use the matching entry below.

Skill files such as `mailbox.md` describe the workflow; they are not message transport files. New Ghostty message bodies and replies are stored in SQLite.

This is a dispatcher. Do not inline every workflow from memory. Read exactly one flow file from this skill directory before acting:

- `launch [claude|agy|antigravity]`: read `readiness.md` and run `bridge ensure-peer codex <requested-peer>` (default claude).
- No arguments: read `readiness.md`.
- Plain topic on cmux: read `analyze.md`.
- `analyze ...` on cmux: read `analyze.md`.
- `ask ...` on cmux: read `ask.md`.
- `cowork ...`: read `cowork.md`.
- `cowork-stop ...`: read `cowork-stop.md`.
- `resume`: read `resume.md`.
- `callback RUN_ID=... AGENT=... ROUND=... RESP=...`: read `callback.md`.
- `status`: read `status.md`.
- `recover <ID>`: read `mailbox.md`; diagnose first, then reclaim only with the user's explicit authorization and expected claim version.
- Incoming trigger `[crosstalk] preamble <agent> RUN_ID=...`: read `analyze.md`.
- Incoming trigger `[crosstalk] round <NN> <agent> RUN_ID=...`: read `analyze.md`.
- Incoming trigger `[crosstalk] ask <agent> RUN_ID=...`: read `ask.md`.
- Incoming trigger `[crosstalk] cowork-task <agent> RUN_ID=...`: read `cowork.md`.
- Incoming trigger `[crosstalk] review-round <NN> <agent> RUN_ID=...`: read `review.md`.

Use `~/.claude/scripts/crosstalk_bridge.sh` for terminal setup and legacy transport. Use `~/.claude/scripts/crosstalk` for Ghostty mailbox messages. Codex does not have Claude-style `$ARGUMENTS`; treat the full user message after `$crosstalk` as the argument string.

## Legacy file protocol only

The following instructions apply only to cmux workflows and explicit legacy `RUN_ID` conversations, including old Ghostty runs. They do not apply to new Ghostty mailbox discussions.

When starting a legacy run from Codex, call:

```bash
CROSSTALK_MODERATOR_KIND=codex ~/.claude/scripts/crosstalk_bridge.sh start-run
```

The bridge also detects the current terminal surface and writes `moderator_surface` and `moderator_kind` to the manifest. If the terminal cannot be identified or the bridge is missing, follow `readiness.md` and preserve the topic when needed.

When handling an explicit legacy `RUN_ID` trigger as a peer, do not answer the trigger directly. Parse `RUN_ID` and `agent`, read the referenced file under `/tmp/crosstalk/run-<RUN_ID>/`, follow its instructions, write the required response file, then call `~/.claude/scripts/crosstalk_bridge.sh ping`.
