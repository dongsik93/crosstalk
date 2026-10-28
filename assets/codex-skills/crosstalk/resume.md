# $crosstalk resume

Resume a topic preserved when `$crosstalk <topic>` was called outside a supported terminal.

```bash
TOPIC=$(~/.claude/scripts/crosstalk_bridge.sh pending-load 2>/dev/null)
```

If empty, tell the user there is no preserved topic.

Show the topic. An explicit user request to resume already authorizes continuation; otherwise confirm intent. Clear pending only after the topic is durably queued or a legacy run starts successfully:

```bash
~/.claude/scripts/crosstalk_bridge.sh pending-clear
```

Then detect the backend: on Ghostty follow readiness and the protocol-2 mailbox; on cmux follow `analyze.md`.

This resumes a topic retained after preparation failed. It is not recovery of a stored message. For an interrupted mailbox claim, use `recover ID` diagnosis and explicit authorized reclaim; never create a new request to replace it.
