---
description: Independent multi-agent analysis with conditional ping-pong. No moderator. Each peer analyzes the same raw input, results are compared, and disagreements trigger respect-based ping-pong until consensus or respectful divergence.
allowed-tools: Bash, AskUserQuestion
argument-hint: <분석 주제 / 자료 본문>
---

# /crosstalk:analyze (사회자 없는 독립 분석 + 조건부 핑퐁)

## 컨셉

사용자가 던진 주제를 **각 참가자(호출자 + 켜져있는 peer 전원)가 독립적으로 분석**하고, 결과를 비교한다. 사회자(중재자)가 따로 없다 — 호출한 본인이 fan-out + 비교표 출력 책임만 진다.

**핵심 원칙**:

- **자료 가공 X**: 사용자 원문 그대로 fan-out (지식 오염 방지).
- **룰/페르소나는 옵션**: 1회만 주입. 기본은 형식 강요 없음.
- **합의 강제 X**: 1라운드 분석 후 *대치 시에만* 핑퐁. 종료는 합의 / 존중 분기 / 하드 캡 10라운드.
- **verdict는 마커로만**: `[AGREE]` / `[RESPECT_DISAGREE: 사유]` 마커는 bridge가 정규식으로 잡는다. 사회자가 본문을 읽고 "합의 같다"고 판단해 종료할 수 없다 — 마커 없으면 핑퐁 진행.

## 옵션

- `--rules <name>` — 일회성 룰 프리셋 (예: `default`, `brainstorm`, `debate`). 옵션 없으면 `~/.claude/crosstalk/config.json`의 `active_rules` 사용. `none` 지정 시 룰 섹션을 빼고 보낸다 (각자 자기 페이스).
- `--persona <name>` — 일회성 페르소나 프리셋 (예: `senior-junior`, `critic-builder`, `triple-perspective`). `none` 지정 시 페르소나 섹션을 빼고 보낸다.
- 자료 본문은 가공 없이 **사용자 원문 그대로** fan-out된다.

룰/페르소나 본문은 active 파일에서 *그대로* 주입한다 — 압축/요약 X. 사용자가 룰 파일을 편집한 의도를 보존.

## 전제 조건

- cmux 환경에서 실행 중
- 본인 외 cmux split 안에 다른 AI CLI(Codex/Gemini) 1개 이상 있음 (없으면 `/crosstalk:launch` 안내 후 종료)
- bridge 스크립트 설치 완료

## 트리거 수신 규약 (v0.6.0+)

긴 본문은 cmux로 직접 보내지 않는다. peer pane이 아래 짧은 트리거를 받으면, 해당 파일을 직접 읽고 그 안의 절차를 따른다.

- `[crosstalk] preamble <agent> RUN_ID=<RUN_ID>` → `cat /tmp/crosstalk/run-<RUN_ID>/preambles/<agent>.md`
- `[crosstalk] round <NN> <agent> RUN_ID=<RUN_ID>` → `cat /tmp/crosstalk/run-<RUN_ID>/rounds/r<NN>-<agent>.md`

트리거 자체에는 답하지 말고, 파일 본문을 읽은 뒤 응답 파일 작성 + ping까지 수행한다.

## 0단계: 옵션 파싱 + 룰/페르소나 로드

`$ARGUMENTS`에서 옵션 추출:
- `--rules <name>` (있으면) → `RULES_NAME=<name>`
- `--persona <name>` (있으면) → `PERSONA_NAME=<name>`
- 나머지 텍스트 = `TOPIC` (가공 X)

`TOPIC`이 비어있으면 사용법 안내 후 종료:

```
사용법: /crosstalk:analyze [--rules <name>] [--persona <name>] <분석 주제 / 자료 본문>

예:
  /crosstalk:analyze 이 PR을 머지해도 안전한지 봐줘. <PR 본문>
  /crosstalk:analyze Compose vs XML — 우리 프로젝트 기준 어느 쪽이 나아?
  /crosstalk:analyze --persona critic-builder 이 설계 어떻게 봐?
  /crosstalk:analyze --rules debate 이 의사결정 진짜 맞나?
```

옵션 없으면 active 프리셋 로드:
```bash
CONFIG=~/.claude/crosstalk/config.json
LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac
ACTIVE_RULES=$(jq -r '.active_rules // "default"' "$CONFIG" 2>/dev/null || echo "default")
ACTIVE_PERSONA=$(jq -r '.active_persona // "default"' "$CONFIG" 2>/dev/null || echo "default")
RULES_NAME="${RULES_NAME:-$ACTIVE_RULES}"
PERSONA_NAME="${PERSONA_NAME:-$ACTIVE_PERSONA}"
```

룰/페르소나 본문 로드 (자가치유: 디렉토리 비어있으면 마켓 캐시에서 자동 보충):
```bash
~/.claude/scripts/crosstalk_bridge.sh ensure-presets "$LANGUAGE" >/dev/null 2>&1 || true

RULES_FILE="$HOME/.claude/crosstalk/rules/${LANGUAGE}/${RULES_NAME}.md"
PERSONA_FILE="$HOME/.claude/crosstalk/personas/${LANGUAGE}/${PERSONA_NAME}.md"

# none 또는 파일 없으면 빈 본문 (해당 섹션 생략)
[ "$RULES_NAME" = "none" ] || [ ! -f "$RULES_FILE" ] && RULES_BODY="" || RULES_BODY=$(cat "$RULES_FILE")
[ "$PERSONA_NAME" = "none" ] || [ ! -f "$PERSONA_FILE" ] && PERSONA_BODY="" || PERSONA_BODY=$(cat "$PERSONA_FILE")
```

> 룰/페르소나 본문은 *압축/요약하지 마라*. 사용자가 파일을 수정한 의도를 보존해야 한다.

## 1단계: peer 탐색

```bash
# 자기 자신 제외한 cmux pane 목록 — <surface>\t<kind> 형식
PEERS_RAW=$(~/.claude/scripts/crosstalk_bridge.sh list-peers)

# kind가 claude/codex/gemini 인 것만 추출.
# awk 표현식은 반드시 single-quote로 감싸 셸 변수 치환을 방지한다 ($2는 awk 필드 참조).
PEERS=$(printf '%s\n' "$PEERS_RAW" | awk -F'\t' '$2 ~ /^(claude|codex|gemini)$/ {print $1"|"$2}')
```

`PEERS`가 비어있으면 `/crosstalk:launch` 안내 후 종료.

## 2단계: run 디렉토리 + manifest 생성

```bash
RUN_ID=$(~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
MANIFEST="$RUN_DIR/manifest.json"
echo "📁 run dir: $RUN_DIR"
```

`start-run`이 자동으로 `moderator_surface`를 manifest에 박는다. 추가로 *참가자 목록 + 모드*를 manifest에 머지한다 (callback 재진입 시 컨텍스트 복원용):

```bash
# AGENTS = 호출자(moderator_kind) + 감지된 peer kinds
MODERATOR_KIND=$(jq -r '.moderator_kind // "claude"' "$MANIFEST")
case "$MODERATOR_KIND" in
  claude|codex) ;;
  *) MODERATOR_KIND="claude" ;;
esac

AGENTS=("$MODERATOR_KIND")
for p in $PEERS; do
  AGENTS+=("${p#*|}")
done

# manifest 갱신 (mode + agents + current_round)
TMP_MANIFEST=$(mktemp)
jq --arg mode analyze \
   --argjson round 1 \
   --argjson agents "$(printf '%s\n' "${AGENTS[@]}" | jq -R . | jq -s .)" \
   '. + {mode: $mode, agents: $agents, current_round: $round}' \
   "$MANIFEST" > "$TMP_MANIFEST" && mv "$TMP_MANIFEST" "$MANIFEST"
```

> 별도 `state.sh`는 만들지 않는다. **manifest.json이 단일 진실** — callback 재진입 시 manifest만 읽으면 컨텍스트 복원 가능.

## 3단계: fan-out preamble 작성 + 짧은 트리거 전송

각 peer용 전체 preamble을 디스크에 저장한다. cmux로는 짧은 트리거만 보낸다.

```bash
mkdir -p "$RUN_DIR/preambles"

for entry in $PEERS; do
  PEER_SURFACE="${entry%|*}"
  PEER_KIND="${entry#*|}"
  PREAMBLE_FILE="$RUN_DIR/preambles/${PEER_KIND}.md"

  cat > "$PREAMBLE_FILE" <<CROSSTALK_PREAMBLE
[Crosstalk analyze]

다음 주제에 대한 너의 독립 분석을 듣고 싶다.
다른 참가자가 무엇을 답할지 의식하지 말고 너의 결론을 내라.

[페르소나 본문이 있을 때만]
═══ 페르소나 (${PERSONA_NAME}) ═══
${PERSONA_BODY}

[룰 본문이 있을 때만]
═══ 룰 (${RULES_NAME}) ═══
${RULES_BODY}

═══ 주제 (사용자 원문) ═══
${TOPIC}

═══ 답변 형식 ═══
1. 핵심 결론 (1-2문장)
2. 근거 (자유 길이)
3. 신뢰도 (high / medium / low)

═══ 답변 절차 ═══
답변 본문을 다음 셸로 파일에 기록 후 ping을 호출해라.
WriteFile 같은 도구 사용 X — 그냥 셸 heredoc.

cat > /tmp/crosstalk/run-${RUN_ID}/responses/${PEER_KIND}-r01.md <<'EOF'
<답변 본문>
EOF

~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} ${PEER_KIND} 1
CROSSTALK_PREAMBLE

  TRIGGER="[crosstalk] preamble ${PEER_KIND} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$PEER_SURFACE" "$PREAMBLE_FILE" "$TRIGGER"
  sleep 1
done
```

> 페르소나/룰 섹션은 1라운드 fan-out에만 한 번 박는다. 핑퐁 라운드(6단계)에는 다시 박지 않는다 — 이미 컨텍스트에 살아있음.
> 사용자 원문 `$TOPIC`는 *압축/요약/재해석 없이* 그대로 박는다.
> 트리거는 40~80자 수준이어야 한다. 큰 본문을 `send`로 직접 보내지 마라.

**호출자 본인도 동일 자료로 분석 시작** (다른 peer 답변 보지 않은 상태에서):
- 위 답변 형식대로 자기 분석을 작성
- `cat > $RUN_DIR/responses/${MODERATOR_KIND}-r01.md <<'EOF' ... EOF`
- `~/.claude/scripts/crosstalk_bridge.sh ping $RUN_ID $MODERATOR_KIND 1`

> **중요**: 호출자도 다른 peer ping 도착하기 *전에* 자기 답을 마쳐야 한다. 본인 의견을 먼저 박은 뒤 비교 단계로 가야 비교가 공정함.

## 4단계: 슬래시 커맨드 종료 (callback 대기)

callback 모델 — 한 라운드만 발송하고 슬래시 커맨드 종료. ping 메시지가 도착할 때마다 *새 슬래시 커맨드 진입*으로 다음 단계 진행. (사회자 bash 프로세스가 살아있을 필요 없음)

## 5단계: callback 핸들링 — 결론 비교

호출자 pane이 callback 메시지를 받으면:

- Claude caller: `[crosstalk] <agent> R<N> done — RUN_ID=...`
- Codex caller: `$crosstalk callback RUN_ID=... AGENT=... ROUND=... RESP=...`

1. RUN_ID / AGENT / ROUND 파싱
2. **manifest.json**에서 컨텍스트 복원:
   ```bash
   MANIFEST="/tmp/crosstalk/run-${RUN_ID}/manifest.json"
   AGENTS=($(jq -r '.agents[]' "$MANIFEST"))
   CURRENT_ROUND=$(jq -r '.current_round' "$MANIFEST")
   MODE=$(jq -r '.mode' "$MANIFEST")
   ```
3. **모든 참가자 ping 도착 확인**:
   ```bash
   ROUND_PADDED=$(printf '%02d' "$ROUND")
   ALL_DONE=1
   for agent in "${AGENTS[@]}"; do
     [ -f "$RUN_DIR/done/${agent}-r${ROUND_PADDED}" ] || ALL_DONE=0
   done
   ```
   - 빠진 참가자가 있으면 → 사회자는 *조용히 종료*. 마지막 ping 도착 시 다시 진입.

4. 모두 도착 → 응답 파일 읽어서 결론 추출:
   ```bash
   for agent in "${AGENTS[@]}"; do
     RESP="$RUN_DIR/responses/${agent}-r${ROUND_PADDED}.md"
     if [ ! -s "$RESP" ]; then
       # 답변 누락 — AskUserQuestion으로 재시도/스킵/중단 선택
       :
     fi
   done
   ```
   - 각 답변에서 "핵심 결론" 한 줄과 신뢰도, [AGREE]/[RESPECT_DISAGREE] 마커 추출

5. **결론 비교**:
   - 의미상 동일한 결론 → ✅ **합의 종료** (8단계 종합 결론)
   - 결론이 갈림 → 6단계 **핑퐁 라운드**

## 6단계: 핑퐁 라운드 (조건부)

대치 발생 시. 모든 참가자에게 보낼 *현재 분기 상황*과 입장 갱신 요청을 파일로 저장하고 짧은 트리거만 보낸다.

```bash
NEXT_ROUND=$((CURRENT_ROUND + 1))
ROUND_PADDED=$(printf '%02d' "$NEXT_ROUND")
mkdir -p "$RUN_DIR/rounds"

for entry in $PEERS; do
  PEER_SURFACE="${entry%|*}"
  PEER_KIND="${entry#*|}"
  ROUND_FILE="$RUN_DIR/rounds/r${ROUND_PADDED}-${PEER_KIND}.md"

  cat > "$ROUND_FILE" <<CROSSTALK_ROUND
[Crosstalk analyze - Round ${NEXT_ROUND}]

현재 분기 상황:

🟦 ${MODERATOR_KIND}: <한 줄 결론>
🟧 codex:   <한 줄 결론>
🟪 gemini:  <한 줄 결론>   ← 3자일 때만

핵심 이견: <어느 가정/우선순위에서 갈렸는지 — 호출자가 한 줄 정리>

너의 선택 (자유 형식 가능, 다음 중 하나로 끝낼 것):
  (a) 입장 유지 + 새 근거 추가
  (b) 상대 근거 인정하고 [AGREE]
  (c) 입장 변경 + 새 결론
  (d) 더 이상 양보 어려움 → [RESPECT_DISAGREE: <사유>]

답변 → 파일 → ping (포맷 동일):
cat > /tmp/crosstalk/run-${RUN_ID}/responses/${PEER_KIND}-r${ROUND_PADDED}.md <<'EOF'
<답변>
EOF
~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} ${PEER_KIND} ${NEXT_ROUND}
CROSSTALK_ROUND

  TRIGGER="[crosstalk] round ${ROUND_PADDED} ${PEER_KIND} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$PEER_SURFACE" "$ROUND_FILE" "$TRIGGER"
  sleep 1
done
```

> 호출자가 정리하는 "핵심 이견"은 *각 답변에서 발췌한 표현 기반*이어야 한다 — 새 해석 추가 X.

각 참가자에게 trigger 전송 후, **manifest의 current_round를 증가**시키고 슬래시 커맨드 종료:

```bash
TMP=$(mktemp)
jq --argjson r "$NEXT_ROUND" '.current_round = $r' "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"
```

다음 라운드는 다음 ping callback에서 진입.

## 7단계: 종료 조건 검사

각 응답 파일에서 verdict를 *bridge로 추출*한다 (LLM 자유 해석 X — deterministic):

```bash
declare -A VERDICTS REASONS CONFIDENCES
for agent in "${AGENTS[@]}"; do
  RESP="$RUN_DIR/responses/${agent}-r${ROUND_PADDED}.md"
  eval "$(~/.claude/scripts/crosstalk_bridge.sh extract-verdict "$RESP" \
    | sed -E 's/^/AG_/')"
  # AG_verdict / AG_reason / AG_confidence 변수가 채워짐
  VERDICTS["$agent"]="$AG_verdict"
  REASONS["$agent"]="$AG_reason"
  CONFIDENCES["$agent"]="$AG_confidence"
done
```

종료 판정:

| 조건 | 결과 |
|---|---|
| 전원 verdict=AGREE | ✅ 합의 종료 → 8단계 (합의) |
| 한 명 이상 verdict=RESPECT_DISAGREE | 🤝 존중 분기 종료 → 8단계 (분기) |
| 전원이 직전 라운드와 새 근거 없이 같은 주장 반복 | 🤝 존중 분기 종료 → 8단계 (분기) |
| 라운드 = 10 | ⚠️ 하드 캡 종료 → 8단계 (강제) |
| 위 어느 것도 아님 | 6단계 핑퐁 한 번 더 |

> verdict 마커(`[AGREE]`, `[RESPECT_DISAGREE: 사유]`)는 bridge가 정규식으로 잡는다. 사회자가 "이건 합의 같다" 같은 자유 해석으로 종료하지 말 것 — 마커만 신뢰.
>
> "새 근거 없이 같은 주장" 판정만 LLM 휴리스틱: 직전 응답 파일과 이번 응답 파일 비교. 보수적으로 (의심스러우면 한 라운드 더).

## 8단계: 최종 산출물

종료 유형에 따라 출력 형식 분기.

**합의 종료**:
```
✅ 종합 결론 (${ROUND} 라운드, 전원 합의)

결론: <한 단락>

근거 (공통):
- ...
- ...

라운드별 입장 변화 (간략):
- R1: <moderator>=X, codex=Y
- R2: 전원=X
```

**존중 분기 종료**:
```
🤝 존중 분기 (${ROUND} 라운드, 합의 불가 — 가치/우선순위 차이)

🟦 <moderator>: <결론> (근거: ...) [verdict: ${VERDICT}, conf: ${CONF}]
🟧 codex:   <결론> (근거: ...) [verdict: ${VERDICT}, conf: ${CONF}]
🟪 gemini:  <결론> (근거: ...) [verdict: ${VERDICT}, conf: ${CONF}]

핵심 이견: <어느 가정/우선순위에서 갈렸는지>

근거 (footnote): 각 verdict는 응답 파일에서 bridge가 추출. RESPECT_DISAGREE 사유는
응답 파일의 [RESPECT_DISAGREE: ...] 마커에서 가져왔다.
```

**하드 캡 종료**:
```
⚠️ 10 라운드 도달 — 강제 종료

각 참가자 마지막 입장:
🟦 <moderator>: ...
🟧 codex:   ...
🟪 gemini:  ...

(추가 라운드를 원하면 같은 주제로 다시 호출)
```

## 9단계: 보관 + 마지막 run 등록 (v0.2.6+)

```bash
ANALYSIS_FILE="$RUN_DIR/analysis.md"
cp <위 산출물> "$ANALYSIS_FILE"
echo "💾 보관: $ANALYSIS_FILE"

# 영구 위치(~/.crosstalk/last)로 사본 등록 — /tmp 정리 정책 영향 없음
LAST_DIR=$(~/.claude/scripts/crosstalk_bridge.sh register-last "$RUN_ID")

# 사용자 화면에 1줄 요약 + 경로 출력
SUMMARY=$(grep -m1 -E '^[^#[:space:]]' "$ANALYSIS_FILE" 2>/dev/null | head -c 200)
echo ""
echo "✅ ${SUMMARY}"
echo "📁 last: $LAST_DIR  (또는 $RUN_DIR)"
```

응답 파일은 `$RUN_DIR/responses/`와 `$LAST_DIR/responses/`에 모두 보존.

---

## 디렉토리 구조 (참고)

```
/tmp/crosstalk/run-<RUN_ID>/
  manifest.json       # mode=analyze + moderator + peers + agents + current_round (단일 진실)
  done/
    <moderator>-r01   # ping 마커
    codex-r01
    gemini-r01
    <moderator>-r02
    ...
  responses/
    <moderator>-r01.md # 라운드별 답변 본문
    codex-r01.md
    gemini-r01.md
    ...
  preambles/
    codex.md          # 1라운드 fan-out 본문
    gemini.md
  rounds/
    r02-codex.md      # 핑퐁 라운드 본문
    r02-gemini.md
  analysis.md         # 최종 산출물
```

## 주의

- **사용자 원문은 절대 가공하지 마라.** 압축/요약/재해석 = 지식 오염.
- **사회자가 의견 추가하지 마라.** 호출자 본인 분석은 자기 ping으로 들어가는 것이지, 비교표에 추가 코멘트 X.
- **합의를 강요하지 마라.** 존중 분기는 정상 종료. 합의가 늘 옳은 결과는 아니다.
- 핑퐁 메시지의 "핵심 이견" 한 줄은 각 답변 표현 발췌. 호출자의 새 해석 X.
