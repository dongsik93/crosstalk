# $crosstalk resume

Resume a topic preserved when `$crosstalk <topic>` was called outside a supported terminal.

```bash
TOPIC=$(~/.claude/scripts/crosstalk_bridge.sh pending-load 2>/dev/null)
```

If empty, tell the user there is no preserved topic.

Show the topic and ask whether to continue. If yes, clear pending only after a run starts successfully:

```bash
~/.claude/scripts/crosstalk_bridge.sh pending-clear
```

Then follow `analyze.md` using the preserved topic.
