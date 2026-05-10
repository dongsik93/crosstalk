---
description: Co-work mode. Each peer runs its own /goal in its own CLI to deliver a piece of the task in parallel. Crosstalk fans out the assignments, isolates work in git worktrees, and collects results when all peers ping done (or after the time cap).
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: [--no-worktree] [--max-time <duration>] "claude=A 작업, codex=B 작업, goal=Y"
---

# /crosstalk:cowork (다중 AI 공동 작업)

각 peer가 *자기 환경의 `/goal` 슬래시 명령*을 호출해 분담받은 작업을 알아서 진행한다. Crosstalk은 트리거 + 격리 + 결과 수집만. 판정/검증은 peer의 `/goal` 훅에 위임.

## 옵션

- `--no-worktree` — git worktree 없이 현재 디렉토리에서 같이 작업 (충돌 위험. 기본은 worktree 격리).
- `--max-time <duration>` — 시간 캡 (기본 `1h`). 형식: `30m`, `2h` 등.
- `$ARGUMENTS`의 자유 텍스트가 작업 분담 + goal. 예:
  ```
  /crosstalk:cowork "claude=Repository 레이어, codex=ViewModel 레이어, goal=메일 검색 기능 완성하고 unit test 통과"
  ```
  명시적 형식이 어려우면 자유 텍스트로 던져도 호출자가 분배 시도.

## 전제 조건

- cmux 환경, split 안에 다른 CLI(Codex/Gemini) 1개 이상
- bridge 설치 완료
- `--no-worktree`가 아니면 git 레포 안

## 1단계: 옵션 파싱

```bash
ARGS="$ARGUMENTS"
USE_WORKTREE=true
MAX_TIME="1h"

if echo "$ARGS" | grep -q -- '--no-worktree'; then
  USE_WORKTREE=false
  ARGS=$(echo "$ARGS" | sed 's/--no-worktree//' | tr -s ' ')
fi
if echo "$ARGS" | grep -qE -- '--max-time[[:space:]]+[0-9]+[smh]'; then
  MAX_TIME=$(echo "$ARGS" | grep -oE -- '--max-time[[:space:]]+[0-9]+[smh]' | awk '{print $2}')
  ARGS=$(echo "$ARGS" | sed -E 's/--max-time[[:space:]]+[0-9]+[smh]//' | tr -s ' ')
fi

TASK_BODY=$(echo "$ARGS" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')
```

`TASK_BODY` 비었으면 사용법 안내 후 종료.

`MAX_TIME`을 초로 변환 (`30m → 1800`, `1h → 3600`, `90m → 5400`).

## 2단계: peer 탐색

```bash
PEERS_RAW=$(~/.claude/scripts/crosstalk_bridge.sh list-peers)
PEERS=$(printf '%s\n' "$PEERS_RAW" | awk -F'\t' '$2 ~ /^(claude|codex|gemini)$/ {print $1"|"$2}')
```

`PEERS` 비어있으면 `/crosstalk:launch` 안내 후 종료.

## 3단계: run 디렉토리 + 참가자 목록 생성

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
```

`start-run`이 `moderator_surface`, `moderator_kind`를 manifest에 박는다. Claude caller는 기존처럼 `claude`, Codex caller는 `$crosstalk` skill 경로에서 `codex`가 된다.

## 4단계: 작업 분담 자동 분배

자유 텍스트 `TASK_BODY`를 호출자가 한 번 해석해서 *각 참가자별 분담* + *공통 goal*로 정리.

규칙:
- "claude=X, codex=Y, goal=Z" 같은 명시 형식이면 그대로 파싱.
- 명시 안 됐으면 호출자가 적당히 분배. 참가자 수에 맞춰 균등 분담. goal은 전체 작업 완료 조건으로 설정.
- 호출자도 작업 참여 — 자기 분담 + 진행자 1인 2역.

결과를 manifest에 머지:
```bash
jq --arg goal "..." \
   --argjson assignments '{...}' \
   --argjson agents "$(printf '%s\n' "${AGENTS[@]}" | jq -R . | jq -s .)" \
   '. + {mode: "cowork", goal: $goal, assignments: $assignments, agents: $agents, current_round: 1}' \
   "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"
```

## 5단계: worktree 격리 (USE_WORKTREE=true)

사용자에게 확인 (AskUserQuestion):

```
🌳 작업 격리 방식

  [worktree] git worktree로 분리 (안전, 충돌 X) — 권장
  [shared]   현재 디렉토리에서 같이 작업 (빠르지만 충돌 위험)
  [cancel]
```

`worktree` 선택:
```bash
declare -A WORKTREES
for entry in "${AGENTS[@]}"; do
  WT=$(~/.claude/scripts/crosstalk_bridge.sh start-worktree "$RUN_ID" "$entry")
  WORKTREES["$entry"]="$WT"
done

# manifest에 worktree 경로 머지
WT_JSON=$(for k in "${!WORKTREES[@]}"; do printf '"%s":"%s"\n' "$k" "${WORKTREES[$k]}"; done | jq -R -s 'split("\n") | map(select(length>0) | split(":") | {(.[0]|gsub("\""; "")): (.[1]|gsub("\""; ""))}) | add')
TMP=$(mktemp)
jq --argjson wt "$WT_JSON" '.worktrees = $wt' "$MANIFEST" > "$TMP" && mv "$TMP" "$MANIFEST"
```

`shared` 선택: 모든 peer의 작업 디렉토리 = `$(pwd)`.
`cancel`: 즉시 종료.

## 6단계: fan-out (각 peer에 작업 + /goal 발동)

각 peer에 다음 메시지를 cmux send:

```
[Crosstalk cowork — RUN_ID=${RUN_ID}]

너의 작업 분담:
${ASSIGNMENT_FOR_AGENT}

작업 디렉토리:
${WORKTREE_PATH_OR_PWD}

═══ 진행 방식 (변경 불가) ═══
1. 작업 디렉토리로 이동:
   cd ${WORKTREE_PATH_OR_PWD}

2. 너의 /goal 슬래시 명령으로 작업을 시작해라:
   /goal "${GOAL}"

   /goal 훅이 너의 stop을 막는 동안, 너는 위 분담을 *처음부터 끝까지* 자율적으로 진행한다.
   - 코드 작성 / 수정 / git commit 자유.
   - 단, ${WORKTREE_PATH_OR_PWD} 디렉토리 밖은 수정 금지.

3. goal 달성했다고 판단되면 /goal clear (또는 자동 clear되도록 너의 /goal 구현이 처리).

4. 마지막으로 작업 보고를 파일에 기록:
   cat > /tmp/crosstalk/run-${RUN_ID}/responses/<AGENT>-r01.md <<'EOF'
   # 작업 보고
   - 분담: ${ASSIGNMENT_FOR_AGENT}
   - 커밋: <git log --oneline 결과>
   - 변경 파일: <주요 파일 목록>
   - 미완 / 이슈: <있으면 명시>
   EOF

5. ping 호출:
   ~/.claude/scripts/crosstalk_bridge.sh ping ${RUN_ID} <AGENT> 1

═══ 안전 ═══
- max ${MAX_TIME} 초 후 사회자가 강제 종료 신호를 보낸다 (cowork-stop).
- 외부에서 [crosstalk:cowork-stop] 메시지를 받으면 즉시 작업 중단 + 현재까지 보고만 작성하고 ping.
```

전송:
```bash
for entry in "${PEERS[@]}"; do
  PEER_SURFACE="${entry%|*}"
  PEER_KIND="${entry#*|}"
  ~/.claude/scripts/crosstalk_bridge.sh send "$PEER_SURFACE" "$MSG_FOR_${PEER_KIND}"
  sleep 1
done
```

**호출자 본인**도 동등하게 작업:
- worktree 또는 현재 디렉토리로 이동
- 자기 분담 작업 진행 (이 슬래시 커맨드 종료 후, 사용자가 다시 호출하면 진행)
- 단, 호출자는 *진행 모니터링*도 같이 맡음 — callback 시 통합 보고 작성

## 7단계: 슬래시 커맨드 종료 → callback 대기

분기:
- 모든 peer ping 도착 → 8단계 (정상 종료)
- max_time 초과 → 9단계 (강제 종료)
- 사용자가 `/crosstalk:cowork-stop` 호출 → 9단계 (사용자 stop)

callback 메시지에서 RUN_ID 파싱 후 manifest 읽어 컨텍스트 복원.

## 8단계: 정상 종료 — 결과 통합

모든 peer 응답 파일 (`responses/<agent>-r01.md`) 읽어 통합 보고 작성:

```bash
SUMMARY="$RUN_DIR/cowork-summary.md"
{
  echo "# Cowork 결과 (RUN_ID=$RUN_ID)"
  echo ""
  echo "## Goal"
  echo "$GOAL"
  echo ""
  echo "## 작업 결과"
  for agent in "${AGENTS[@]}"; do
    echo "### $agent"
    cat "$RUN_DIR/responses/${agent}-r01.md"
    echo ""

    # worktree가 있으면 git log 같이 첨부
    WT="${WORKTREES[$agent]:-}"
    if [ -n "$WT" ] && [ -d "$WT" ]; then
      echo "**커밋:**"
      (cd "$WT" && git log --oneline "$(git merge-base HEAD HEAD@{u} 2>/dev/null || git log --reverse --format=%H | head -1)..HEAD" 2>/dev/null) || echo "(no commits)"
    fi
    echo ""
  done
} > "$SUMMARY"

LAST=$(~/.claude/scripts/crosstalk_bridge.sh register-last "$RUN_ID")
echo ""
echo "✅ Cowork 완료 (RUN_ID=$RUN_ID)"
echo "📁 결과: $SUMMARY"
echo "📁 last: $LAST"
```

worktree 정리 옵션 제시 (AskUserQuestion):

```
🌳 worktree 정리

각 worktree:
  - <moderator>: <path> (N commits)
  - codex:  <path> (N commits)

다음 옵션:
  [keep]  worktree 그대로 두고 사용자가 수동 검토 — 권장
  [merge] 메인 브랜치로 자동 시도 (충돌 발생 시 keep으로 폴백)
  [drop]  worktree 폐기 + 브랜치 삭제 (커밋 손실 주의)
```

`keep` (기본): 아무것도 안 함. 사용자가 직접 `cd <worktree>` 후 검토.
`merge`: 각 브랜치를 현재 브랜치로 cherry-pick 시도. 충돌 시 즉시 중단 + keep으로 폴백.
`drop`: `~/.claude/scripts/crosstalk_bridge.sh cleanup-worktrees $RUN_ID` 호출 + 브랜치 삭제 확인.

## 9단계: 강제 종료 (timeout 또는 사용자 stop)

```bash
~/.claude/scripts/crosstalk_bridge.sh notify-stop "$RUN_ID"
```

→ 모든 peer에 `/goal clear` + 종료 메시지 cmux send.
→ 5초 대기 후 8단계와 동일한 결과 수집 (응답 파일이 있는 만큼만 수집).
→ 통합 보고 끝에 "⚠️ 강제 종료 — 일부 작업 미완" 표시.

## 디렉토리 구조

```
/tmp/crosstalk/run-<RUN_ID>/
  manifest.json       # mode=cowork + goal + assignments + worktrees
  done/
    <moderator>-r01
    codex-r01
  responses/
    <moderator>-r01.md # 각자 작업 보고
    codex-r01.md
  cowork-summary.md   # 통합 보고

/tmp/crosstalk/worktrees/run-<RUN_ID>/
  <moderator>/        # git worktree (브랜치 cowork/<RUN_ID>-<moderator>)
  codex/              # git worktree (브랜치 cowork/<RUN_ID>-codex)
```

## 주의

- **MVP는 cross-check 없음**. peer끼리 서로 진행을 모름. 끝나면 호출자가 합침.
- **자동 머지 X (기본)**: 충돌 위험 때문에 사용자 수동 검토가 안전.
- **goal 검증은 각 CLI의 `/goal` 책임**. Crosstalk은 LLM 판정/명령 검증/사용자 확인 어느 것도 안 한다.
- **max_time이 절대 캡**: peer의 `/goal`이 무한 진행해도 외부에서 깰 수 있게 보장.
