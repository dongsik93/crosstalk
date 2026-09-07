# Crosstalk

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.9.0-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Discuss a topic with Claude and Codex side by side in Ghostty. Ask from either CLI; Crosstalk reuses the other AI's pane or opens a native split, passes the question, and brings the response back. No tmux required.

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

See the [Ghostty verification record](docs/ghostty-verification.md) for the actual checks and their limits. This checkout contains the Ghostty integration; an older marketplace installation must be updated before following its quick start.

## Features

- **Visible discussion**: watch Claude and Codex work in neighboring Ghostty panes, starting from either CLI.
- **Reuse existing CLI accounts**: Crosstalk does not introduce a separate model API integration.
- **Automatic peer preparation**: launch the other CLI in the current directory when no labelled peer exists in the tab; wait for its startup acknowledgement before sending a task.
- **Independent answers**: each participant receives the user's original topic.
- **File-backed messages**: long prompts and responses live under `/tmp/crosstalk/run-*`; terminal input carries only short triggers and callbacks.
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

For status without launching a peer, invoke `$crosstalk` or `/crosstalk` without a topic. The readiness check shows the backend, caller, and peers. If the caller cannot be identified, report that error and preserve the topic for `$crosstalk resume` or `/crosstalk:resume`.

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

Long messages and responses stay in files; only a short trigger naming the file crosses the terminal input. This avoids large pastes and keeps interrupted exchanges inspectable. Completion ping is an acknowledgement of finished work, not guaranteed delivery of each input: busy CLIs and permission dialogs still need attention. No daemon, socket server, or clipboard is used. macOS may ask for Automation permission to control Ghostty.

Run the isolated transport regression check with `python3 tests/test_bridge.py`.

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

## How It Works

1. **Fan-out, raw, via files**: Crosstalk finds peer AI panes in the caller's Ghostty tab or cmux workspace, writes each peer's full prompt to disk, then sends only a short trigger through that terminal backend. No large prompt is typed into another pane.
2. **Peers read their message file**: analyze preambles live in `preambles/<agent>.md`, ping-pong and review rounds live in `rounds/r<NN>-<agent>.md`, and cowork tasks live in `assignments/<agent>.md`.
3. **Independent answers in parallel**: each peer writes its answer to a response file:
   ```bash
   cat > /tmp/crosstalk/run-<RUN_ID>/responses/<agent>-r<NN>.md <<'EOF'
   <conclusion + reasoning + confidence + verdict marker>
   EOF
   ~/.claude/scripts/crosstalk_bridge.sh ping <RUN_ID> <agent> <round>
   ```
4. **Callback wakes the moderator**: `bridge ping` reads the manifest, finds the caller pane, and sends a short callback message with the response file path. Claude callers receive the legacy `[crosstalk] ...` message; Codex callers receive `$crosstalk callback RUN_ID=... AGENT=... ROUND=... RESP=...`. The caller exits between rounds — no polling, no idle bash process.
5. **Deterministic verdict extraction**: when all peers ping, the bridge runs `extract-verdict` on each response file to parse `[AGREE]` / `[RESPECT_DISAGREE: reason]` / `confidence: high|medium|low` markers. The LLM does not interpret consensus.
6. **Compare or ping-pong**:
   - All `verdict=AGREE` → consensus. Print combined conclusion.
   - One or more `RESPECT_DISAGREE` → respectful divergence. Print each verdict with its reason.
   - Otherwise → one more file-backed round. Each peer sees the current divergence summary and updates: keep, change, agree, or respect-disagree.
7. **Hard cap at 10 rounds** to prevent runaway loops.

> Why file + trigger? Earlier versions sent full prompts through cmux input simulation. Large prompts could take 30-60 seconds to paste and make the caller command time out, risking duplicate fan-out. v0.6.0 writes every large message to disk and sends only a short deterministic trigger.
>
> Why deterministic verdict extraction? Earlier versions had the moderator LLM decide "this looks like consensus." v0.3.0 makes verdict a parsed marker. The moderator only summarizes; it cannot silently end a run.

Example Ghostty analysis run (Codex caller, Claude peer):

```text
/tmp/crosstalk/run-<RUN_ID>/
  manifest.json          # caller terminal ID/kind, peers, mode, current_round
  done/
    codex-r01
    claude-r01
  responses/
    codex-r01.md
    claude-r01.md
  preambles/
    claude.md
  rounds/
    r02-claude.md
```

File-backed channels:

- `preambles/<agent>.md`: analyze round 1 prompt.
- `rounds/r<NN>-<agent>.md`: analyze ping-pong and review prompts.
- `assignments/<agent>.md`: cowork task prompt.
- `responses/<agent>-r<NN>.md`: peer answers and cowork reports.

The terminal backend receives only short triggers such as `[crosstalk] preamble codex RUN_ID=...`, `[crosstalk] round 02 codex RUN_ID=...`, `[crosstalk] cowork-task codex RUN_ID=...`, and callback messages.

## Advanced workflows — cmux

Use cmux for co-work, PR review, and Antigravity peers. These workflows have not yet been ported to Ghostty.

For PR review, run `/crosstalk:review <PR>`. The experimental `--deep` variant checks out the PR branch and attempts to restore the previous branch afterward.

### Co-work

`analyze` is for *opinions*. `cowork` is for *delivery*. Hand out an assignment and a goal, each peer runs its own `/goal` slash command in its own CLI and works until it thinks the goal is met.

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
- **No hard sandbox**: Crosstalk instructs peer CLIs to write only their response file, but it cannot fully sandbox another CLI process.
- **Peer must call `bridge ping`**: completion is event-based — if a peer never pings, the moderator stays idle. You can manually call `bridge ping <RUN_ID> <agent> <round>` from any pane to unblock.
- **AI may ignore transport instructions**: cmux opt-in `--transport file/screen` modes treat this as a protocol error with retry/skip/stop choices.
- **Deep PR review is experimental**: it touches the current git worktree through checkout/stash/restore.
- **Callbacks depend on CLI input handling**: Ghostty two-way transport has been checked locally, but a busy CLI or permission dialog may delay or prevent input processing. A completion ping does not guarantee delivery of every earlier trigger.
- **Antigravity caller is not supported**: Antigravity (`agy`) participates as a peer only; runs must be started from Claude or Codex.

## Roadmap

- Ghostty support for advanced cowork/review workflows
- Per-peer model and effort selection
- Stronger message delivery acknowledgement
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
