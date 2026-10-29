# $crosstalk status

Read-only inspection. Do not launch, label, bind, receive, retry, reclaim, create a DB, copy presets or advance a run to display status.

```bash
~/.claude/scripts/crosstalk capabilities --json
~/.claude/scripts/crosstalk doctor --offline
~/.claude/scripts/crosstalk status
```

For a known discussion run, use `run status <RUN_ID>`, `run next <RUN_ID>` or explicit `run report <RUN_ID>`. These do not claim messages or submit input. Show lifecycle, phase, round, exact participant roles, actionable blocker and a concrete next step. Keep submission/receipt/completion separate; no peer body or conclusion summary is exposed before the caller initial-position barrier. Ask results are sampled individual answers, not consensus.

Capabilities reports runtime/protocol/schema/engine versions and actual instruction paths. Session status distinguishes a compatible ordinary protocol-2 binding from protocol-3/engine-1 readiness. Every Codex tool call requires its exact current surface/config context as described in readiness.md. A label or same CLI thread cache is not readiness.

Use pagination for ordinary mailbox status/history. Missing DB or partial installation is a diagnosis, not authorization to initialize or repair it. The user may separately request notification retry, message recover, run continue, or installation repair; status does none of them automatically.
