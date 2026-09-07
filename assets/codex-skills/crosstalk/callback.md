# $crosstalk callback

Handle bridge callbacks sent to a Codex moderator.

Callback format:

```text
$crosstalk callback RUN_ID=<id> AGENT=<agent> ROUND=<n> RESP=<path>
```

## Parse and restore

Extract `RUN_ID`, `AGENT`, `ROUND`, and `RESP`.

```bash
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"
MODE=$(jq -r '.mode // ""' "$MANIFEST")
CURRENT_ROUND=$(jq -r '.current_round // 1' "$MANIFEST")
AGENTS=($(jq -r '.agents[]' "$MANIFEST"))
```

If the manifest is missing, report the broken run and stop.

## Wait until all participants are done

```bash
ROUND_PADDED=$(printf '%02d' "$ROUND")
ALL_DONE=1
for agent in "${AGENTS[@]}"; do
  [ -f "$RUN_DIR/done/${agent}-r${ROUND_PADDED}" ] || ALL_DONE=0
done
```

If any participant is missing, exit quietly with a short note such as `Waiting for remaining Crosstalk peers...`. Do not summarize yet.

## Cowork mode

If `MODE=cowork`, read all available `responses/<agent>-r01.md` files and write:

```text
/tmp/crosstalk/run-${RUN_ID}/cowork-summary.md
```

Register last:

```bash
~/.claude/scripts/crosstalk_bridge.sh register-last "$RUN_ID"
```

Then print the summary path and stop.

## Analyze mode

For each response file in the current round, run deterministic verdict extraction:

```bash
~/.claude/scripts/crosstalk_bridge.sh extract-verdict "$RESP"
```

Do not infer verdicts yourself.

End conditions:

- All verdicts are `AGREE`: print a consensus summary and register last.
- Any verdict is `RESPECT_DISAGREE`: print respectful divergence with each reason and register last.
- Round >= 10: print hard-cap summary and register last.
- Otherwise start the next ping-pong round.

## Next ping-pong round

Increment `current_round` in the manifest and write each participant's divergence summary to:

```text
/tmp/crosstalk/run-${RUN_ID}/rounds/r<NN>-<agent>.md
```

Resolve each peer's terminal from the original run (never from current focus):

```bash
PEER_SURFACE=$(jq -er --arg agent "$AGENT" '.peers[$agent]' "$MANIFEST")
```

Then send only the short trigger:

```bash
~/.claude/scripts/crosstalk_bridge.sh send-via-file \
  "$PEER_SURFACE" \
  "$RUN_DIR/rounds/r<NN>-<agent>.md" \
  "[crosstalk] round <NN> <agent> RUN_ID=${RUN_ID}"
```

The round file must ask the peer to write:

```text
/tmp/crosstalk/run-${RUN_ID}/responses/<agent>-r<NN>.md
```

and then ping:

```bash
~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} <agent> ${NEXT_ROUND}
```

Codex's own next-round response must also be written to `responses/codex-r<NN>.md`, followed by `ping "$RUN_ID" codex "$NEXT_ROUND"`.
