# $crosstalk resume

`resume` retains its existing meaning: continue the raw topic saved after preparation failed. Inspect a known active discussion run with `run status`/`run next` first; do not replace that stored run with a new start.

Read the preserved topic with `crosstalk_bridge.sh pending-load`. If absent, say so. If the user explicitly asked to resume, use that authorization; do not ask again merely for an ordinary next action. Preserve the exact topic and its earlier engine/ordinary choice. On Ghostty follow readiness and the corresponding canonical workflow (`discussion.md` for explicit engine opt-in, `mailbox.md` for ordinary threads); cmux retains analyze.md.

Clear pending with `bridge pending-clear` only after the topic is durably stored in its intended run/thread. Preparation failure must not discard it.

Keep recovery operations distinct: `run continue` releases workflow pause or explicitly reissues an unfinished local handle after validated rebinding; `recover <MESSAGE_ID>` reclaims a message lease only with authorization; `retry <MESSAGE_ID>` resubmits a notification. None of them creates a new topic or silently repeats peer analysis.
