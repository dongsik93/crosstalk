# $crosstalk status

Show Crosstalk setup status without starting a run.

Collect:

- `~/.claude/crosstalk/config.json`
- active language/rules/persona
- available rules/personas for that language
- Ghostty or cmux panes, when the caller can be identified
- whether `~/.claude/scripts/crosstalk_bridge.sh` exists
- whether `~/.codex/skills/crosstalk/SKILL.md` exists

Use:

```bash
~/.claude/scripts/crosstalk_bridge.sh list-all
```

when the caller terminal can be identified.

Output a compact status block and include both start commands:

```text
Claude caller: /crosstalk <topic>
Codex caller:  $crosstalk <topic>
```
