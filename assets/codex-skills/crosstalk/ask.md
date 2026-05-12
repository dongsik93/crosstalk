# $crosstalk ask

Quick opinion sampling from Codex as the moderator. Each peer answers once. No debate, no ping-pong, no verdict markers.

## Trigger reception

For incoming peer trigger:

```
[crosstalk] ask <agent> RUN_ID=<RUN_ID>
```

Do not answer the trigger directly. Instead:

```bash
cat /tmp/crosstalk/run-${RUN_ID}/preambles/<agent>.md
```

Follow the procedure in that file: write your answer to `responses/<agent>-r01.md` and call ping.

## Caller flow ($crosstalk ask <question>)

### Parse

Treat the full text after `$crosstalk` as arguments. If it starts with `ask`, remove that word. The remainder is the question.

If empty, show usage and stop:

```text
$crosstalk ask <question>
```

### Preconditions

Run the checks from `readiness.md`. If outside cmux, save the question with `pending-save` and stop. If no peers are available, ask the user to launch.

### Start run

```bash
PEERS_RAW=$(~/.claude/scripts/crosstalk_bridge.sh list-peers)
PEERS=$(printf '%s\n' "$PEERS_RAW" | awk -F'\t' '$2 ~ /^(claude|codex|gemini)$/ {print $1"|"$2}')

RUN_ID=$(CROSSTALK_MODERATOR_KIND=codex ~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"

MODERATOR_KIND=$(jq -r '.moderator_kind // "codex"' "$MANIFEST")
AGENTS=("$MODERATOR_KIND")
for p in $PEERS; do
  AGENTS+=("${p#*|}")
done

TMP=$(mktemp)
jq --arg mode ask \
   --argjson round 1 \
   --argjson agents "$(printf '%s\n' "${AGENTS[@]}" | jq -R . | jq -s .)" \
   '. + {mode: $mode, agents: $agents, current_round: $round}' \
   "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"
```

### Codex's own answer

Write your own answer to `responses/${MODERATOR_KIND}-r01.md` and ping yourself before fan-out (so the user sees Codex's pane respond too):

```bash
cat > "$RUN_DIR/responses/${MODERATOR_KIND}-r01.md" <<'EOF'
<your answer in your own way>
EOF
~/.claude/scripts/crosstalk_bridge.sh ping "$RUN_ID" "$MODERATOR_KIND" 1
```

### Fan-out

For each peer, write a minimal preamble to `preambles/<agent>.md` and send the trigger:

```bash
mkdir -p "$RUN_DIR/preambles"
for entry in $PEERS; do
  PEER_SURFACE="${entry%|*}"
  PEER_KIND="${entry#*|}"
  PREAMBLE_FILE="$RUN_DIR/preambles/${PEER_KIND}.md"

  cat > "$PREAMBLE_FILE" <<CROSSTALK_ASK
[Crosstalk ask]

The user is asking everyone the same question. Answer it once, in your own way.
This is not a debate. There is no follow-up round. No verdict markers required.

=== Question (user's raw input) ===
${TOPIC}

=== How to respond ===
cat > /tmp/crosstalk/run-${RUN_ID}/responses/${PEER_KIND}-r01.md <<'EOF'
<your answer here — any length, any form>
EOF

~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} ${PEER_KIND} 1
CROSSTALK_ASK

  TRIGGER="[crosstalk] ask ${PEER_KIND} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$PEER_SURFACE" "$PREAMBLE_FILE" "$TRIGGER"
  sleep 1
done
```

### After fan-out

Stop and wait for the bridge callback. The bridge will send `$crosstalk callback ...` to this Codex pane when peers ping.

### Callback handling

When all participants have pinged (use the same all-done check as `callback.md`):

- Do not aggregate, summarize, or re-print peer answers.
- Each peer already wrote its answer in its own pane and on disk.
- Output only:

```bash
LAST=$(~/.claude/scripts/crosstalk_bridge.sh register-last "$RUN_ID")
echo "✅ ask done — RUN_ID=$RUN_ID"
echo "📁 responses: $RUN_DIR/responses/  (last: $LAST)"
```

The user will look at each peer pane directly.

## Notes

- ask is *opinion sampling*, not analysis. If the user wants consensus or divergence judgment, route to `analyze.md`.
- Peer answers are free-form. Do not enforce length or `[AGREE]` markers.
- No ping-pong rounds.
