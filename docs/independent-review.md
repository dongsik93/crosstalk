# Independent review in v0.12.2

The supported entry is a natural request to Claude, such as “이거 Codex랑 독립적으로 검토해.” No engine option is required. Claude keeps its conversational context, while Codex gets a first task built from captured user statements and fixed neutral instructions in a new input-bound CLI conversation.

## Input boundary

The Claude plugin's UserPromptSubmit hook records its native `prompt_id` before the model processes a prompt. Preparation matches that ID to exactly one human transcript entry's `promptId`, then checks its body digest. Identical text in an earlier or later event is never a substitute. If the event is not recorded yet, retry the same capture after it appears. A missing native event ID, duplicate event or content mismatch fails explicitly; older unstarted captures without this binding must be recaptured. Assistant/tool/meta entries remain excluded, and a hook arrival alone is not human approval.

The caller lists eligible source messages and selects the earliest relevant question through the exact current event. Both explicit and automatic ranges must contain substantive input; selecting a vague directive by ID does not bypass that check. Automatic selection is allowed only when there is a single substantive source; multiple questions/constraints require an explicit range instead of silently keeping only the last constraint. The input ID, exact text and source digests are immutable. These checks do not certify semantic completeness; genuinely unclear scope needs one focused clarification.

Mentions and quoted examples are candidates, not confirmed execution requests. Preparing a candidate cannot silently promote it to independent review. A clear request retains its guard while source verification is pending or fails; an explicit user cancellation releases the pending request. Known nonhuman events cannot establish or clear a human request. If capture fails before its head is stored, the hook blocks native processing of the requested prompt rather than only warning Claude. Hook process failure/timeout is configured to block as well. Intent classification remains conservative, not a claim of perfect natural-language understanding; there is no model-callable `ignore` or `approved` bypass flag.

Consumption is derived from the run's committed `capture_id`/`input_id` relationship in SQLite, written in the same transaction as run creation and its operation result. Retrying after a lost response does not depend on a separate marker write. Existing v0.12.1 runs can be recognized through their stored input ID and immutable bundle; marker files alone are never authoritative. Existing runs retain their original stored inputs and are not silently rewritten by this upgrade.

Independent `run start` accepts that input ID, not a new topic body or caller-selected rules/persona. Notifications remain generic. The pending independent request and active independent run cannot be replaced by a rewritten raw mailbox send through the normal workflow.

## New-context boundary

`bridge launch codex --fresh-for-input <ID>` starts a new native process without resume/fork flags. Its exact surface and process evidence are recorded for that input. Retries reuse the same pending launch. Run preparation verifies the receipt against the current binding, initial generation, Codex session identity and prior Crosstalk-message history before sending the first task.

The old pane is preserved. New panes are splits beside the intended caller, and permission expansion remains a separate per-launch user choice. Once first analyses are stored, subsequent rounds retain the same conversation and exchange arguments normally.

This is not symmetric amnesia: Claude retains prior context. A new Codex conversation can still load project instructions, memory and shared repository files. Native transcript and launch evidence are cooperation boundaries for normal Crosstalk paths, not cryptographic human authentication or protection against a malicious same-OS-user process rewriting those files.

## Intent labels and compatibility

- `independent`: captured user input, neutral first task, fresh Codex context and first-result barrier.
- `proposal_review`: critique an explicitly supplied proposal; the proposal's opinions are legitimate input and this is not blind alternative analysis.
- `additional_opinion`: obtain another opinion with existing context, without a fresh-context claim.

The protected intake currently supports Claude as caller and Codex as peer. Existing ordinary engine, mailbox-v2 and legacy threads keep their meaning; they are not retroactively labeled independent. General engine creation remains opt-in, but the natural independent-review route selects the protected engine automatically.

Install the v0.12.2 runtime and updated Claude plugin, then reload its hooks/instructions. `capabilities --json` exposes `independent_review_available` and `independent_instructions`. A missing hook, missing capture or unsupported transcript metadata must produce an explicit source/scope error, not a free-body fallback. See the [canonical workflow](../assets/codex-skills/crosstalk/independent.md) for executable commands.

Targeted implementation checks and actual live verification must be reported separately. This document does not claim the full release matrix or a production installation was verified.
