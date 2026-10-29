# Changelog

## 0.12.0 — unreleased

Discussion engine 1 is explicit opt-in (`run start`, or analyze/ask `--engine`) while live gates remain pending. Runtime protocol and database schema move to 3; existing mailbox-v2 threads retain their owner and behavior. The source baseline is v0.11 commit `0d8a24e692bfde2ee3ee61fe84731050b85b0c0f`.

- Store run/round/action progression, immutable inputs/results and operation-id retry results beside the existing mailbox.
- Compose peer reply, comparison ack, next request and engine transitions in the same SQLite transaction; reuse existing leases, recovery and binding fencing.
- Withhold the first peer body/conclusion through normal APIs until the caller submits its own initial analysis; this is disclosure order, not a security sandbox or truth guarantee.
- Preserve caller comparison provenance and distinguish concluded, diverged, unresolved, round_limit and partial results. Finalization/export reuse saved decisions without another model call.
- Keep ask as single-result sampling: no comparison, follow-up, caller reply wake-up or synthetic acknowledgement of unread informational results.
- Separate built-in CLI launch specifications from exact terminal operations, preserving short startup, native splits, pending-pane reuse and explicit per-launch permission choices.
- Add owner-aware dispatch and guards, protocol-3/engine-1 readiness, explicit schema migration, recursive package/template inventory and ordinary-thread continuation.

Not added: daemon workers, direct model API, new AI/terminal backends, agy caller, multi-peer quorum, model/effort control, Ghostty cowork/review, forced consensus, or lossless down-migration. See [v0.12 verification](docs/verification-v0.12.md); configured tests and historical live results are not release acceptance.

## 0.11.0 — baseline implementation

Reliability implementation for mailbox protocol 2 / schema 2. Release readiness remains subject to the automated and actual-terminal checks in [verification](docs/verification-v0.11.md).

- Separate logical sessions, execution instances and physical pane bindings; exact challenge handshake and generation fencing replace ownership inferred from labels/cwd.
- Add claim leases, explicit recover/renew/cancel, reply acknowledgement, and atomic next-round creation. Requests and replies both retain interrupted processing state.
- Distinguish durable save, notification submission, receipt and processing completion. Read-only doctor/status do not repair or consume work.
- Replace response eval with JSON verdict fields. v2 verdicts are explicit arguments, not body markers.
- Isolate deep review in owned detached worktrees at pinned commits; preserve dirty/untracked/ignored or uncertain worktrees during cleanup.
- Keep startup text short; load the full handshake from a private temporary file, remove it after success, and retain it for a failed startup retry.
- Diagnose missing runtime modules before import; restore verified replacement generations while preserving damaged files and DB/config, and reject unhealthy JSON diagnostics before activation.
- Add explicit backed-up schema migration and staged installation with a manifest; preserve user settings, DB, backups and unfinished review work on uninstall.

Compatibility changes: Python 3.11+; v0.10 runtimes cannot write schema 2; loaded CLI instructions must be refreshed before handshake. `receive ID --replay` no longer reclaims work: inspect `recover ID`, then explicitly authorize reclaim of that message. New replies require valid leases; follow-ups require the source reply's claim. `resume` continues a preserved topic and is separate from recover. cmux legacy RUN_ID/file/ping workflows remain; Ghostty cowork/review, unattended recovery, numeric confidence, and external exactly-once execution are not added. Safe cleanup may retain older worktrees without ownership records.

No claim is made here that unexecuted tests, live integrations or release gates passed.
