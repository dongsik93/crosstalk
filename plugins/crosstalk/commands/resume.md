---
description: Resume the preserved topic through the detected Ghostty or cmux backend.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: (no arguments)
---

# /crosstalk:resume

Read the preserved topic with `~/.claude/scripts/crosstalk_bridge.sh pending-load`. If empty, report that no topic is saved. Show the original topic; do not alter its wording. If the user has already requested resumption, continue without asking again.

Run the current `/crosstalk` entrypoint from `~/.claude/commands/crosstalk.md` with that topic. It detects the backend through the bridge:

- Ghostty: prepare the peer and use `~/.claude/crosstalk/mailbox.md`. Do not create a legacy run or tell the user to start cmux.
- cmux: use the existing cmux analysis workflow.
- Identification error: retain pending and show the error. If Ghostty reports multiple same-directory candidates, use `/crosstalk:setup --surface ghostty:<UUID>` from the intended CLI once.

Clear pending with `bridge pending-clear` only after the topic has been successfully queued/started. A failed preparation must not discard it. Only the most recently saved topic is retained.
