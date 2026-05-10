---
name: crosstalk
description: Run Crosstalk multi-agent analysis, cowork, status, resume, and callback workflows through cmux panes from Codex.
---

# Crosstalk for Codex

Use this skill when the user invokes `$crosstalk` or asks Codex to run Crosstalk as the caller/moderator.

This is a dispatcher. Do not inline every workflow from memory. Read exactly one flow file from this skill directory before acting:

- No arguments: read `readiness.md`.
- Plain topic: read `analyze.md`.
- `analyze ...`: read `analyze.md`.
- `cowork ...`: read `cowork.md`.
- `cowork-stop ...`: read `cowork-stop.md`.
- `resume`: read `resume.md`.
- `callback RUN_ID=... AGENT=... ROUND=... RESP=...`: read `callback.md`.
- `status`: read `status.md`.

Always use `~/.claude/scripts/crosstalk_bridge.sh` as the transport bridge. Codex does not have Claude-style `$ARGUMENTS`; treat the full user message after `$crosstalk` as the argument string.

When starting a run from Codex, call:

```bash
CROSSTALK_MODERATOR_KIND=codex ~/.claude/scripts/crosstalk_bridge.sh start-run
```

The bridge also detects the current cmux surface and writes `moderator_surface` and `moderator_kind` to the manifest. If cmux or the bridge is missing, follow `readiness.md` and preserve the topic when needed.
