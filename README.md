# Crosstalk

English | [한국어](README.ko.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.10.0-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Discuss a topic with Claude and Codex side by side in Ghostty. Ask from either CLI. Crosstalk reuses the other AI's pane or opens a native split, sends the question, and returns the response. No tmux required.

![Crosstalk hero](docs/hero.png)

## Overview

Crosstalk connects existing interactive AI CLIs. Start from Codex with `$crosstalk <topic>` or Claude Code with `/crosstalk <topic>`. Each participant analyzes independently, and the caller compares the answers — consensus or respectful disagreement, without forcing agreement.

**Ghostty is the main getting-started path for Claude ↔ Codex discussion.** The existing cmux backend remains available for advanced workflows. Support differs by backend:

| Capability | Ghostty on macOS | cmux |
| --- | --- | --- |
| Claude ↔ Codex analysis and callbacks | Supported; two-way transport verified locally | Supported; Codex caller experimental |
| Quick opinions (`ask`) | Supported | Supported |
| Prepare peer panes | Native split or reuse in the same tab | Workspace splits through `:launch` |
| Antigravity peer | Not supported | Supported |
| Co-work and PR review | Not yet ported | Available; deep review experimental |
| Screen capture / screen transport | Unavailable through the Ghostty 1.3 AppleScript API | Available |

See the [Ghostty verification record](docs/ghostty-verification.md) for the actual checks and their limits. This checkout includes the Ghostty integration. Update older marketplace installations before following the quick start.

## Features

- **Visible discussion**: watch Claude and Codex work in neighboring Ghostty panes, starting from either CLI.
- **Reuse existing CLI accounts**: Crosstalk does not introduce a separate model API integration.
- **Automatic peer preparation**: launch the other CLI in the current directory when no labelled peer exists in the tab; wait for its startup acknowledgement before sending a task.
- **Independent answers**: each participant receives the user's original topic.
- **Durable mailbox**: Ghostty requests and replies are stored in SQLite. `send`, `receive`, and `reply` handle IDs, receipt state, and reply notifications; AIs no longer manage per-message MD files or ping commands.
- **Explicit verdicts**: the bridge parses `[AGREE]` and `[RESPECT_DISAGREE]` markers to guide subsequent rounds.
- **Quick opinions**: `ask` lets each AI answer in its own pane without callbacks or aggregation.
- **Advanced cmux workflows**: co-work in git worktrees, PR review, and Antigravity peers remain available through cmux.

## Requirements

| Tool | Needed for | Notes |
| --- | --- | --- |
| macOS | Both terminal backends | Use an OS version supported by your terminal app |
| Ghostty 1.3+ | Native Claude ↔ Codex workflow | macOS AppleScript support; no cmux or tmux required |
| Claude Code and Codex CLI | Ghostty discussion | Install and authenticate both CLIs |
| jq | Bridge and configuration | Required |
| Python 3 with sqlite3 | Ghostty mailbox | Standard library only; no pip packages or server |
| Node.js / npm | Installing npm-distributed AI CLIs | Not a separate Crosstalk runtime |
| cmux 1.3+ | Alternative backend and advanced workflows | Optional for Ghostty discussion |
| GitHub CLI (`gh`) | PR review | Optional |

Antigravity (`agy`) is a standalone download and currently participates through cmux only.

## Language

Crosstalk supports English and Korean command UI. During `/crosstalk:install`, choose the interface language:

- English
- Korean

The setting is stored in:

```text
~/.claude/crosstalk/config.json
```

```json
{
  "active_rules": "default",
  "active_persona": "default",
  "language": "en"
}
```

Use `"language": "ko"` for Korean. Built-in rules and personas are installed in both languages:

```text
~/.claude/crosstalk/rules/{en,ko}/
~/.claude/crosstalk/personas/{en,ko}/
```

## Installation

In Claude Code:

```text
/plugin marketplace add dongsik93/crosstalk
/plugin install crosstalk@dongsik93/crosstalk
```

Then run the one-time setup:

```text
/crosstalk:install
```

This installs:

- `~/.claude/scripts/crosstalk` and a `~/.local/bin/crosstalk` symlink (if that name is free)
- `~/.claude/crosstalk/mailbox.md`
- `~/.claude/scripts/crosstalk_bridge.sh`
- `~/.claude/scripts/crosstalk_ghostty.sh`
- `~/.claude/commands/crosstalk.md`
- `~/.codex/skills/crosstalk/`
- built-in rules and personas under `~/.claude/crosstalk/`

## Quick Start — Ghostty

After installing the Ghostty-enabled version of Crosstalk, open your project in Ghostty and run either CLI normally. Existing sessions can stay open.

**Starting from Codex:**

```text
$crosstalk Should this project use Compose or XML? Discuss it with Claude.
```

**Starting from Claude Code:**

```text
/crosstalk Should this project use Compose or XML?
```

Crosstalk reuses a labelled peer in the same tab or creates a right split and starts the other CLI in the current directory. Finish any first-use login/trust prompts there. Once startup is acknowledged, the question is delivered and completion callbacks return to the caller.

```text
Ghostty tab
├── Codex  ← questions and responses →  Claude
```

For quick independent opinions, use `$crosstalk ask <question>` or `/crosstalk:ask <question>`. Each AI answers in its own pane; no combined result is produced.

To check status without launching a peer, run `$crosstalk` or `/crosstalk` without a topic. The readiness check shows the backend, caller, and peers. If the caller cannot be identified, report that error and preserve the topic for `$crosstalk resume` or `/crosstalk:resume`.

### Models and reasoning effort

Crosstalk does not currently set a model or effort level. Reused panes keep their session settings; newly launched CLIs use their own defaults. Codex settings are not copied to Claude, or vice versa. There is no Crosstalk-specific model/effort override yet.

## Ghostty setup and troubleshooting

If startup times out, finish login/trust prompts in the existing peer pane and retry. Crosstalk keeps track of that pending startup so a retry does not create a duplicate.

The bridge's first connection to an existing CLI requires a unique working directory among Ghostty terminals. That binding is then tied to the caller process identity. Ambiguous directories fail instead of guessing the focused terminal; set `CROSSTALK_SURFACE_ID=ghostty:<UUID>` explicitly for those bridge calls. Newly launched peers inherit their exact ID. IDs and directories can be inspected with:

```sh
osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'
```

Manual bridge commands:

```sh
~/.claude/scripts/crosstalk_bridge.sh self
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex claude
# From a Claude caller: ensure-peer claude codex
```

This first Ghostty integration covers Claude/Codex analyze, ask, and callbacks. Advanced cowork/review flows remain cmux-oriented. Ghostty 1.3 does not expose screen contents through AppleScript, so capture, screen transport, and footer-based readiness are unavailable. Unknown existing panes need an explicit `bridge label <ID> claude|codex|shell`.

Long messages and responses stay in the local SQLite mailbox; Ghostty receives a short notification containing the message ID. Only `receive` acknowledges receipt. No daemon, socket server, or clipboard is used. macOS may ask for Automation permission to control Ghostty. Existing file/ping runs still work for compatibility.

Run `python3 tests/test_bridge.py` and `python3 tests/test_mailbox.py` for isolated terminal and mailbox checks.

## Demo

The existing demo and hero image show the cmux workflow. They are not recordings of the new Ghostty integration.

![Crosstalk cmux demo](docs/demo.gif)

## Commands

### Main (everyday use)

| Command | Description |
| --- | --- |
| `/crosstalk <topic>` | **Single entrypoint.** Runs analyze; inline-handles missing setup; prepares a Codex peer on Ghostty. |
| `/crosstalk` | Empty call → readiness doctor (installed / backend / peers + next single action). |
| `/crosstalk:analyze <topic>` | Explicit analyze. Independent multi-agent analysis with conditional ping-pong, ends in consensus or respectful divergence. |
| `/crosstalk:ask <question>` | **Lightweight opinion sampling (v0.7.0+).** Each peer answers once in its own pane. No debate, no ping-pong, no aggregation. |
| `/crosstalk:resume` | Resume a topic that was preserved when `/crosstalk` was unable to identify its caller terminal. |
| `/crosstalk:cowork "claude=A, codex=B, goal=Y"` | **cmux workflow.** Each peer runs its own `/goal` in its own CLI to deliver a piece of the task in parallel. Worktree-isolated by default. |
| `/crosstalk:cowork-stop [RUN_ID]` | **cmux workflow.** Stop an in-flight cowork run. Sends `/goal clear` + termination notice to every peer. |
| `/crosstalk:status` | Show active rules, personas, and pane status. |
| `/crosstalk:install` / `/crosstalk:uninstall` | Install or remove Crosstalk components. |

### Codex caller (experimental)

Run these from a Codex pane after `/crosstalk:install` has installed `~/.codex/skills/crosstalk/`.

| Command | Description |
| --- | --- |
| `$crosstalk <topic>` | Codex caller entrypoint. Runs analyze and uses Codex as the moderator. |
| `$crosstalk analyze [--rules <name>] [--persona <name>] <topic>` | Explicit analyze from Codex. |
| `$crosstalk ask <question>` | Lightweight opinion sampling from Codex (v0.7.0+). |
| `$crosstalk cowork "claude=A, antigravity=B, goal=Y"` | Start co-work mode from Codex (cmux workflow). |
| `$crosstalk cowork-stop [RUN_ID]` | Stop an in-flight cowork run from Codex (cmux workflow). |
| `$crosstalk resume` | Resume a preserved topic from Codex. |
| `$crosstalk status` | Show setup and pane status from Codex. |

### Advanced

These exist for manual control or recovery — you typically don't need them.

| Command | Description |
| --- | --- |
| `/crosstalk:analyze --rules <name> <topic>` | Apply a rules preset for one analyze run. |
| `/crosstalk:analyze --persona <name> <topic>` | Apply a persona preset for one analyze run. |
| `/crosstalk:launch` | Prepare the other CLI in Ghostty, or launch workspace peers in cmux. |
| `/crosstalk:setup` | Label already-open terminal panes (`--language en\|ko` also switches UI language). |
| `/crosstalk:rules` / `/crosstalk:persona` | Switch, create, edit, or delete presets. |
| `/crosstalk:review [PR]` | cmux workflow: moderator-driven PR review using `gh pr diff`. |
| `/crosstalk:review --deep [PR]` | cmux workflow: experimental deep PR review with checkout/stash/restore. |

## How It Works — Ghostty mailbox

Both AI CLIs use the same shell commands:

```sh
crosstalk send claude "What do you think of this design?"
crosstalk receive
crosstalk reply <MESSAGE_ID> "My analysis..."
```

Use `codex` as the destination when Claude is the caller. Readiness prepares the peer first with `bridge ensure-peer`; `send` requires exactly one labelled peer in the current tab. If `~/.local/bin` is not in PATH, use `~/.claude/scripts/crosstalk` directly. Long bodies can be piped via `--stdin` instead of passed as command arguments.

1. **Send** stores the body in `~/.claude/crosstalk/mailbox.sqlite3`, then notifies the peer using its exact Ghostty terminal ID.
2. **Receive** atomically claims one pending message and returns its body as JSON. Duplicate notifications return `actionable: false`; they do not instruct the AI to process the request twice.
3. **Reply** stores and links the answer, marks the request replied, and notifies the original caller. The AI does not write response files or call ping.
4. **Compare**: the caller reads the reply, compares it against its own view, and summarizes or sends a follow-up with `send <peer> --thread <ROOT_ID>`. The tool enforces a maximum of 10 request/reply rounds per thread.

```text
request: pending → received → replied
                              └─ reply message: pending → received
```

The tool extracts explicit verdict markers from replies. A marker describes the peer's position; the caller still compares both views before claiming consensus. With `send --mode ask`, the answer is stored and printed in the peer pane, but no reply notification is sent to the caller.

### Recovery

| Command | Purpose |
| --- | --- |
| `status [ID]` | Inspect receipt/reply state and notification errors without consuming messages |
| `history ID` | Read all messages in a thread |
| `retry ID` | Resend a pending notification without inserting another message |
| `receive ID --replay` | Deliberately resume a message received before an interruption |
| `send ... --id <KEY>` | Reuse an ID for an identical request; conflicting content is rejected |

If notification fails, the tool returns the saved message ID and exits nonzero. Use `retry` with that ID instead of creating another request. Repeating `reply` with the same body returns the existing reply; a different body cannot overwrite it.

The database survives process restarts. It is private to the local user. It does not sandbox that user's AI processes. Both sides must use the same `CROSSTALK_CONFIG_DIR` if overriding the default. Terminal IDs remain the delivery addresses: closing a pane requires manual recovery; the tool does not silently redirect its messages to another pane. A busy CLI or permission dialog can still block wake-up. There is no unattended retry daemon.

### Legacy file protocol

cmux workflows and existing `RUN_ID` conversations continue using `/tmp/crosstalk/run-*` with `preambles/`, `rounds/`, `assignments/`, `responses/`, and completion `ping`. The old low-level `crosstalk_bridge.sh send <surface> <text>` remains available; it is separate from the new mailbox `crosstalk send <peer> <body>` command.

## Advanced workflows — cmux

Use cmux for co-work, PR review, and Antigravity peers. These workflows have not yet been ported to Ghostty.

For PR review, run `/crosstalk:review <PR>`. The experimental `--deep` variant checks out the PR branch and attempts to restore the previous branch afterward.

### Co-work

`analyze` is for *opinions*. `cowork` is for *delivery*. Give each peer an assignment and a goal. Each runs its own `/goal` slash command in its CLI and works until it considers the goal met.

```text
/crosstalk:cowork "claude=Repository layer, codex=ViewModel layer, goal=mail search feature shipping with passing tests"
```

Flow:

1. **Crosstalk parses the assignment**, asks once whether to isolate work in git worktrees (recommended), and falls back to `--no-worktree` for shared-tree work.
2. **Fan-out**: each peer's slice + `/goal "<goal>"` + final report instructions are written to `assignments/<agent>.md`; cmux receives only `[crosstalk] cowork-task <agent> RUN_ID=...`.
3. **Each peer runs its own `/goal`**. The peer's CLI keeps stop blocked until it judges the goal met — Crosstalk doesn't second-guess that judgment.
4. **Time cap**: default 1 hour. On timeout (or on `/crosstalk:cowork-stop`), bridge sends `/goal clear` + a termination notice to every peer via cmux.
5. **Result aggregation**: the moderator reads each peer's report + their git log inside the worktree and writes `cowork-summary.md`. Worktree handling is up to the user — `keep` (default), `merge`, or `drop`.

```text
/tmp/crosstalk/run-<RUN_ID>/
  manifest.json
  responses/
    claude-r01.md          # each peer's work report
    codex-r01.md
  assignments/
    claude.md              # each peer's work prompt
    codex.md
  cowork-summary.md        # moderator's rolled-up summary

/tmp/crosstalk/worktrees/run-<RUN_ID>/
  claude/                  # git worktree on branch cowork/<RUN_ID>-claude
  codex/                   # git worktree on branch cowork/<RUN_ID>-codex
```

> Why delegate goal judgment to the peer's `/goal`? It keeps Crosstalk *thin*: peers know their own model's signal best, and Crosstalk doesn't have to invent a verifier. The cap + `cowork-stop` are the only safety nets — no LLM judging "looks done."
>
> MVP scope: peers don't see each other's progress (no live cross-check). They run in parallel; the moderator stitches results at the end. Cross-check between peers is on the roadmap.

## Rules and Personas (advanced)

Optional. Default analyze runs with no persona assignment and minimal rules. Pass a preset only when you want to shape the discussion.

Built-in rule presets:

| Rule | Style |
| --- | --- |
| `default` | constraints + tone only — peers choose their own length and form |
| `brainstorm` | short, exploratory, yes-and style |
| `debate` | deeper critique, slower agreement |

Built-in persona presets:

| Persona | Roles |
| --- | --- |
| `default` | no assigned persona |
| `senior-junior` | conservative senior vs progressive junior |
| `critic-builder` | critic vs builder |
| `triple-perspective` | conservative, innovator, pragmatic |

Example:

```text
/crosstalk:analyze --rules debate --persona critic-builder Should we merge this PR?
```

Custom presets live here (each rule/persona file is loaded into the preamble verbatim — no compression):

```text
~/.claude/crosstalk/rules/{en,ko}/
~/.claude/crosstalk/personas/{en,ko}/
```

## Limitations

- **macOS only**: the terminal backends currently require macOS.
- **cmux CLI UI detection can change**: cmux launch readiness and auto-detection use CLI footer patterns. If detection fails, run `/crosstalk:setup` and label panes manually.
- **No hard sandbox**: Crosstalk coordinates local CLI processes; it does not sandbox them.
- **Legacy file runs require `bridge ping`**: completion is event-based — if a peer never pings, the moderator stays idle. You can manually call `bridge ping <RUN_ID> <agent> <round>` from any pane to unblock.
- **AI may ignore transport instructions**: cmux opt-in `--transport file/screen` modes treat this as a protocol error with retry/skip/stop choices.
- **Deep PR review is experimental**: it touches the current git worktree through checkout/stash/restore.
- **Callbacks depend on CLI input handling**: Ghostty two-way transport has been checked locally, but a busy CLI or permission dialog may delay or prevent input processing. Check mailbox receipt state before assuming the peer started work; legacy ping does not acknowledge each earlier trigger.
- **Antigravity caller is not supported**: Antigravity (`agy`) participates as a peer only; runs must be started from Claude or Codex.

## Roadmap

- Ghostty support for advanced cowork/review workflows
- Per-peer model and effort selection
- Unattended delivery recovery and explicit rebinding after pane closure
- Antigravity moderator mode
- Additional CLI adapters
- tmux and zellij support
- Better troubleshooting docs
- More robust launch detection
- Public examples of real PR review sessions

## Contributing

Issues and pull requests are welcome. Good first contributions include:

- updating CLI footer detection patterns
- adding rules or persona presets
- improving install and troubleshooting docs
- testing against different Codex/Antigravity/Claude CLI versions
- exploring tmux or zellij adapters

## License

Crosstalk is released under the [MIT License](LICENSE).
