# $crosstalk readiness

Run this when `$crosstalk` has no arguments, or before starting a topic.

## Checks

Use shell commands and keep user output concise.

```bash
BRIDGE="$HOME/.claude/scripts/crosstalk_bridge.sh"
[ -x "$BRIDGE" ] && INSTALLED="OK" || INSTALLED="missing"

if [ "$INSTALLED" = "OK" ] && cmux identify >/dev/null 2>&1; then
  CMUX="inside"
else
  CMUX="outside"
fi

if [ "$CMUX" = "inside" ]; then
  PEERS=$("$BRIDGE" list-peers 2>/dev/null \
    | awk -F'\t' '$2 ~ /^(claude|codex|gemini)$/' \
    | wc -l | tr -d ' ')
else
  PEERS="?"
fi
```

## Output

Show:

```text
Crosstalk — readiness

  installed:  <OK|missing>
  cmux:       <inside|outside>
  peers:      <N|?> detected

Next:
  <single next action>
```

Next action rules:

- `installed=missing`: ask the user to run `/crosstalk:install` once in Claude Code. This installs both Claude commands and the Codex `$crosstalk` skill.
- `cmux=outside`: tell the user to open or enter a cmux workspace. If a topic was provided, save it first with `pending-save`.
- `cmux=inside, peers=0`: tell the user to run `/crosstalk:launch` in Claude Code or open another AI CLI pane and label it with `/crosstalk:setup`.
- `cmux=inside, peers>=1`: say `$crosstalk <topic>` is ready.

If a topic was provided while outside cmux:

```bash
"$BRIDGE" pending-save "$TOPIC"
```

Then say the topic was preserved and can be resumed with `$crosstalk resume` from inside cmux.
