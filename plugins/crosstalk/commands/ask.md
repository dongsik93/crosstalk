---
description: Quick opinion sampling. Fire-and-forget — caller fans out the question, everyone answers in their own pane once, then it's done. No ping, no callback, no aggregation.
allowed-tools: Bash, AskUserQuestion
argument-hint: <질문>
---

# /crosstalk:ask (가벼운 의견 수집 — fire-and-forget)

각 peer에게 같은 질문을 한 번 던지고, 호출자도 자기 답을 그 자리에서 출력하고, 끝. callback도 ping도 통합도 없음.

**analyze와 차이**: analyze는 ping/callback/verdict/핑퐁이 다 강제 — *합의가 목적*이라. ask는 그게 *전혀 없음* — *opinion sampling이 목적*이라.

**핵심**: 호출자는 *던지고 자기 답하고 끝남*. peer가 답을 줄 때까지 기다리지 않는다. peer는 자기 pane에서 알아서 답한다.

## 옵션

옵션 없음. `$ARGUMENTS` 전체가 질문.

## 전제 조건

- cmux 환경, split 안에 다른 AI CLI(Codex/Gemini) 1개 이상
- bridge 설치 완료

## 트리거 수신 규약 (peer가 받는 메시지)

- `[crosstalk] ask <agent> RUN_ID=<RUN_ID>` → `cat /tmp/crosstalk/run-<RUN_ID>/preambles/<agent>.md`

peer는 preamble 파일을 읽고 *자기 pane에 답을 출력*한다. ping 호출하지 마라 (ask는 callback 안 씀).

## 0단계: 인자 검증

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

`PEERS` 비어있으면 `/crosstalk:launch` 안내 후 종료.

## 2단계: run 디렉토리 (preamble 보관용만)

callback 안 쓰지만 preamble 파일을 디스크에 두려면 run 디렉토리는 필요.

```bash
RUN_ID=$(~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"

TMP=$(mktemp)
jq --arg mode ask '. + {mode: $mode}' "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"
```

`agents` / `current_round` 등은 *박지 않는다* — ask는 callback 흐름이 없으므로 컨텍스트 복원이 필요 없음.

## 3단계: fan-out (각 peer에 짧은 preamble + 트리거)

각 peer에 minimal preamble. **ping 호출 명령은 들어가지 않는다** — ask는 fire-and-forget.

```bash
mkdir -p "$RUN_DIR/preambles"

for entry in $PEERS; do
  PEER_SURFACE="${entry%|*}"
  PEER_KIND="${entry#*|}"
  PREAMBLE_FILE="$RUN_DIR/preambles/${PEER_KIND}.md"

  cat > "$PREAMBLE_FILE" <<CROSSTALK_ASK
[Crosstalk ask]

The user is asking everyone the same question. Answer it once, in your own way,
right here in your pane. This is fire-and-forget:

- No debate, no follow-up round, no verdict markers required.
- Do NOT call any ping or bridge command.
- Do NOT write any response file.
- Just print your answer to your own pane and stop.

=== Question (user's raw input) ===
${TOPIC}
CROSSTALK_ASK

  TRIGGER="[crosstalk] ask ${PEER_KIND} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$PEER_SURFACE" "$PREAMBLE_FILE" "$TRIGGER"
  sleep 1
done
```

## 4단계: 호출자 본인 답변 (즉시, 자기 pane에)

호출자는 자기 답을 *바로 자기 화면에 출력*하고 끝낸다. ping 호출 X, callback 대기 X, 응답 파일 작성 X.

```text
🟦 Claude:
<자기 답변 한 번>
```

(호출자가 Codex caller일 경우 `🟧 Codex:` 톤. 어쨌든 자기 pane에 자기 답만.)

## 5단계: 종료 한 줄

```bash
echo "✅ ask done — peers will answer in their own panes."
echo "📁 RUN_ID=$RUN_ID  (preambles: $RUN_DIR/preambles/)"
```

끝. callback 안 들어옴, 사용자가 *각 peer pane을 직접 본다*.

## 디렉토리 구조

```
/tmp/crosstalk/run-<RUN_ID>/
  manifest.json            # mode=ask
  preambles/
    <agent>.md             # 각 peer에 보낸 짧은 preamble (보관/디버깅용)
```

`responses/`, `done/` 디렉토리는 ask에서 안 쓴다 (callback 없으므로). start-run이 디렉토리를 미리 만들어도 무시.

## 주의

- **fire-and-forget**: 호출자는 *던지고 자기 답하고 끝*. peer 답변을 기다리지 않는다.
- **답변 통합 X**: 호출자는 다른 peer 답변을 *모으거나 요약하지 않는다*. 각 peer는 자기 pane에 그대로 띄움.
- **ping/callback 안 씀**: bridge ping 호출 안 함, callback 메시지 안 받음. 그래서 무한 대기 사고 0.
- **합의/판정 X**: 사용자가 각 pane 보고 본인이 판단.
- 가벼운 *opinion sampling* 용. 의사결정에 합의가 필요하면 `/crosstalk:analyze` 사용.
