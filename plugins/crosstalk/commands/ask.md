---
description: Quick opinion sampling. Each peer answers once in their own way. No debate, no ping-pong, no verdict markers — just collect parallel answers.
allowed-tools: Bash, AskUserQuestion
argument-hint: <질문>
---

# /crosstalk:ask (가벼운 의견 수집)

각 peer에게 같은 질문을 한 번씩 던지고 답변을 모아 출력. 토론도 합의도 없음.

**analyze와 차이**: analyze는 "결론 비교 + 합의/분기"가 목적이라 verdict 마커, 신뢰도, 핑퐁 라운드가 강제됨. ask는 그냥 *각자 한 번 답하고 끝*. 의사결정이 아니라 *opinion sampling*.

## 옵션

옵션 없음. `$ARGUMENTS` 전체가 질문.

## 전제 조건

- cmux 환경, split 안에 다른 AI CLI(Codex/Gemini) 1개 이상
- bridge 설치 완료

## 트리거 수신 규약 (peer가 받는 메시지)

- `[crosstalk] ask <agent> RUN_ID=<RUN_ID>` → `cat /tmp/crosstalk/run-<RUN_ID>/preambles/<agent>.md`

트리거 자체에는 답하지 말고, preamble 파일을 읽은 뒤 응답 파일 작성 + ping까지 수행한다.

## 0단계: 인자 검증

`$ARGUMENTS`가 비어있으면 사용법 안내 후 종료.

```bash
TOPIC="$ARGUMENTS"
if [ -z "$(echo "$TOPIC" | tr -d '[:space:]')" ]; then
  cat <<'USAGE'
Usage: /crosstalk:ask <question>

Examples:
  /crosstalk:ask 이 PR 안전?
  /crosstalk:ask Compose vs XML — 우리 프로젝트 기준 어느 쪽이 나아?
  /crosstalk:ask 이 코드 왜 이래?
USAGE
  exit 0
fi
```

## 1단계: peer 탐색

```bash
PEERS_RAW=$(~/.claude/scripts/crosstalk_bridge.sh list-peers)
PEERS=$(printf '%s\n' "$PEERS_RAW" | awk -F'\t' '$2 ~ /^(claude|codex|gemini)$/ {print $1"|"$2}')
```

`PEERS`가 비어있으면 `/crosstalk:launch` 안내 후 종료.

## 2단계: run 디렉토리 + manifest

```bash
RUN_ID=$(~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"

MODERATOR_KIND=$(jq -r '.moderator_kind // "claude"' "$MANIFEST")
case "$MODERATOR_KIND" in
  claude|codex) ;;
  *) MODERATOR_KIND="claude" ;;
esac

AGENTS=("$MODERATOR_KIND")
for p in $PEERS; do
  AGENTS+=("${p#*|}")
done

TMP=$(mktemp)
jq --arg mode ask \
   --argjson round 1 \
   --argjson agents "$(printf '%s\n' "${AGENTS[@]}" | jq -R . | jq -s .)" \
   '. + {mode: $mode, agents: $agents, current_round: $round}' \
   "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"
```

## 3단계: fan-out (각 peer에 짧은 preamble + 트리거)

각 peer의 preamble을 파일로 작성. 본문은 *최소* — 답변 형식 강제 X, verdict 마커 X.

```bash
for entry in $PEERS; do
  PEER_SURFACE="${entry%|*}"
  PEER_KIND="${entry#*|}"
  PREAMBLE_FILE="$RUN_DIR/preambles/${PEER_KIND}.md"

  cat > "$PREAMBLE_FILE" <<CROSSTALK_ASK
[Crosstalk ask]

The user is asking everyone the same question. Answer it once, in your own way.
This is not a debate. There is no follow-up round. No verdict markers required.

=== Question (user's raw input) ===
${TOPIC}

=== How to respond ===
Write your answer to the following file with a shell heredoc.
Do not use WriteFile-like tools.

cat > /tmp/crosstalk/run-${RUN_ID}/responses/${PEER_KIND}-r01.md <<'EOF'
<your answer here — any length, any form>
EOF

~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} ${PEER_KIND} 1
CROSSTALK_ASK

  TRIGGER="[crosstalk] ask ${PEER_KIND} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$PEER_SURFACE" "$PREAMBLE_FILE" "$TRIGGER"
  sleep 1
done
```

**호출자 본인**도 동등하게 자기 답변 작성:

```bash
cat > "$RUN_DIR/responses/${MODERATOR_KIND}-r01.md" <<'EOF'
<자기 답변 — 자유 길이/형식>
EOF
~/.claude/scripts/crosstalk_bridge.sh ping "$RUN_ID" "$MODERATOR_KIND" 1
```

## 4단계: 슬래시 커맨드 종료 → callback 대기

callback 모델 — analyze와 동일. 한 라운드만 발송하고 종료.

## 5단계: callback 핸들링 — 답변 모아서 출력

호출자 pane이 callback 메시지를 받으면 (Claude는 `[crosstalk] ... done`, Codex는 `$crosstalk callback ...`):

1. RUN_ID / AGENT / ROUND 파싱
2. manifest에서 컨텍스트 복원:
   ```bash
   MANIFEST="/tmp/crosstalk/run-${RUN_ID}/manifest.json"
   AGENTS=($(jq -r '.agents[]' "$MANIFEST"))
   MODE=$(jq -r '.mode' "$MANIFEST")    # "ask"
   ```
3. 모든 참가자 ping 도착 확인 (analyze와 동일):
   ```bash
   ALL_DONE=1
   for agent in "${AGENTS[@]}"; do
     [ -f "$RUN_DIR/done/${agent}-r01" ] || ALL_DONE=0
   done
   ```
   - 빠진 참가자가 있으면 → 사회자는 *조용히 종료*. 마지막 ping 도착 시 다시 진입.

4. **모두 도착 → 출력 (통합 X — 사회자는 답변을 *모으거나 합치지 않는다*)**:

각 peer는 이미 자기 응답 파일에 답변을 썼고, 자기 pane 화면에도 답변을 그대로 출력해뒀다. 사용자는 cmux split에서 *각 peer pane을 직접 본다*. 사회자(호출자)는 다음 한 줄만 출력:

```bash
LAST=$(~/.claude/scripts/crosstalk_bridge.sh register-last "$RUN_ID")
echo "✅ ask done — RUN_ID=$RUN_ID"
echo "📁 responses: $RUN_DIR/responses/  (last: $LAST)"
```

호출자 자신의 답변도 *자기 pane에서 자연스럽게 출력*된 상태. 다른 peer 답변을 *재출력하거나 요약하지 마라*.

## 6단계: 끝

토론 라운드 X, 합의 판정 X, 답변 통합 X. 사용자가 각 peer pane을 보고 *본인이 직접 판단*.

추가 라운드를 원하면 사용자가 *명시적으로* `/crosstalk:analyze <topic>`을 호출 (다른 흐름).

## 디렉토리 구조

```
/tmp/crosstalk/run-<RUN_ID>/
  manifest.json            # mode=ask, agents, current_round
  done/
    <agent>-r01            # ping 마커
  responses/
    <agent>-r01.md         # 각 peer의 답변 (자유 형식)
  preambles/
    <agent>.md             # 각 peer에 보낸 짧은 preamble
```

답변은 통합 파일로 합치지 않는다. 사용자는 각 peer pane을 직접 보고, 디스크 사본은 `responses/<agent>-r01.md` 또는 `~/.crosstalk/last/responses/`에서 확인.

## 주의

- **답변 형식 강제 X**: 각자 자기 페이스로 답함. 1줄도 OK, 페이지도 OK.
- **verdict 마커 강제 X**: `[AGREE]` `[RESPECT_DISAGREE]` 안 써도 됨. 사용자가 본인 판단.
- **핑퐁 라운드 X**: 1라운드로 끝.
- **답변 통합 X**: 호출자가 답변을 *모으거나 요약하거나 재출력하지 마라*. 각 peer는 자기 pane에 답변을 띄우고, 사용자가 그걸 직접 본다. 호출자는 마지막에 "ask done" 한 줄과 보관 경로만 출력.
- analyze보다 가벼운 *opinion sampling* 용. 의사결정에 합의가 필요하면 analyze 사용.
