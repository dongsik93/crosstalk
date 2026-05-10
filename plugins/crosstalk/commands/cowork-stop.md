---
description: Stop an in-flight cowork run. Sends /goal clear + termination notice to every participating peer via cmux. Then collects whatever they have written so far.
allowed-tools: Bash, AskUserQuestion
argument-hint: [RUN_ID]
---

# /crosstalk:cowork-stop

진행 중인 cowork run에 강제 종료 신호. 각 peer의 `/goal` 훅이 stop을 막고 있어도 외부에서 깬다.

## 동작

### 1) RUN_ID 결정

`$ARGUMENTS`가 비어있으면 가장 최근 cowork run을 자동 선택:

```bash
ARG_RUN_ID="$ARGUMENTS"
if [ -z "$ARG_RUN_ID" ]; then
  # ~/.crosstalk/last의 manifest가 cowork면 그것 사용. 아니면 /tmp/crosstalk에서 가장 최근.
  LAST_MANIFEST="$HOME/.crosstalk/last/manifest.json"
  if [ -f "$LAST_MANIFEST" ] && [ "$(jq -r '.mode' "$LAST_MANIFEST")" = "cowork" ]; then
    RUN_ID=$(jq -r '.run_id' "$LAST_MANIFEST")
  else
    # /tmp/crosstalk/run-* 중 가장 최근 mode=cowork
    RUN_ID=""
    for D in $(ls -t /tmp/crosstalk/run-* 2>/dev/null); do
      M="$D/manifest.json"
      if [ -f "$M" ] && [ "$(jq -r '.mode' "$M" 2>/dev/null)" = "cowork" ]; then
        RUN_ID=$(jq -r '.run_id' "$M")
        break
      fi
    done
  fi

  if [ -z "$RUN_ID" ]; then
    echo "❌ 진행 중인 cowork run을 찾을 수 없습니다."
    echo "Next: 명시적으로 RUN_ID를 인자로 주세요: /crosstalk:cowork-stop <RUN_ID>"
    exit 0
  fi

  echo "🛑 가장 최근 cowork run을 stop합니다: RUN_ID=$RUN_ID"
else
  RUN_ID="$ARG_RUN_ID"
fi
```

### 2) 사용자 확인

```
🛑 cowork run-${RUN_ID} 강제 종료

다음이 발생합니다:
  - 모든 peer 세션에 /goal clear 신호 발송
  - "[crosstalk:cowork-stop] 작업 중단" 안내 메시지 발송
  - peer의 현재까지 작업분은 *그대로 유지* (커밋/파일 그대로)
  - worktree는 keep (사용자 수동 검토용)

계속할까요?
```

AskUserQuestion: [stop / cancel].

### 3) notify-stop

```bash
~/.claude/scripts/crosstalk_bridge.sh notify-stop "$RUN_ID"
```

bridge가 manifest의 peers를 순회하며 각 surface에 cmux send.

### 4) 결과 수집 (있으면)

5초 대기 후 응답 파일 존재 여부 확인:

```bash
sleep 5
RUN_DIR="/tmp/crosstalk/run-$RUN_ID"
HAS_ANY=0
for f in "$RUN_DIR/responses"/*.md; do
  [ -f "$f" ] && HAS_ANY=1 && break
done
```

응답 있으면 cowork.md 7단계와 같은 통합 보고 생성 (끝에 "⚠️ 사용자 stop — 작업 일부 미완" 표시).
응답 없으면:
```
⚠️ 응답 파일 없음. peer가 작업 보고를 쓰기 전에 종료됨.

각 worktree 직접 확인:
  - claude: <path>
  - codex:  <path>
```

### 5) 마지막 안내

```
✅ cowork-stop 완료
📁 결과 (있으면): /tmp/crosstalk/run-${RUN_ID}/cowork-summary.md
📁 worktrees:    /tmp/crosstalk/worktrees/run-${RUN_ID}/

worktree 정리하려면: 각 worktree에서 git status 확인 후
  git worktree remove --force <path>
또는 일괄:
  ~/.claude/scripts/crosstalk_bridge.sh cleanup-worktrees ${RUN_ID}
```

## 주의

- **수동 정리 안전**: cowork-stop은 *신호만* 보낸다. 파일/커밋은 손대지 않음.
- **peer가 stop 신호를 무시할 수도**: `/goal` 훅 구현에 따라. 그 경우 사용자가 peer pane에서 직접 Ctrl+C.
- **여러 cowork 동시 실행 가능**: 각 RUN_ID 독립. RUN_ID 명시해서 stop.
