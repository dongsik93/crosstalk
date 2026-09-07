# $crosstalk ask — fire-and-forget

Quick opinion sampling. Caller fans out the question and answers in its own pane. Peers answer in their own panes. No ping, no callback, no aggregation.

## Trigger reception (peer side)

For incoming peer trigger:

```
[crosstalk] ask <agent> RUN_ID=<RUN_ID>
```

Do not answer the trigger directly. Instead:

```bash
cat /tmp/crosstalk/run-${RUN_ID}/preambles/<agent>.md
```

Read the preamble. Then **print your answer to your own pane and stop**. Do not call ping, do not write any response file.

## Caller flow ($crosstalk ask <question>)

### Parse

Treat the full text after `$crosstalk` as arguments. If it starts with `ask`, remove that word. The remainder is the question.

If empty, show usage and stop:

```text
$crosstalk ask <question>
```

### Preconditions

Run `readiness.md`, including automatic `ensure-peer codex claude` on Ghostty. Continue only when it succeeds. Preserve the topic and report the bridge error if preparation fails.

### Start run (preambles only)

```bash
PEERS_RAW=$(~/.claude/scripts/crosstalk_bridge.sh list-peers)
PEERS=$(printf '%s\n' "$PEERS_RAW" | awk -F'\t' '$2 ~ /^(claude|codex|antigravity)$/ {print $1"|"$2}')

RUN_ID=$(CROSSTALK_MODERATOR_KIND=codex ~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"

TMP=$(mktemp)
jq --arg mode ask '. + {mode: $mode}' "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"
```

### Fan-out (no ping instruction inside)

For each peer, write a minimal preamble and send the trigger:

```bash
mkdir -p "$RUN_DIR/preambles"
for entry in $PEERS; do
  PEER_SURFACE="${entry%|*}"
  PEER_KIND="${entry#*|}"
  PREAMBLE_FILE="$RUN_DIR/preambles/${PEER_KIND}.md"

  cat > "$PREAMBLE_FILE" <<CROSSTALK_ASK
[Crosstalk ask]

The user is asking everyone the same question. Answer it once, in your own way,
right here in your pane. This is fire-and-forget:

- No debate, no follow-up round, no verdict markers required.
- Do NOT call any ping or bridge command.
- Do NOT write any response file.
- Just print your answer to your own pane and stop.

=== Question (user's raw input) ===
${TOPIC}
CROSSTALK_ASK

  TRIGGER="[crosstalk] ask ${PEER_KIND} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$PEER_SURFACE" "$PREAMBLE_FILE" "$TRIGGER"
  sleep 1
done
```

### Codex's own answer (immediate, in own pane)

Print Codex's answer right in this pane. Do not write to any file, do not ping. Just answer:

```text
🟧 Codex:
<your answer in your own way>
```

### Final one-liner

```bash
echo "✅ ask done — peers will answer in their own panes."
echo "📁 RUN_ID=$RUN_ID  (preambles: $RUN_DIR/preambles/)"
```

That's it. No callback will arrive. The user reads each peer pane directly.

## Notes

- ask is fire-and-forget. The caller does not wait for peers. There is no `$crosstalk callback ...` for ask runs.
- Peer answers stay in each peer's own pane. The caller does not aggregate them.
- If the user wants consensus or a verdict, route to `analyze.md`.
