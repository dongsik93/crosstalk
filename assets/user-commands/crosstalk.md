---
description: Run Crosstalk through verified Ghostty protocol-2 sessions, or retain cmux legacy workflows.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: <분석 주제>
---

# /crosstalk

Use the full `$ARGUMENTS` as the raw topic. Preserve its wording.

```bash
CT="$HOME/.claude/scripts/crosstalk"
BRIDGE="$HOME/.claude/scripts/crosstalk_bridge.sh"
"$CT" capabilities --json
BACKEND=$("$BRIDGE" backend)
```

On Ghostty require protocol 2, supported schema and healthy installation. Read the exact `mailbox_instructions` path returned by capabilities. If runtime or instructions are old/partial, show the upgrade/reload action. Do not automatically migrate the DB or fall back to tokenless v0.10 commands.

Incoming `[Crosstalk] 질문:/답변:/Question:/Reply:` previews are wake-up hints. Follow the installed mailbox instructions: receive one queued message, process its full body with its lease, then reply or ack/atomic follow-up. Do not answer previews, infer IDs, create a new run, or use legacy ping. For old `[crosstalk] mailbox <ID>` wake-ups, receive that ID without replay. Explicit legacy `RUN_ID` triggers instead keep their task-file/response/ping workflow.

No topic: show capabilities, `doctor --offline`, and read-only status. Do not launch peers, label, bind, claim, or repair just to display readiness.

With a Ghostty topic, follow `/crosstalk:setup` to verify caller and peer bindings. Use `bridge strict-self` for exact caller identity; if it cannot identify this pane, retain the topic with `pending-save`, show candidates, and let the user select the intended pane. A label/cwd/focus is not identity proof. `--surface` explicitly selected by the user can be bound in that CLI's own context. Do not run another CLI's bind on its behalf. For a Codex participant, every protocol-2 tool invocation must explicitly supply its current target `CROSSTALK_SURFACE_ID` and shared `CROSSTALK_CONFIG_DIR`; a thread cache or previous bridge bind alone is not proof. After resume/restart reselect its exact target and handshake, never reuse the former pane ID from conversation memory.

Use Codex by default, or Antigravity only when requested. `bridge ensure-peer claude <peer-kind>` may reuse an existing candidate or open a native split. A new launch must finish protocol-2 handshake; an existing label alone is insufficient. Inspect `session status` before sending. Use CLI default permissions unless the user explicitly selected auto-approval for this launch. Preserve pending panes on timeout; do not create duplicates, restart peers, or increase permissions.

Then follow the mailbox instructions to send the unchanged topic. A saved request remains saved even if notification is unknown: use its status/history and retry the same ID, never a replacement request. Ask has no automatic callback/discussion. `resume` resumes a topic retained after preparation failed; stored message recovery uses `recover` with explicit authorization.

On cmux retain `/crosstalk:launch` and `/crosstalk:analyze` legacy flows. A Ghostty identity error does not justify switching to cmux.
