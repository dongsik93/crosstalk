# Recovering Crosstalk work

The ordinary-message sections below apply to `mailbox-v2`; use the discussion-v1 section for engine actions and do not raw-reply/ack managed messages.

Start with `crosstalk doctor --offline`, `status <ID>` and `history <ID>`. These inspect; they do not execute messages, launch peers, or repair installation. Both participants must use the same `CROSSTALK_CONFIG_DIR`. Status/history default to a page; use `--limit` and `--offset` to inspect remaining rows.

## Saved request, missing notification

A result with `saved=true` means the message is already stored. Check its recipient binding and delivery state. `submitted` is not receipt; `unknown` is not proof of no delivery. Once the exact target is verified, run `crosstalk retry <ID>` for the same notification. Never send a replacement with a fresh ID. If output was lost, find the original in status/history before doing anything else.

## Peer stopped after receipt

Check the effective recovery state, claim version, attempts and previous owner. A lease's expiry does not prove the old process stopped or that no file was changed. Inspect history and external work first. Bind the intended new execution to the same logical session through a fresh target challenge and explicit transfer; see [protocol 2](protocol-v2.md).

After the user authorizes resuming that exact work, reclaim it:

```sh
crosstalk recover <ID>
crosstalk recover <ID> --reclaim --expected-claim-version <N> --confirm-external-effects
```

Retain the new token privately and process the returned same message. Never reuse an old token, reset attempt counts, automatically kill the former CLI, or silently make a fresh thread. A claim limit failure preserves the message for inspection. A new thread after manual review is a separate explicit request.

## Reply saved, caller interrupted

Inspect the completed request and its linked reply before asking the peer to repeat analysis. Retry reply notification only when needed. The caller claims the queued reply with receive and persists its comparison through ack, or creates one atomic follow-up with `send --after-reply`. If the reply was already claimed and interrupted, recover that reply explicitly. If ack/follow-up already committed, use its saved outcome/link. Do not duplicate a round after lost command output.

## Several panes or a resumed CLI

Use session status and exact pane candidates. The user chooses the target; that target executes its own handshake. Same cwd, kind, label, focus or CLI session ID does not prove a new pane's ownership. For Codex, supply the newly selected exact `CROSSTALK_SURFACE_ID` and shared config root in each tool invocation. Strict identity rejects CODEX_THREAD_ID cache alone even while its previous pane is alive. Do not reuse an old remembered or inherited surface after resume. Keep the old binding until an explicit validated transfer. Review the repository context and history before handing over work; old generation claims cannot commit afterward.

## Interrupted deep review

Do not stash-pop or restore a branch in the original repository. Use `crosstalk review status <RUN_ID>` to inspect the owned worktree and pinned SHAs. Preserve unfinished artifacts and changes; confirm execution has stopped before finish/cleanup. Dirty, untracked, ignored, changed-HEAD or unowned worktrees remain intact. See [review safety](review-safety.md). Cowork cleanup similarly requires confirmed stop and ownership and never uses force removal.

## Interrupted upgrade

Run doctor offline and inspect the installation phase, active runtime, schema and verified migration backup. A missing runtime module is diagnosed before importing it (`INSTALLATION_INCOMPLETE`, exit 7); run the installer from an intact source copy, retaining the same config directory and installation home. Do not delete the DB or replace it with an old backup. Resume the same release through the [installer procedure](upgrade-v0.11.md). A v2 DB with new writes cannot be rolled back by restoring v0.10 data without losing those writes. Prefer a compatible v0.11 runtime or forward fix. Reload old CLI instructions before handshake; do not allow tokenless legacy writes.

`/crosstalk:resume` and `$crosstalk resume` resume only the raw topic preserved after preparation failed. They must not replace any already saved message. Cancellation stops result acceptance, not external processes. There is no automatic retry daemon or external exactly-once guarantee.

## Discussion-v1 runs (v0.12)

Inspect `run status <RUN_ID>`, `run next <RUN_ID>` and an explicit `run report <RUN_ID>`. These do not take work or advance the run. Use the canonical [discussion workflow](../assets/codex-skills/crosstalk/discussion.md); ordinary mailbox-v2 threads retain the sections above.

| Observed point | Continue the saved work | Do not do |
| --- | --- | --- |
| Preparing run/pending peer | Reuse the saved start operation and exact pending pane. If not already selected, attach its `--peer-surface` or logical `--peer-session` with `run continue --operation-id`; complete readiness, then advance the same run. | Start a replacement run or guess another peer. |
| Peer result exists, caller initial pending | Submit the caller's fixed initial action first. | Leak the peer body through history/report/export or alter the first analysis after disclosure. |
| Peer request claim interrupted | Rebind if needed, explicitly recover that message, then `run take <ACTION_ID> --lease-token <NEW_TOKEN>`. | Add another round or bypass the claim. |
| Caller comparison claim interrupted | Recover the same peer reply, retake the same compare action and decide from stored results. | Ask the peer to analyze the same input again. |
| Caller local initial binding changed | After validated transfer, `run continue <RUN_ID> --operation-id <ID> --confirm-rebind` reissues the local epoch; take again. | Treat this local handle as a mailbox lease or submit its old epoch. |
| Decision saved, finalizing | `run advance <RUN_ID>` constructs the report from saved inputs. | Call an AI for another conclusion. |
| Report export failed | Retry `run export <RUN_ID>`; overwrite only by explicit choice. | Restart the completed discussion or delete a user file. |
| Paused/cancelled | Continue a pause explicitly or inspect the partial cancelled transcript. | Infer that processes/external edits stopped or revive cancelled work. |

`run continue` does not reclaim expired leases, `recover` does not release workflow pause, and `retry` only resubmits a notification. Managed raw reply/ack/send returns `RUN_MANAGED_BY_ENGINE`; it is not a reason to remove the guard. Completed ask replies are informational and need no fake read/ack to finish the run.

For schema 3 use [v0.12 upgrade guidance](upgrade-v0.12.md). Preserve existing thread ownership and protocol-3/engine-1 readiness for new runs. Same-user direct DB access or viewing neighboring panes remains outside the API disclosure barrier.
