# $crosstalk cowork

Run Crosstalk co-work mode from Codex as the moderator.

## Parse

Remove the leading `cowork` word. Supported options:

- `--no-worktree`
- `--max-time <duration>` where duration is like `30m` or `2h`

The remaining text is the assignment body. If empty, show usage:

```text
$crosstalk cowork "claude=Repository layer, gemini=QA, goal=ship feature with tests"
```

## Start run

Check cmux and peers first. Then:

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
```

Interpret the assignment body into a common `GOAL` and per-agent assignments. If explicit `claude=...`, `codex=...`, `gemini=...`, `goal=...` fields exist, preserve them. Otherwise split the work pragmatically across `AGENTS`.

Merge `mode`, `agents`, `goal`, `assignments`, and `current_round=1` into the manifest.

## Worktrees

Default to git worktrees unless `--no-worktree` is present. Ask the user before creating worktrees. Use:

```bash
~/.claude/scripts/crosstalk_bridge.sh start-worktree "$RUN_ID" "$agent"
```

For shared mode, use the current working directory for every agent.

## Fan-out

For each peer, send:

- `[Crosstalk cowork]`
- `RUN_ID`
- that agent's assignment
- work directory
- instruction to run its own `/goal "<GOAL>"`
- instruction to write `/tmp/crosstalk/run-${RUN_ID}/responses/<agent>-r01.md`
- ping command

Codex also participates. Start or perform Codex's own assignment after fan-out, then write `responses/codex-r01.md` and ping `codex 1`.

When all participants ping, callback mode will aggregate the reports.
