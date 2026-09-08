---
name: crosstalk
description: Discuss with Claude from Codex using the Ghostty SQLite mailbox (send/receive/reply), with legacy cmux workflows available.
---

# Crosstalk for Codex

Use this skill when the user invokes `$crosstalk` or asks Codex to run Crosstalk as the caller/moderator.

## Route first

- Incoming `[Crosstalk] 질문:/답변:/Question:/Reply:` summary: read `mailbox.md`, then use ID-less `receive`. The preview is display-only; process the returned DB row and drain pending messages one at a time.

- Incoming `[crosstalk] mailbox <ID>`: read `mailbox.md`. Call `~/.claude/scripts/crosstalk receive <ID>` and use `reply` for requests. Never call `start-run` or `ping` for mailbox messages.
- New topic, `analyze`, or `ask`: check `~/.claude/scripts/crosstalk_bridge.sh backend`. On Ghostty, read `mailbox.md` and use `~/.claude/scripts/crosstalk send/receive/reply`. On cmux, use the legacy flow files below.
- No topic, launch, status, resume, cowork, or an explicit legacy `RUN_ID` trigger: use the matching entry below.

Skill files such as `mailbox.md` describe the workflow; they are not message transport files. New Ghostty message bodies and replies are stored in SQLite.

This is a dispatcher. Do not inline every workflow from memory. Read exactly one flow file from this skill directory before acting:

- `launch [claude]`: read `readiness.md` and run `bridge ensure-peer codex claude`.
- No arguments: read `readiness.md`.
- Plain topic on cmux: read `analyze.md`.
- `analyze ...` on cmux: read `analyze.md`.
- `ask ...` on cmux: read `ask.md`.
- `cowork ...`: read `cowork.md`.
- `cowork-stop ...`: read `cowork-stop.md`.
- `resume`: read `resume.md`.
- `callback RUN_ID=... AGENT=... ROUND=... RESP=...`: read `callback.md`.
- `status`: read `status.md`.
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
