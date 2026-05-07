---
description: cmux의 다른 AI pane(Codex/Gemini)들과 자동 토론. 1:1 또는 다자(Claude 사회자) 모드. 한쪽이 [AGREE] 표시 또는 15턴까지.
allowed-tools: Bash, AskUserQuestion
argument-hint: <토론 주제>
---

# Crosstalk — 다중 AI 토론 (Claude 사회자)

cmux 안에서 분할된 다른 AI CLI(Codex/Gemini)들과 자동으로 토론을 진행한다.
**이 명령을 호출한 본인(Claude)이 사회자**가 된다.

## 전제 조건

- cmux 환경에서 실행 중
- 본인 외에 cmux split 안에 다른 AI CLI(Codex/Gemini) 1개 이상 떠있음
- bridge 스크립트가 설치되어 있음: `~/.claude/scripts/crosstalk_bridge.sh`
  - 미설치 시 `/crosstalk:install` 먼저 실행 안내

## 1단계: 환경 스캔

```bash
~/.claude/scripts/crosstalk_bridge.sh list-peers
```

출력 형식: `<surface_ref>\t<kind>` 라인들. `kind`는 `claude`/`codex`/`gemini`/`shell`/`unknown`.

검증:
- 0줄 → cmux 안 아님 또는 split 없음. 사용자에게 안내 후 종료.
- 모두 `unknown` → `/crosstalk:setup` 실행 안내 후 종료.
- `unknown`/`shell`은 후보 목록에서 제외.

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

## 4단계: 임시 로그 파일

```bash
LOG_TMP="/tmp/crosstalk-$(date +%Y%m%d-%H%M%S)-$$.md"
~/.claude/scripts/crosstalk_bridge.sh save "$LOG_TMP" "# 토론 로그: <주제>

- 일시: $(date '+%Y-%m-%d %H:%M:%S')
- 사회자: Claude
- 모드: 1:1(vs <CLI>) 또는 다자
"
```

## 5단계: 토론 실행

### 모드 A: 1:1

매 턴마다 self-contained 메시지:

```
[Claude vs <CLI> 토론 - 턴 N/15]

주제: <주제>

[지금까지의 논의 요약]
- 턴 1 Claude: <한 줄>
- 턴 1 <CLI>: <한 줄>
- ...

[Claude 의 이번 턴 의견]
<한 단락 3-5문장>

[너의 답변 형식]
- 한 단락(3-5문장)
- 합의 시 답변 끝에 [AGREE]
- 이견이면 [AGREE] 없이 반박/보완
```

전송 흐름:
```bash
LINES=$(~/.claude/scripts/crosstalk_bridge.sh lines <peer>)
PROMPTS=$(~/.claude/scripts/crosstalk_bridge.sh prompt-count <peer>)
EXPECTED=$((PROMPTS + 1))

~/.claude/scripts/crosstalk_bridge.sh send <peer> "<메시지>"

STABLE_SECONDS=5 MAX_WAIT=180 \
  ~/.claude/scripts/crosstalk_bridge.sh wait <peer> $LINES $EXPECTED 2> /tmp/crosstalk_stderr
```

`/tmp/crosstalk_stderr`에 `INTERVENTION:` 있으면 사용자에게 *옆 pane에 직접 입력 감지, 답변 신뢰 어려움* 안내 + 재전송/무시/중단 선택.

`[AGREE]` 감지 시 종료. 15턴 도달 시 강제 종료.

### 모드 B: 다자 (Claude 사회자)

각 참여자에게 동일 self-contained 메시지 전송:

```
[다자 토론 라운드 N/10]

주제: <주제>
참여자: Claude(사회자), <발견된 다른 CLI들>

[직전 라운드 답변 요약]
- Claude / 각 CLI: <한 줄씩>

[이번 라운드 질문]
<Claude가 종합한 다음 논점>

[너의 답변 형식]
- 한 단락(3-5문장)
- [AGREE] 또는 [DISAGREE: 사유]
```

각 참여자에게 보낼 때마다 1:1과 동일한 흐름 (lines/prompt-count → send → wait, INTERVENTION 처리).

종료 조건: 모든 참여자가 [AGREE] 또는 10라운드 도달.

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

## 9단계: 로그 보관 질문

`AskUserQuestion`으로:
```
header: 토론 로그
question: 이번 토론 로그를 보관할까요?
options:
  - 보관 (~/Documents/crosstalk/<날짜>-<주제slug>.md)
  - 폐기
```

**보관**:
```bash
mkdir -p ~/Documents/crosstalk
DATE=$(date '+%Y-%m-%d')
SLUG=$(echo "<주제>" | tr ' /' '--' | tr -cd '[:alnum:]-' | head -c 50)
DEST=~/Documents/crosstalk/${DATE}-${SLUG}.md
mv "$LOG_TMP" "$DEST"
```

**폐기**: `rm -f "$LOG_TMP"`

## Ctrl+C 대응

bridge에 정지 신호 + 즉시 8단계 종합으로 점프 → 9단계 보관 질문:

```bash
~/.claude/scripts/crosstalk_bridge.sh stop <surface>
```

## 주의사항

- 한 발언당 한 단락(3-5문장) 엄수.
- 같은 논점 반복 금지. 새 근거/관점 없으면 양보 + [AGREE].
- 답변 캡처 시 cmux 박스 라인, 프롬프트 마커, "Working…" 같은 노이즈 무시. 답변 본문만 추출.
- bridge 호출 실패(소켓 단절 등) 즉시 사용자에게 보고 + 종료.
- 토론 시작 시 사용자에게 *토론이 끝날 때까지 다른 cmux pane에 직접 입력하지 마세요* 안내.
