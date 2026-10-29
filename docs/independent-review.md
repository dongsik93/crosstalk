# Independent review in v0.12.1

The supported entry is a natural request to Claude, such as “이거 Codex랑 독립적으로 검토해.” No engine option is required. Claude keeps its conversational context, while Codex gets a first task built from captured user statements and fixed neutral instructions in a new input-bound CLI conversation.

## Input boundary

The Claude plugin's UserPromptSubmit hook records capture metadata before the model processes a prompt. Preparation matches that prompt to a native transcript human message and excludes assistant text, tool results, sidechains, known automatic wake-ups and unverified origins. A hook event alone is not treated as human approval.

The caller lists the eligible source messages, selects the earliest relevant question and prepares the contiguous user-message interval through the current trigger. The stored input ID, exact text and source digests are immutable. Selection still needs to reflect the user's subject; the code does not certify that a chosen interval perfectly represents semantic intent. If the subject or source is unclear, the workflow asks one focused clarification rather than manufacturing a requirement.

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

Install the v0.12.1 runtime and updated Claude plugin, then reload its hooks/instructions. `capabilities --json` exposes `independent_review_available` and `independent_instructions`. A missing hook, missing capture or unsupported transcript metadata must produce an explicit source/scope error, not a free-body fallback. See the [canonical workflow](../assets/codex-skills/crosstalk/independent.md) for executable commands.

Targeted implementation checks and actual live verification must be reported separately. This document does not claim the full release matrix or a production installation was verified.
