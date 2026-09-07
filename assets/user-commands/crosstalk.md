---
description: Run Crosstalk analysis from Claude, automatically preparing a Codex peer in Ghostty, or show readiness without a topic.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: <분석 주제>
---

# /crosstalk

Use the full `$ARGUMENTS` as the raw topic. Preserve its wording.

```bash
BRIDGE="$HOME/.claude/scripts/crosstalk_bridge.sh"
BACKEND=$("$BRIDGE" backend)
SELF=$("$BRIDGE" self)
"$BRIDGE" label "$SELF" claude
"$BRIDGE" list-peers
```

If the bridge is missing, run `/crosstalk:install`. If `self` fails, preserve a supplied topic with `pending-save` and report that error. Do not guess the focused pane or move the user to cmux when Ghostty is available.

With no topic: show backend, caller, peers, and one next action. Do not launch peers merely to display status.

With a topic on Ghostty:

```bash
PEER=$("$BRIDGE" ensure-peer claude codex)
```

This reuses a labelled Codex in the same tab or splits right and starts Codex in the current directory. On startup timeout, let the user finish login/trust prompts in that existing pane; do not launch a duplicate or bypass permissions.

Then read and execute `/crosstalk:analyze` with the unchanged topic. All terminal communication uses the bridge. Ghostty uses file responses plus ping callbacks, not screen capture. On cmux, run `/crosstalk:launch` if peers are missing and then continue analyze.

For an incoming Crosstalk peer message, read the task file named in the message and follow its response/ping instructions instead of starting another run. For a completion callback, restore that run's manifest and continue its existing analysis rounds; do not launch a new run.

Ghostty's first binding requires a unique working directory. If ambiguous, set `CROSSTALK_SURFACE_ID=ghostty:<UUID>` for bridge calls; never select an arbitrary same-directory terminal. List IDs with `osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'`.
