# CLI and terminal adapter contracts

The v0.12 adapter boundary separates CLI execution details from physical terminal addressing. Engine policy never chooses a model, parses a terminal screen, or constructs arbitrary shell programs. Built-ins cover Claude, Codex and agy, and Ghostty/cmux; no downloaded plugin or arbitrary adapter path is accepted.

## Values

- `SurfaceRef(backend, native_id)` keeps backend and native identity separate. Its parser/address representation preserves the established Ghostty and cmux external address forms; it is not a logical session ID.
- `LaunchSpec` carries an absolute executable, argv tuple, cwd, allowed environment delta, bootstrap instruction, requested permission mode and startup timeout policy. PATH/config propagation preserves Unicode, spaces and quotes.
- `CapabilitySet` uses `supported|unsupported|unknown` with observation time and evidence. Unknown is not true merely because a version string looks recent.
- `SubmissionOutcome` distinguishes `submitted|failed|unknown`. Submission does not establish receive, analysis or completion.

## CLI side

`inspect_cli`, `identify_cli_context`, `build_launch_spec`, `build_bootstrap` and `describe_permission_mode` own executable discovery, allowed launch flags, bootstrap instructions and observed CLI evidence. Claude/Codex support caller and peer roles; agy supports peer only. Existing peer permission state may be unknown; desired flags are not proof that an existing session has those permissions.

Defaults retain existing CLI configuration and model/effort. Only an explicit per-launch auto-approval choice adds the corresponding CLI flag. Startup failure, timeout and analyze mode do not authorize permission escalation, retries through a different CLI, or a sandbox/read-only claim.

The visible startup prompt is short and points to a private instruction file. That file supplies the exact runtime/config/surface context and protocol-3/engine-1 challenge/bind. Success deletes it; failed startup retains it with the pending pane. Long bootstrap commands are not pasted into the normal initial user message. New panes use native splits beside an explicit existing anchor, not a guessed focused pane or a new window.

## Terminal side

The built-in registry selects a `TerminalAdapter` by an explicit supported backend. It supplies `capabilities`, `inspect_self_evidence`, `list_surfaces`, `exists`, `launch_peer`, `submit_input` and optional `capture`. `call_terminal(*args, timeout=...)` is the compatibility facade used by existing state-management callers. Tests may explicitly inject `CROSSTALK_BRIDGE`; production uses the restricted terminal driver.

The terminal driver receives only terminal operations. It does not interpret run phases, round decisions, verdicts or model configuration. Engine code calls adapters, adapters call terminal-only operations, and the legacy bridge remains a public compatibility wrapper. A terminal operation cannot recurse into engine dispatch. Tests trace this dependency direction and golden CLI/terminal behavior.

Ghostty exact identity uses observed target/TTY/foreground evidence and explicit per-invocation Codex context. A label/cwd/thread cache is not current caller ownership. Ghostty capture remains unsupported; screen capture is not necessary for engine progress. cmux retains its existing workspace/surface and screen semantics through the compatibility path. Unsupported required capabilities return errors before creating work; no transport switch occurs silently.

No public close operation is required by this boundary. Pause/cancel cannot automatically close user panes. Helpers have bounded timeouts and owned process groups; timeout cleanup must not kill the user's AI processes by name. Input accepted before a later helper failure remains `unknown` when submission cannot be established.

## Acceptance and limits

Exact verified session, exact physical addressing, input submission, protocol 3 and result schema 1 are required for a new engine participant. Native splitting is optional when an already prepared peer exists; screen reading and model/effort override are optional or unsupported. Importing adapter modules must not create a DB, launch panes or alter environment.

See [verification](verification-v0.12.md) for actual tested combinations. Existing v0.11 startup/transport evidence is retained as a baseline, not a claim that adapter extraction or the new engine passed live tests.
