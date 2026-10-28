---
description: Review a GitHub PR with peer AI CLI panes. Supports en/ko UI. Deep mode uses a fixed detached worktree.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: [--deep] [--rules <name>] [--persona <name>] [PR번호]
---

# Crosstalk Review — 다중 AI PR 리뷰 토론

PR diff/branch를 자료로 공유하고, 사회자(Claude)가 turn-taking으로 진행하는 PR 리뷰 토론. analyze와 별개 흐름 — PR 리뷰는 *자료가 크고 사회자 정리가 필요해서* turn-taking 모델 유지.

## 두 모드

| 모드 | 자료 공유 | 시간 | 깊이 |
|------|----------|------|------|
| **빠른 (default)** | `gh pr diff` 결과를 임시 파일로 공유 | 5~10분 | hunk 위주 |
| **깊은 (`--deep`)** | 고정된 PR SHA의 별도 detached worktree | 15~30분 | caller 추적, 컨텍스트 |

## 전제 조건

- cmux 환경, split 안에 다른 CLI(Codex/Antigravity) 1개 이상
- bridge: `~/.claude/scripts/crosstalk_bridge.sh`
- `gh` CLI 인증 완료
- 현재 디렉토리가 git 레포

## 트리거 수신 규약 (v0.6.0+)

긴 리뷰 라운드 본문은 cmux로 직접 보내지 않는다. peer pane이 아래 짧은 트리거를 받으면 파일을 직접 읽고 그 안의 transport 절차를 따른다.

- `[crosstalk] review-round <NN> <agent> RUN_ID=<RUN_ID>` → `cat /tmp/crosstalk/run-<RUN_ID>/rounds/r<NN>-<agent>.md`

트리거 자체에는 답하지 말고, round 파일 본문을 읽은 뒤 응답 파일 작성 + ping까지 수행한다.

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
LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac
RULES_NAME="${RULES_NAME:-$(jq -r '.active_rules // "default"' "$CONFIG" 2>/dev/null || echo "default")}"
PERSONA_NAME="${PERSONA_NAME:-$(jq -r '.active_persona // "default"' "$CONFIG" 2>/dev/null || echo "default")}"

# 자가치유 — 디렉토리 비었으면 마켓 캐시에서 자동 복사
~/.claude/scripts/crosstalk_bridge.sh ensure-presets "$LANGUAGE" >/dev/null 2>&1 || true

# 룰/페르소나 본문 검증
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

# PR 번호
PR_NUM=$(echo "$ARGS" | tr -d '[:space:]')
if [ -z "$PR_NUM" ]; then
  PR_NUM=$(gh pr view --json number --jq .number 2>/dev/null || echo "")
fi
if [ -z "$PR_NUM" ]; then
  [ "$LANGUAGE" = "ko" ] && echo "ERROR: PR 번호를 찾을 수 없습니다." || echo "ERROR: Could not find PR number."
  exit 1
fi

PR_META=$(gh pr view "$PR_NUM" --json title,author,headRefName,baseRefName,additions,deletions,changedFiles,url --jq .)
PR_FILES=$(gh pr view "$PR_NUM" --json files --jq '.files[] | "\(.additions)+ \(.deletions)- \(.path)"')
```

Read 도구로 `$RULES_PATH`, `$PERSONA_PATH` 본문 메모리에 로드 — 이후 모든 토론 메시지에 주입.

## 2단계: 깊은 모드의 작업 경로

깊은 모드는 원본 디렉터리의 브랜치·index·stash·작업 파일을 바꾸지 않는다. peer 선택 뒤 `crosstalk review prepare`가 별도 detached worktree와 고정 SHA diff를 준비한다. Git 객체와 worktree 메타데이터는 공유하므로 보안 샌드박스는 아니다.

원본에서 브랜치를 바꾸거나 stash를 만들고 복원하는 절차를 실행하지 않는다. 중단 시에도 남은 review run을 조회하고 보존한다. 새 기능은 cmux review 전용이며 Ghostty review 지원을 뜻하지 않는다.

## 3단계: 모드별 자료 준비

### 빠른 모드
```bash
DIFF_PATH="/tmp/pr-${PR_NUM}-$(date +%Y%m%d-%H%M%S).diff"
gh pr diff "$PR_NUM" > "$DIFF_PATH"
DIFF_LINES=$(wc -l < "$DIFF_PATH" | tr -d ' ')
SHARED_LABEL="diff 파일: $DIFF_PATH ($DIFF_LINES lines)"
if [ "$LANGUAGE" = "ko" ]; then
  SHARED_INSTR="이 diff 파일을 너의 환경에서 직접 읽어 분석해주세요."
else
  SHARED_INSTR="Read this diff file in your environment and review it directly."
fi
```

### 깊은 모드

이 단계에서는 자료를 받지 않는다. peer 선택 후 `review prepare`가 동일한 base/head snapshot에서 worktree와 diff를 함께 생성한다. 별도로 받은 최신 PR diff를 섞지 않는다.

## 4단계: 환경 스캔 + 상대 선택 (peer 검증 우선)

peer 검증 흐름:

1. `~/.claude/scripts/crosstalk_bridge.sh list-peers` 로 후보 수집 (`unknown`/`shell` 제외).
2. **후보가 0개**:
   - `cmux ping` 실패 → cmux 미실행/미설치 안내 후 종료.
   - `cmux ping` 성공 → 사용자에게 안내 후 종료 (아직 review worktree를 만들지 않았으므로 정리할 것 없음):
     ```
     🛑 cmux split 안에 다른 AI pane(Codex/Antigravity)이 없어 PR 리뷰 토론을 시작할 수 없습니다.

     다음 순서로 다시 시도해주세요:
       1. /crosstalk:launch
       2. 원래 호출했던 명령 그대로 다시 실행
          예: /crosstalk:review 1440      또는      /crosstalk:review --deep 1440
     ```
     슬래시 커맨드는 다른 슬래시 커맨드를 자동 호출하지 않는다.
3. 후보가 1개 이상이면 `AskUserQuestion`으로 상대 선택.

## 4.5단계: 깊은 모드 — 고정 snapshot 준비

peer를 선택한 뒤 실행한다. `PEER_KIND`는 선택한 CLI 종류(`codex`, `antigravity`, `claude`)다. DB가 구버전이면 먼저 업그레이드 문서의 명시적 migration을 수행한다. 자동 migration이나 원본 경로 fallback은 하지 않는다.

```bash
if [ "$MODE" = "deep" ]; then
  REVIEW_JSON=$(~/.claude/scripts/crosstalk review prepare "$PR_NUM" --repo "$PWD" --peer "$PEER_KIND") || exit 1
  REVIEW_RUN_ID=$(printf '%s' "$REVIEW_JSON" | jq -r '.run_id')
  REVIEW_ROOT=$(printf '%s' "$REVIEW_JSON" | jq -r '.review_root')
  REVIEW_HEAD=$(printf '%s' "$REVIEW_JSON" | jq -r '.head_sha')
  REVIEW_BASE=$(printf '%s' "$REVIEW_JSON" | jq -r '.base_sha')
  DIFF_PATH=$(printf '%s' "$REVIEW_JSON" | jq -r '.diff_path')
  SHARED_LABEL="review_root=$REVIEW_ROOT reviewed_commit=$REVIEW_HEAD diff=$DIFF_PATH"
  SHARED_INSTR="Read only the absolute review_root $REVIEW_ROOT and diff $DIFF_PATH. Before reviewing, verify git -C '$REVIEW_ROOT' rev-parse HEAD equals $REVIEW_HEAD. Every file and Git tool call must explicitly use this review_root. Include reviewed_commit=$REVIEW_HEAD and evidence paths in the response. Do not fall back to the original repository or change the worktree. Write the response only to the Transport response path."
fi
```

JSON 값은 데이터로 파싱하며 `eval`하지 않는다. 위 지시문에 경로를 삽입할 때 경로의 따옴표가 실행 코드가 되도록 조립하지 말고, 실제 도구 인수로 경로를 전달한다. review_root에 접근할 수 없는 peer는 접근 문제를 보고하고 중단한다. 원격 PR head가 나중에 달라져도 이 run은 고정한 SHA만 리뷰한다.

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
mkdir -p "$RUN_DIR/rounds"
```

이후 모든 AI 답변(1단계 리뷰, 2단계 토론)은 `$RUN_DIR/responses/<agent>-r<NN>-a<N>.md`에서 읽는다. 모든 리뷰 라운드 요청 본문은 `$RUN_DIR/rounds/r<NN>-<agent>.md`에 저장하고, cmux로는 짧은 `review-round` 트리거만 보낸다.

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

**모든 AGENT(`claude`/`codex`/`antigravity`)는 file 모드**로 다음을 그대로 주입한다.

[file 모드 — 공통]
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

| 모드 | MAX_WAIT |
|---|---|
| fast | 600s |
| deep | 1800s |

활동 감지(`ACTIVITY_GRACE=30 ACTIVITY_EXTEND_BY=120 ACTIVITY_EXTEND_MAX=3`)로 *살아있는 한* 자동 연장. 위 값은 "최소 대기" 기준.

callback 패턴 — analyze와 동일한 구조:

```bash
# 메시지 발송 후 곧바로 종료. AI 답변이 끝나면 bridge ping이 사회자 pane을 깨움.
# 메시지 본문에 ping 안내 한 줄 포함 (preamble 또는 메시지 끝):
#   "리뷰 마치면: ~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} ${AGENT} 1"

# 1단계 컨텍스트를 manifest.json에 머지 (단일 진실).
# state.sh 패턴 X — manifest만 읽으면 callback 재진입 시 복원 가능.
PEERS_JSON=$(printf '%s\n' "${AGENTS[@]}" | jq -R '.' \
  | jq -s --argjson surfaces "$(printf '"%s"\n' "${PEERS[@]}" | jq -s .)" \
       'to_entries | map({key:.value, value:$surfaces[.key]}) | from_entries')

TMP=$(mktemp)
jq --arg phase review \
   --argjson round 1 \
   --argjson agents "$(printf '%s\n' "${AGENTS[@]}" | jq -R . | jq -s .)" \
   --argjson peers "$PEERS_JSON" \
   --arg review_run_id "${REVIEW_RUN_ID:-}" --arg review_root "${REVIEW_ROOT:-}" \
   --arg reviewed_commit "${REVIEW_HEAD:-}" --arg diff_path "$DIFF_PATH" \
   '. + {mode: $phase, current_round: $round, agents: $agents, peers: $peers, review_run_id: $review_run_id, review_root: $review_root, reviewed_commit: $reviewed_commit, diff_path: $diff_path}' \
   "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"

# 메시지 파일 작성 + 짧은 트리거 발송 (1:1이든 다자든 동일)
mkdir -p "$RUN_DIR/rounds"
for i in "${!AGENTS[@]}"; do
  agent="${AGENTS[$i]}"; peer="${PEERS[$i]}"
  ROUND_FILE="$RUN_DIR/rounds/r01-${agent}.md"
  substitute_msg "$RAW_MSG" "$agent" > "$ROUND_FILE"  # <RUN_ID>/<AGENT> 치환
  TRIGGER="[crosstalk] review-round 01 ${agent} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$peer" "$ROUND_FILE" "$TRIGGER"
done

# 사회자 슬래시 커맨드는 여기서 종료. AI 답변 도착하면 bridge ping이 자동으로 사회자를 깨움.
```

#### Callback 핸들링 (1단계 → 2단계)

claude pane이 `[crosstalk] codex R1 done — RUN_ID=...` 메시지를 받으면:
1. `$RUN_DIR/manifest.json` 읽어 컨텍스트 복원:
   ```bash
   MANIFEST="/tmp/crosstalk/run-${RUN_ID}/manifest.json"
   MODE=$(jq -r '.mode' "$MANIFEST")    # "review"
   AGENTS=($(jq -r '.agents[]' "$MANIFEST"))
   ROUND=$(jq -r '.current_round' "$MANIFEST")
   ```
2. `$RUN_DIR/done/<agent>-r01` 파일들 확인 → 모든 참여자 완료됐는지 검사
3. 미완료면 → 그냥 종료 (마지막 ping 도착 시 다시 진입)
4. 모두 완료면 → 각 peer의 응답 파일(`$RUN_DIR/responses/<agent>-r01.md`) 읽어 본문 정리 → **2단계 토론 라운드** 시작

#### Transport 대기 시간

옵션 흐름은 callback 위에 얹어진다. `MAX_WAIT`은 모드별:

| 모드 | MAX_WAIT |
|---|---|
| fast | 600s |
| deep | 1800s |

`[REVIEW_DONE]` 마커는 응답 본문 끝에서 확인.

Claude 본인도 같은 자료로 분석:
- fast: `cat $DIFF_PATH` 또는 Read
- deep: 모든 조회에 `$REVIEW_ROOT` 절대 경로를 사용하고 HEAD가 `$REVIEW_HEAD`인지 확인한다.

각 결과 변수 저장 → 로그 append.

## 7단계: 토론 라운드 (2단계)

```
[다중 AI PR 리뷰 - 2단계: 토론 라운드 N/10]

PR: #${PR_NUM} <title>
공유 자료: ${SHARED_LABEL}
${SHARED_INSTR}
응답에 reviewed_commit과 근거 파일의 review_root 기준 경로를 포함한다.

═══ 페르소나 (${PERSONA_NAME}) ═══
<역할 매핑>

═══ 토론 규칙 (${RULES_NAME}) ═══
<룰 본문>

═══ 시스템 규칙 (변경 불가) ═══
- 합의 시 [AGREE], 이견 시 [DISAGREE: 사유]

═══ Transport (변경 불가) ═══
**모든 AGENT(claude/codex/antigravity)는 file 모드.**

[file — 공통] ${RUN_DIR}/responses/<RESP_BASENAME> 에 본문 그대로 쓰고 화면에 `DONE <MSG_ID>` 한 줄.

  RESP_BASENAME = <agent>-r<NN>-a<N>.md
  MSG_ID        = run-<run-id>-r<NN>-<agent>-a<N>

[1단계 리뷰 요약]
- Claude (<verdict>): <한 줄>
- Codex (<verdict>): <한 줄>
- Antigravity (<verdict>): <한 줄>

[직전 라운드] (2라운드부터)
- 각 CLI: <한 줄씩>

[이번 라운드 질문]
<Claude가 종합한 논점>
```

전송 흐름 (callback 패턴 — analyze와 동일):
- 라운드 메시지를 `$RUN_DIR/rounds/r<NN>-<agent>.md`에 저장
- 짧은 `[crosstalk] review-round <NN> <agent> RUN_ID=<RUN_ID>` 트리거만 `send-via-file`로 발송
- manifest의 `current_round` 갱신 → 슬래시 커맨드 종료
- AI 답변 끝 → `bridge ping` 호출 → 사회자 pane callback
- 모든 참여자 ping 도착 → 다음 라운드 또는 종합 의견 단계로

ping 안내 문구는 메시지에 한 줄로:
> "답변 끝나면: `~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} ${AGENT} ${ROUND}`"

(Transport 옵션 켰으면 `make-msg-id` → `read-response` 사용. off면 응답 파일 `$RUN_DIR/responses/<agent>-r<NN>.md`에서 직접 읽음.)

라운드 발송 예:

```bash
ROUND_PADDED=$(printf '%02d' "$ROUND")
mkdir -p "$RUN_DIR/rounds"
for i in "${!AGENTS[@]}"; do
  agent="${AGENTS[$i]}"; peer="${PEERS[$i]}"
  ROUND_FILE="$RUN_DIR/rounds/r${ROUND_PADDED}-${agent}.md"
  render_review_round "$agent" "$ROUND" > "$ROUND_FILE"
  TRIGGER="[crosstalk] review-round ${ROUND_PADDED} ${agent} RUN_ID=${RUN_ID}"
  ~/.claude/scripts/crosstalk_bridge.sh send-via-file "$peer" "$ROUND_FILE" "$TRIGGER"
done
```

## 8단계: 종합

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 PR #${PR_NUM} 리뷰 토론 종합
모드: ${MODE}
종료: 합의 / 리밋 / 중단

[1단계 리뷰 결과]
🟦 Claude: <verdict> — <근거>
🟧 Codex: <verdict> — <근거>
🟪 Antigravity: <verdict> — <근거>

[2단계 토론 결론]
🎯 머지 권장: Yes / No / Conditional
🎯 핵심 근거: <1-2문장>
🎯 보완 필요: <bullet>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

`$LOG_TMP`에 append.

## 9단계: 결과 보존과 안전한 정리

모든 peer의 응답과 최종 요약을 `$LOG_TMP`에 포함한다. 깊은 모드는 해당 SHA를 검토했다는 `reviewed_commit`을 확인한다. 아직 응답 중인 peer가 있거나 종료 여부를 확인할 수 없으면 finish/cleanup을 실행하지 않고 run을 남긴다.

모든 peer와 작업 명령이 worktree 사용을 끝낸 것을 확인한 경우에만:

```bash
if [ "$MODE" = "deep" ]; then
  ~/.claude/scripts/crosstalk review finish "$REVIEW_RUN_ID" \
    --outcome completed --result-stdin --confirm-stopped < "$LOG_TMP" || exit 1
  ~/.claude/scripts/crosstalk review cleanup "$REVIEW_RUN_ID"
fi
```

중단된 리뷰도 종료를 확인한 뒤 실패 이유와 기존 응답을 보존해 `--outcome failed`로 finish한다. cleanup은 변경 파일·새 commit·ignored 파일·소유권 불일치가 있으면 worktree를 남긴다. 실패했다고 강제 삭제하지 않는다. `artifact_path`의 결과와 고정 diff는 cleanup 이후에도 보존된다.

## 10단계: 결과 안내

review run ID, 검토한 SHA, 보존된 artifact 경로, cleanup 결과를 사용자에게 보여준다. 추가 보관을 요청하면 결과를 복사하되 유일한 원본 자료를 지우지 않는다. 빠른 모드의 기존 로그와 transport 응답도 결과 안내 전까지 보존한다. 파일 삭제는 별도의 명시적인 사용자 요청으로만 수행한다.

## 중단 후 재개

callback에서는 manifest의 `review_run_id`, `review_root`, `reviewed_commit`, `diff_path`를 복원한다. 깊은 모드였으면 `crosstalk review status <review_run_id>`를 조회하고 고정 SHA와 소유권 진단을 확인한다. 작업이 멈췄다는 이유로 원본 브랜치를 바꾸거나 stash를 복원하지 않는다.

worktree 생성 직후 종료된 `preparing` run도 status에서 Git 등록 정보를 대조할 수 있다. 단순히 경로가 존재한다는 이유만으로 준비 완료로 취급하지 않는다. 검증된 checkout과 고정 자료를 확인한 뒤 계속 읽거나, 모든 작업이 멈춘 것을 확인하고 실패 결과를 보존한다.

## 주의사항

- 빠른 모드는 hunk 중심이며 전체 caller 분석을 대신하지 않는다.
- 깊은 모드의 모든 분석 도구는 절대 review_root를 명시한다. peer의 전역 cwd 변경을 가정하지 않는다.
- review prepare는 저장소 테스트나 스크립트를 실행하지 않는다. 명시적인 추가 실행 요청은 별도로 판단한다.
- bridge 오류가 발생하면 해당 오류와 run ID를 보고하고 자료를 보존한다.
