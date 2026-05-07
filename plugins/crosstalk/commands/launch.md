---
description: cmux를 자동 실행하고 워크스페이스를 분할해 Claude/Codex/Gemini를 동시에 띄운 뒤 라벨링까지 완료. /crosstalk:install 이후 1회 실행하면 토론 환경 한 방에 셋업.
allowed-tools: Bash, AskUserQuestion
argument-hint: (인자 없음)
---

# Crosstalk Launch — cmux 환경 한방 셋업

cmux 안 떠있으면 실행 + 워크스페이스 + 분할 + AI CLI 시작 + 라벨링까지 자동 처리.

## 전제 조건

- macOS (cmux는 macOS 전용)
- cmux 설치됨 (`brew install --cask cmux`)
- `/crosstalk:install` 1회 실행 완료
- AI CLI들이 설치되고 인증됨 (claude/codex/gemini 중 사용할 것들)

## 1단계: 환경 검증

```bash
# cmux 실행/설치 확인
if ! which cmux >/dev/null; then
  echo "ERROR: cmux 미설치. brew install --cask cmux"
  exit 1
fi

# 이미 cmux가 떠있으면 ping 가능
CMUX_RUNNING=false
cmux ping >/dev/null 2>&1 && CMUX_RUNNING=true

# 각 CLI 설치 확인
HAS_CLAUDE=$(which claude >/dev/null && echo true || echo false)
HAS_CODEX=$(which codex >/dev/null && echo true || echo false)
HAS_GEMINI=$(which gemini >/dev/null && echo true || echo false)
```

설치 안 된 CLI는 `AskUserQuestion`으로 *제외하고 진행할지 / 취소할지* 결정.

## 2단계: 사용자에게 구성 선택

`AskUserQuestion`:
```
header: 토론 환경 구성
question: 어떤 AI CLI들을 띄울까요?
options (동적 — 설치된 것만):
  - Claude + Codex + Gemini (3분할)
  - Claude + Codex (2분할 좌우)
  - Claude + Gemini (2분할 좌우)
  - Codex + Gemini (2분할 좌우)
  - 취소
```

## 3단계: cmux 실행 (안 떠있으면)

```bash
if ! $CMUX_RUNNING; then
  open -na cmux
  # cmux 실행 대기 (소켓 활성화까지)
  for i in 1 2 3 4 5 6 7 8 9 10; do
    cmux ping >/dev/null 2>&1 && break
    sleep 1
  done
fi
```

10초 안에 안 떠지면 사용자에게 *cmux 수동 실행 후 재시도* 안내.

## 4단계: 워크스페이스 + pane 셋업

3분할 예시:
```bash
# 새 워크스페이스
WS_OUTPUT=$(cmux new-workspace --name "crosstalk" --focus true)
WS_REF=$(echo "$WS_OUTPUT" | grep -oE 'workspace:[0-9]+' | head -1)

# 첫 surface 정보
FIRST_SURFACE=$(cmux list-pane-surfaces --workspace "$WS_REF" 2>/dev/null \
  | awk '/surface:/ {gsub("[*]",""); print $1; exit}')

# 우측에 split 추가
cmux new-split right --workspace "$WS_REF" --focus false
sleep 0.3

# 우측 위에서 다시 아래로 split
RIGHT_SURFACES=$(cmux list-pane-surfaces --workspace "$WS_REF" 2>/dev/null \
  | awk '/surface:/ {gsub("[*]",""); print $1}')
# 왼쪽(첫번째)을 제외한 surface가 우측 — 그 surface 기준으로 down split
RIGHT_FIRST=$(echo "$RIGHT_SURFACES" | grep -v "^${FIRST_SURFACE}$" | head -1)
cmux new-split down --surface "$RIGHT_FIRST" --focus false
sleep 0.3
```

2분할이면 `new-split right` 한 번만.

## 5단계: 각 pane에서 AI CLI 시작

각 surface에 매핑:
- 좌측(첫 번째) → Claude
- 우측 위 → Codex
- 우측 아래 → Gemini

```bash
# 각 surface ID 확정
SURFACES=$(cmux list-pane-surfaces --workspace "$WS_REF" 2>/dev/null \
  | awk '/surface:/ {gsub("[*]",""); print $1}')

# 매핑 (사용자 선택에 따라 동적 — 여기는 3분할 예시)
LEFT=$(echo "$SURFACES" | sed -n '1p')
RIGHT_TOP=$(echo "$SURFACES" | sed -n '2p')
RIGHT_BOT=$(echo "$SURFACES" | sed -n '3p')

# 각 pane에서 AI CLI 실행
~/.claude/scripts/crosstalk_bridge.sh send "$LEFT" "claude"
sleep 1

if $HAS_CODEX; then
  ~/.claude/scripts/crosstalk_bridge.sh send "$RIGHT_TOP" "codex"
  sleep 1
fi

if $HAS_GEMINI; then
  ~/.claude/scripts/crosstalk_bridge.sh send "$RIGHT_BOT" "gemini"
  sleep 1
fi
```

## 6단계: AI CLI 시작 대기 (10~15초)

각 CLI 시작 화면이 뜨고 안정화될 시간 필요. 사용자에게 진행 상황 표시:

```
⏳ AI CLI 시작 대기 중 (15초)...
  - Claude: 시작 중
  - Codex:  시작 중
  - Gemini: 시작 중
```

```bash
sleep 15
```

## 7단계: 라벨 자동 박기

```bash
~/.claude/scripts/crosstalk_bridge.sh label "$LEFT" claude
$HAS_CODEX  && ~/.claude/scripts/crosstalk_bridge.sh label "$RIGHT_TOP" codex
$HAS_GEMINI && ~/.claude/scripts/crosstalk_bridge.sh label "$RIGHT_BOT" gemini
```

## 8단계: 인증 안 된 CLI 감지 + 안내

각 CLI 화면 캡처 후 *로그인 화면이 떠있는지* 검사:
```bash
SCREEN=$(~/.claude/scripts/crosstalk_bridge.sh capture "$RIGHT_TOP" | tail -30)
if echo "$SCREEN" | grep -qiE "sign in|login|authenticate|oauth"; then
  echo "⚠️ Codex pane에 로그인 화면 감지. 사용자가 직접 인증 후 다시 /crosstalk:setup 실행 필요."
fi
```

(완벽 감지는 어려움 — 휴리스틱 수준.)

## 9단계: 완료 안내

```
🎉 Crosstalk 환경 셋업 완료!

cmux 워크스페이스: crosstalk
  ┌─────────────┬─────────────┐
  │             │   Codex     │
  │   Claude    ├─────────────┤
  │             │   Gemini    │
  └─────────────┴─────────────┘

라벨링 완료:
  ✅ surface:N → claude
  ✅ surface:N → codex
  ✅ surface:N → gemini

(인증 안 된 CLI 있을 시) ⚠️ 안내 메시지 표시.

다음 단계: cmux 창 좌측 Claude pane에서
  /crosstalk 1+1은 2다 동의해?       ← 단독 명령
  /crosstalk:debate <주제>            ← 명시적
  /crosstalk:review <PR번호>          ← PR 리뷰 토론
```

## 주의사항

- 이미 다른 cmux 워크스페이스 사용 중이라면 `crosstalk` 워크스페이스가 추가됨 (기존 영향 없음).
- AI CLI 시작 시간은 시스템에 따라 다름. 15초로 부족하면 `sleep` 더 늘리거나 사용자가 *완료된 후 /crosstalk:setup 으로 라벨링*.
- 첫 실행 시 cmux/각 CLI가 OAuth 인증을 요구할 수 있음. 인증 후 라벨링 다시 해야 할 수도.
- 이 명령은 호출 주체 cmux가 아니어도(예: Ghostty에서 실행) 동작 — cmux를 *외부에서 실행*하는 형태.
