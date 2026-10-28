---
description: Install or resume a verified Crosstalk release while preserving user data.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: [--presets-only] [--language en|ko]
---

# Crosstalk installation

Installation changes user-level Crosstalk files. Use the deterministic installer below; do not copy files, migrate SQLite, change symlinks, or restore a backup manually.

1. Identify the exact plugin checkout. If `CLAUDE_PLUGIN_ROOT` points to `plugins/crosstalk`, its parent’s parent is the source root. Verify that `VERSION` and `assets/scripts/crosstalk_lib/installer.py` exist. Do not pick the first matching marketplace if several installations exist.
2. Check `python3` is at least 3.11 and imports `sqlite3`. Ghostty/cmux integration needs macOS; `jq` is required by the bridge, and `gh` is needed for PR review. Report missing CLI or authentication separately. Do not silently install AI CLIs or change permissions.
3. Preserve the existing language unless the user requests `en` or `ko`; ask only when needed. Confirm update intent if it is not already authorized. Before upgrading, finish or explicitly stop in-flight Crosstalk commands and peer work. Installation does not stop those processes.
4. Run the source executable with argv values; never evaluate `$ARGUMENTS` as shell code:

```bash
python3 "$SOURCE_ROOT/assets/scripts/crosstalk" install --source "$SOURCE_ROOT"
```

Pass `--language en` or `--language ko` when selected. `CROSSTALK_CONFIG_DIR` selects the state directory for the installer and launched runtime. `--home` is intended for isolated installation/testing. If processing claims remain after the user explicitly stopped their workers, use `--quiesced`; do not infer that a lease timeout stopped the process.

For the existing presets-only operation, run:

```bash
python3 "$SOURCE_ROOT/assets/scripts/crosstalk" install --source "$SOURCE_ROOT" --presets-only
```

This only adds missing rules/personas and optionally updates language, preserving existing presets and unknown config keys.

The full installer stages a checksum-verified immutable release, backs up replaced files, enables maintenance, migrates the DB, switches the runtime pointer atomically, installs instructions, and runs offline checks. It preserves custom rules/personas, unknown configuration keys, conversation data, logs, review worktrees, and unrelated symlinks. Changed command/skill files are backed up before replacement; show returned backup paths.

If installation is interrupted, preserve the state directory and rerun the **same release** and source command. A partial installation remains gated by maintenance. Never delete the DB, overwrite it with an old backup, or activate a different release to bypass the gate. Migration errors leave the previous runtime pointer in place; after schema migration use the same v0.11 release to repair forward.

On success, show the release version, migration backup (if any), and replaced-file backups from JSON. Tell the user to reload instructions in already-open Claude/Codex/agy sessions and complete the protocol-2 handshake. Copying new instruction files does not reload them inside running CLIs. Then verify:

```bash
~/.claude/scripts/crosstalk capabilities --json
~/.claude/scripts/crosstalk doctor --offline
```

An offline installation check is not evidence that actual Ghostty setup or a Claude↔Codex conversation passed. Keep those results separate. The installer does not grant automatic approval permissions or install third-party CLIs.
