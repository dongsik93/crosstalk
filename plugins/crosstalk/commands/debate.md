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
- `--transport off|file|screen` — 답변 받는 방법. **기본 `off`** (자연스러운 핑-퐁 토론, 화면 캡처).
  - `off` (기본): 사회자가 화면 텍스트를 직접 읽고 정리. AI에게 transport 지시 안 함 → 답변 instruction following 좋음.
  - `file`: 답변 본문을 별도 파일에 쓰게 함. 긴 답변 안전. (claude/codex 권장)
  - `screen`: 답변을 BEGIN/END 블록으로 출력하게 함. (gemini용 — agentic 도구 사고 방지)
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
1. 답변은 한 단락 텍스트만.
2. WriteFile/Shell/외부 API 같은 도구 사용 금지. 화면에 답변 텍스트만.
3. 합의 시 [AGREE], 이견 시 [DISAGREE: 사유].
4. 사회자(Claude)가 매 라운드 짧은 메시지로 차례를 넘긴다 — 그 메시지에만 답해라.
5. 이 preamble에는 답하지 마라. 다음 메시지를 기다려라.
```

`LANGUAGE=en`이면 영어, `LANGUAGE=ko`이면 한국어. 다음은 fallback 안내용 짧은 버전 (실제 본문은 위 형태로 페르소나/룰을 주입해 보낸다):

en:
```
[Crosstalk safe mode]

We will debate this topic: <topic>

Rules:
1. Reply with one paragraph of text opinion only.
2. Do not modify files, run shell commands, or call external APIs.
   One exception: each turn's Transport section may allow writing exactly one response file.
   Do not touch any other file or directory.
3. If you agree, end with [AGREE]. If not, end with [DISAGREE: reason].
4. Wait for the first debate turn. Do not answer this preamble.
```

ko:
```
[Claude 주관 토론 안전 모드 시작]

지금부터 다음 주제로 토론합니다: <주제>

토론 규칙:
1. 답변은 한 단락(3-5문장)의 텍스트 의견만.
2. 파일 수정/셸 명령/외부 API 호출 금지. **텍스트 의견만 출력**.
   - 도구(WriteFile/Shell/등) 사용 금지. 그냥 화면에 답변 텍스트만 출력하면 된다.
   - 사회자가 화면을 보고 직접 읽는다 — 별도 마커나 파일 작성 불필요.
   - (사회자가 `--transport file|screen` 옵션을 켰으면 매 턴 ═══ Transport ═══ 섹션이 별도 지시를 준다.
      그 경우엔 그 지시만 따르면 된다.)
3. 토론 자료는 메시지에 직접 첨부됩니다.
4. 합의 가능하면 답변 끝에 [AGREE], 이견이면 [DISAGREE: 사유].
5. 첫 메시지를 받으면 토론 시작입니다. 이 프리앰블은 별도 답변 없이 다음 메시지를 기다리세요.

준비됐으면 다음 메시지를 기다려주세요.
```

전송:
```bash
~/.claude/scripts/crosstalk_bridge.sh send <peer> "<프리앰블>"
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

# `--transport off` 면 run 디렉토리 안 만든다 (필요 없음).
if [ "$TRANSPORT_OPTION" != "off" ]; then
  RUN_ID=$(~/.claude/scripts/crosstalk_bridge.sh start-run)
  RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
  echo "📁 transport run: $RUN_DIR"
fi
```

`TRANSPORT_OPTION=off` (기본)이면 답변은 화면 캡처. `file`/`screen`이면 `$RUN_DIR/responses/<agent>-r<NN>-a<N>.md`.

## 5단계: 토론 실행 — 핑-퐁 패턴

**핵심: 페르소나/룰/시스템 마커는 3단계 preamble에서 *한 번만* 박았다. 이후 턴 메시지는 짧은 대화체.**

### 5-A. 첫 턴 (Round 1): 주제 던지기

3단계 preamble을 *각 참여자에게 이미 한 번씩* 보냈다고 가정. 첫 라운드는 **주제만 짧게 던진다**:

```
[Round 1] 주제: <주제>

너의 의견을 한 단락(3-5문장)으로. 합의 가능하면 [AGREE], 이견이면 [DISAGREE: 사유]로 끝.
```

(`TRANSPORT_OPTION=file` 또는 `screen`이면 메시지 끝에 ═══ Transport ═══ 섹션을 옵션값에 맞춰 추가. `off`면 안 넣음.)

### 5-B. 이후 턴 (follow-up): 대화체

직전 답변을 짧게 인용하고 차례를 넘긴다. **페르소나/룰/시스템 마커 다시 안 박는다 — preamble이 살아있음.**

1:1 예:
```
[Round 3] codex가 직전에 이렇게 말했어:
"파전이 더 적합 — 습한 날 뜨거운 국물은 부담."

너 입장은? 한 단락으로.
```

다자 예:
```
[Round 2] 직전 라운드 정리:
- Codex: 파전 (습도 부담 근거)
- Gemini: 국밥 (정서적 위로 근거)

너 차례. 어느 쪽에 동의/반박할지 한 단락.
```

> 메시지 길이 가이드: **first-turn 200자 이내, follow-up 300자 이내**. 페르소나/룰 다시 박지 마라.
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

### 전송 + 대기 흐름

각 참여자(`peer`, `kind`)에게 한 턴 보낼 때, `TRANSPORT_OPTION` 값에 따라 다른 흐름:

```bash
ROUND=N                  # 턴/라운드 번호
AGENT="$kind"            # codex / gemini / claude (peer 쪽)

# agent별 MAX_WAIT (옵션 무관 공통)
case "$AGENT" in
  gemini) AGENT_MAX_WAIT=360 ;;
  codex)  AGENT_MAX_WAIT=240 ;;
  *)      AGENT_MAX_WAIT=180 ;;
esac

if [ "$TRANSPORT_OPTION" = "off" ]; then
  # ───── 기본 흐름: 화면 캡처. 사회자가 직접 읽는다. ─────
  # 보내기 전에 현재 화면 라인 수 기록 → 답변 후 새로 추가된 줄만 추출
  PREV_LINES=$(~/.claude/scripts/crosstalk_bridge.sh lines "$peer")

  ~/.claude/scripts/crosstalk_bridge.sh send "$peer" "<메시지>"

  # 화면이 안정될 때까지 대기 (legacy wait — 활동 감지 + 안정 시점)
  STABLE_SECONDS=5 MAX_WAIT="$AGENT_MAX_WAIT" \
    ~/.claude/scripts/crosstalk_bridge.sh wait "$peer" "$PREV_LINES" 2>/dev/null \
    > /tmp/crosstalk_resp_raw

  # raw 화면 텍스트 → 사회자(Claude)가 본문만 추출. CLI 박스, 진행 표시(✦/⏵), 푸터, 사용자 프롬프트 라인 등을 무시하고 답변 단락만 정리.
  # (Claude 본인이 LLM이므로 후처리 잘 함. 별도 마커 불필요.)
else
  # ───── 옵션 흐름: file / screen transport ─────
  ATTEMPT=1
  MSG_ID=$(~/.claude/scripts/crosstalk_bridge.sh make-msg-id "$RUN_ID" "$ROUND" "$AGENT" "$ATTEMPT")
  RESP_BASENAME="${AGENT}-r$(printf '%02d' "$ROUND")-a${ATTEMPT}.md"

  # gemini는 agentic CLI라 file 모드 시키면 WriteFile 사고 → screen 강제. 그 외는 file.
  if [ "$TRANSPORT_OPTION" = "screen" ] || [ "$AGENT" = "gemini" ]; then
    AGENT_TRANSPORT=screen
  else
    AGENT_TRANSPORT=file
  fi

  ~/.claude/scripts/crosstalk_bridge.sh send "$peer" "<치환된 메시지>"

  STABLE_SECONDS=5 MAX_WAIT="$AGENT_MAX_WAIT" DONE_GRACE=5 \
  ACTIVITY_GRACE=30 ACTIVITY_EXTEND_BY=60 ACTIVITY_EXTEND_MAX=3 \
  TRANSPORT_MODE="$AGENT_TRANSPORT" \
    ~/.claude/scripts/crosstalk_bridge.sh wait-turn "$peer" "$RUN_ID" "$MSG_ID" 2> /tmp/crosstalk_state
fi
WAIT_RC=$?
STATE_LINE=$(cat /tmp/crosstalk_state)

# 응답 파일 읽기 (원문 보존, 너무 크면 stdout만 truncate + WARN)
MAX_RESPONSE_BYTES=20000 \
  ~/.claude/scripts/crosstalk_bridge.sh read-response "$RUN_ID" "$MSG_ID" > /tmp/crosstalk_resp 2>> /tmp/crosstalk_state || true
```

### 상태별 처리

**`TRANSPORT_OPTION=off` (기본)**: state 없음. 화면 캡처 후 사회자가 후처리. 답변이 비었거나 노이즈만 있으면 사회자가 *답변 누락 / 재요청* 결정.

**`file`/`screen` 옵션**: 아래 표 적용.

`wait-turn`은 stderr에 `STATE: <state> ...`를 한 줄 출력한다. exit code:
- `clean`, `soft-complete` → 0
- `protocol-error`, `timeout` → 1

| 상태 | 처리 |
|------|------|
| `clean` | 정상. 파일 내용을 답변으로 사용. |
| `soft-complete` | 파일은 받았지만 DONE 마커 못 봄. 파일 내용 사용 + 화면 표시에 ⚠️ "DONE 마커 누락" 한 줄 노출. |
| `protocol-error` | DONE 마커는 봤는데 파일이 없거나 비어있음. 사용자에게 *재시도(ATTEMPT+1) / 무시 / 중단* `AskUserQuestion`. 재시도 시 메시지 끝에 *직전 시도가 파일을 만들지 않았다, 위 RESP_BASENAME에 정확히 써달라* 한 줄 추가. |
| `timeout` | MAX_WAIT(+ 활동 기반 자동 연장 한도) 초과. 사용자에게 *조금 더 기다리기(MAX_WAIT 추가) / 재시도(ATTEMPT+1) / 무시(부분 종합) / 중단* `AskUserQuestion`. **재시도 전에 직전 attempt 응답 파일이 *나중에 도착해서* 두 답변이 동시에 떠다니는 케이스를 항상 안내**. |

INTERVENTION/prompt-count 휴리스틱은 v0.1.4부터 사용하지 않는다 (파일 마커가 진실). 사용자가 옆 pane에 끼어들었더라도 답변 파일이 정상 도착했으면 그대로 신뢰한다.

`wait-turn`은 화면/응답 파일에 변화가 *최근 ACTIVITY_GRACE 초 안에* 있으면 `MAX_WAIT` 도달 시점에 자동으로 `ACTIVITY_EXTEND_BY` 만큼 연장한다 (최대 `ACTIVITY_EXTEND_MAX` 회). 즉 Gemini처럼 답변 시작이 늦어도 *살아있는 한* 강제 timeout 시키지 않는다. extension이 stderr에 `INFO: activity detected near deadline...` 으로 표시되면 진행 표시도 *기다리는 중* 로 갱신.

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

- 한 발언당 한 단락(3-5문장) 엄수.
- 같은 논점 반복 금지. 새 근거/관점 없으면 양보 + [AGREE].
- v0.1.4부터 답변은 **파일 기반 transport**로 받는다. 화면 캡처 폴백은 사용하지 않는다.
- bridge 호출 실패(소켓 단절 등) 즉시 사용자에게 보고 + 종료.
- 토론 시작 시 사용자에게 *옆 pane에 직접 입력해도 답변 파일은 그대로 도착하지만, 토론 흐름이 끊길 수 있음* 안내.
- 응답 파일 원문은 `$RUN_DIR/responses/`에 그대로 보존된다. 화면 표시는 잘릴 수 있어도 디스크 원문은 온전.
