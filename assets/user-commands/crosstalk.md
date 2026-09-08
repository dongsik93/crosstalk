---
description: Run Crosstalk analysis from Claude, automatically preparing a Codex peer in Ghostty, or show readiness without a topic.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: <분석 주제>
---

# /crosstalk

Incoming `[Crosstalk] 질문:/답변:/Question:/Reply:` previews: read `~/.claude/crosstalk/mailbox.md` and call ID-less `receive`. Do not answer the preview directly or infer an ID from it. Process the actual DB row, then check for the next pending message.

For an incoming `[crosstalk] mailbox <ID>` notification, read `~/.claude/crosstalk/mailbox.md` and handle it without starting a new run.

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

Before creating a new Ghostty peer, read the new-peer permission choice in `~/.claude/crosstalk/mailbox.md` and ask whether to retain CLI defaults or explicitly auto-approve this launch. Reusing an existing peer does not ask again or change permissions.

With a topic on Ghostty, use Codex by default. If the user explicitly requests agy/Antigravity, set PEER_KIND=antigravity and use that same target for sending:

```bash
PEER=$("$BRIDGE" ensure-peer claude "${PEER_KIND:-codex}")
```

This reuses a labelled Codex in the same tab or splits right and starts Codex in the current directory. On startup timeout, let the user finish login/trust prompts in that existing pane; do not launch a duplicate or bypass permissions.

On Ghostty, read `~/.claude/crosstalk/mailbox.md` and use its send/receive/reply flow with the unchanged topic. Do not execute the legacy file/ping analysis flow for a new Ghostty discussion. On cmux, run `/crosstalk:launch` if peers are missing and then continue `/crosstalk:analyze`.

For an incoming Crosstalk peer message, read the task file named in the message and follow its response/ping instructions instead of starting another run. For a completion callback, restore that run's manifest and continue its existing analysis rounds; do not launch a new run.

Ghostty's first binding requires a unique working directory. If ambiguous, run `/crosstalk:setup --surface ghostty:<UUID>` once from this CLI after selecting its candidate ID; never select an arbitrary same-directory terminal. List IDs with `osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'`.
