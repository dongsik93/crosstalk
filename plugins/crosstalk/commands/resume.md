---
description: Resume a Crosstalk run from a topic that was preserved when /crosstalk was called outside cmux. Reads ~/.claude/crosstalk/pending.json and feeds the topic back into /crosstalk.
allowed-tools: Bash, AskUserQuestion
argument-hint: (no arguments)
---

# /crosstalk:resume

`/crosstalk <topic>`을 cmux *외부*에서 호출하면 topic이 `~/.claude/crosstalk/pending.json`에 저장되고, cmux 워크스페이스로 이동한 뒤 이 명령으로 *그대로* 이어 진행한다. 사용자는 topic을 다시 입력하지 않는다.

## 동작

1. **pending 로드**:
   ```bash
   TOPIC=$(~/.claude/scripts/crosstalk_bridge.sh pending-load 2>/dev/null)
   ```
   - 비어있으면 안내 후 종료:
     ```
     보존된 topic이 없습니다. /crosstalk <주제>로 새로 시작하세요.
     ```

2. **확인 프롬프트** (실수로 다른 toption 이어가지 않게):
   ```
   📌 저장된 topic을 이어 진행합니다:

     "${TOPIC}"

   계속할까요?
   ```
   AskUserQuestion: [계속 / 새 토픽으로 변경 / 취소]
   - "새 토픽으로 변경" → 사용자에게 topic 입력 받음
   - "취소" → pending 그대로 두고 종료

3. **/crosstalk 본문 실행** (= readiness 통과한 상태로 analyze 진입):
   - cmux 안에 있고, peer 1개 이상 → 즉시 `/crosstalk:analyze ${TOPIC}` 본문 실행
   - peer 0개 → `/crosstalk:launch` 자동 실행 후 analyze 진입
   - cmux 외부면 → `/crosstalk:resume` 자체가 cmux 안에서 호출돼야 함을 안내 (이건 사용자 실수)

4. **성공 시 pending 정리**:
   ```bash
   ~/.claude/scripts/crosstalk_bridge.sh pending-clear
   ```

## 활용 시나리오

```
[cmux 외부 Claude]
사용자> /crosstalk Compose vs XML — 어느 쪽이 우리 프로젝트에 맞을까?

⚠️  cmux 워크스페이스 밖입니다. topic을 보존했습니다.
   다음: cmux 안에서 /crosstalk:resume

[cmux 안 Claude]
사용자> /crosstalk:resume

📌 저장된 topic을 이어 진행합니다:
   "Compose vs XML — 어느 쪽이 우리 프로젝트에 맞을까?"
   계속할까요? [계속]

→ analyze 진입, peer fan-out, 결과 비교까지 자동
```

## 주의

- pending은 *마지막 1개*만 저장한다. 새 `/crosstalk <topic>`이 cmux 외부에서 다시 호출되면 덮어씀.
- pending 파일은 평문 JSON — 민감 정보 들어갈 수 있다면 cmux 안에서 직접 입력 권장.
