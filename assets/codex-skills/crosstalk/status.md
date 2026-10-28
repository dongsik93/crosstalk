# $crosstalk status

Read-only inspection; do not launch, label, bind, receive, retry, reclaim, create a DB, or copy presets.

```bash
~/.claude/scripts/crosstalk capabilities --json
~/.claude/scripts/crosstalk doctor --offline
~/.claude/scripts/crosstalk status
```

If the terminal can be identified, `crosstalk_bridge.sh list-all` may list candidates. A label is not a protocol-2 binding. Show runtime/protocol/schema, installation health, unresolved sessions, queued/processing/completed and effective recovery_required states, and separate delivery status. Missing DB is a diagnosis, not a request to create it. Use pagination before claiming there are no other pending or interrupted messages.

Read config, rules/personas and their names under `CROSSTALK_CONFIG_DIR` (default `~/.claude/crosstalk`) without changing them. Show one concrete next action for each blocking diagnosis. Status never authorizes recover or an automatic permission change.

Start commands: Claude `/crosstalk <topic>`; Codex `$crosstalk <topic>`.
