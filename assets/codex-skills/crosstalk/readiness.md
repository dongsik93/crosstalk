# $crosstalk readiness

Use the installed bridge, never a direct cmux check:

```bash
BRIDGE="$HOME/.claude/scripts/crosstalk_bridge.sh"
[ -x "$BRIDGE" ] || { echo 'Crosstalk bridge missing: run /crosstalk:install'; exit 1; }
BACKEND=$("$BRIDGE" backend)
SELF=$("$BRIDGE" self)
"$BRIDGE" label "$SELF" codex
"$BRIDGE" list-peers
```

For an empty invocation, show backend, caller ID, and labelled peers. Do not launch an AI just to show status.

For a topic on Ghostty, automatically prepare the requested Claude peer:

```bash
PEER=$("$BRIDGE" ensure-peer codex claude)
```

This reuses one labelled Claude peer in the caller's tab or splits right and launches Claude in the same directory. It waits for a real startup acknowledgement. On timeout, stop and report the existing pane's login/trust prompt; never launch another copy or bypass permissions. Then continue the requested flow automatically.

On cmux, keep the existing launch/setup flow if no peers exist.

If `self` fails, preserve a supplied topic with `pending-save` and show the bridge error. Do not guess the focused pane. The initial Ghostty binding requires a unique working directory across Ghostty terminals; if ambiguous, use `CROSSTALK_SURFACE_ID=ghostty:<UUID>` consistently for bridge calls. IDs are available through:

```bash
osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'
```

Ghostty uses the SQLite mailbox and send/receive/reply for new discussions. See `mailbox.md`. Existing file/ping runs can still finish. Screen capture, UI footer detection, and screen transport are unavailable. Do not call `wait-ready` or `wait-turn` on Ghostty; `ensure-peer` handles startup.
