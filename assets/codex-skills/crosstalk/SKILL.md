---
name: crosstalk
description: Run or resume Crosstalk discussions with verified Ghostty sessions; preserve ordinary mailbox and cmux legacy workflows.
---

# Crosstalk for Codex

Use this skill when the user invokes `$crosstalk` or asks Codex to act as a Crosstalk caller. Read `readiness.md` for exact current-pane context and runtime health. Every Codex tool invocation supplies the verified current `CROSSTALK_SURFACE_ID` and shared `CROSSTALK_CONFIG_DIR`; a thread cache is not proof after resume.

Run the installed runtime's `capabilities --json` before routing. v0.12.1 advertises protocol 3/schema 3 and discussion engine 1. Read the instruction path returned by capabilities rather than guessing a config-directory path. Reload stale instructions; never auto-migrate or weaken a missing capability/lease check.

## Route by stored owner, not by preview text

- A `[Crosstalk]` notification is a wake-up, not a new user topic. Call `receive` without an ID. If it returns `handler=discussion`, read `discussion_instructions` (canonical `discussion.md`) and use the returned action with `run take/submit/decide`. Never create a new run from a notification or call raw reply/ack/send on managed work.
- An ordinary `mailbox-v2` envelope follows `mailbox_instructions` (`mailbox.md`). Existing old ID-bearing `[crosstalk] mailbox <ID>` notifications may receive that ID, but dispatch still selects the stored owner. No `--replay` reclamation.
- An explicit legacy `RUN_ID` trigger keeps the matching file/ping workflow below. Do not interpret engine run/action IDs as RUN_IDs.
- Natural independent-review requests in the supported Claude-caller flow use `independent_instructions` automatically, without requiring the user to know `--engine`. As the Codex peer, execute the returned managed action without fetching Claude’s private conversation or beginning another run. A Codex-caller request cannot silently claim this Claude-capture protection; explain the supported entry if requested.
- New Ghostty `analyze --engine` or `ask --engine`: explicit engine opt-in; read `discussion_instructions` and start exactly one caller/peer run. The caller is Codex, default peer Claude; agy is peer-only and selected only when requested.
- Other new Ghostty requests without an independence request or explicit engine opt-in retain the ordinary mailbox workflow while v0.12 live gates are pending. Do not switch existing work between owners, even if defaults later change.
- New cmux requests: use the legacy analyze/ask files. Engine support is not implied on cmux and failure never silently falls back to another transport.
- Empty invocation or `status`: read `status.md`; inspect only, without launching, binding, claiming or repairing.
- `launch`: read `readiness.md`; reuse a verified candidate/pending pane or create an authorized native split beside the existing pane.
- `resume`: read `resume.md`; distinguish a saved raw topic from a stored run and message recovery.
- `run status|next|report|pause|continue|cancel|advance|export` or an engine-managed action: read `discussion.md` and use the actual CLI help. Normal rounds do not need fresh user approval.
- `recover`: diagnose first; only reclaim the exact interrupted message after user authorization. `retry` is notification-only, and `run continue` is workflow/local-handle continuation.

## Legacy files

Only cmux and explicit legacy RUN_ID conversations use these files:

- `analyze.md`: analyze, preamble and round triggers.
- `ask.md`: one-shot ask trigger.
- `callback.md`: `callback RUN_ID=... AGENT=... ROUND=... RESP=...`.
- `review.md`: review-round trigger.
- `cowork.md` / `cowork-stop.md`: cowork tasks and stop.

For a legacy run started by Codex, use `CROSSTALK_MODERATOR_KIND=codex` with bridge `start-run`. Follow its manifest, task-file, response and ping contract. Do not transplant those steps into a discussion-v1 run.

The full text after `$crosstalk` is the user's argument string; Codex does not have Claude-style `$ARGUMENTS`. Preserve the raw topic and store structured results through the owning workflow. No model/effort override, auto-permission escalation or new AI referee is part of this skill.
