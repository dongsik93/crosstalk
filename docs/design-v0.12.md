# v0.12 implementation baseline and design

## Verified starting point

The supplied proposal was written against remote v0.10.6 without access to the v0.11 implementation. This work starts from the actual pushed v0.11 commit `0d8a24e692bfde2ee3ee61fe84731050b85b0c0f`. No v0.11 tag exists in this repository; that immutable commit is the source baseline, not an invented release tag or a claim that every original v0.11 release gate passed.

The pinned source was extracted to a separate temporary directory before executing its tests. All twelve scripts passed: 123 unittest cases plus the original bridge/mailbox integration scripts. Local evidence is `.dsgoal/artifacts/v012-baseline.txt`. The fixture archive `tests/fixtures/crosstalk_v0_11.zip` contains only the prior executable/package source and its commit metadata, never a user DB or credentials.

## Mapping the proposal to existing code

| Required foundation | Actual v0.11 implementation | v0.12 integration |
| --- | --- | --- |
| SQLite connection / writer ownership | `db.connect`, `db.transaction`, schema version 2 | Same DB and short top-level transaction; explicit schema-3 migration. |
| Request/reply persistence | `mailbox.send`, `reply`, `ack`, `complete` | Extract connection-scoped mutations; engine service owns the transaction and related run writes. |
| Claim/fencing | `mailbox.claim`, `lease`, `current_binding`, `renew`, `recover` | Reuse message leases for peer and compare actions; no second lease/attempt counter. |
| Session identity | `sessions.identity`, `actor`, `challenge`, `bind` | Add explicitly confirmed protocol/engine readiness; retain exact surface, instance and generation checks. |
| Delivery/outbox | `delivery.seed`, `latest`, `notify`, `bridge` | Preserve saved-before-input and attempt semantics; managed summaries and run holds must be checked before input. |
| Installation and repair | `installer.install`, `_stage`, `_check_runtime`, manifest/current pointer | Include recursive engine/adapter/templates and require successful runtime health before activation. |
| Original checkout protection | `reviews.prepare`, `finish`, `cleanup` | Preserve the existing cmux review safety implementation; no Ghostty port. |
| Startup UX | `ghostty_launch`, private startup file, short prompt | Preserve short visible text, exact split target, explicit per-launch permissions and pending reuse during adapter extraction. |

## Versions and compatibility

Release is `0.12.0`, DB schema and message/command protocol are `3`, discussion engine and prompt bundle are `1`. Existing v2 database values, message sequence, claims, replies and binding generations must survive migration unchanged. Existing threads become explicitly `mailbox-v2`; they are not reconstructed as engine runs.

A protocol-2/engine-0 session binding can continue ordinary mailbox work. It cannot start or execute a discussion action merely because the new files are on disk. Protocol-3/engine-1 challenge and bind are explicit readiness acknowledgements. Rebinding still invalidates old claims; unfinished local engine actions require a separate confirmed continuation/epoch change.

The v0.11 executable must reject schema 3 before writing or notifying. Tests execute the archived real runtime to verify that property. No automatic down-migration or overwrite with a stale backup is provided.

## State and transaction boundaries

The engine owns four tables: runs, rounds, actions and idempotent operations. Thread/message ownership identifies the handler permanently. `engine.store.SCHEMA` is appended to the common schema; storage helpers do not commit independently.

Initial analysis is a local action with an immutable input digest and binding/epoch handle, not a self-addressed mailbox message. Peer actions use request leases; comparison actions use reply leases. A single service transaction composes related message mutations, decisions, next-round creation, run changes and operation results. UI input and export happen after that transaction.

The caller cannot obtain the first peer answer or its revealing summary through normal API paths before saving the caller's initial result. Managed receive dispatches an action without claiming or returning its body. Raw managed reply/ack/follow-up mutations are refused; history/status/report/export and notification paths share the disclosure policy. This is an API ordering barrier, not an OS sandbox or a guarantee against looking at the adjacent pane.

Ask saves two independent answers and becomes sampled, without a comparison action, next round or caller reply wake-up. Its stored informational reply is excluded from actionable inbox work without inventing a human read acknowledgement.

Finish stores a decision and finalizing state before deterministic report construction. Advance can finish that saved work after interruption; it never calls a model or automatically reclaims a lease. Export writes the saved report and cannot change its conclusion.

## Activation and validation boundaries

New discussion execution remains explicit opt-in until its supported entrypoints have real verification. Existing ordinary mailbox and cmux RUN_ID flows keep their handlers. Unsupported combinations fail explicitly rather than replaying a run through a different engine.

Live verification respects the user's established operational preferences: split an existing intended pane, retain short startup text, and do not launch cmux for live checks. Mock cmux compatibility checks remain part of automated adapter regression. Any unexecuted full release scenario must be recorded, not treated as passed.
