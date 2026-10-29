# Discussion engine 1

v0.12 introduces an explicit, opt-in Ghostty workflow for one Claude/Codex caller and one Claude/Codex/agy peer. It stores the next work in SQLite; it does not run a daemon, call model APIs, appoint an LLM referee, force agreement, or certify an answer's truth. Supported runtime numbers are release 0.12.0, schema 3, protocol 3 and engine 1. Result payload schema 1 is a separate contract.

The canonical executable workflow is [discussion.md](../assets/codex-skills/crosstalk/discussion.md). Claude commands, Codex skill routing and agy peer routing refer to that one document. The actual CLI `--help` and strict result validators define the accepted arguments and fields.

## Ownership and atomicity

A new run fixes its caller, versions, execution driver, original topic, prompt templates and actual rule/persona contents. Preparation records an explicitly selected `--peer-surface` and/or `--peer-session`; both must identify the same verified binding before the first request fixes the logical peer. A preparing run with no selected peer does not adopt a newly appearing same-kind pane: attach the intended target with `run continue --peer-surface` or `--peer-session` and a stable operation ID. Stored selectors cannot be changed, and participant-selection flags are rejected after preparing. Existing threads remain `mailbox-v2`; new threads use `discussion-v1`. Old `RUN_ID` file/ping conversations remain legacy. Owner/default changes do not transform existing work, and an engine error never creates a fallback legacy run.

`engine.service` owns each write transaction and composes mailbox internal mutations on the same connection. A peer reply and its engine result link commit together; a continue decision, reply acknowledgement, next request, round and actions commit together. Terminal submission and export happen after commit. There is no second engine lease timer or attempt counter.

Operations are scoped by actor, command kind and stable operation ID. Identical retries return stored IDs/results; different semantic payloads conflict. Completed operation results are checked before new-transition state checks, so a lost stdout result can be recovered after the run advances. Topic/body whitespace and Unicode are preserved, not normalized into a different user request.

## Lifecycle and phases

Lifecycle is `active|paused|completed|cancelled|failed`. Phase is `preparing|collecting|comparing|finalizing|terminal`. A round counts a logical peer request, not tool calls, delivery attempts or recoveries. The fixed round limit is 1–10, default 10.

| Work | Input and completion |
| --- | --- |
| `local_initial` | Fixed original topic/config; no self-send or lease. First valid result is immutable. |
| `peer_analysis` | Fixed peer request; existing mailbox request claim owns its result. |
| `compare` | Fixed caller position plus exact current peer reply; that reply's existing claim owns the decision. |
| `finalizing` | A saved finish decision is rendered into DB JSON/Markdown without another AI call. `run advance` can finish after interruption. |

The four engine tables are `discussion_runs`, `discussion_rounds`, `discussion_actions` and `discussion_operations`. Peer body text remains canonical in its mailbox reply, referenced by the action; local results and decisions are stored on their actions. Events reuse the existing events table without logging bodies/tokens.

## Initial-position disclosure barrier

The caller must store its first independent analysis before normal APIs expose the peer's first body or conclusion summary. The barrier covers notifications, receive dispatch, history, status excerpts, report and export. Before then only result existence/state is visible. The peer's first task also does not contain the caller initial result.

This orders disclosures through Crosstalk APIs. It cannot isolate an AI's existing context, a human reading a neighboring pane, or another process under the same OS user reading the DB. Cancelling can reveal a preserved partial transcript; it cannot turn that run back into a normally independent completed run.

## Managed dispatch and result integrity

`receive` routes ready managed work with `handler=discussion`, run/action identity and structured `next_action`; it does not claim or expose the task. `run take` claims peer/compare work and returns its fixed input, action epoch/digest and current mailbox handle. Local take is read-only. Barrier-blocked replies and informational ask results do not block other actionable queue entries.

Raw `reply`, `ack` and `send --thread` cannot mutate managed messages. The service's internal transaction path validates owner/run/action relations; it is not enabled by a secret environment variable. Engine-owned messages still use the same lease token, claim version, binding generation and recovery attempt limits as ordinary mailbox work.

JSON rejects unknown fields, duplicate keys, non-finite numbers and wrong types. Topic/analysis body limits are 1 MiB UTF-8; decision JSON is 256 KiB; a rendered task is 4 MiB. Oversized input fails explicitly without truncating the original. Evidence references distinguish accessible internal action/message IDs from external url/file/claim assertions marked `reported`, not independently verified.

## Decisions and outcomes

Analysis has body, optional display summary, categorical confidence, assumptions, unresolved questions, evidence refs and explicit peer verdict. An `agree` verdict alone cannot conclude a run. Compare decisions cite both current result IDs and preserve the caller's position, comparison summary, unresolved questions and closing summary.

- `finish/concluded`: the caller's comparison conclusion, not a global proof of consensus.
- `finish/diverged`: disagreement or different conditions retained.
- `finish/unresolved`: insufficient information retained.
- `continue`: needs a follow-up body and reason; caller position is fixed before the next peer reply.
- `round_limit`: requested continue becomes applied finish using the already supplied closing summary, with explicit override reason. No extra request is created.

Ask has local initial and one peer result but no comparison, follow-up or caller reply wake-up. Once both are stored it ends as `sampled`. Its informational peer reply is not falsely acknowledged as read and does not become stuck inbox work. Explicit report shows the individual answers without a new AI summary.

## Recovery and reporting

`status`, `next`, `report` and doctor are read-only. `advance` only applies saved deterministic transitions; it does not think, reclaim expired leases or repeatedly retry uncertain input. See [recovery](recovery.md) for message retry/recover versus workflow continuation.

Pause holds new work/claims/notifications. Already running peer analysis may save a valid result, but paused compare cannot decide a next round. Cancel preserves confirmed material while revoking unfinished result acceptance; it does not stop external processes or undo files.

After caller rebinding, an authorized `run continue --confirm-rebind` reissues an unfinished local action epoch; old local handles fail. Remote peer/compare work instead needs the existing message recover procedure and its new claim. Neither procedure silently changes the fixed logical participants.

DB JSON/Markdown is the final-result source of truth. Export uses fixed internal run paths, preserves existing files unless overwrite was explicit, and never reruns the discussion after I/O failure. Cancelled/failed reports are partial and identify missing material. Lifecycle outcome is not a semantic quality score.

## Activation status

`run start` is explicit engine opt-in. Capability `engine_default=false` keeps normal new-user entrypoints on ordinary mailbox behavior until actual supported paths meet the live gates. The current [verification record](verification-v0.12.md) states what ran; source/test existence is not proof of real terminal success.
