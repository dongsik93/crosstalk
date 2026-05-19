# $crosstalk cowork

Run Crosstalk co-work mode from Codex as the moderator.

## Incoming peer trigger

If the user message is:

```text
[crosstalk] cowork-task <agent> RUN_ID=<RUN_ID>
```

handle it as a peer. Read and follow:

```bash
cat /tmp/crosstalk/run-${RUN_ID}/assignments/<agent>.md
```

Do not answer the trigger directly. The assignment file tells you the work directory, `/goal` command, report path, and ping command.

## Parse

Remove the leading `cowork` word. Supported options:

- `--no-worktree`
- `--max-time <duration>` where duration is like `30m` or `2h`

The remaining text is the assignment body. If empty, show usage:

```text
$crosstalk cowork "claude=Repository layer, antigravity=QA, goal=ship feature with tests"
```

## Start run

Check cmux and peers first. Then:

```bash
PEERS_RAW=$(~/.claude/scripts/crosstalk_bridge.sh list-peers)
PEERS=$(printf '%s\n' "$PEERS_RAW" | awk -F'\t' '$2 ~ /^(claude|codex|antigravity)$/ {print $1"|"$2}')

RUN_ID=$(CROSSTALK_MODERATOR_KIND=codex ~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"
mkdir -p "$RUN_DIR/assignments"

MODERATOR_KIND=$(jq -r '.moderator_kind // "codex"' "$MANIFEST")
AGENTS=("$MODERATOR_KIND")
for p in $PEERS; do
  AGENTS+=("${p#*|}")
done
```

Interpret the assignment body into a common `GOAL` and per-agent assignments. If explicit `claude=...`, `codex=...`, `antigravity=...`, `goal=...` fields exist, preserve them. Otherwise split the work pragmatically across `AGENTS`.

Merge `mode`, `agents`, `goal`, `assignments`, and `current_round=1` into the manifest.

## Worktrees

Default to git worktrees unless `--no-worktree` is present. Ask the user before creating worktrees. Use:

```bash
~/.claude/scripts/crosstalk_bridge.sh start-worktree "$RUN_ID" "$agent"
```

For shared mode, use the current working directory for every agent.

## Fan-out

For each peer, write the full assignment to:

```text
/tmp/crosstalk/run-${RUN_ID}/assignments/<agent>.md
```

The assignment file includes:

- `[Crosstalk cowork]`
- `RUN_ID`
- that agent's assignment
- work directory
- instruction to run its own `/goal "<GOAL>"`
- instruction to write `/tmp/crosstalk/run-${RUN_ID}/responses/<agent>-r01.md`
- ping command

Then send only the short trigger:

```bash
~/.claude/scripts/crosstalk_bridge.sh send-via-file \
  "$PEER_SURFACE" \
  "$RUN_DIR/assignments/<agent>.md" \
  "[crosstalk] cowork-task <agent> RUN_ID=${RUN_ID}"
```

Codex also participates. Start or perform Codex's own assignment after fan-out, then write `responses/codex-r01.md` and ping `codex 1`.

When all participants ping, callback mode will aggregate the reports.
