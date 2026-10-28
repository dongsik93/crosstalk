# Upgrading to v0.11

v0.11 uses Python 3.11+, mailbox protocol 2, and SQLite schema 2. It retains Ghostty analyze/ask and the cmux legacy transport; it does not port cmux review/cowork to Ghostty. Existing Python/CLI installations are not modified automatically.

## Preparation

Finish or explicitly stop in-flight Crosstalk commands and peer work. A timeout does not establish that an AI stopped editing files. Keep the source release available until installation succeeds. If using a custom state location, export the same `CROSSTALK_CONFIG_DIR` for installation and both participants.

From the selected source checkout:

```bash
python3 assets/scripts/crosstalk install --source "$PWD"
```

Optional flags are `--language en|ko`, `--home PATH` for an isolated home, and `--quiesced` only after remaining active workers were explicitly stopped. `--presets-only` adds missing built-in presets without changing runtime or DB. Existing presets and unknown config keys are preserved.

The installation lives under the state directory (default `~/.claude/crosstalk`):

- `releases/<version>-<content-id>` contains an immutable runtime and instruction snapshot.
- `current` is the atomically replaced runtime pointer.
- `installation.json` records checksums, destinations, backup paths, previous release and the current phase.
- `maintenance.json` prevents starting work during an incomplete installation.
- `install-backups/<install-id>` preserves files replaced during installation.

Wrappers retain `~/.claude/scripts/crosstalk` and bridge paths. The optional executable symlink is `~/.local/bin/crosstalk`; an unrelated command at that location is preserved and blocks installation rather than being overwritten. The Python package and launcher are always activated together. Runtime lookup is independent of cwd and marketplace cache location.

## Migration and instruction reload

The installer invokes explicit `migrate` after staging and before changing the runtime pointer. Migration uses a verified SQLite backup and preserves message IDs, bodies, reply relationships and FIFO order. Old received work requires recovery; old pane addresses do not automatically establish new session ownership. Normal mailbox calls do not silently migrate.

After installation, inspect `capabilities --json` and `doctor --offline`. Reload updated instructions in already-open Claude/Codex/agy sessions, then complete the protocol-2 handshake. An old in-memory instruction set is not compatible merely because disk files were updated. Protocol-1 replies without a lease are rejected. Run the actual setup and bidirectional conversation checks separately from offline installation checks.

## Interrupted installation and rollback

If an installed Python module is missing or changed, the launcher checks the runtime manifest before importing the package. `crosstalk doctor --offline --json` reports `INSTALLATION_INCOMPLETE` with exit code 7 without consuming messages or changing the DB. Repair using an intact copy of the same source release, not the damaged executable:

```bash
CROSSTALK_CONFIG_DIR="<existing-state-directory>" \
  python3 "<verified-source>/assets/scripts/crosstalk" install \
  --source "<verified-source>" --home "<original-installation-home>"
```

The installer stages and validates a fresh release generation, then atomically replaces `current`. It retains the damaged directory (including modified or unknown files) at the manifest's `retained_release` path. DB and existing config values are preserved. A staging failure leaves the old pointer and directory untouched; rerunning the same source resumes the recorded replacement before or after pointer activation. Keep the retained directory until its contents have been inspected.

The installer checks the doctor's JSON `runtime_healthy` result as well as its exit code. That field becomes true only after runtime import and database inspection finish successfully. A missing or false value stops activation. Pending notification issues and expected installation-in-progress notices do not make an otherwise healthy runtime fail this check.

Rerun the exact same source release and command. The installer validates staged checksums and the actual DB state before continuing. It refuses to resume a different release over an unfinished installation. Do not remove the maintenance marker by hand or delete the database to make a check pass.

Before migration, failure leaves the previous active runtime in place. After migration, repair forward with the same compatible v0.11 runtime. The installer does not provide automatic down-migration or replace a live v2 DB with an older backup. In particular, messages created after migration would be lost by restoring that backup. A legacy v0.10 source is rejected before any DB mutation. A manual pre-use rollback, if required, must separately verify that no v2 writes occurred and preserve both DB copies; it is not an installer command.

The active runtime pointer changes atomically. Distributed home-directory instruction files are not one filesystem transaction; manifest validation and maintenance cover the remaining steps. Replacing executables cannot retroactively stop an old process already running, which is why quiescing work before upgrade is required.

## Uninstall

`crosstalk uninstall` removes only unchanged manifest-owned runtime/instruction files and owned symlinks. Modified files are reported and retained. State, backups, rules/personas, logs and uncleaned review worktrees remain. Without a manifest, removal refuses to guess legacy ownership. Third-party CLIs and the marketplace plugin are not removed.
