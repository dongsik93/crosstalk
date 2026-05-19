---
description: Launch or prepare a cmux workspace for Crosstalk. User-facing prompts support en/ko.
allowed-tools: Bash, AskUserQuestion
argument-hint: (인자 없음)
---

# Crosstalk Launch — cmux 환경 한방 셋업

이 명령은 **호출 위치에 따라 다르게 동작**한다:

- **cmux 외부에서 호출** (Ghostty, Terminal.app, Warp 등): cmux 앱만 띄우고 안내 (cmux 안에서 다시 `/crosstalk:launch` 실행하라)
- **cmux 안에서 호출**: 현재 워크스페이스에 split 추가 + AI CLI 자동 시작 + 라벨링

이유: cmux의 분할/통신 API는 cmux 안에서 실행되는 셸에서만 접근 가능 (`cmux ping`이 외부에선 broken pipe 반환).

## 전제 조건

- macOS (cmux는 macOS 전용)
- cmux 설치됨 (`brew install --cask cmux`)
- `/crosstalk:install` 1회 실행 완료
- AI CLI들이 설치되고 인증됨 (claude/codex/antigravity 중 사용할 것들)

---

## 1단계: cmux 안에서 실행 중인지 확인

```bash
CONFIG=~/.claude/crosstalk/config.json
LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac

if ! which cmux >/dev/null; then
  [ "$LANGUAGE" = "ko" ] && echo "❌ cmux 미설치" || echo "❌ cmux is not installed"
  [ "$LANGUAGE" = "ko" ] && echo "   설치: brew install --cask cmux 또는 https://www.cmux.dev/" || echo "   Install: brew install --cask cmux or https://www.cmux.dev/"
  exit 1
fi

# cmux 소켓 통신 가능 = cmux 안에 있다는 뜻
CMUX_INSIDE=false
if cmux ping >/dev/null 2>&1; then
  CMUX_INSIDE=true
fi
```

## 2단계: cmux 외부에서 호출된 경우 — 띄우기 + 안내만

`CMUX_INSIDE=false`이면:

```bash
ALREADY_RUNNING=false
pgrep -x "cmux" >/dev/null 2>&1 && ALREADY_RUNNING=true

if ! $ALREADY_RUNNING; then
  open -na cmux
  echo "🚀 cmux 앱을 실행 중..."
  sleep 2
fi
```

사용자에게 명확히 안내. `LANGUAGE=en`이면:

```text
ℹ️ /crosstalk:launch must run inside cmux to create splits automatically.

This Claude Code session is currently outside cmux, so Crosstalk can only open the cmux app here.

Next:
  1. Switch to the cmux window
  2. Run claude inside cmux
  3. Run /crosstalk:install once in that Claude session
  4. Run /crosstalk:launch again inside cmux
```

`LANGUAGE=ko`이면:

```
ℹ️ /crosstalk:launch 는 cmux 안에서 실행되어야 자동 셋업이 가능합니다.

지금 이 Claude Code 세션은 cmux 외부에서 돌고 있어,
여기서는 cmux 분할/통신 API에 접근할 수 없습니다.

다음 단계:
  1. 방금 띄운 cmux 창으로 이동
  2. cmux 안에서 claude 실행
  3. 그 claude에서 /crosstalk:install 한 번
  4. 그 다음 /crosstalk:launch 다시 호출
     → 자동으로 split + Codex/Antigravity 시작 + 라벨링까지 완료됨
```

이 단계에서 종료. **외부에서는 cmux를 띄우는 것 외에 자동 셋업 불가**.

---

## 3단계: cmux 안에서 호출된 경우 — 진짜 셋업

`CMUX_INSIDE=true`이면 본격 진행.

### 3-1. 본인 위치 식별

```bash
IDENTITY=$(cmux identify 2>/dev/null)
SELF_WS=$(echo "$IDENTITY" | awk '/"caller"/{f=1} f && /"workspace_ref"/{print; exit}' | sed 's/.*: "//; s/".*//')
SELF_SURFACE=$(echo "$IDENTITY" | awk '/"caller"/{f=1} f && /"surface_ref"/{print; exit}' | sed 's/.*: "//; s/".*//')

if [ -z "$SELF_WS" ] || [ -z "$SELF_SURFACE" ]; then
  echo "❌ 본인 cmux 위치를 식별할 수 없습니다 (cmux identify 실패)."
  exit 1
fi
```

### 3-2. 각 CLI 설치 확인

```bash
HAS_CLAUDE=$(which claude >/dev/null && echo true || echo false)
HAS_CODEX=$(which codex >/dev/null && echo true || echo false)
HAS_AGY=$(which agy >/dev/null && echo true || echo false)   # antigravity 바이너리
```

설치 안 된 CLI는 옵션에서 제외.

### 3-3. 본인 정체 식별 (이미 떠있는 CLI 재실행 방지)

```bash
SELF_KIND=$(~/.claude/scripts/crosstalk_bridge.sh detect "$SELF_SURFACE")
# claude / codex / antigravity / shell / unknown
```

본인이 이미 AI CLI라면 그 pane엔 다시 명령 안 보냄. 본인 라벨도 자동으로 박아둠.

### 3-4. 사용자에게 구성 선택 — 동적 옵션

`AskUserQuestion`. 문구는 언어별:

- en: header `Launch peers`, question `Choose peer AI CLIs to add to this cmux workspace.`
- ko: header `AI CLI 추가`, question `현재 cmux 워크스페이스에 추가할 AI CLI를 선택하세요.`

옵션은 **본인 + 새로 띄울 상대들** 조합:

본인이 claude인 경우:
- "Codex 추가 (좌:claude, 우:codex)" — 본인 + codex 1개
- "Antigravity 추가 (좌:claude, 우:antigravity)"
- "Codex + Antigravity 추가 (좌:claude, 우상:codex, 우하:antigravity)"
- "취소"

본인이 codex/antigravity/shell이면 본인 종류에 맞춰 옵션 구성. (본인이 unknown이면 *수동으로 라벨 박은 후 재실행* 안내).

설치 안 된 CLI는 옵션에서 자동 제외.

### 3-5. 현재 워크스페이스 surface 목록 기록 (split 전)

```bash
BEFORE=$(cmux list-pane-surfaces --workspace "$SELF_WS" 2>/dev/null \
  | awk '/surface:/ {gsub("[*]",""); print $1}' | sort)
```

### 3-6. 우측에 split 추가

```bash
cmux new-split right --surface "$SELF_SURFACE" --focus false
sleep 0.5
```

### 3-7. 새로 생긴 surface 식별

```bash
AFTER=$(cmux list-pane-surfaces --workspace "$SELF_WS" 2>/dev/null \
  | awk '/surface:/ {gsub("[*]",""); print $1}' | sort)
NEW_SURFACE_1=$(comm -13 <(echo "$BEFORE") <(echo "$AFTER") | head -1)

if [ -z "$NEW_SURFACE_1" ]; then
  echo "❌ Split 생성에 실패했습니다."
  exit 1
fi
```

### 3-8. 3분할이면 우측을 다시 아래로 split

```bash
# 사용자가 *2개 추가* 선택했을 때만
BEFORE2=$(echo "$AFTER")
cmux new-split down --surface "$NEW_SURFACE_1" --focus false
sleep 0.5

AFTER2=$(cmux list-pane-surfaces --workspace "$SELF_WS" 2>/dev/null \
  | awk '/surface:/ {gsub("[*]",""); print $1}' | sort)
NEW_SURFACE_2=$(comm -13 <(echo "$BEFORE2") <(echo "$AFTER2") | head -1)

if [ -z "$NEW_SURFACE_2" ]; then
  echo "❌ 두 번째 split 생성에 실패했습니다."
  exit 1
fi
```

### 3-9. 각 새 surface에서 AI CLI 시작

**사용자 선택을 (NEW_SURFACE_n, SURFACE_KIND_n) 매핑으로 명시.** 그래야 "Antigravity만 추가" 같이 단일 추가 케이스에서도 NEW_SURFACE_1=antigravity로 정확히 들어간다. 하드코딩(첫 번째는 무조건 codex) 금지.

선택 → 매핑 규칙 (본인은 이미 떠있는 CLI, 명령 안 보냄):

| 사용자 선택 | NEW_SURFACE_1 | SURFACE_KIND_1 | NEW_SURFACE_2 | SURFACE_KIND_2 |
|------------|---------------|----------------|---------------|----------------|
| Codex만 추가 | (split 1)    | `codex`        | ""            | ""             |
| Antigravity만 추가 | (split 1) | `antigravity` | ""           | ""             |
| Codex + Antigravity 추가 | (split 1) | `codex` | (split 2)   | `antigravity`  |

> **kind ≠ 실행 명령어 주의**: `claude`/`codex`는 kind 이름이 곧 바이너리지만 `antigravity`의 바이너리는 `agy`다. 아래 `kind_to_cmd` 매핑으로 변환해서 띄운다. (`antigravity` → `agy --dangerously-skip-permissions`. 권한 자동승인 플래그가 있어야 file 모드에서 응답 파일을 막힘 없이 쓴다.)

```bash
# kind → 실제 실행 명령어
kind_to_cmd() {
  case "$1" in
    claude)      echo "claude" ;;
    codex)       echo "codex" ;;
    antigravity) echo "agy --dangerously-skip-permissions" ;;
    *)           echo "$1" ;;
  esac
}

# 위 표대로 SURFACE_KIND_1 / SURFACE_KIND_2 를 사용자 선택에 맞춰 설정한 뒤:
~/.claude/scripts/crosstalk_bridge.sh send "$NEW_SURFACE_1" "$(kind_to_cmd "$SURFACE_KIND_1")"
sleep 1
if [ -n "$NEW_SURFACE_2" ]; then
  ~/.claude/scripts/crosstalk_bridge.sh send "$NEW_SURFACE_2" "$(kind_to_cmd "$SURFACE_KIND_2")"
  sleep 1
fi

# Antigravity 첫 실행 시 "Do you trust this folder?" 프롬프트가 뜬다 (Yes가 기본 선택).
# Enter 1회로 통과. 이미 신뢰된 폴더면 프롬프트가 안 떠 빈 입력으로 무해(idempotent).
for IDX in 1 2; do
  eval "S=\$NEW_SURFACE_$IDX; K=\$SURFACE_KIND_$IDX"
  if [ -n "$S" ] && [ "$K" = "antigravity" ]; then
    sleep 2
    cmux send-key --surface "$S" enter >/dev/null 2>&1 || true
  fi
done
```

### 3-10. AI CLI 시작 대기 (wait-ready 폴링)

`sleep 15` 고정 대기 대신 `wait-ready`로 각 pane이 실제 입력 가능 상태가 될 때까지 폴링.
**라벨링은 ready 확인 후에 박는다** — ready 전에 라벨이 박히면 detect가 라벨 우선이라 오판 가능.

```bash
# READY_MAX_WAIT=20s, READY_INTERVAL=2s 기본 (필요 시 환경변수 override)
~/.claude/scripts/crosstalk_bridge.sh wait-ready "$NEW_SURFACE_1" "$SURFACE_KIND_1" 2> /tmp/crosstalk_ready_1
RC1=$?

RC2=0
if [ -n "$NEW_SURFACE_2" ]; then
  ~/.claude/scripts/crosstalk_bridge.sh wait-ready "$NEW_SURFACE_2" "$SURFACE_KIND_2" 2> /tmp/crosstalk_ready_2
  RC2=$?
fi
```

분기 (각 pane별로, 사용자 표시 문구는 언어별):
- exit 0 (`STATE: ready`) → 정상. 라벨링 단계로.
- exit 2 (`STATE: auth-needed`) →
  - en: `<kind> needs login/OAuth. Complete auth in that pane, then run /crosstalk:setup.`
  - ko: `<kind> pane이 OAuth/로그인 화면입니다. 인증 후 /crosstalk:setup으로 라벨링하세요.`
- exit 1 (`STATE: timeout`) →
  - en: `<kind> was not ready within 20s. Check the pane or run /crosstalk:setup manually.`
  - ko: `<kind> pane 시작이 20초 내 확인되지 않음. pane을 확인하거나 /crosstalk:setup을 실행하세요.`

사용자에게 진행 상황 (예시 — 실제 kind는 SURFACE_KIND_n 으로 표시):
```
⏳ AI CLI 시작 대기 중...
  본인:        claude (이미 시작됨)
  새 split #1: $SURFACE_KIND_1   ✓ ready (4s)
  새 split #2: $SURFACE_KIND_2   ⚠ auth-needed (OAuth 필요)
```

### 3-11. 라벨 박기 (ready 통과한 pane만)

```bash
# 본인 (이미 떠있는 AI CLI) — 별도 wait-ready 불필요
~/.claude/scripts/crosstalk_bridge.sh label "$SELF_SURFACE" "$SELF_KIND"

# 새 surface들 — wait-ready 0번 통과한 것만 SURFACE_KIND_n 으로 라벨
[ "$RC1" -eq 0 ] && ~/.claude/scripts/crosstalk_bridge.sh label "$NEW_SURFACE_1" "$SURFACE_KIND_1"
[ -n "$NEW_SURFACE_2" ] && [ "$RC2" -eq 0 ] && \
  ~/.claude/scripts/crosstalk_bridge.sh label "$NEW_SURFACE_2" "$SURFACE_KIND_2"
```

### 3-12. 인증 안 된 CLI 감지 (휴리스틱)

```bash
for SURF in "$NEW_SURFACE_1" "$NEW_SURFACE_2"; do
  [ -z "$SURF" ] && continue
  SCREEN=$(~/.claude/scripts/crosstalk_bridge.sh capture "$SURF" | tail -30)
  if echo "$SCREEN" | grep -qiE "sign in|log ?in|authenticate|oauth|enter your token|paste.*url|browser"; then
    KIND=$(~/.claude/scripts/crosstalk_bridge.sh get-label "$SURF")
    echo "⚠️ ${KIND} pane(${SURF})에 인증 화면 감지됨. 직접 인증 후 /crosstalk:setup 으로 라벨 다시 박기 권장."
  fi
done
```

(완벽 감지는 어려움 — 휴리스틱 수준.)

### 3-13. 완료 안내

en:
```text
🎉 Crosstalk workspace ready.

Labeled panes:
  ✅ surface:N → claude (self)
  ✅ surface:N → codex
  ✅ surface:N → antigravity

Next, run in the Claude pane:
  /crosstalk Is 1+1 equal to 2?
  /crosstalk:analyze <topic>      (explicit form)
  /crosstalk:review <PR>          (PR review, advanced)
```

ko:
```text
🎉 Crosstalk 환경 셋업 완료!

워크스페이스: workspace:N (현재 사용 중인 워크스페이스)
  ┌─────────────┬─────────────┐
  │             │   Codex     │
  │   Claude    ├─────────────┤
  │   (현재)    │ Antigravity │
  └─────────────┴─────────────┘

라벨링 완료:
  ✅ surface:N → claude (본인)
  ✅ surface:N → codex
  ✅ surface:N → antigravity

(인증 안 된 CLI 있을 시) ⚠️ 안내 메시지.

다음 단계: 본인 (Claude) pane에서
  /crosstalk 1+1은 2다 동의해?       ← 단독 명령 (권장)
  /crosstalk:analyze <주제>           ← 명시적
  /crosstalk:review <PR번호>          ← PR 리뷰 (advanced)
```

---

## 주의사항

- **외부 호출**: cmux 띄우기만 함. 자동 셋업은 cmux 안에서만 가능.
- **내부 호출**: 현재 워크스페이스에 split이 추가됨. **새 워크스페이스 만들지 않음** (기존 작업 영향 없음).
- 본인 pane은 그대로 유지 — 본인이 이미 claude면 claude 재실행 안 함.
- 본인이 unknown인 경우(셸 등) 자동 셋업 불가 — `/crosstalk:setup`으로 수동 라벨링 후 재실행.
- AI CLI 시작 시간은 시스템에 따라 다름. 15초로 부족하면 사용자가 *완료 후 /crosstalk:setup* 으로 라벨 다시 박기.
- 첫 실행 시 cmux/각 CLI가 OAuth 인증을 요구할 수 있음. 인증 후 `/crosstalk:setup`으로 라벨 다시 박기.
