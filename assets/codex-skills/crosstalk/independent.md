# Natural independent review — Claude caller, fresh Codex peer

Use this workflow when the user asks Claude to review independently with Codex, including ordinary conversation such as “야, 옆에 애랑 독립적으로 좀 검토해.” The user does not need to name an engine, add `--engine`, or repeat the whole topic. This route takes priority over ordinary mailbox routing. Currently it supports a Claude caller and a Codex peer on Ghostty; do not silently substitute an unsupported caller/backend or label an ordinary opinion as independent review.

The caller keeps its existing conversation. The peer is a new Codex CLI conversation launched for this input, not a reset or reuse of the already-open Codex. Project instructions, memory and shared files may still affect it. This is protection against forwarding the caller's private first opinion through Crosstalk, not proof of an unbiased model or an OS sandbox.

## Readiness and capture

Read `independent_instructions` from the installed runtime's `capabilities --json`; require `independent_review_available=true`. Preserve the exact runtime path, current `CROSSTALK_SURFACE_ID` and shared `CROSSTALK_CONFIG_DIR` on every tool invocation. Caller readiness uses the existing protocol-3/engine-1 handshake in `readiness.md`. Keep the installed plugin's UserPromptSubmit capture hook enabled and reload the plugin/session after installing this version.

The hook supplies a capture ID in tool context. It records a prompt digest and native transcript location, then preparation checks the matching native human-message metadata. Hook arrival by itself is not human authorization. Known wake-ups, tool results, assistant messages and unverified origins must not become user requirements.

```bash
CT="$HOME/.claude/scripts/crosstalk"
BRIDGE="$HOME/.claude/scripts/crosstalk_bridge.sh"
"$CT" input sources "<CAPTURE_ID>"
```

If the hook ID is not in current context, `input sources` without an ID inspects this actor's latest capture. Do not fabricate a capture event, transcript, origin flag or approval to make the command succeed.

## Select the user's subject without rewriting it

Inspect the returned user-message IDs and original texts. Select the **earliest relevant user question** for the current task; preparation includes the contiguous eligible user messages from there through the current trigger, including later constraints. Do not select only the last constraint, omit a contrary requirement, or use an assistant draft as the subject.

```bash
"$CT" input prepare "<CAPTURE_ID>" --from-message "<EARLIEST_RELEVANT_USER_MESSAGE_ID>"
```

Retain the returned `input_id`. The engine will use its saved text and source references; do not rewrite it into a new first body or append background, recommendations, a proposed answer, rules, persona or a summary containing your opinion.

If the subject is clear from those user messages, proceed. Only if “이거” lacks a usable subject, the selected scope would require guessing, or provenance cannot be established, ask one focused clarification. Let the user's next actual answer be captured, inspect sources again and prepare the appropriate interval. Do not ask for approval every round or require the user to type engine options. “Yes” to an assistant proposal is not a self-contained substitute for the missing question; do not promote the assistant's prose into a user requirement.

## Start the saved run, then prepare a new peer

Use one stable operation ID for this start and preserve it on retries:

If an earlier analyze run is still active, do not start a duplicate. When the user explicitly asks to restart that review independently, cancel the old run with that reason and preserve its stored results, then start this fresh review. Do not kill or reset its participant CLI. If it is unclear whether the user means a new review or the existing run, ask one focused question.

```bash
"$CT" run start codex --input-id "<INPUT_ID>" --review-mode independent --operation-id "<START_OPERATION_ID>"
```

Do not pass positional topic text, `--stdin`, `--rules` or `--persona`. The first independent task uses fixed neutral instructions and the recorded user input. Existing first-position disclosure barriers and generic notifications remain in force. A raw `send` rejection is a routing guard, not an invitation to try another transport.

A preparing run keeps the input without guessing an existing peer. Launch a new Codex conversation for this same input:

```bash
"$BRIDGE" launch codex --fresh-for-input "<INPUT_ID>"
```

Use default permissions unless the user already explicitly authorized auto-approval for this launch; only then add `--auto-approve`. Never add resume/fork/continue flags, clear an existing conversation or close a user's existing pane. Keep the short startup message and split beside the caller's existing pane, not a separate window/tab.

The launcher records the exact new surface and its launch evidence. A retry with the same input reuses its pending launch, including a login/approval wait; do not create another pane. Keep both the saved run and input IDs. When the returned peer has completed its own handshake, attach the exact surface:

```bash
"$CT" run continue "<RUN_ID>" --peer-surface "ghostty:<RETURNED_NEW_SURFACE>" --operation-id "<PREPARE_OPERATION_ID>"
```

The runtime checks that the launch belongs to this input, the bound Codex process/session matches, its binding generation is initial and it has not already participated in another Crosstalk message. An existing or unverified conversation must not be described as new. Do not bypass a failed check by switching to free-body `run start`, raw mailbox or legacy commands.

## Analyze first, then exchange opinions

Follow the existing `discussion.md` action workflow: `run next`, `run take`, analysis `run submit`, then `run decide` with the exact action/lease/input references. Each participant stores an immutable first answer. The caller cannot see the peer's first answer before storing its own; the peer receives no caller first position in its initial task.

Once both initial results are stored, comparisons and later questions may exchange positions and reasons normally. Keep changed opinions in later decisions rather than editing the first analysis. A `[Crosstalk]` notification is a wake-up for the saved run, never a new independent request. Receive and dispatch by stored owner; do not prepare another input or start a new run from it.

## Other review intents

When the user explicitly asks to critique Claude's proposal, use an engine run labeled `--review-mode proposal_review` with the proposal body. That input is intentionally opinionated and is not independent alternative analysis. `--review-mode additional_opinion` labels a further opinion using existing context. Ordinary `analyze/ask --engine` remains available for other engine discussions, and ordinary mailbox/legacy work keeps its existing owner.

If the user asks for independence, never silently choose one of those weaker modes. Explain a genuinely unavailable source/context and ask the one clarification needed, rather than claiming the protected route ran.
