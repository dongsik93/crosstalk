---
description: cmux의 다른 AI pane(Codex/Gemini)들과 자동 토론. 1:1 또는 다자(Claude 사회자) 모드. 한쪽이 [AGREE] 표시 또는 15턴까지. --rules / --persona 옵션 지원.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: [--rules <name>] [--persona <name>] <토론 주제>
---

# Crosstalk — 다중 AI 토론 (Claude 사회자)

cmux 안에서 분할된 다른 AI CLI(Codex/Gemini)들과 자동으로 토론을 진행한다.
**이 명령을 호출한 본인(Claude)이 사회자**가 된다.

## 옵션

- `--rules <name>` — 일회성 룰 프리셋 명시 (예: `brainstorm`, `debate`, `default`)
- `--persona <name>` — 일회성 페르소나 프리셋 명시 (예: `senior-junior`, `critic-builder`)
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
- 나머지 텍스트 = 토론 주제

옵션 없으면 active 프리셋 로드:
```bash
CONFIG=~/.claude/crosstalk/config.json
ACTIVE_RULES=$(jq -r '.active_rules // "default"' "$CONFIG" 2>/dev/null || echo "default")
ACTIVE_PERSONA=$(jq -r '.active_persona // "default"' "$CONFIG" 2>/dev/null || echo "default")
RULES_NAME="${RULES_NAME:-$ACTIVE_RULES}"
PERSONA_NAME="${PERSONA_NAME:-$ACTIVE_PERSONA}"
```

룰/페르소나 본문 Read:
```bash
RULES_PATH=~/.claude/crosstalk/rules/${RULES_NAME}.md
PERSONA_PATH=~/.claude/crosstalk/personas/${PERSONA_NAME}.md
[ ! -f "$RULES_PATH" ] && echo "❌ 룰 '$RULES_NAME' 없음 — /crosstalk:rules 확인" && exit 1
[ ! -f "$PERSONA_PATH" ] && echo "❌ 페르소나 '$PERSONA_NAME' 없음 — /crosstalk:persona 확인" && exit 1
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

  - `CMUX_OK=false` → cmux 미실행/미설치. *cmux를 먼저 띄우거나 `/crosstalk:launch`를 외부에서 실행해야 한다* 안내 후 종료.
  - `CMUX_OK=true` → 사용자에게 명확히 안내 후 종료:
    ```
    🛑 cmux split 안에 다른 AI pane(Codex/Gemini)이 없어 토론을 시작할 수 없습니다.

    다음 순서로 다시 시도해주세요:
      1. 먼저 다음 명령으로 환경을 셋업:
           /crosstalk:launch
      2. 그 다음 이 명령을 다시 실행:
           /crosstalk <주제>   또는   /crosstalk:debate <주제>
    ```
    슬래시 커맨드는 다른 슬래시 커맨드를 자동 호출하지 않는다 — 사용자가 직접 두 번 실행해야 한다.

## 2단계: 사용자에게 상대 선택 받기

`AskUserQuestion` 도구로 토론 상대 선택. 발견된 CLI 종류에 따라 옵션 동적 구성:

- 각 CLI별 1:1 토론
- 2개 이상이면 "전체 다자 토론(Claude 사회자)"
- "취소"

`header`는 `토론 상대`, `multiSelect`는 `false`.

선택이 "취소"면 즉시 종료.

## 3단계: 안전 모드 프리앰블

선택된 모든 참여자에게 한 번씩 프리앰블 메시지 전송:

```
[Claude 주관 토론 안전 모드 시작]

지금부터 다음 주제로 토론합니다: <주제>

토론 규칙:
1. 답변은 한 단락(3-5문장)의 텍스트 의견만.
2. 파일 수정/셸 명령/외부 API 호출 금지. 텍스트 의견만.
   ※ 단 하나의 예외: 매 턴 메시지의 ═══ Transport ═══ 섹션이 지정한
     응답 파일 1개에 답변 본문을 쓰는 것은 허용된다 (정확한 경로/파일명은 매 턴 Transport 섹션이 알려준다).
     이건 "응답을 화면 대신 디스크로 보내는 것"이지 코드 수정이 아니다.
     그 외의 파일/디렉토리는 일절 건드리지 마라.
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

# AI 응답 transport run
RUN_ID=$(~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
echo "📁 transport run: $RUN_DIR"
```

이후 모든 AI 응답은 화면 캡처가 아니라 `$RUN_DIR/responses/<agent>-r<NN>-a<N>.md` 파일에서 읽는다.

## 5단계: 토론 실행 (파일 기반 transport)

### 메시지 템플릿 — 모든 AI 답변에 강제

매 턴 메시지는 self-contained로 보내되, **transport 섹션**을 반드시 포함한다. 이걸 통해 AI가 응답을 화면이 아니라 파일에 쓰게 된다.

```
[Claude vs <CLI> 토론 - 턴 N/15]   (1:1)
또는
[다자 토론 라운드 N/10]              (다자)

주제: <주제>

═══ 페르소나 (${PERSONA_NAME}) ═══
<페르소나 파일에서 *너의 역할 매핑*만 추출해서 주입>
- 사회자(호출자) → moderator 섹션
- 첫 참여자 → 페르소나 파일의 두 번째 역할
- 두 번째 참여자 → 페르소나 파일의 세 번째 역할
- 페르소나가 default면 *각자 본연의 시각으로 토론* 한 줄만

═══ 토론 규칙 (${RULES_NAME}) ═══
<룰 파일 본문 그대로>

═══ 시스템 규칙 (변경 불가) ═══
- 합의 시 답변 끝에 [AGREE]
- 이견 시 답변 끝에 [DISAGREE: 사유]
- 위 사용자 규칙과 충돌 시 시스템 규칙 우선

═══ Transport (변경 불가) ═══
이 턴의 답변은 화면이 아니라 파일에 기록한다.

1. 답변 본문 전체를 다음 파일에 그대로 써라:
     ${RUN_DIR}/responses/<RESP_BASENAME>
2. 파일 작성이 끝나면 화면(터미널)에 정확히 한 줄을 출력해라:
     DONE <MSG_ID>
3. 파일 외에 추가 가공/요약/박스 출력은 하지 마라.
4. 파일이 이미 존재하면 덮어써라.

  RESP_BASENAME = <agent>-r<NN>-a<N>.md   (예: codex-r03-a1.md)
  MSG_ID        = run-<run-id>-r<NN>-<agent>-a<N>

[지금까지의 논의 요약]
- 턴 N-1 ...

[이번 턴 사회자 메시지]
<Claude가 종합한 논점 또는 직전 답변에 대한 반론>
```

### 전송 + 대기 흐름

각 참여자(`peer`, `kind`)에게 한 턴 보낼 때:

```bash
ROUND=N                  # 턴/라운드 번호
ATTEMPT=1                # 재시도 시 +1
AGENT="$kind"            # codex / gemini / claude (peer 쪽)

MSG_ID=$(~/.claude/scripts/crosstalk_bridge.sh make-msg-id "$RUN_ID" "$ROUND" "$AGENT" "$ATTEMPT")
RESP_BASENAME="${AGENT}-r$(printf '%02d' "$ROUND")-a${ATTEMPT}.md"

# 메시지 안의 <RESP_BASENAME> / <MSG_ID> 자리표시자를 위 값들로 치환해서 전송
~/.claude/scripts/crosstalk_bridge.sh send "$peer" "<치환된 메시지>"

# 응답 파일이 안정될 때까지 대기 (DONE 마커 + 파일 안정 → clean / 파일만 안정 → soft-complete)
STABLE_SECONDS=5 MAX_WAIT=180 DONE_GRACE=5 \
  ~/.claude/scripts/crosstalk_bridge.sh wait-turn "$peer" "$RUN_ID" "$MSG_ID" 2> /tmp/crosstalk_state
WAIT_RC=$?
STATE_LINE=$(cat /tmp/crosstalk_state)

# 응답 파일 읽기 (원문 보존, 너무 크면 stdout만 truncate + WARN)
MAX_RESPONSE_BYTES=20000 \
  ~/.claude/scripts/crosstalk_bridge.sh read-response "$RUN_ID" "$MSG_ID" > /tmp/crosstalk_resp 2>> /tmp/crosstalk_state || true
```

### 상태별 처리

`wait-turn`은 stderr에 `STATE: <state> ...`를 한 줄 출력한다. exit code:
- `clean`, `soft-complete` → 0
- `protocol-error`, `timeout` → 1

| 상태 | 처리 |
|------|------|
| `clean` | 정상. 파일 내용을 답변으로 사용. |
| `soft-complete` | 파일은 받았지만 DONE 마커 못 봄. 파일 내용 사용 + 화면 표시에 ⚠️ "DONE 마커 누락" 한 줄 노출. |
| `protocol-error` | DONE 마커는 봤는데 파일이 없거나 비어있음. 사용자에게 *재시도(ATTEMPT+1) / 무시 / 중단* `AskUserQuestion`. 재시도 시 메시지 끝에 *직전 시도가 파일을 만들지 않았다, 위 RESP_BASENAME에 정확히 써달라* 한 줄 추가. |
| `timeout` | MAX_WAIT 초과. 사용자에게 *재시도 / 무시(부분 종합 진행) / 중단* `AskUserQuestion`. |

INTERVENTION/prompt-count 휴리스틱은 v0.1.4부터 사용하지 않는다 (파일 마커가 진실). 사용자가 옆 pane에 끼어들었더라도 답변 파일이 정상 도착했으면 그대로 신뢰한다.

### 종료 조건

- **1:1**: 어느 한쪽 답변에 `[AGREE]` 포함 → 종료. 15턴 도달 → 강제 종료.
- **다자**: 모든 참여자가 같은 라운드에서 `[AGREE]` → 종료. 10라운드 도달 → 강제 종료.

## 6단계: 사용자 화면 표시

매 턴/라운드:

**1:1**:
```
━━━ Turn N/15 ━━━
🟦 Claude (나): <한 단락>
🟧 <CLI>: <한 단락>
```

**다자**:
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

`AskUserQuestion`으로:
```
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
