# Crosstalk

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.3.1-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Independent multi-agent analysis from one Claude Code slash command. Each CLI analyzes the same raw input on its own; results are compared and ping-pong only when verdicts diverge.

![Crosstalk hero](docs/hero.png)

## Overview

Crosstalk is a Claude Code plugin that coordinates multiple AI CLIs inside [cmux](https://www.cmux.dev/) split panes. You ask once, each peer analyzes independently, and Crosstalk compares their conclusions — consensus or respectful divergence, no forced agreement.

Unlike headless multi-agent tools, Crosstalk keeps the work visible. You watch each CLI respond in its own pane while one Claude session fans out the question and collects the verdicts.

## Features

- **Use your existing CLI subscriptions**: no separate API keys or per-token integration required.
- **Visible multi-agent workflow**: Claude, Codex, and Gemini run in neighboring cmux panes.
- **Independent analysis, no knowledge pollution**: the user's raw input is fan-out unchanged — no moderator summary, no agenda setting.
- **Deterministic verdict extraction**: `[AGREE]` / `[RESPECT_DISAGREE]` markers are parsed by the bridge, not interpreted by an LLM.
- **File-based response transport**: responses are written to `/tmp/crosstalk/run-*/responses/*.md`, avoiding terminal scrollback loss for long answers.
- **Topic preservation across cmux entry**: call `/crosstalk` outside cmux, then `/crosstalk:resume` inside — your topic is kept.
- **PR review mode** *(advanced)*: moderator-driven review using `gh pr diff`.

## Requirements

| Tool | Required | Notes |
| --- | --- | --- |
| macOS 14+ | Yes | cmux is macOS-only |
| Node.js + npm 18+ | Yes | Used to install missing AI CLIs |
| cmux 1.3+ | Yes | `brew install --cask cmux` |
| jq | Yes | Used for rules/persona config |
| GitHub CLI | Optional | Required for PR review mode |

You only need the AI CLIs you plan to use. `/crosstalk:install` can help install missing Codex and Gemini CLI packages through npm.

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
- built-in rules and personas under `~/.claude/crosstalk/`

## Quick Start

Just type your question:

```text
/crosstalk Should this Android project use Compose or XML?
```

That's it. If anything is missing (cmux not running, no peer CLIs in the workspace), `/crosstalk` will tell you the next single action and **preserve your topic** — you don't need to retype it. From cmux, run `/crosstalk:resume` to pick up where you left off (v0.2.6+).

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
| `/crosstalk:resume` | Resume a topic that was preserved when `/crosstalk` was called outside cmux. |
| `/crosstalk:status` | Show active rules, personas, and pane status. |
| `/crosstalk:install` / `/crosstalk:uninstall` | Install or remove Crosstalk components. |

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

## How It Works (v0.3.0)

1. **Fan-out, raw**: Crosstalk scans the cmux workspace for peer AI panes and sends each peer the user's topic *unchanged*. No moderator summary, no agenda. Claude itself also analyzes in parallel as one more participant.
2. **Independent answers in parallel**: each peer writes its analysis to a response file:
   ```bash
   cat > /tmp/crosstalk/run-<RUN_ID>/responses/<agent>-r<NN>.md <<'EOF'
   <conclusion + reasoning + confidence + verdict marker>
   EOF
   ~/.claude/scripts/crosstalk_bridge.sh ping <RUN_ID> <agent> <round>
   ```
3. **Callback wakes the moderator**: `bridge ping` reads the manifest, finds the calling Claude pane, and sends a callback message with the response file path. Claude exits the slash command between rounds — no polling, no idle bash process.
4. **Deterministic verdict extraction**: when all peers ping, the bridge runs `extract-verdict` on each response file to parse `[AGREE]` / `[RESPECT_DISAGREE: reason]` / `confidence: high|medium|low` markers. The LLM does not interpret consensus.
5. **Compare or ping-pong**:
   - All `verdict=AGREE` → consensus. Print combined conclusion.
   - One or more `RESPECT_DISAGREE` → respectful divergence. Print each verdict with its reason.
   - Otherwise → one more round. Each peer sees the current divergence summary and updates: keep, change, agree, or respect-disagree.
6. **Hard cap at 10 rounds** to prevent runaway loops.

> Why file + callback? Earlier versions screen-captured peer panes, which raced — a peer sometimes pinged before finishing the on-screen answer. v0.2.1+ moves the answer to a file and treats `ping` as a pure completion signal.
>
> Why deterministic verdict extraction? Earlier versions had the moderator LLM decide "this looks like consensus." v0.3.0 makes verdict a parsed marker. The moderator only summarizes; it cannot silently end a run.

Example run directory:

```text
/tmp/crosstalk/run-PpP6hTWx/
  manifest.json          # includes moderator_surface, mode, agents, current_round
  done/
    codex-r01            # ping markers (also kept for debugging)
    gemini-r01
  responses/             # always populated — moderator reads from here
    codex-r01.md
    gemini-r01.md
    claude-r01.md
```

All three transport modes write to `responses/`:

- `off` (default): peer writes the response file via shell heredoc. Simplest, recommended.
- `file`: explicit per-turn Transport block instructs the peer to write to a per-attempt file (`<agent>-r<NN>-a<N>.md`). Useful for very long-running runs.
- `screen` (legacy): peer prints `CROSSTALK_BEGIN`/`CROSSTALK_END` blocks; bridge converts to a response file. Kept for agentic CLIs (e.g. Gemini) that mishandle shell heredocs.

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
- **Claude-only moderation**: Codex/Gemini moderator mode is not supported yet.

## Roadmap

- Codex and Gemini moderator modes
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
- testing against different Codex/Gemini/Claude CLI versions
- exploring tmux or zellij adapters

## License

Crosstalk is released under the [MIT License](LICENSE).
