---
description: PR을 cmux의 다른 AI(Codex/Gemini)들과 함께 리뷰. 빠른 모드(diff 공유) 또는 깊은 모드(--deep, 현재 디렉토리를 PR 브랜치로 checkout). --rules / --persona 옵션 지원.
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

### 깊은 모드
```bash
STASH_REF=""
if $HAS_CHANGES; then
  git stash push -u -m "crosstalk-review-${PR_NUM}-$(date +%s)"
  STASH_REF=$(git stash list | head -1 | cut -d: -f1)
fi
gh pr checkout "$PR_NUM" || { echo "ERROR: PR checkout 실패"; exit 1; }
CURRENT_DIR=$(pwd)
DIFF_PATH="/tmp/pr-${PR_NUM}-$(date +%Y%m%d-%H%M%S).diff"
gh pr diff "$PR_NUM" > "$DIFF_PATH"
DIFF_LINES=$(wc -l < "$DIFF_PATH" | tr -d ' ')
SHARED_LABEL="현재 디렉토리: $CURRENT_DIR (PR 브랜치 체크아웃됨), diff 참조: $DIFF_PATH"
SHARED_INSTR="현재 디렉토리($CURRENT_DIR)가 PR 브랜치입니다. grep/find/read로 자유롭게 분석. 코드 수정/커밋 금지."

restore_branch() {
  git checkout "$ORIG_BRANCH" 2>/dev/null
  if [ -n "$STASH_REF" ]; then
    git stash pop "$STASH_REF" 2>/dev/null
  fi
  echo "✓ 원래 브랜치(${ORIG_BRANCH})로 복귀 완료"
}
trap restore_branch EXIT INT TERM
```

## 4단계: 환경 스캔 + 상대 선택

`/crosstalk:debate`와 동일.

## 5단계: 임시 로그

```bash
LOG_TMP="/tmp/crosstalk-review-${PR_NUM}-$(date +%Y%m%d-%H%M%S)-$$.md"
~/.claude/scripts/crosstalk_bridge.sh save "$LOG_TMP" "# PR #${PR_NUM} 리뷰 토론

- 일시: $(date '+%Y-%m-%d %H:%M:%S')
- PR: <title>, <author>
- 모드: ${MODE}
- 공유 자료: ${SHARED_LABEL}
- URL: <url>
"
```

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

전송 + 답변 대기 (`MAX_WAIT`은 모드별):
- fast: `STABLE_SECONDS=8 MAX_WAIT=600`
- deep: `STABLE_SECONDS=12 MAX_WAIT=1800`

`[REVIEW_DONE]` / `INTERVENTION` 처리는 `/crosstalk:debate`와 동일.

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

[1단계 리뷰 요약]
- Claude (<verdict>): <한 줄>
- Codex (<verdict>): <한 줄>
- Gemini (<verdict>): <한 줄>

[직전 라운드] (2라운드부터)
- 각 CLI: <한 줄씩>

[이번 라운드 질문]
<Claude가 종합한 논점>
```

전송 흐름은 `/crosstalk:debate`와 동일 (`STABLE_SECONDS=5 MAX_WAIT=180`).

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

## 9단계: 브랜치 복귀 (deep 필수)

```bash
restore_branch
```

성공 안내 또는 실패 시 수동 복구 안내.

## 10단계: 로그 + 자료 보관 질문

`AskUserQuestion`:
```
header: 리뷰 자료
question: PR #${PR_NUM} 리뷰 자료를 보관할까요?
options:
  - 보관 (~/Documents/crosstalk/PR-${PR_NUM}-<날짜>/)
  - 폐기
```

**보관**:
```bash
mkdir -p ~/Documents/crosstalk
DATE=$(date '+%Y-%m-%d')
DEST_DIR=~/Documents/crosstalk/PR-${PR_NUM}-${DATE}
mkdir -p "$DEST_DIR"
mv "$LOG_TMP" "$DEST_DIR/discussion.md"
mv "$DIFF_PATH" "$DEST_DIR/pr.diff"
```

**폐기**: `rm -f "$LOG_TMP" "$DIFF_PATH"`

## Ctrl+C 대응

trap이 `restore_branch` 자동 호출 → 브랜치 복귀 보장. 이후 8~10단계 점프.

## 주의사항

- 빠른 모드는 hunk 위주 — caller/다른 파일 영향 못 잡음.
- 깊은 모드는 현재 디렉토리 일시 전환. trap으로 복귀 보장. 사전 동의 필수.
- 모든 cmux pane이 같은 디렉토리에서 시작됐어야 깊은 모드 가능.
- bridge 호출 실패 즉시 사용자에게 보고 + (deep이면 복귀 후) 종료.
