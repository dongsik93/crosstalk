# Upgrading to v0.12

The implementation baseline is v0.11 commit `0d8a24e692bfde2ee3ee61fe84731050b85b0c0f`; this checkout did not have a v0.11 tag when work began. v0.12 keeps Python 3.11+, moves the database to schema 3 and runtime protocol to 3, and adds discussion engine 1/result schema 1. Do not confuse those independent version numbers.

## Preserve active work first

Finish or explicitly stop in-flight mutations and inspect any ongoing AI work. Expiry or cancellation does not prove a process stopped editing files. Preserve the same `CROSSTALK_CONFIG_DIR` for installation and both participants. Do not copy a live SQLite file by hand or reset state to avoid an upgrade error.

Use an intact verified source checkout:

```bash
python3 assets/scripts/crosstalk install --source "$PWD"
```

The existing staged installer, manifest, backup, maintenance and atomic runtime-pointer behavior applies. Engine and adapter packages, terminal driver, canonical discussion instructions and templates are part of the release inventory. Missing or unhealthy runtime contents must fail before activation; use the intact source installer for repair. See the [v0.11 installation foundation](upgrade-v0.11.md) for preservation and interruption details.

## Schema and owner transition

Explicit migration backs up the old DB and preserves IDs, message text, seq/FIFO, replies, claims/lease state and binding generations. Existing threads become explicitly `mailbox-v2`; their history is not interpreted to synthesize discussion runs. No run is created merely by migration. New runs alone use `discussion-v1` and the four engine tables.

The actual pinned v0.11 runtime is used as a compatibility fixture to verify it rejects schema 3 before writing or sending UI input. Supporting existing messages means the new runtime handles their stored owner; it does not permit the old binary to write the new DB. Normal receive/status do not migrate in the background.

## Reload and handshake

After installation inspect capabilities and doctor offline, then reload instructions in already open CLIs. Files copied to disk do not prove the current AI has read them. New engine participants explicitly challenge and bind with `--protocol 3 --engine-version 1`; protocol-2-only bindings remain ordinary mailbox compatibility, not engine readiness. Preserve exact current surface/config context on every Codex tool call, and reselect/rebind on resume.

The canonical workflow is returned as `discussion_instructions`; ordinary thread instructions remain `mailbox_instructions`. Existing RUN_ID paths stay legacy. Agy stays peer-only, and cmux does not become an engine backend. Keep launch permission choices explicit and local to the chosen launch.

## Explicit opt-in and rollback

`run start` explicitly opts into the discussion engine. The user-facing `analyze --engine` / `ask --engine` route follows that contract. With `engine_default=false`, ordinary new Ghostty requests keep mailbox behavior until live release gates are recorded. Changing a future creation default cannot change the execution driver of an existing run.

A schema-3 DB with new results must not be replaced by a schema-2 backup. This release does not promise lossless down-migration to v0.11. Prefer repairing with a compatible v0.12 runtime; keep the current DB, backups, reports and retained runtime files. An export failure is not a reason to rerun an analysis or roll back the database.

Actual upgrade/reload/setup checks remain listed individually in [verification](verification-v0.12.md); an isolated automated installation pass is not equivalent to an upgrade of a user's active home and CLIs.
