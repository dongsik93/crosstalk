---
description: Resume the preserved topic through the detected Ghostty or cmux backend.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: (no arguments)
---

# /crosstalk:resume

Read the preserved topic with `~/.claude/scripts/crosstalk_bridge.sh pending-load`. If empty, report that no topic is saved. Show the original topic; do not alter its wording. If the user has already requested resumption, continue without asking again.

Run the current `/crosstalk` entrypoint from `~/.claude/commands/crosstalk.md` with that topic. It detects the backend through the bridge:

- Ghostty: prepare the peer and check `crosstalk capabilities --json` and read `discussion_instructions` for the earlier explicit engine choice or `mailbox_instructions` for ordinary work. A known stored run is inspected with `run status/next` rather than replaced with a new run. Do not create a legacy run or tell the user to start cmux.
- cmux: use the existing cmux analysis workflow.
- Identification error: retain pending and show the error. If Ghostty reports multiple same-directory candidates, use `/crosstalk:setup --surface ghostty:<UUID>` from the intended CLI once.

Clear pending with `bridge pending-clear` only after the topic has been successfully queued/started. A failed preparation must not discard it. Only the most recently saved topic is retained.

`resume`는 준비 실패 때 보관한 주제를 재개합니다. 이미 DB에 저장된 메시지는 `recover ID`로 진단하고 사용자 승인 후 같은 메시지를 재점유합니다. `resume`으로 새 요청을 만들어 기존 claim을 대체하지 않습니다.

`run continue`는 workflow 보류/승인된 local action 인계이고, `recover`는 message lease 재점유이며, `retry`는 같은 알림 재전송이다. 세 동작을 `resume`이라는 이름으로 자동 실행하지 않는다.
