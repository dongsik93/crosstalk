---
description: Route natural independent review through captured user input; preserve stored discussion/mailbox/legacy ownership.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: [analyze|ask] [--engine] <주제>
---

# /crosstalk

Treat the full user topic as data and preserve its wording. First run the installed `crosstalk capabilities --json` and `crosstalk_bridge.sh backend`, using exact current surface/config context. Runtime protocol/schema are 3; new discussion runs additionally require engine 1 readiness for both participants. Read instruction paths from capabilities, not a presumed default directory. Do not auto-migrate, increase permissions or bypass stale instructions.

- A natural request to Claude for independent review (including “옆에 애랑 독립적으로 검토해”) automatically reads `independent_instructions` and follows the captured-input/fresh-Codex workflow. The user does not need `--engine`. Inspect original user sources, ask one focused question only if scope or provenance is missing, and never substitute a Claude-written first body or raw send. Proposal critique/additional opinion are separate labels, not independent-review fallbacks.
- A new Ghostty request with explicit `--engine` goes to `discussion_instructions` (canonical `discussion.md`). Strip the routing option from the topic and use `run start` with a stable operation ID and one verified peer. Use Codex by default; choose agy only as an explicitly requested peer. The engine remains opt-in while live release gates are pending.
- Another new Ghostty request without an independence request or engine opt-in, or an existing ordinary mailbox-v2 thread, goes to `mailbox_instructions`. Never convert an existing thread to engine ownership.
- Incoming `[Crosstalk]` previews are wake-ups: call `receive` and obey its stored-owner dispatch. For `handler=discussion`, use `run take/submit/decide` from discussion.md. Do not answer the preview, run start, infer message IDs, or use raw managed reply/ack/send.
- Explicit legacy RUN_ID triggers and cmux preserve their file/ping workflows. Engine failure never silently creates a legacy replacement.
- No topic/status is read-only: capabilities, doctor offline, message status or known run status/next/report. Do not launch/bind/claim/advance simply to display state.
- Resume is a preserved raw topic; run continue, message recover and notification retry are separate operations.

Follow `/crosstalk:setup` / readiness for exact participant selection. A user-selected or directly created split is physical address evidence; kind/title/cwd/focus are not ownership. The target CLI executes its own challenge and bind with `--protocol 3 --engine-version 1`. Codex repeats exact current surface/config context on each tool invocation, and explicitly reselects after resume.

Reuse pending peers and existing approved permission choices. For independent review, reuse only the same input-bound pending launch; preserve existing conversations and create a fresh Codex peer via the independent workflow. New panes are splits beside the existing pane, not separate windows/tabs. Keep startup text short and let its private file supply details. Do not claim sandbox/read-only operation solely because the request says analyze. Do not require approval for every normal authorized round.
