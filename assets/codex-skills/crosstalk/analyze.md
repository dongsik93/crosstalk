# $crosstalk analyze

For a new Ghostty request or an incoming mailbox notification, read `mailbox.md` and follow it instead of the legacy steps below. Existing RUN_ID triggers still follow the legacy steps.

Run independent multi-agent analysis from Codex as the moderator.

## Incoming peer triggers

If the user message is a Crosstalk trigger, handle it as a peer and stop after pinging.

For first-round analysis:

```text
[crosstalk] preamble <agent> RUN_ID=<RUN_ID>
```

Read and follow:

```bash
cat /tmp/crosstalk/run-${RUN_ID}/preambles/<agent>.md
```

For ping-pong rounds:

```text
[crosstalk] round <NN> <agent> RUN_ID=<RUN_ID>
```

Read and follow:

```bash
cat /tmp/crosstalk/run-${RUN_ID}/rounds/r<NN>-<agent>.md
```

Do not answer the trigger directly. The file body tells you where to write `responses/<agent>-rNN.md` and which `ping` command to call.

## Parse

Treat the full text after `$crosstalk` as arguments. If it starts with `analyze`, remove that word.

Supported options:

- `--rules <name>`
- `--persona <name>`

The remaining text is `TOPIC`. If empty, show usage:

```text
$crosstalk <topic>
$crosstalk analyze [--rules <name>] [--persona <name>] <topic>
```

## Preconditions

Run `readiness.md`, including automatic `ensure-peer codex claude` on Ghostty. Continue only when it succeeds. Preserve the topic and report the bridge error if preparation fails.

## Load presets

Use the same config as Claude commands:

```bash
CONFIG="$HOME/.claude/crosstalk/config.json"
LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac

ACTIVE_RULES=$(jq -r '.active_rules // "default"' "$CONFIG" 2>/dev/null || echo "default")
ACTIVE_PERSONA=$(jq -r '.active_persona // "default"' "$CONFIG" 2>/dev/null || echo "default")
RULES_NAME="${RULES_NAME:-$ACTIVE_RULES}"
PERSONA_NAME="${PERSONA_NAME:-$ACTIVE_PERSONA}"

~/.claude/scripts/crosstalk_bridge.sh ensure-presets "$LANGUAGE" >/dev/null 2>&1 || true

RULES_FILE="$HOME/.claude/crosstalk/rules/${LANGUAGE}/${RULES_NAME}.md"
PERSONA_FILE="$HOME/.claude/crosstalk/personas/${LANGUAGE}/${PERSONA_NAME}.md"
```

If a preset name is `none` or its file is missing, omit that section. Otherwise read the file verbatim.

## Start run

```bash
PEERS_RAW=$(~/.claude/scripts/crosstalk_bridge.sh list-peers)
PEERS=$(printf '%s\n' "$PEERS_RAW" | awk -F'\t' '$2 ~ /^(claude|codex|antigravity)$/ {print $1"|"$2}')

RUN_ID=$(CROSSTALK_MODERATOR_KIND=codex ~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"
mkdir -p "$RUN_DIR/preambles" "$RUN_DIR/rounds"

MODERATOR_KIND=$(jq -r '.moderator_kind // "codex"' "$MANIFEST")
AGENTS=("$MODERATOR_KIND")
for p in $PEERS; do
  AGENTS+=("${p#*|}")
done

TMP_MANIFEST=$(mktemp)
jq --arg mode analyze \
   --argjson round 1 \
   --argjson agents "$(printf '%s\n' "${AGENTS[@]}" | jq -R . | jq -s .)" \
   '. + {mode: $mode, agents: $agents, current_round: $round}' \
   "$MANIFEST" > "$TMP_MANIFEST" && mv "$TMP_MANIFEST" "$MANIFEST"
```

Persist the peer mapping so callbacks can route later rounds:

```bash
for entry in $PEERS; do
  TMP_MANIFEST=$(mktemp)
  jq --arg kind "${entry#*|}" --arg surface "${entry%|*}" \
    '.peers[$kind] = $surface' "$MANIFEST" > "$TMP_MANIFEST" && mv "$TMP_MANIFEST" "$MANIFEST"
done
```

## Moderator's own response

Before waiting for peers, write Codex's independent analysis to:

```text
/tmp/crosstalk/run-${RUN_ID}/responses/codex-r01.md
```

End it with one of:

- `[AGREE]`
- `[RESPECT_DISAGREE: <reason>]`

Also include `confidence: high|medium|low`.

Then ping yourself:

```bash
~/.claude/scripts/crosstalk_bridge.sh ping "$RUN_ID" codex 1
```

## Fan-out

For every peer, write a preamble file that includes:

- `[Crosstalk analyze]`
- `RUN_ID`
- the raw topic
- optional rules/persona sections verbatim
- response path: `/tmp/crosstalk/run-${RUN_ID}/responses/<agent>-r01.md`
- ping command: `~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} <agent> 1`

Save it to:

```text
/tmp/crosstalk/run-${RUN_ID}/preambles/<agent>.md
```

Then send only the short trigger:

```bash
~/.claude/scripts/crosstalk_bridge.sh send-via-file \
  "$PEER_SURFACE" \
  "$RUN_DIR/preambles/<agent>.md" \
  "[crosstalk] preamble <agent> RUN_ID=${RUN_ID}"
```

After fan-out, stop and wait for callback. The bridge will send `$crosstalk callback ...` to this Codex pane when peers ping.
