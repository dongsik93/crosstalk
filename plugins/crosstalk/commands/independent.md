---
description: Review the current user task independently with a fresh Codex conversation, using captured user statements instead of a rewritten first question.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: [검토 대상 또는 추가 제약]
---

# /crosstalk:independent

This is the explicit alias for natural requests such as “옆에 Codex랑 독립적으로 검토해.” The user does not need `--engine`.

Run the installed runtime's `capabilities --json` with exact current surface/config context and read its `independent_instructions` path. Follow that single workflow. The current implementation supports a Claude caller and a fresh Codex peer on Ghostty.

Use the hook-provided capture ID, inspect `input sources`, select the earliest relevant original user message and prepare the contiguous source interval. Never turn `$ARGUMENTS`, a Claude-generated summary, or a guessed user intention into a self-certified captured input. If the actual question is clear, proceed; ask one focused question only for missing scope or unverified provenance.

Start with `run start codex --input-id ... --review-mode independent --operation-id ...`, create the input-bound fresh split with `bridge launch codex --fresh-for-input ...`, then attach its exact surface through the same run's `run continue`. Preserve IDs on retries and normal permission settings. Do not reuse or clear an existing Codex conversation.

After preparation, use the canonical discussion actions, leases and initial disclosure barrier. Do not copy a second set of round rules here, use raw managed send/reply/ack, or start another run from a wake-up.
