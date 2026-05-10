---
description: Run a Crosstalk debate with peer AI CLI panes. Supports en/ko UI, rules, and personas.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: [--rules <name>] [--persona <name>] [--transport off|file|screen] <토론 주제>
---

# Crosstalk — 다중 AI 토론 (Claude 사회자)

cmux 안에서 분할된 다른 AI CLI(Codex/Gemini)들과 자동으로 토론을 진행한다.
**이 명령을 호출한 본인(Claude)이 사회자**가 된다.

## 옵션

- `--rules <name>` — 일회성 룰 프리셋 명시 (예: `brainstorm`, `debate`, `default`)
- `--persona <name>` — 일회성 페르소나 프리셋 명시 (예: `senior-junior`, `critic-builder`)
- `--transport off|file|screen` — 답변 받는 방법. **기본 `off`** (모두 응답 파일 기반).
  - `off` (기본, v0.2.1+): peer가 셸 heredoc로 응답 파일 작성 → ping. 사회자는 *파일에서 읽음* (화면 캡처 X).
  - `file`: 별도 transport 섹션을 매 턴 추가해 파일 작성 명시. (긴 답변/장기 운영 시)
  - `screen`: 답변을 BEGIN/END 블록으로 화면에 출력하게 함. (legacy; gemini agentic 도구 사고 방지용)
- 옵션 없으면 `~/.claude/crosstalk/config.json`의 active 프리셋 사용

룰/페르소나 관리는 `/crosstalk:rules`, `/crosstalk:persona`, `/crosstalk:status` 참고.

## 전제 조건

- cmux 환경에서 실행 중
- 본인 외에 cmux split 안에 다른 AI CLI(Codex/Gemini) 1개 이상 떠있음
- bridge 스크립트가 설치되어 있음: `~/.claude/scripts/crosstalk_bridge.sh`
  - 미설치 시 `/crosstalk:install` 먼저 실행 안내

## 0단계: 옵션 파싱 + 룰/페르소나 로드

`$ARGUMENTS`에서 옵션 추출:
- `--rules <name>` (있으면) → `RULES_NAME=<name>`
- `--persona <name>` (있으면) → `PERSONA_NAME=<name>`
- `--transport off|file|screen` (있으면) → `TRANSPORT_OPTION=<value>`. **기본 `off`** — 자연스러운 핑-퐁 토론.
- 나머지 텍스트 = 토론 주제

```bash
TRANSPORT_OPTION="${TRANSPORT_OPTION:-off}"
case "$TRANSPORT_OPTION" in off|file|screen) ;; *) TRANSPORT_OPTION="off" ;; esac
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

룰/페르소나 본문 Read (자가치유: 디렉토리 비어있으면 마켓 캐시에서 자동 보충):
```bash
# 자가치유 — 처음 toggle한 언어든, 사용자가 디렉토리 지웠든 빈 디렉토리면 채워준다.
~/.claude/scripts/crosstalk_bridge.sh ensure-presets "$LANGUAGE" >/dev/null 2>&1 || true

RULES_PATH=~/.claude/crosstalk/rules/${LANGUAGE}/${RULES_NAME}.md
PERSONA_PATH=~/.claude/crosstalk/personas/${LANGUAGE}/${PERSONA_NAME}.md
[ ! -f "$RULES_PATH" ] && RULES_PATH=~/.claude/crosstalk/rules/en/${RULES_NAME}.md
[ ! -f "$PERSONA_PATH" ] && PERSONA_PATH=~/.claude/crosstalk/personas/en/${PERSONA_NAME}.md
if [ ! -f "$RULES_PATH" ]; then
  [ "$LANGUAGE" = "ko" ] && echo "❌ 룰 '$RULES_NAME' 없음 — /crosstalk:rules 확인" || echo "❌ Rule '$RULES_NAME' not found — run /crosstalk:rules"
  exit 1
fi
if [ ! -f "$PERSONA_PATH" ]; then
  [ "$LANGUAGE" = "ko" ] && echo "❌ 페르소나 '$PERSONA_NAME' 없음 — /crosstalk:persona 확인" || echo "❌ Persona '$PERSONA_NAME' not found — run /crosstalk:persona"
  exit 1
fi
```

Read 도구로 두 파일 본문 메모리에 로드. 이후 모든 토론 메시지에 주입.

## 1단계: 환경 스캔

```bash
~/.claude/scripts/crosstalk_bridge.sh list-peers
```

출력 형식: `<surface_ref>\t<kind>` 라인들. `kind`는 `claude`/`codex`/`gemini`/`shell`/`unknown`.

검증:
- `unknown`/`shell`은 후보 목록에서 제외.
- 모두 `unknown` → `/crosstalk:setup` 실행 안내 후 종료.
- 후보가 0개(0줄 또는 모두 제외됨) → **launch 제안**:

  먼저 `cmux ping`으로 cmux 자체가 떠있는지 확인:
  ```bash
  cmux ping >/dev/null 2>&1 && CMUX_OK=true || CMUX_OK=false
  ```

  - `CMUX_OK=false` → cmux 미실행/미설치. 언어에 따라 안내 후 종료:
    - en: Start cmux first, or run `/crosstalk:launch` outside cmux.
    - ko: cmux를 먼저 띄우거나 `/crosstalk:launch`를 외부에서 실행해야 한다.
  - `CMUX_OK=true` → 사용자에게 명확히 안내 후 종료:
    en:
    ```text
    🛑 No peer AI pane was found in the current cmux split.

    Run these commands in order:
      1. Set up panes:
           /crosstalk:launch
      2. Then retry:
           /crosstalk <topic>   or   /crosstalk:debate <topic>
    ```
    ko:
    ```text
    🛑 cmux split 안에 다른 AI pane(Codex/Gemini)이 없어 토론을 시작할 수 없습니다.

    다음 순서로 다시 시도해주세요:
      1. 먼저 다음 명령으로 환경을 셋업:
           /crosstalk:launch
      2. 그 다음 이 명령을 다시 실행:
           /crosstalk <주제>   또는   /crosstalk:debate <주제>
    ```
    슬래시 커맨드는 다른 슬래시 커맨드를 자동 호출하지 않는다 — 사용자가 직접 두 번 실행해야 한다.

## 2단계: 사용자에게 상대 선택 받기

`AskUserQuestion` 도구로 토론 상대 선택. 문구는 `LANGUAGE`에 따라 분기:

- en: header `Debate peer`, question `Choose peer AI panes for this debate.`
- ko: header `토론 상대`, question `토론할 AI pane을 선택하세요.`

발견된 CLI 종류에 따라 옵션 동적 구성:

- 각 CLI별 1:1 토론
- 2개 이상이면 "전체 다자 토론(Claude 사회자)"
- "취소"

`header`는 `토론 상대`, `multiSelect`는 `false`.

선택이 "취소"면 즉시 종료.

## 3단계: 안전 모드 + 페르소나 + 룰 preamble

**중요: 페르소나/룰/시스템 마커는 이 preamble에서 *한 번만* 박는다. 이후 매 턴 메시지에는 다시 박지 않는다.** AI가 매 턴 셋업을 다시 처리하느라 instruction following을 망치는 걸 막기 위함.

각 참여자에게 다음 형태로 한 번씩 전송:

```
[Crosstalk preamble]

주제: <주제>

═══ 페르소나 (${PERSONA_NAME}) ═══
<페르소나 본문 — 너의 역할 매핑만 추출해서 한 줄~세 줄>

═══ 토론 규칙 (${RULES_NAME}) ═══
<룰 본문 그대로>

═══ 안전 규칙 (변경 불가) ═══
1. 답변은 자연스러운 텍스트로. 길이/형식은 룰 섹션을 따른다.
2. WriteFile/외부 API 같은 도구 사용 금지. 답변 채널은 *셸을 통한 파일 작성 + ping 호출* 두 가지뿐.
3. 합의 시 [AGREE], 이견 시 [DISAGREE: 사유].
4. 사회자(Claude)가 매 라운드 짧은 메시지로 차례를 넘긴다 — 그 메시지에만 답해라.
5. 이 preamble에는 답하지 마라. 다음 메시지를 기다려라.

═══ 답변 절차 (변경 불가) ═══
너는 `<AGENT>` (claude / codex 중 하나) pane이다. RUN_ID는 `<RUN_ID>`.

매 라운드 답변은 두 단계로 처리한다.

**1단계 — 답변을 파일에 기록**

다음 셸 명령으로 답변 본문을 파일에 *직접* 써라 (WriteFile 같은 도구 사용 X, 그냥 셸 heredoc):

```bash
cat > /tmp/crosstalk/run-<RUN_ID>/responses/<AGENT>-r<NN>.md <<'EOF'
<답변 본문 여기에>
EOF
```

- `<NN>`: 라운드 번호를 두 자리로 (예: 1 → r01, 3 → r03).
- 답변 본문에 `[AGREE]` 또는 `[DISAGREE: 사유]` 포함.
- 화면에 답변 따로 출력하지 않아도 된다 — 파일이 진실.

**2단계 — callback ping**

파일 작성이 *완전히 끝난 다음*, 다음 한 줄을 호출해 사회자에게 신호:

```bash
~/.claude/scripts/crosstalk_bridge.sh ping <RUN_ID> <AGENT> <ROUND>
```

> 1단계가 *반드시 먼저*. ping이 먼저 가면 사회자가 빈 파일을 읽는다. 순서 중요.

예: codex가 1라운드 답변할 때
```bash
cat > /tmp/crosstalk/run-${RUN_ID}/responses/codex-r01.md <<'EOF'
비 오는 날 국밥은 정서적 위로 측면에서 분명한 가치가 있다...
[AGREE]
EOF
~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} codex 1
```
```

`LANGUAGE` 와 무관하게 — **위 [Crosstalk preamble] 형식 하나만 사용한다**. 룰/페르소나는 active 파일에서 *그대로* 주입.

룰 본문 로딩:
```bash
LANG=$(~/.claude/scripts/crosstalk_bridge.sh get-language 2>/dev/null || echo en)
RULES_FILE="$HOME/.claude/crosstalk/rules/${LANG}/${RULES_NAME}.md"
PERSONA_FILE="$HOME/.claude/crosstalk/personas/${LANG}/${PERSONA_NAME}.md"

RULES_BODY=$(cat "$RULES_FILE")
PERSONA_BODY=$(cat "$PERSONA_FILE")
```

> 룰/페르소나 본문을 *압축/요약하지 마라*. 사용자가 룰 파일을 수정한 의도를 보존해야 한다.
> active rule 이름은 `~/.claude/crosstalk/config.json`의 `active_rules` 키에서 읽고, 일회성 `--rules <name>` 옵션이 있으면 그걸 우선한다.

전송:
```bash
PREAMBLE=$(cat <<EOF
[Crosstalk preamble]

주제: ${TOPIC}

═══ 페르소나 (${PERSONA_NAME}) ═══
${PERSONA_BODY}

═══ 토론 규칙 (${RULES_NAME}) ═══
${RULES_BODY}

═══ 안전 규칙 (변경 불가) ═══
1. 답변은 자연스러운 텍스트로. 길이/형식은 토론 규칙 섹션을 따른다.
2. WriteFile/외부 API 같은 도구 사용 금지. 답변 채널은 *셸을 통한 파일 작성 + ping 호출* 두 가지뿐.
3. 합의 시 [AGREE], 이견 시 [DISAGREE: 사유].
4. 사회자(Claude)가 매 라운드 짧은 메시지로 차례를 넘긴다 — 그 메시지에만 답해라.
5. 이 preamble에는 답하지 마라. 다음 메시지를 기다려라.

═══ 답변 절차 (변경 불가) ═══
너는 \`${AGENT}\` pane이다. RUN_ID는 \`${RUN_ID}\`.

매 라운드 답변은 두 단계:

1단계 — 답변을 파일에 기록:
  cat > /tmp/crosstalk/run-${RUN_ID}/responses/${AGENT}-r<NN>.md <<'EOF2'
  <답변 본문>
  EOF2

2단계 — callback ping:
  ~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} ${AGENT} <ROUND>

순서 중요 — 1단계가 반드시 먼저. ping이 먼저 가면 사회자가 빈 파일을 읽는다.
EOF
)

~/.claude/scripts/crosstalk_bridge.sh send <peer> "$PREAMBLE"
sleep 3
```

프리앰블 답변은 의도적으로 무시 (대기/캡처 없이 다음 단계로).

## 4단계: 임시 로그 + run 디렉토리

토론 로그(사람이 읽을 마크다운)와 별도로, AI 응답을 받기 위한 **파일 기반 transport run**을 생성한다.

```bash
# 사람용 토론 로그
LOG_TMP="/tmp/crosstalk-$(date +%Y%m%d-%H%M%S)-$$.md"
~/.claude/scripts/crosstalk_bridge.sh save "$LOG_TMP" "# 토론 로그: <주제>

- 일시: $(date '+%Y-%m-%d %H:%M:%S')
- 사회자: Claude
- 모드: 1:1(vs <CLI>) 또는 다자
"

# RUN_ID는 모드 무관 항상 만든다 — off 모드에서도 ping 파일을 위해 필요.
RUN_ID=$(~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
echo "📁 run dir: $RUN_DIR"
```

용도:
- `TRANSPORT_OPTION=off` (기본): 답변 본문은 `$RUN_DIR/responses/<agent>-r<NN>.md` (AI가 셸 heredoc로 작성). ping은 *완료 신호*만 (`$RUN_DIR/done/<agent>-r<NN>` 마커 + cmux callback).
- `file`/`screen`: 답변 본문이 `$RUN_DIR/responses/<agent>-r<NN>-a<N>.md`.

## 5단계: 토론 실행 — callback 핑-퐁

**핵심 변경 (v0.2.0): polling 제거. 진짜 이벤트 기반.**

이전(v0.1.x)은 사회자(Claude)가 `wait-ping`으로 무한 polling하며 모든 ping을 기다렸다. 그래서 사회자 bash 프로세스가 살아있어야 했고, 슬래시 커맨드 흐름이 한 번 끊기면 복구 불가.

지금(v0.2.0):
1. 사회자가 *한 라운드만* 보내고 슬래시 커맨드 종료 — pane은 입력 대기 상태로 idle.
2. AI는 답변 끝나면 `bridge ping` 호출 → bridge가 manifest의 `moderator_surface`로 cmux send.
3. claude pane이 `[crosstalk] codex R6 done — RUN_ID=...` 메시지를 *새 사용자 입력*으로 받음.
4. claude는 그 메시지를 보고 *바로 다음 라운드*를 진행 (slash command 흐름 다시 시작).
5. 위 1~4 반복.

> Polling 의존도 제거 → bash 프로세스 안 살아있어도 됨. 사용자가 중간에 다른 거 시켜도 ping 메시지 도착 시 자연스럽게 재진입.

### 5-A. 첫 턴 (Round 1): 주제 던지기

3단계 preamble을 *각 참여자에게 이미 한 번씩* 보냈다고 가정. 첫 라운드는 **주제만 짧게 던진다**:

```
[Round 1] 주제: <주제>

너의 의견은? 합의 가능하면 [AGREE], 이견이면 [DISAGREE: 사유]로 끝.
답변 끝나면: `~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} <너> 1`
```

(`TRANSPORT_OPTION=file` 또는 `screen`이면 메시지 끝에 ═══ Transport ═══ 섹션을 옵션값에 맞춰 추가. `off`면 안 넣음.)

### 5-B. 이후 턴 (follow-up): 대화체

직전 답변을 짧게 인용하고 차례를 넘긴다. **페르소나/룰/시스템 마커 다시 안 박는다 — preamble이 살아있음.**

1:1 예:
```
[Round 3] codex가 직전에 이렇게 말했어:
"파전이 더 적합 — 습한 날 뜨거운 국물은 부담."

너 입장은? (답변 끝나면 `~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} gemini 3`)
```

다자 예:
```
[Round 2] 직전 라운드 정리:
- Codex: 파전 (습도 부담 근거)
- Gemini: 국밥 (정서적 위로 근거)

너 차례. 어느 쪽에 동의/반박? (답변 끝나면 `~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} <너> 2`)
```

> 메시지 길이 가이드: **사회자가 보내는 메시지를 짧게**. 페르소나/룰 다시 박지 마라.
> AI 답변 길이는 강제하지 않는다 — 룰의 "자연스러운 사고 흐름" 가이드 따름.
> 사회자(Claude)가 *직전 답변 한 줄 요약*만 메시지에 붙인다. 전체 히스토리 X.

> `TRANSPORT_OPTION=off` (기본)이면 이 메시지에 **═══ Transport ═══ 섹션을 넣지 않는다**.
> `file`/`screen`이면 메시지 끝에 옵션값에 맞춘 Transport 섹션을 추가 (자세한 형식은 [Transport 섹션 참조](#transport-블록-옵션-file--screen일-때만)).

### Transport 블록 (옵션 file / screen일 때만)

`TRANSPORT_OPTION=off`이면 이 블록을 *통째로* 메시지에서 빼라.

[file — claude/codex 권장]
```
═══ Transport ═══
이 턴 답변은 화면이 아니라 파일에 기록한다.

1. 답변 본문 전체를 다음 파일에 그대로 써라:
     ${RUN_DIR}/responses/<RESP_BASENAME>
2. 파일 작성이 끝나면 화면에 정확히 한 줄: DONE <MSG_ID>
3. 파일 외 가공/요약/박스 출력 금지. 이미 있으면 덮어써라.

  RESP_BASENAME = <agent>-r<NN>-a<N>.md
  MSG_ID        = run-<run-id>-r<NN>-<agent>-a<N>
```

[screen — gemini용]
```
═══ Transport ═══
파일에 쓰지 마라. WriteFile/Shell 도구 사용 금지.
화면에 정확히 한 번만:

  CROSSTALK_BEGIN <MSG_ID>
  <답변 본문 한 단락>
  CROSSTALK_END <MSG_ID>

다른 텍스트 출력 금지. 같은 답변 여러 번 출력 금지.
  MSG_ID = run-<run-id>-r<NN>-gemini-a<N>
```

### 전송 흐름 (callback)

#### 메시지 치환 (공통)

각 peer별로 메시지에 박힌 placeholder를 *보내기 직전* sed로 치환:

```bash
substitute_msg() {
  local raw="$1" agent="$2"
  printf '%s' "$raw" \
    | sed "s|<RUN_ID>|${RUN_ID}|g" \
    | sed "s|<AGENT>|${agent}|g" \
    | sed "s|<ROUND>|${ROUND}|g"
}
```

> placeholder가 그대로 들어가면 AI가 `bridge ping <RUN_ID> codex 1`을 *문자열 그대로* 호출해 실패한다. 치환 필수.

#### 한 라운드 발송 + 종료

`/crosstalk:debate`는 *한 라운드만 발송*하고 종료한다. 다음 라운드는 ping callback이 도착했을 때 자동으로 시작.

```bash
# 모든 참여자에게 메시지 일괄 전송 (1:1이든 다자든 동일 패턴)
declare -a AGENTS PEERS
# 예: AGENTS=(codex), PEERS=(surface:8)             # 1:1
# 또는 AGENTS=(codex gemini), PEERS=(surface:8 surface:9)  # 다자

# 보내기 *전*에 각 pane의 현재 라인 수 기록 (ping 도착 시 새 텍스트 추출용)
declare -A PREV_LINES_MAP
for i in "${!AGENTS[@]}"; do
  agent="${AGENTS[$i]}"; peer="${PEERS[$i]}"
  PREV_LINES_MAP[$agent]=$(~/.claude/scripts/crosstalk_bridge.sh lines "$peer")
done

# state 파일에 PREV_LINES_MAP 같이 보관 (다음 ping 받았을 때 복원)
{
  echo "ROUND=$ROUND"
  for agent in "${AGENTS[@]}"; do
    echo "PREV_LINES_${agent}=${PREV_LINES_MAP[$agent]}"
    echo "PEER_${agent}=${PEERS[$( eval echo \$index_${agent})]}"
  done
} > "$RUN_DIR/state.sh"

# 메시지 발송
for i in "${!AGENTS[@]}"; do
  agent="${AGENTS[$i]}"; peer="${PEERS[$i]}"
  MSG=$(substitute_msg "$RAW_MSG" "$agent")
  ~/.claude/scripts/crosstalk_bridge.sh send "$peer" "$MSG"
done

# 사회자(Claude) 본인도 답변할 차례면 *지금 자기 답변을 출력*하고 ping 호출
# (1:1 모드는 본인 차례 따로 없음 — peer 대답 받은 후 다음 라운드에서 본인 발언)
```

#### Callback 핸들링 (다음 라운드 자동 진행)

claude pane이 ping 메시지 (`[crosstalk] codex R6 done — RUN_ID=...`) 를 받으면 다음 흐름:

1. 메시지에서 `RUN_ID` / `AGENT` / `R<N>` 파싱
2. `$RUN_DIR/state.sh` source 해서 라운드 컨텍스트 복원
3. `$RUN_DIR/done/<agent>-r<NN>` 파일 존재 확인 (= ping 정말 왔는지 검증)
4. **모든 참여자 ping 도착했는지 확인**:
   - `for agent in $AGENTS; do [ -f "$RUN_DIR/done/${agent}-r${ROUND_PADDED}" ] || NOT_READY=1; done`
   - 누군가 빠졌으면 → 사회자는 *그냥 종료*. 마지막 ping 도착 시 자동으로 다시 진입함.
5. 모두 도착했으면 — **답변 본문은 화면이 아니라 응답 파일에서 읽는다**:
   ```bash
   for agent in "${AGENTS[@]}"; do
     ROUND_PADDED=$(printf '%02d' "$ROUND")
     RESP_FILE="$RUN_DIR/responses/${agent}-r${ROUND_PADDED}.md"
     if [ -f "$RESP_FILE" ] && [ -s "$RESP_FILE" ]; then
       cp "$RESP_FILE" "/tmp/crosstalk_resp_${agent}"
     else
       # 파일이 없거나 비었음 — AI가 ping은 보냈는데 파일 작성 누락
       # AskUserQuestion: 재요청 / 무시(부분 진행) / 중단
       :
     fi
   done
   ```
   - 본문 정리 (Claude가 후처리)
   - 다음 라운드 메시지 작성 → 위 "한 라운드 발송 + 종료" 단계 다시
   - 종료 조건 (`[AGREE]` / 라운드 한도) 도달이면 8단계 (종합 의견)로

> 핵심: 답변 본문은 *파일에서 읽는다*. 화면 캡처(v0.2.0의 `capture` 호출) 의존 제거. AI가 *답변 파일을 다 쓴 다음에* ping을 호출하는 순서를 지켜주면 race 없음.

> v0.2.0과의 차이: v0.2.0은 화면 캡처 + ping callback이라 *AI가 답을 다 쓰기 전에 ping이 먼저 가는 race* 가 있었다. v0.2.1에서 답변 채널을 *파일*로 옮기고 ping은 *순수 신호*로 단순화. 답변이 어디 있는지 한 군데로 통일.

> **사회자 본인 답변 ping**: 다자에서 Claude 본인이 자기 의견 출력 후 즉시 `~/.claude/scripts/crosstalk_bridge.sh ping "$RUN_ID" claude "$ROUND"` 호출. 본인이 본인 pane을 깨우는 형태 (cmux send self → callback) — 자연스럽게 다음 단계로.

#### Transport 옵션 (file / screen) 사용 시

옵션 흐름은 callback 구조 *위에* 얹어진다:
- 메시지 끝에 ═══ Transport ═══ 섹션 추가 (이전 절 참조).
- AI가 답변 본문은 파일/screen block에 쓰고, ping은 똑같이 호출.
- callback에서 capture 대신 `read-response` 호출:
  ```bash
  MSG_ID=$(~/.claude/scripts/crosstalk_bridge.sh make-msg-id "$RUN_ID" "$ROUND" "$AGENT" 1)
  ~/.claude/scripts/crosstalk_bridge.sh read-response "$RUN_ID" "$MSG_ID" > "/tmp/crosstalk_resp_${AGENT}"
  ```

### 상태 / 에러 처리

**ping 안 옴 → 사회자가 idle 상태로 영영 깨어나지 않을 수 있다.** 이 케이스 대비:
- 사용자에게 안내: 이 상태에서 사용자가 claude pane에 직접 *"codex가 답을 안 주는 것 같아 timeout 처리해줘"* 같은 메시지 입력 가능.
- 또는 *수동 ping*: 사용자가 직접 `~/.claude/scripts/crosstalk_bridge.sh ping <RUN_ID> codex <ROUND>` 호출해 사회자 깨우고, callback 핸들러에서 *답변 누락 → 다음 라운드로 무시* 결정.
- **자동 timeout은 일부러 안 둔다** — 자동 폴링하면 idle 모델로 돌아가지 못함.

### 종료 조건

- **1:1**: 어느 한쪽 답변에 `[AGREE]` 포함 → 종료. 15턴 도달 → 강제 종료.
- **다자**: 모든 참여자가 같은 라운드에서 `[AGREE]` → 종료. 10라운드 도달 → 강제 종료.

## 6단계: 사용자 화면 표시

매 턴/라운드:

`LANGUAGE=en`:
```text
━━━ Turn N/15 ━━━
Claude (me): <paragraph>
<CLI>: <paragraph>
```

`LANGUAGE=ko` 1:1:
```
━━━ Turn N/15 ━━━
🟦 Claude (나): <한 단락>
🟧 <CLI>: <한 단락>
```

`LANGUAGE=ko` 다자:
```
━━━ Round N/10 ━━━
🟦 Claude (나): <한 단락>
🟧 Codex: <한 단락>
🟪 Gemini: <한 단락>
```

cmux 명령 결과/raw 출력은 노출 금지. 대화 내용만.

## 7단계: 로그 자동 저장

매 턴/라운드 발언을 `$LOG_TMP`에 누적:

```bash
~/.claude/scripts/crosstalk_bridge.sh save "$LOG_TMP" "<마크다운 형식 발언 블록>"
```

## 8단계: 종합 의견

토론 끝나면 (합의/리밋/중단 어떤 경로든) 반드시:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 종합 (총 N턴/라운드, 종료: 합의/리밋/중단)
사회자: Claude
모드: 1:1(vs <CLI>) 또는 다자

🟦 Claude 입장: <한 줄>
🟧 <CLI> 입장: <한 줄>
🟪 Gemini 입장: <한 줄>  ← 다자만

🎯 결론: <합의점 또는 핵심 차이 1-2문장>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

종합도 `$LOG_TMP`에 append.

## 9단계: 로그 + transport run 보관/폐기 질문

`AskUserQuestion`으로 언어별 질문:
```
en:
header: Debate log
question: Keep this debate log? (includes raw response files)
options:
  - Keep (~/Documents/crosstalk/<date>-<topic-slug>/)
  - Discard (delete LOG_TMP and transport run directory)

ko:
header: 토론 로그
question: 이번 토론 로그를 보관할까요? (응답 원문 파일 포함)
options:
  - 보관 (~/Documents/crosstalk/<날짜>-<주제slug>/)
  - 폐기 (LOG_TMP + transport run 디렉토리 모두 삭제)
```

**보관** — discussion.md + responses/ 같이 디렉토리째:
```bash
mkdir -p ~/Documents/crosstalk
DATE=$(date '+%Y-%m-%d')
SLUG=$(echo "<주제>" | tr ' /' '--' | tr -cd '[:alnum:]-' | head -c 50)
DEST_DIR=~/Documents/crosstalk/${DATE}-${SLUG}
mkdir -p "$DEST_DIR"
mv "$LOG_TMP" "$DEST_DIR/discussion.md"
# transport run 의 응답 원문도 같이 보관
if [ -d "$RUN_DIR" ]; then
  cp -R "$RUN_DIR/responses" "$DEST_DIR/responses"
  cp "$RUN_DIR/manifest.json" "$DEST_DIR/manifest.json" 2>/dev/null || true
  rm -rf "$RUN_DIR"
fi
```

**폐기** — LOG_TMP + RUN_DIR 모두 제거:
```bash
rm -f "$LOG_TMP"
[ -d "$RUN_DIR" ] && rm -rf "$RUN_DIR"
```

## Ctrl+C 대응

bridge에 정지 신호 + 즉시 8단계 종합으로 점프 → 9단계 보관 질문:

```bash
~/.claude/scripts/crosstalk_bridge.sh stop <surface>
```

## 주의사항

- 답변 길이는 룰 프리셋 가이드에 맡긴다. 강제 X — 자연스러운 사고 흐름 우선.
- 같은 논점 반복 금지. 새 근거/관점 없으면 양보 + [AGREE].
- v0.1.4부터 답변은 **파일 기반 transport**로 받는다. 화면 캡처 폴백은 사용하지 않는다.
- bridge 호출 실패(소켓 단절 등) 즉시 사용자에게 보고 + 종료.
- 토론 시작 시 사용자에게 *옆 pane에 직접 입력해도 답변 파일은 그대로 도착하지만, 토론 흐름이 끊길 수 있음* 안내.
- 응답 파일 원문은 `$RUN_DIR/responses/`에 그대로 보존된다. 화면 표시는 잘릴 수 있어도 디스크 원문은 온전.
