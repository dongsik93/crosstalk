---
description: PR을 cmux의 다른 AI(Codex/Gemini)들과 함께 리뷰. 빠른 모드(diff 공유) 또는 깊은 모드(--deep, experimental — 현재 디렉토리를 PR 브랜치로 checkout). --rules / --persona 옵션 지원.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: [--deep] [--rules <name>] [--persona <name>] [PR번호]
---

# Crosstalk Review — 다중 AI PR 리뷰 토론

`/crosstalk:debate`의 PR 리뷰 특화 버전.

## 두 모드

| 모드 | 자료 공유 | 시간 | 깊이 |
|------|----------|------|------|
| **빠른 (default)** | `gh pr diff` 결과를 임시 파일로 공유 | 5~10분 | hunk 위주 |
| **깊은 (`--deep`)** | 현재 디렉토리를 PR 브랜치로 checkout | 15~30분 | caller 추적, 컨텍스트 |

## 전제 조건

- cmux 환경, split 안에 다른 CLI(Codex/Gemini) 1개 이상
- bridge: `~/.claude/scripts/crosstalk_bridge.sh`
- `gh` CLI 인증 완료
- 현재 디렉토리가 git 레포

## 사용 예

```
/crosstalk:review              ← 현재 브랜치 PR 자동 감지, 빠른 모드
/crosstalk:review 1440         ← PR 1440, 빠른 모드
/crosstalk:review --deep       ← 자동 감지, 깊은 모드
/crosstalk:review --deep 1440  ← PR 1440, 깊은 모드
```

---

## 1단계: 옵션 파싱 + PR 정보 + 룰/페르소나 로드

`$ARGUMENTS`에서 옵션 추출:

```bash
ARGS="$ARGUMENTS"
MODE="fast"
RULES_NAME=""
PERSONA_NAME=""

# --deep
if echo "$ARGS" | grep -q -- '--deep'; then
  MODE="deep"
  ARGS=$(echo "$ARGS" | sed 's/--deep//' | tr -s ' ')
fi

# --rules <name>
if echo "$ARGS" | grep -qE -- '--rules[[:space:]]+[^[:space:]]+'; then
  RULES_NAME=$(echo "$ARGS" | sed -E 's/.*--rules[[:space:]]+([^[:space:]]+).*/\1/')
  ARGS=$(echo "$ARGS" | sed -E 's/--rules[[:space:]]+[^[:space:]]+//' | tr -s ' ')
fi

# --persona <name>
if echo "$ARGS" | grep -qE -- '--persona[[:space:]]+[^[:space:]]+'; then
  PERSONA_NAME=$(echo "$ARGS" | sed -E 's/.*--persona[[:space:]]+([^[:space:]]+).*/\1/')
  ARGS=$(echo "$ARGS" | sed -E 's/--persona[[:space:]]+[^[:space:]]+//' | tr -s ' ')
fi

# 옵션 미지정 시 active 프리셋
CONFIG=~/.claude/crosstalk/config.json
RULES_NAME="${RULES_NAME:-$(jq -r '.active_rules // "default"' "$CONFIG" 2>/dev/null || echo "default")}"
PERSONA_NAME="${PERSONA_NAME:-$(jq -r '.active_persona // "default"' "$CONFIG" 2>/dev/null || echo "default")}"

# 룰/페르소나 본문 검증
RULES_PATH=~/.claude/crosstalk/rules/${RULES_NAME}.md
PERSONA_PATH=~/.claude/crosstalk/personas/${PERSONA_NAME}.md
[ ! -f "$RULES_PATH" ] && echo "❌ 룰 '$RULES_NAME' 없음 — /crosstalk:rules 확인" && exit 1
[ ! -f "$PERSONA_PATH" ] && echo "❌ 페르소나 '$PERSONA_NAME' 없음 — /crosstalk:persona 확인" && exit 1

# PR 번호
PR_NUM=$(echo "$ARGS" | tr -d '[:space:]')
if [ -z "$PR_NUM" ]; then
  PR_NUM=$(gh pr view --json number --jq .number 2>/dev/null || echo "")
fi
if [ -z "$PR_NUM" ]; then
  echo "ERROR: PR 번호를 찾을 수 없습니다."
  exit 1
fi

PR_META=$(gh pr view "$PR_NUM" --json title,author,headRefName,baseRefName,additions,deletions,changedFiles,url --jq .)
PR_FILES=$(gh pr view "$PR_NUM" --json files --jq '.files[] | "\(.additions)+ \(.deletions)- \(.path)"')
```

Read 도구로 `$RULES_PATH`, `$PERSONA_PATH` 본문 메모리에 로드 — 이후 모든 토론 메시지에 주입.

## 2단계: 깊은 모드 동의 확인 (deep만)

```bash
ORIG_BRANCH=$(git rev-parse --abbrev-ref HEAD)
HAS_CHANGES=false
[ -n "$(git status --porcelain)" ] && HAS_CHANGES=true
```

`AskUserQuestion`:
```
header: 깊은 모드 주의사항
question: 깊은 모드는 현재 작업 디렉토리를 PR #${PR_NUM} 브랜치로 갈아탑니다.

[현재 상태]
- 브랜치: ${ORIG_BRANCH}
- 작업 중 변경사항: ${HAS_CHANGES} (있으면 자동 stash → 종료 시 복원)

[주의]
- 모든 cmux pane이 같은 디렉토리에 있어야 합니다.
- 토론 중 코드 수정/커밋/git 작업 금지.
- 토론은 15~30분 소요됩니다.
- 종료 시 자동으로 원래 브랜치 복귀.

options:
  - 진행
  - 빠른 모드로 변경
  - 취소
```

## 3단계: 모드별 자료 준비

### 빠른 모드
```bash
DIFF_PATH="/tmp/pr-${PR_NUM}-$(date +%Y%m%d-%H%M%S).diff"
gh pr diff "$PR_NUM" > "$DIFF_PATH"
DIFF_LINES=$(wc -l < "$DIFF_PATH" | tr -d ' ')
SHARED_LABEL="diff 파일: $DIFF_PATH ($DIFF_LINES lines)"
SHARED_INSTR="이 diff 파일을 너의 환경에서 직접 읽어 분석해주세요."
```

### 깊은 모드 (이 단계에서는 diff만 받는다 — checkout/stash는 4단계 뒤로 미룬다)
```bash
DIFF_PATH="/tmp/pr-${PR_NUM}-$(date +%Y%m%d-%H%M%S).diff"
gh pr diff "$PR_NUM" > "$DIFF_PATH"
DIFF_LINES=$(wc -l < "$DIFF_PATH" | tr -d ' ')
# SHARED_LABEL/SHARED_INSTR/CURRENT_DIR 는 checkout 직후 4.5단계에서 확정.
```

> **중요**: 깊은 모드의 `git stash` + `gh pr checkout` 은 *peer 검증을 통과한 뒤*에 수행한다.
> peer가 0개라 종료되는 경로에서 stash가 남아있는 사고를 막기 위함.

## 4단계: 환경 스캔 + 상대 선택 (peer 검증 우선)

`/crosstalk:debate`의 1·2단계와 동일한 흐름:

1. `~/.claude/scripts/crosstalk_bridge.sh list-peers` 로 후보 수집 (`unknown`/`shell` 제외).
2. **후보가 0개**:
   - `cmux ping` 실패 → cmux 미실행/미설치 안내 후 종료.
   - `cmux ping` 성공 → 사용자에게 안내 후 종료 (이 시점까지 stash/checkout 미수행, 정리할 것 없음):
     ```
     🛑 cmux split 안에 다른 AI pane(Codex/Gemini)이 없어 PR 리뷰 토론을 시작할 수 없습니다.

     다음 순서로 다시 시도해주세요:
       1. /crosstalk:launch
       2. 원래 호출했던 명령 그대로 다시 실행
          예: /crosstalk:review 1440      또는      /crosstalk:review --deep 1440
     ```
     슬래시 커맨드는 다른 슬래시 커맨드를 자동 호출하지 않는다.
3. 후보가 1개 이상이면 `/crosstalk:debate` 2단계처럼 `AskUserQuestion`으로 상대 선택.

## 4.5단계: 깊은 모드 — checkout (peer 확정 후, 명시 restore)

> ⚠️ **`--deep` 모드는 experimental 입니다.** 자동 복구를 신뢰하지 마세요.
> 슬래시 커맨드는 여러 bash 호출에 걸쳐 실행되며, `trap`은 *현재 호출* 끝나면 사라집니다.
> 따라서 trap에만 의존하지 않고, 9단계에서 `restore_branch`를 **명시적으로 호출**해야 합니다.
> 자동 복구 실패 시 사용자가 손으로 복구할 수 있도록 *수동 복구 명령*을 출력합니다.

깊은 모드일 때만, peer 선택까지 마친 *지금 시점*에 stash/checkout 수행:

```bash
if [ "$MODE" = "deep" ]; then
  STASH_REF=""
  if $HAS_CHANGES; then
    git stash push -u -m "crosstalk-review-${PR_NUM}-$(date +%s)"
    STASH_REF=$(git stash list | head -1 | cut -d: -f1)
  fi
  gh pr checkout "$PR_NUM" || {
    echo "ERROR: PR checkout 실패"
    echo "  자동 복구 시도..."
    [ -n "$STASH_REF" ] && git stash pop "$STASH_REF" 2>/dev/null || true
    echo "  수동 복구가 필요하면:"
    echo "    git checkout $ORIG_BRANCH"
    [ -n "$STASH_REF" ] && echo "    git stash pop $STASH_REF"
    exit 1
  }
  CURRENT_DIR=$(pwd)
  SHARED_LABEL="현재 디렉토리: $CURRENT_DIR (PR 브랜치 체크아웃됨), diff 참조: $DIFF_PATH"
  SHARED_INSTR="현재 디렉토리($CURRENT_DIR)가 PR 브랜치입니다. grep/find/read로 자유롭게 분석. 코드 수정/커밋/git 작업 금지. 단, 매 턴 메시지의 ═══ Transport ═══ 섹션이 지정한 응답 파일 1개 작성은 허용된다 (정확한 경로/파일명은 그 섹션이 알려준다)."

  restore_branch() {
    git checkout "$ORIG_BRANCH" 2>/dev/null || {
      echo "⚠️  자동 브랜치 복귀 실패. 수동 실행 필요:"
      echo "    git checkout $ORIG_BRANCH"
    }
    if [ -n "$STASH_REF" ]; then
      git stash pop "$STASH_REF" 2>/dev/null || {
        echo "⚠️  자동 stash 복구 실패. 수동 실행 필요:"
        echo "    git stash pop $STASH_REF"
      }
    fi
    echo "✓ 원래 브랜치(${ORIG_BRANCH}) 복귀 처리 완료"
  }
  # 같은 bash 호출 내 강제 종료 대비한 보조 안전망. 9단계 명시 호출이 1차 보장.
  trap restore_branch EXIT INT TERM
fi
```

## 5단계: 임시 로그 + transport run

```bash
LOG_TMP="/tmp/crosstalk-review-${PR_NUM}-$(date +%Y%m%d-%H%M%S)-$$.md"
~/.claude/scripts/crosstalk_bridge.sh save "$LOG_TMP" "# PR #${PR_NUM} 리뷰 토론

- 일시: $(date '+%Y-%m-%d %H:%M:%S')
- PR: <title>, <author>
- 모드: ${MODE}
- 공유 자료: ${SHARED_LABEL}
- URL: <url>
"

RUN_ID=$(~/.claude/scripts/crosstalk_bridge.sh start-run)
RUN_DIR="/tmp/crosstalk/run-${RUN_ID}"
```

이후 모든 AI 답변(1단계 리뷰, 2단계 토론)은 `$RUN_DIR/responses/<agent>-r<NN>-a<N>.md`에서 읽는다.

## 6단계: 1단계 메시지 — 각 CLI에 리뷰 요청

```
[다중 AI PR 리뷰 - 1단계: 분석 + 의견]
[모드: ${MODE}]

PR #${PR_NUM} 을 리뷰해주세요.

═══ 페르소나 (${PERSONA_NAME}) ═══
<페르소나 본문에서 너의 역할 매핑 추출>

═══ 토론 규칙 (${RULES_NAME}) ═══
<룰 본문>

═══ 시스템 규칙 (변경 불가) ═══
- 1단계 답변 마지막 줄에 [REVIEW_DONE]
- 2단계(토론)에서 합의 시 [AGREE], 이견 시 [DISAGREE: 사유]

═══ Transport (변경 불가) ═══
이 턴 답변은 화면이 아니라 파일에 기록한다.

1. 답변 본문 전체를 다음 파일에 그대로 써라:
     ${RUN_DIR}/responses/<RESP_BASENAME>
2. 파일 작성이 끝나면 화면에 정확히 한 줄: DONE <MSG_ID>
3. 파일 외 가공/박스 출력 금지. 이미 있으면 덮어써라.

  RESP_BASENAME = <agent>-r<NN>-a<N>.md   (1단계는 r01)
  MSG_ID        = run-<run-id>-r<NN>-<agent>-a<N>

[PR 정보]
- 제목: <title>
- 브랜치: <headRefName> → <baseRefName>
- 변경: +<additions> / -<deletions>, <changedFiles> files
- URL: <url>

[변경 파일]
<파일별 +/- 라인>

[리뷰 자료]
${SHARED_INSTR}

[작업 요청]
1. 위 자료로 PR 분석
2. 보안/성능/아키텍처/유지보수성/컨벤션 관점 검토
3. 머지 가부 의견: Approve / Request Changes / Comment
4. 핵심 근거 1-2개

[답변 형식]
룰의 답변 형식 + PR 리뷰는 5-12문장 (모드/룰에 따라).
마지막 줄에 [REVIEW_DONE] 마커.
```

전송 + 답변 대기 (파일 기반 transport, `MAX_WAIT`은 모드별):
- fast: `STABLE_SECONDS=8 MAX_WAIT=600 DONE_GRACE=5`
- deep: `STABLE_SECONDS=12 MAX_WAIT=1800 DONE_GRACE=5`

```bash
ATTEMPT=1
AGENT="$kind"
MSG_ID=$(~/.claude/scripts/crosstalk_bridge.sh make-msg-id "$RUN_ID" 1 "$AGENT" "$ATTEMPT")
RESP_BASENAME="${AGENT}-r01-a${ATTEMPT}.md"

# 메시지 안의 <RESP_BASENAME>/<MSG_ID> 자리표시자 치환 후 전송
~/.claude/scripts/crosstalk_bridge.sh send "$peer" "<치환된 메시지>"

# wait-turn: stderr에 STATE 라인, exit code로 성공/실패
STABLE_SECONDS=8 MAX_WAIT=600 DONE_GRACE=5 \
  ~/.claude/scripts/crosstalk_bridge.sh wait-turn "$peer" "$RUN_ID" "$MSG_ID" 2> /tmp/crosstalk_state
WAIT_RC=$?
STATE_LINE=$(cat /tmp/crosstalk_state)

# 분기: 성공 경로일 때만 read-response 호출
if [ "$WAIT_RC" -eq 0 ]; then
  # clean / soft-complete — 본문 사용 가능
  MAX_RESPONSE_BYTES=20000 \
    ~/.claude/scripts/crosstalk_bridge.sh read-response "$RUN_ID" "$MSG_ID" > /tmp/crosstalk_resp
  # soft-complete면 사용자 화면에 ⚠️ "DONE 마커 누락" 한 줄 노출
else
  # protocol-error / timeout — 사용자에게 재시도/무시/중단 AskUserQuestion
  # 재시도 시 ATTEMPT+1 후 위 흐름 재실행 (메시지에 *직전 시도가 응답 파일을 만들지 않았다* 한 줄 추가)
  :
fi
```

상태별 처리(`clean`/`soft-complete`/`protocol-error`/`timeout`)는 `/crosstalk:debate`의 표와 동일. `[REVIEW_DONE]` 마커는 응답 본문 끝에서 확인. INTERVENTION 휴리스틱은 v0.1.4부터 사용하지 않음.

Claude 본인도 같은 자료로 분석:
- fast: `cat $DIFF_PATH` 또는 Read
- deep: 현재 디렉토리에서 grep/find/read 자유

각 결과 변수 저장 → 로그 append.

## 7단계: 토론 라운드 (2단계)

```
[다중 AI PR 리뷰 - 2단계: 토론 라운드 N/10]

PR: #${PR_NUM} <title>
공유 자료: ${SHARED_LABEL}

═══ 페르소나 (${PERSONA_NAME}) ═══
<역할 매핑>

═══ 토론 규칙 (${RULES_NAME}) ═══
<룰 본문>

═══ 시스템 규칙 (변경 불가) ═══
- 합의 시 [AGREE], 이견 시 [DISAGREE: 사유]

═══ Transport (변경 불가) ═══
이 턴 답변은 파일에 기록.
1. ${RUN_DIR}/responses/<RESP_BASENAME>  에 본문 그대로
2. 화면에 한 줄: DONE <MSG_ID>
   RESP_BASENAME = <agent>-r<NN>-a<N>.md
   MSG_ID        = run-<run-id>-r<NN>-<agent>-a<N>

[1단계 리뷰 요약]
- Claude (<verdict>): <한 줄>
- Codex (<verdict>): <한 줄>
- Gemini (<verdict>): <한 줄>

[직전 라운드] (2라운드부터)
- 각 CLI: <한 줄씩>

[이번 라운드 질문]
<Claude가 종합한 논점>
```

전송 흐름은 `/crosstalk:debate`와 동일 (`make-msg-id` → `send` → `wait-turn` → `read-response`, `STABLE_SECONDS=5 MAX_WAIT=180 DONE_GRACE=5`).

## 8단계: 종합

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 PR #${PR_NUM} 리뷰 토론 종합
모드: ${MODE}
종료: 합의 / 리밋 / 중단

[1단계 리뷰 결과]
🟦 Claude: <verdict> — <근거>
🟧 Codex: <verdict> — <근거>
🟪 Gemini: <verdict> — <근거>

[2단계 토론 결론]
🎯 머지 권장: Yes / No / Conditional
🎯 핵심 근거: <1-2문장>
🎯 보완 필요: <bullet>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

`$LOG_TMP`에 append.

## 9단계: 브랜치 복귀 (deep 필수, 명시 호출)

`--deep`이면 *반드시* `restore_branch`를 명시적으로 호출한다. trap에 기대지 말 것
(슬래시 커맨드는 여러 bash 호출로 쪼개질 수 있어 trap이 발동 안 될 수 있음):

```bash
if [ "$MODE" = "deep" ]; then
  restore_branch
fi
```

`restore_branch` 함수가 자동 복구 실패 시 수동 복구 명령을 stdout에 출력한다.
사용자에게 그 안내를 그대로 보여주고, 복구 확인 후 다음 단계로.

## 10단계: 로그 + 자료 보관 질문

`AskUserQuestion`:
```
header: 리뷰 자료
question: PR #${PR_NUM} 리뷰 자료를 보관할까요?
options:
  - 보관 (~/Documents/crosstalk/PR-${PR_NUM}-<날짜>/)
  - 폐기
```

**보관** — discussion.md + diff + responses/ 모두:
```bash
mkdir -p ~/Documents/crosstalk
DATE=$(date '+%Y-%m-%d')
DEST_DIR=~/Documents/crosstalk/PR-${PR_NUM}-${DATE}
mkdir -p "$DEST_DIR"
mv "$LOG_TMP" "$DEST_DIR/discussion.md"
mv "$DIFF_PATH" "$DEST_DIR/pr.diff"
if [ -d "$RUN_DIR" ]; then
  cp -R "$RUN_DIR/responses" "$DEST_DIR/responses"
  cp "$RUN_DIR/manifest.json" "$DEST_DIR/manifest.json" 2>/dev/null || true
  rm -rf "$RUN_DIR"
fi
```

**폐기** — LOG_TMP + DIFF + RUN_DIR 모두:
```bash
rm -f "$LOG_TMP" "$DIFF_PATH"
[ -d "$RUN_DIR" ] && rm -rf "$RUN_DIR"
```

## Ctrl+C 대응

`trap restore_branch EXIT INT TERM`은 *현재 bash 호출* 안에서만 유효하다.
같은 호출에서 Ctrl+C가 발생하면 trap이 발동해 복귀를 시도한다 — *보조 안전망*일 뿐 1차 보장은 아니다.
어떤 경로로 끝나든 사용자에게 "원래 브랜치 복귀 처리 완료" 또는 "수동 복구 명령" 둘 중 하나를 명시적으로 보여줄 것.
이후 8~10단계 점프.

## 주의사항

- 빠른 모드는 hunk 위주 — caller/다른 파일 영향 못 잡음.
- 깊은 모드(⚠️ experimental)는 현재 디렉토리를 일시 전환. **9단계의 명시 `restore_branch` 호출이 1차 보장**, `trap restore_branch EXIT INT TERM`은 같은 bash 호출 내 강제 종료 대비 보조 안전망. 사전 동의 필수.
- 모든 cmux pane이 같은 디렉토리에서 시작됐어야 깊은 모드 가능.
- bridge 호출 실패 즉시 사용자에게 보고 + (deep이면 복귀 후) 종료.
