# $crosstalk cowork-stop

Stop an in-flight cowork run.

If a RUN_ID argument is present, use it. Otherwise find the latest cowork run from `~/.crosstalk/last/manifest.json` or `/tmp/crosstalk/run-*/manifest.json`.

Ask the user for confirmation in plain text. Then run:

```bash
~/.claude/scripts/crosstalk_bridge.sh notify-stop "$RUN_ID"
```

Wait briefly, then report any existing response files and the worktree directory:

```text
/tmp/crosstalk/run-${RUN_ID}/responses/
/tmp/crosstalk/worktrees/run-${RUN_ID}/
```

Do not delete worktrees or branches unless the user explicitly asks.
