---
description: Remove manifest-owned Crosstalk runtime files, preserving user data and edits.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: (no arguments)
---

# Crosstalk uninstall

Explain the concrete scope and confirm removal unless the user already authorized it. Finish in-flight work first; uninstall does not terminate AI processes.

Run the installed CLI, or the matching source CLI if the installation is incomplete:

```bash
~/.claude/scripts/crosstalk uninstall
```

Keep the same `CROSSTALK_CONFIG_DIR` used at installation. Do not substitute `rm -rf`, guessed file lists, or wildcard removal.

The installer manifest identifies owned runtime files, wrapper files, Codex skill files, the user command, optional agy command, and the `~/.local/bin/crosstalk` symlink. Only files still matching their installed checksum and symlinks still pointing to their owned target are removed. Modified files and unknown additional files remain and are listed in `retained_modified`.

DB, events, configuration, rules/personas, backups, conversation logs, and review worktrees remain. The marketplace plugin, AI CLIs, Ghostty, and cmux remain installed. To remove the marketplace plugin itself, the user can separately invoke `/plugin uninstall crosstalk`.

If no manifest exists, automatic removal refuses to guess ownership. Inspect the legacy installation and prepare an exact removal list instead of deleting whole directories.

Report the actual `removed` and `retained_modified` results. Do not claim the Codex skill remains installed when its files were removed; only retained modified files remain in that case.
