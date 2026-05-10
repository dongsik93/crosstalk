# Crosstalk

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.2.4-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Run a visible multi-agent debate between Claude, Codex, and Gemini from one Claude Code slash command.

![Crosstalk hero](docs/hero.png)

## Overview

Crosstalk is a Claude Code plugin that coordinates multiple AI CLIs inside [cmux](https://www.cmux.dev/) split panes. Claude acts as the moderator, sends structured debate turns to Codex and Gemini, reads their responses, and produces a final summary.

Unlike headless multi-agent tools, Crosstalk keeps the work visible. You can watch each CLI respond in its own pane while Claude manages the conversation.

## Features

- **Use your existing CLI subscriptions**: no separate API keys or per-token integration required.
- **Visible multi-agent workflow**: Claude, Codex, and Gemini run in neighboring cmux panes.
- **Claude as moderator**: the calling Claude session asks, challenges, summarizes, and decides when the debate is done.
- **File-based response transport**: responses are written to `/tmp/crosstalk/run-*/responses/*.md`, avoiding terminal scrollback loss for long answers.
- **PR review mode**: ask multiple AI CLIs to review a GitHub PR and discuss merge readiness.
- **Rules and personas**: switch between lightweight brainstorming, stricter debate, or custom role presets.

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

Start or attach to a cmux workspace:

```text
/crosstalk:launch
```

Then run a debate from the Claude pane:

```text
/crosstalk Should this Android project use Compose or XML?
```

For PR review:

```text
/crosstalk:review 1440
```

Deep PR review is available but experimental:

```text
/crosstalk:review --deep 1440
```

`--deep` checks out the PR branch in the current working directory and attempts to restore the previous branch afterward. Use the default fast review mode unless you explicitly need repository-wide context.

## Demo

![Crosstalk demo](docs/demo.gif)

## Commands

### Debate

| Command | Description |
| --- | --- |
| `/crosstalk <topic>` | Shortcut for a standard debate |
| `/crosstalk:debate <topic>` | Standard debate with one or more peer CLIs |
| `/crosstalk:debate --rules <name> <topic>` | Use a rules preset once |
| `/crosstalk:debate --persona <name> <topic>` | Use a persona preset once |
| `/crosstalk:analyze <topic>` | Independent analysis without a moderator. Each peer analyzes the same raw input; ping-pong only on disagreement, ends in consensus or respectful divergence (v0.2.2+). |
| `/crosstalk:analyze --rules <name> <topic>` | Apply a rules preset for one analyze run (v0.2.4+) |
| `/crosstalk:analyze --persona <name> <topic>` | Apply a persona preset for one analyze run (v0.2.4+) |
| `/crosstalk:review [PR]` | Fast PR review using `gh pr diff` |
| `/crosstalk:review --deep [PR]` | Experimental deep PR review with checkout/stash/restore |

### Setup and Configuration

| Command | Description |
| --- | --- |
| `/crosstalk:install` | Install Crosstalk components into the user home directory (use `--presets-only [--language en\|ko]` to refresh just the rules/personas) |
| `/crosstalk:launch` | Create cmux splits, start AI CLIs, and label panes |
| `/crosstalk:setup` | Label already-open cmux panes (use `--language en\|ko` to also switch UI language) |
| `/crosstalk:status` | Show active rules, personas, and pane status |
| `/crosstalk:rules` | Switch, create, edit, or delete debate rules |
| `/crosstalk:persona` | Switch, create, edit, or delete personas |
| `/crosstalk:uninstall` | Remove user-level Crosstalk components |

## How It Works (v0.2.1+ — callback ping + file responses)

1. Claude scans the current cmux workspace for peer AI CLI panes and labels them.
2. `start-run` records the moderator (Claude) surface in the run manifest.
3. Claude sends each peer a preamble (persona + rules + ping protocol + response-file procedure) once, then a short topic message.
4. **Claude exits the slash command** — its pane is now idle, waiting for input.
5. Each peer writes its answer to a response file, then signals completion:
   ```bash
   cat > /tmp/crosstalk/run-<RUN_ID>/responses/<agent>-r<NN>.md <<'EOF'
   <answer body>
   EOF
   ~/.claude/scripts/crosstalk_bridge.sh ping <RUN_ID> <agent> <round>
   ```
6. `bridge ping` reads the manifest, finds the moderator surface, and **sends a callback message into the Claude pane** (e.g. `[crosstalk] codex R3 done — RUN_ID=...`) with the response file path.
7. Claude wakes up on that input, **reads the response file** (no screen capture), and starts the next round (back to step 3).
8. When `[AGREE]` or the round limit is reached, Claude produces the final summary.

> Why file + callback? v0.2.0 used screen capture + callback, which raced — peers sometimes pinged before finishing the on-screen answer. v0.2.1+ moves the answer to a file and treats `ping` as a pure completion signal. The response is in one place; reads are deterministic.

> Why callback instead of polling? Earlier versions made Claude `wait-ping` indefinitely, which broke whenever the user interrupted the slash command. Callbacks keep Claude idle between rounds — any peer's `bridge ping` is enough to resume the conversation.

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

## Rules and Personas

Built-in rule presets:

| Rule | Style |
| --- | --- |
| `default` | natural reasoning flow, balanced, constructive |
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
/crosstalk:debate --rules debate --persona critic-builder Should we merge this PR?
```

Custom presets live here:

```text
~/.claude/crosstalk/rules/
~/.claude/crosstalk/personas/
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
