# $crosstalk status

Show Crosstalk setup status without starting a run.

Collect:

- `~/.claude/crosstalk/config.json`
- active language/rules/persona
- available rules/personas for that language
- cmux panes, when inside cmux
- whether `~/.claude/scripts/crosstalk_bridge.sh` exists
- whether `~/.codex/skills/crosstalk/SKILL.md` exists

Use:

```bash
~/.claude/scripts/crosstalk_bridge.sh list-all
```

when cmux is available.

Output a compact status block and include both start commands:

```text
Claude caller: /crosstalk <topic>
Codex caller:  $crosstalk <topic>
```
