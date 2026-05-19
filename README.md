# Crosstalk

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.7.1-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Multi-agent analysis *and* co-work from one Claude Code slash command or Codex skill call. Ask once and each CLI analyzes independently; or hand out an assignment and each CLI delivers its piece in parallel — both modes ship with deterministic verdicts and a one-line stop button.

![Crosstalk hero](docs/hero.png)

## Overview

Crosstalk coordinates multiple AI CLIs inside [cmux](https://www.cmux.dev/) split panes. You ask once from Claude Code (`/crosstalk`) or Codex (`$crosstalk`), each peer analyzes independently, and Crosstalk compares their conclusions — consensus or respectful divergence, no forced agreement.

Unlike headless multi-agent tools, Crosstalk keeps the work visible. You watch each CLI respond in its own pane while the caller pane fans out the question and collects the verdicts.

## Features

- **Use your existing CLI subscriptions**: no separate API keys or per-token integration required.
- **Visible multi-agent workflow**: Claude, Codex, and Antigravity run in neighboring cmux panes.
- **Codex caller support** *(experimental)*: Codex can start runs with `$crosstalk`, and bridge callbacks re-enter through `$crosstalk callback ...`.
- **Independent analysis, no knowledge pollution**: the user's raw input is fan-out unchanged — no moderator summary, no agenda setting.
- **Deterministic verdict extraction**: `[AGREE]` / `[RESPECT_DISAGREE]` markers are parsed by the bridge, not interpreted by an LLM.
- **File-based messaging** *(v0.6.0+)*: large preambles, ping-pong rounds, cowork assignments, review rounds, and responses all live under `/tmp/crosstalk/run-*`; cmux only sends short triggers.
- **Topic preservation across cmux entry**: call `/crosstalk` outside cmux, then `/crosstalk:resume` inside — your topic is kept.
- **PR review mode** *(advanced)*: moderator-driven review using `gh pr diff`.
- **Co-work mode** *(v0.4.0+)*: each peer runs its own `/goal` to deliver part of a task in parallel, isolated in git worktrees. Crosstalk fans out the assignment, enforces a time cap, and collects results.
- **Ask mode** *(v0.7.0+, fire-and-forget since v0.7.1)*: lightweight opinion sampling. Caller fans out the question, answers in its own pane, and exits. Each peer answers in its own pane. No ping, no callback, no aggregation — use when you want quick parallel takes instead of consensus.

## Requirements

| Tool | Required | Notes |
| --- | --- | --- |
| macOS 14+ | Yes | cmux is macOS-only |
| Node.js + npm 18+ | Yes | Used to install missing AI CLIs |
| cmux 1.3+ | Yes | `brew install --cask cmux` |
| jq | Yes | Used for rules/persona config |
| GitHub CLI | Optional | Required for PR review mode |

You only need the AI CLIs you plan to use. `/crosstalk:install` can install a missing Codex CLI through npm. Antigravity (the `agy` binary) is a standalone download — install it yourself; Crosstalk only detects it.

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
- `~/.claude/commands/crosstalk.md`
- `~/.codex/skills/crosstalk/`
- built-in rules and personas under `~/.claude/crosstalk/`

## Quick Start

Just type your question:

```text
/crosstalk Should this Android project use Compose or XML?
```

From a Codex pane, use the skill entrypoint:

```text
$crosstalk Should this Android project use Compose or XML?
```

That's it. If anything is missing (cmux not running, no peer CLIs in the workspace), `/crosstalk` or `$crosstalk` will tell you the next single action and **preserve your topic** — you don't need to retype it. From cmux, run `/crosstalk:resume` or `$crosstalk resume` to pick up where you left off (v0.2.6+).

To check status without starting a run:

```text
/crosstalk
```

(empty call shows a one-line readiness doctor: installed / cmux / peers).

For PR review (fast):

```text
/crosstalk:review 1440
```

Deep PR review is experimental — `/crosstalk:review --deep 1440` checks out the PR branch in your current working directory and attempts to restore the previous branch afterward. Use the default fast mode unless you explicitly need repository-wide context.

> Advanced: `:install`, `:launch`, `:setup`, `:status`, `:rules`, `:persona`, the explicit `:analyze`, and `:review` are all available for manual control or recovery, but you typically don't need to call them. See [Commands](#commands).

## Demo

![Crosstalk demo](docs/demo.gif)

## Commands

### Main (everyday use)

| Command | Description |
| --- | --- |
| `/crosstalk <topic>` | **Single entrypoint.** Runs analyze; inline-handles missing setup; preserves topic across cmux entry. |
| `/crosstalk` | Empty call → readiness doctor (installed / cmux / peers + next single action). |
| `/crosstalk:analyze <topic>` | Explicit analyze. Independent multi-agent analysis with conditional ping-pong, ends in consensus or respectful divergence. |
| `/crosstalk:ask <question>` | **Lightweight opinion sampling (v0.7.0+).** Each peer answers once in its own pane. No debate, no ping-pong, no aggregation. |
| `/crosstalk:resume` | Resume a topic that was preserved when `/crosstalk` was called outside cmux. |
| `/crosstalk:cowork "claude=A, codex=B, goal=Y"` | **Co-work mode (v0.4.0+).** Each peer runs its own `/goal` in its own CLI to deliver a piece of the task in parallel. Worktree-isolated by default. |
| `/crosstalk:cowork-stop [RUN_ID]` | Stop an in-flight cowork run. Sends `/goal clear` + termination notice to every peer. |
| `/crosstalk:status` | Show active rules, personas, and pane status. |
| `/crosstalk:install` / `/crosstalk:uninstall` | Install or remove Crosstalk components. |

### Codex caller (experimental)

Run these from a Codex pane after `/crosstalk:install` has installed `~/.codex/skills/crosstalk/`.

| Command | Description |
| --- | --- |
| `$crosstalk <topic>` | Codex caller entrypoint. Runs analyze and uses Codex as the moderator. |
| `$crosstalk analyze [--rules <name>] [--persona <name>] <topic>` | Explicit analyze from Codex. |
| `$crosstalk ask <question>` | Lightweight opinion sampling from Codex (v0.7.0+). |
| `$crosstalk cowork "claude=A, antigravity=B, goal=Y"` | Start co-work mode from Codex. |
| `$crosstalk cowork-stop [RUN_ID]` | Stop an in-flight cowork run from Codex. |
| `$crosstalk resume` | Resume a preserved topic from Codex. |
| `$crosstalk status` | Show setup and pane status from Codex. |

### Advanced

These exist for manual control or recovery — you typically don't need them.

| Command | Description |
| --- | --- |
| `/crosstalk:analyze --rules <name> <topic>` | Apply a rules preset for one analyze run. |
| `/crosstalk:analyze --persona <name> <topic>` | Apply a persona preset for one analyze run. |
| `/crosstalk:launch` | Create cmux splits, start AI CLIs, and label panes manually. |
| `/crosstalk:setup` | Label already-open cmux panes (`--language en\|ko` also switches UI language). |
| `/crosstalk:rules` / `/crosstalk:persona` | Switch, create, edit, or delete presets. |
| `/crosstalk:review [PR]` | Moderator-driven PR review using `gh pr diff`. |
| `/crosstalk:review --deep [PR]` | Experimental deep PR review with checkout/stash/restore. |

## How It Works (v0.6.0)

1. **Fan-out, raw, via files**: Crosstalk scans the cmux workspace for peer AI panes, writes each peer's full prompt to disk, then sends only a short trigger through cmux. No large prompt is typed into another pane.
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

Example run directory:

```text
/tmp/crosstalk/run-PpP6hTWx/
  manifest.json          # includes moderator_surface, moderator_kind, mode, agents, current_round
  done/
    codex-r01            # ping markers (also kept for debugging)
    antigravity-r01
  responses/             # always populated — moderator reads from here
    codex-r01.md
    antigravity-r01.md
    claude-r01.md
  preambles/             # analyze round 1 prompts
    codex.md
    antigravity.md
  rounds/                # analyze ping-pong and review round prompts
    r02-codex.md
    r02-antigravity.md
  assignments/           # cowork task prompts
    codex.md
    antigravity.md
```

File-backed channels:

- `preambles/<agent>.md`: analyze round 1 prompt.
- `rounds/r<NN>-<agent>.md`: analyze ping-pong and review prompts.
- `assignments/<agent>.md`: cowork task prompt.
- `responses/<agent>-r<NN>.md`: peer answers and cowork reports.

cmux receives only short triggers such as `[crosstalk] preamble codex RUN_ID=...`, `[crosstalk] round 02 codex RUN_ID=...`, `[crosstalk] cowork-task codex RUN_ID=...`, and callback messages.

## Co-work Mode (v0.4.0+)

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

- **macOS only**: Crosstalk currently depends on cmux.
- **CLI UI detection can change**: launch readiness and auto-detection use CLI footer patterns. If detection fails, run `/crosstalk:setup` and label panes manually.
- **No hard sandbox**: Crosstalk instructs peer CLIs to write only their response file, but it cannot fully sandbox another CLI process.
- **Peer must call `bridge ping`**: completion is event-based — if a peer never pings, the moderator stays idle. You can manually call `bridge ping <RUN_ID> <agent> <round>` from any pane to unblock.
- **AI may ignore transport instructions**: opt-in `--transport file/screen` modes treat this as a protocol error with retry/skip/stop choices.
- **Deep PR review is experimental**: it touches the current git worktree through checkout/stash/restore.
- **Codex caller is experimental**: `$crosstalk` uses Codex skills and cmux callback injection. Verify callback behavior with your Codex/cmux version before relying on long ping-pong or cowork runs.
- **Antigravity caller is not supported**: Antigravity (`agy`) participates as a peer only; runs must be started from Claude or Codex.

## Roadmap

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
