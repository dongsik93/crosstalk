# Crosstalk

English | [한국어](README.ko.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.10.6-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Discuss a topic with Claude and Codex side by side in Ghostty, or invite Antigravity (`agy`) as a peer. Ask from either CLI. Crosstalk reuses the other AI's pane or opens a native split, sends the question, and returns the response. No tmux required.

![Crosstalk hero](docs/hero.png)

> v0.11.0 implementation is unreleased. Protocol 2/schema 2 require an explicit upgrade and refreshed CLI instructions. Current live validation status is in [verification](docs/verification-v0.11.md); earlier v0.10 checks do not certify this protocol.

## Overview

Crosstalk connects existing interactive AI CLIs. Start from Codex with `$crosstalk <topic>` or Claude Code with `/crosstalk <topic>`. Each participant analyzes independently, and the caller compares the answers — consensus or respectful disagreement, without forcing agreement.

**Ghostty is the main getting-started path for Claude ↔ Codex discussion.** The existing cmux backend remains available for advanced workflows. Support differs by backend:

| Capability | Ghostty on macOS | cmux |
| --- | --- | --- |
| Claude ↔ Codex analysis and callbacks | Protocol 2 implemented; live verification pending | Supported; Codex caller experimental |
| Quick opinions (`ask`) | Supported | Supported |
| Prepare peer panes | Native split or reuse in the same tab | Workspace splits through `:launch` |
| Antigravity (`agy`) peer | Protocol 2 mailbox; live verification pending | Supported |
| Co-work and PR review | Not yet ported | Available; deep review experimental |
| Screen capture / screen transport | Unavailable through the Ghostty 1.3 AppleScript API | Available |

See the [Ghostty verification record](docs/ghostty-verification.md) for the actual checks and their limits. This checkout includes the Ghostty integration. Update older marketplace installations before following the quick start.

## Features

- **Visible discussion**: watch Claude and Codex work in neighboring Ghostty panes, starting from either CLI.
- **Reuse existing CLI accounts**: Crosstalk does not introduce a separate model API integration.
- **Automatic peer preparation**: launch the other CLI in the current directory when no labelled peer exists in the tab; wait for its startup acknowledgement before sending a task.
- **Independent answers**: each participant receives the user's original topic.
- **Durable mailbox**: Ghostty requests and replies are stored in SQLite. `send`, `receive`, and `reply` handle IDs, receipt state, and reply notifications; AIs no longer manage per-message MD files or ping commands.
- **Explicit verdicts**: protocol-2 replies use explicit verdict/confidence fields; legacy cmux markers are safely parsed as JSON.
- **Quick opinions**: `ask` lets each AI answer in its own pane without callbacks or aggregation.
- **Advanced cmux workflows**: co-work in git worktrees, PR review, and Antigravity peers remain available through cmux.

## Requirements

| Tool | Needed for | Notes |
| --- | --- | --- |
| macOS | Both terminal backends | Use an OS version supported by your terminal app |
| Ghostty 1.3+ | Native Claude ↔ Codex workflow | macOS AppleScript support; no cmux or tmux required |
| Claude Code or Codex CLI | Discussion caller | At least one is required to start a discussion |
| Claude, Codex, or Antigravity (`agy`) | Peer | Install and authenticate the caller and the peer you choose |
| jq | Bridge and configuration | Required |
| Python 3.11+ with sqlite3 | Ghostty mailbox | Standard library only; no pip packages or server |
| Node.js / npm | Installing npm-distributed AI CLIs | Not a separate Crosstalk runtime |
| cmux 1.3+ | Alternative backend and advanced workflows | Optional for Ghostty discussion |
| GitHub CLI (`gh`) | PR review | Optional |

Antigravity (`agy`) is a standalone download. It can participate as a peer in Ghostty mailbox discussions or legacy cmux runs. Install and authenticate the CLIs you plan to use.

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
/plugin install crosstalk@crosstalk
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

Claude and Codex are the default pair. To use Antigravity, name it explicitly:

```text
$crosstalk Review this design with agy.
/crosstalk Review this design with agy.
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

### Permissions for new peer panes

When the Crosstalk skill or slash command needs to create a new Ghostty peer, it offers two choices:

| Choice | Behavior |
| --- | --- |
| Keep CLI settings (default) | Adds no permission-bypass flag; the CLI keeps its own settings |
| Auto-approve this launch | Adds the option below for this new peer only |

| Peer | Option added by `--auto-approve` |
| --- | --- |
| Codex | `--yolo` — bypasses approvals **and the sandbox** |
| Claude | `--dangerously-skip-permissions` |
| Antigravity (`agy`) | `--dangerously-skip-permissions`; still starts with `--prompt-interactive` |

Auto-approval applies to all tools in that session, not just mailbox commands. The choice is not saved globally. Existing peers keep their current permissions and are reused without another choice. Changing an existing peer's mode requires an explicit user decision to restart it; the bridge will not do so automatically.

Direct bridge commands do not display a choice. Without the flag, they keep CLI defaults:

```sh
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex agy
```

After explicitly choosing auto-approval for a **new** peer:

```sh
~/.claude/scripts/crosstalk_bridge.sh ensure-peer claude codex --auto-approve
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex claude --auto-approve
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex agy --auto-approve
```

An existing matching peer causes `--auto-approve` to be rejected. Omit the flag to reuse it; a timeout or permission prompt is not permission to relaunch with broader access.

## Ghostty setup and troubleshooting

### Antigravity (`agy`) peer

Ask Codex or Claude to discuss a topic with agy, or prepare and contact it directly:

```sh
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex agy
crosstalk send agy "Review this approach" --summary "Reviewing the proposed approach"
```

From Claude, use `ensure-peer claude agy`. `agy` and `antigravity` resolve to the same peer kind. The launcher uses `agy --prompt-interactive` and preserves the caller PATH. The common permission choice above applies to agy too. Finish any login, project, or tool-approval prompts in the new pane. On timeout, reuse the pending pane instead of launching another copy.

New agy panes complete protocol-2 handshake at startup. Existing panes must complete setup and read the `mailbox_instructions` path returned by capabilities before receiving. agy uses the same receive/lease/reply flow; `/crosstalk-peer ... RUN_ID=...` remains the legacy cmux handler. Callers remain Claude or Codex. Actual protocol-2 agy integration is not yet verified.

### Identification and recovery

Protocol 2 separates logical ownership from the physical pane. Claude/agy can use an exact TTY probe; Codex's CLI session ID alone does not prove its pane address. `bridge strict-self` refuses labels/cwd as fallback. Use `/crosstalk:setup --surface ghostty:<UUID>` for a user-selected target and let each CLI execute its own one-use challenge/bind. `session status` confirms readiness; labelling alone does not.

Resuming a CLI in another pane requires explicit rebind to the intended logical session and a new binding generation. Old work does not transfer merely because the old pane closed. If the old pane is still alive or repository context changed, confirm the handoff. Read history and use authorized recover for interrupted claims. Do not guess focus, title, kind or cwd.

Codex must explicitly supply the exact current `CROSSTALK_SURFACE_ID` and shared `CROSSTALK_CONFIG_DIR` on every protocol-2 invocation. Its thread cache cannot prove its pane after resume, even while the previous pane is still alive. Reselect the current target and handshake after restart/resume; do not copy an old surface from conversation memory. See [protocol 2](docs/protocol-v2.md) for the invocation form.

On startup timeout reuse the pending pane and address its observed login/trust prompt; do not launch duplicates or bypass permission settings. Unknown panes may be labelled as candidates but still need protocol-2 handshake. No Ghostty screen-capture/footer-readiness fallback exists. Cowork and review remain cmux-only.

Inspect exact candidate addresses with:

```sh
osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'
crosstalk capabilities --json
crosstalk doctor --offline
crosstalk session status
```

Long bodies remain in SQLite. Notification submission is separate from receipt and completion. The automated suite uses isolated fake terminals; real protocol-2 acceptance is tracked in [verification](docs/verification-v0.11.md).

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
| `/crosstalk:review --deep [PR]` | cmux workflow: pinned detached worktree review with safe cleanup. |

## How It Works — Ghostty mailbox protocol 2

First complete caller and peer handshake through setup. `crosstalk capabilities --json` reports protocol/schema and the actual mailbox instruction path. Labels alone do not establish ownership. `send` selects a verified logical peer; if kind alone is ambiguous, select its `--peer-session` explicitly. `~/.claude/scripts/crosstalk` is the direct path if the executable is not on PATH.

```sh
crosstalk capabilities --json
crosstalk send claude "What do you think of this design?" --summary "Reviewing the design"
crosstalk receive
crosstalk reply <REQUEST_ID> "My analysis..." --lease-token <TOKEN> --verdict none --confidence unknown
```

Use `codex` when Claude is the caller. Long bodies use `--stdin`. Send saves before notifying; receive claims one queued message in insertion order and returns a private token. Reply saves one answer and completes its request atomically. The caller then receives the reply and persists its comparison with `ack <REPLY_ID> --lease-token <TOKEN> --outcome concluded --result-stdin`, or atomically creates the next round with `send <peer> --thread <THREAD_ID> --after-reply <REPLY_ID> --lease-token <TOKEN> --stdin`.

```text
request: queued -> processing -> completed (reply saved)
reply:   queued -> processing -> completed (ack or next request saved)
expired processing -> effective recovery_required -> explicit authorized reclaim
```

Body markers do not set v2 verdicts; `--verdict` and `--confidence` do. A peer's agreement is not proof of correctness. The thread limit remains ten requests. Ask saves replies without callback or automatic discussion; a requested later read is acknowledged as observed. Summaries remain display-only previews, never routing identity. Process the fetched body and one claim at a time.

### Recovery

| Command | Purpose |
| --- | --- |
| `doctor --offline` | Read installation/DB/recovery state without terminal input or repairs. |
| `status [ID]`, `history ID` | Inspect without claiming; use `--limit`/`--offset` for more rows. |
| `retry ID` | Resubmit the same saved notification, not the task. |
| `recover ID` | Diagnose an interrupted claim without changing it. |
| `recover ID --reclaim --expected-claim-version N --confirm-external-effects` | After user authorization, reclaim the same message with a fresh lease. |
| `renew ID --lease-token TOKEN` | Extend a valid claim; does not resurrect an expired one. |

`receive ID --replay` is deprecated. A saved message is not lost because its notification is failed/unknown. Check status and retry its ID rather than creating a replacement. Submitted input is not AI receipt. Read history and check external changes before recovery; the old process may still be running. Rebind invalidates old tokens. Exact duplicate reply submissions confirm the saved result rather than overwrite it.

There is no daemon, automatic reclaim or guarantee that external file/network actions run exactly once. DB and backups hold local plaintext conversation data with private permissions, not a security sandbox or encrypted storage. Both participants share `CROSSTALK_CONFIG_DIR`. See [protocol](docs/protocol-v2.md), [upgrade](docs/upgrade-v0.11.md), [recovery](docs/recovery.md), and [verification](docs/verification-v0.11.md).

### Legacy file protocol

cmux workflows and existing `RUN_ID` conversations continue using `/tmp/crosstalk/run-*` with `preambles/`, `rounds/`, `assignments/`, `responses/`, and completion `ping`. The old low-level `crosstalk_bridge.sh send <surface> <text>` remains available; it is separate from the new mailbox `crosstalk send <peer> <body>` command.

## Advanced workflows — cmux

Use cmux for co-work and PR review. These workflows have not yet been ported to Ghostty; Antigravity mailbox discussions are supported.

For PR review, run `/crosstalk:review <PR>`. Deep review uses an owned detached worktree at pinned base/head commits. Original checkout/index/stash are preserved; dirty or uncertain review worktrees are retained. See [review safety](docs/review-safety.md).

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
- **Deep PR review needs live validation**: detached worktrees share Git metadata and are not a security sandbox; unsafe cleanup is refused.
- **Callbacks depend on CLI input handling**: protocol-2 actual-terminal verification is still pending; a busy CLI or permission dialog may delay input processing. Check mailbox receipt state before assuming the peer started work; legacy ping does not acknowledge each earlier trigger.
- **Antigravity caller is not supported**: Antigravity (`agy`) participates as a peer only; runs must be started from Claude or Codex.

## Roadmap

- Ghostty support for advanced cowork/review workflows
- Per-peer model and effort selection
- Further delivery diagnostics; automatic task re-execution is not a v0.11 guarantee
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
