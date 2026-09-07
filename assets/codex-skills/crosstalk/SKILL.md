---
name: crosstalk
description: Run Crosstalk multi-agent analysis, cowork, status, resume, and callback workflows through Ghostty or cmux panes from Codex.
---

# Crosstalk for Codex

Use this skill when the user invokes `$crosstalk` or asks Codex to run Crosstalk as the caller/moderator.

For incoming `[crosstalk] mailbox <ID>`, read `mailbox.md` first. For a new Ghostty topic/analyze/ask request, read `mailbox.md` and use send/receive/reply instead of the legacy file protocol. Check the backend with the bridge. Legacy RUN_ID callbacks still use the files listed below.

This is a dispatcher. Do not inline every workflow from memory. Read exactly one flow file from this skill directory before acting:

- `launch [claude]`: read `readiness.md` and run `bridge ensure-peer codex claude`.
- No arguments: read `readiness.md`.
- Plain topic: read `analyze.md`.
- `analyze ...`: read `analyze.md`.
- `ask ...`: read `ask.md`.
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

Always use `~/.claude/scripts/crosstalk_bridge.sh` as the transport bridge. Codex does not have Claude-style `$ARGUMENTS`; treat the full user message after `$crosstalk` as the argument string.

When starting a run from Codex, call:

```bash
CROSSTALK_MODERATOR_KIND=codex ~/.claude/scripts/crosstalk_bridge.sh start-run
```

The bridge also detects the current terminal surface and writes `moderator_surface` and `moderator_kind` to the manifest. If the terminal cannot be identified or the bridge is missing, follow `readiness.md` and preserve the topic when needed.

When handling an incoming `[crosstalk] ...` trigger as a peer, do not answer the trigger directly. Parse `RUN_ID` and `agent`, read the referenced file under `/tmp/crosstalk/run-<RUN_ID>/`, follow its instructions, write the required response file, then call `~/.claude/scripts/crosstalk_bridge.sh ping`.
