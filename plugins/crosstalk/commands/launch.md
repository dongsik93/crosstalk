---
description: cmux 안에서 호출하면 현재 워크스페이스에 split을 추가하고 AI CLI를 자동 시작 + 라벨링까지 완료. cmux 외부에서 호출하면 cmux 앱만 띄우고 다음 단계 안내.
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
- AI CLI들이 설치되고 인증됨 (claude/codex/gemini 중 사용할 것들)

---

## 1단계: cmux 안에서 실행 중인지 확인

```bash
if ! which cmux >/dev/null; then
  echo "❌ cmux 미설치"
  echo "   설치: brew install --cask cmux 또는 https://www.cmux.dev/"
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

사용자에게 명확히 안내:

```
ℹ️ /crosstalk:launch 는 cmux 안에서 실행되어야 자동 셋업이 가능합니다.

지금 이 Claude Code 세션은 cmux 외부에서 돌고 있어,
여기서는 cmux 분할/통신 API에 접근할 수 없습니다.

다음 단계:
  1. 방금 띄운 cmux 창으로 이동
  2. cmux 안에서 claude 실행
  3. 그 claude에서 /crosstalk:install 한 번
  4. 그 다음 /crosstalk:launch 다시 호출
     → 자동으로 split + Codex/Gemini 시작 + 라벨링까지 완료됨
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
HAS_GEMINI=$(which gemini >/dev/null && echo true || echo false)
```

설치 안 된 CLI는 옵션에서 제외.

### 3-3. 본인 정체 식별 (이미 떠있는 CLI 재실행 방지)

```bash
SELF_KIND=$(~/.claude/scripts/crosstalk_bridge.sh detect "$SELF_SURFACE")
# claude / codex / gemini / shell / unknown
```

본인이 이미 AI CLI라면 그 pane엔 다시 명령 안 보냄. 본인 라벨도 자동으로 박아둠.

### 3-4. 사용자에게 구성 선택 — 동적 옵션

`AskUserQuestion`. 옵션은 **본인 + 새로 띄울 상대들** 조합:

본인이 claude인 경우:
- "Codex 추가 (좌:claude, 우:codex)" — 본인 + codex 1개
- "Gemini 추가 (좌:claude, 우:gemini)"
- "Codex + Gemini 추가 (좌:claude, 우상:codex, 우하:gemini)"
- "취소"

본인이 codex/gemini/shell이면 본인 종류에 맞춰 옵션 구성. (본인이 unknown이면 *수동으로 라벨 박은 후 재실행* 안내).

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

사용자가 선택한 구성에 따라 매핑하여 명령 전송:

```bash
# 예: 본인=claude, "Codex + Gemini 추가" 선택
~/.claude/scripts/crosstalk_bridge.sh send "$NEW_SURFACE_1" "codex"
sleep 1
~/.claude/scripts/crosstalk_bridge.sh send "$NEW_SURFACE_2" "gemini"
sleep 1
```

본인은 *이미 떠있는 AI CLI*이므로 명령 보내지 않음.

### 3-10. AI CLI 시작 대기

```bash
sleep 15
```

사용자에게 진행 상황:
```
⏳ AI CLI 시작 대기 중 (약 15초)...
  본인:        claude (이미 시작됨)
  새 split #1: codex 시작 중
  새 split #2: gemini 시작 중   (3분할일 때)
```

### 3-11. 라벨 자동 박기

본인 + 새 surface들 모두 라벨링:

```bash
# 본인 (이미 떠있는 AI CLI)
~/.claude/scripts/crosstalk_bridge.sh label "$SELF_SURFACE" "$SELF_KIND"

# 새 surface들 (사용자 선택에 따라)
~/.claude/scripts/crosstalk_bridge.sh label "$NEW_SURFACE_1" codex   # 예시
[ -n "$NEW_SURFACE_2" ] && ~/.claude/scripts/crosstalk_bridge.sh label "$NEW_SURFACE_2" gemini
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

```
🎉 Crosstalk 환경 셋업 완료!

워크스페이스: workspace:N (현재 사용 중인 워크스페이스)
  ┌─────────────┬─────────────┐
  │             │   Codex     │
  │   Claude    ├─────────────┤
  │   (현재)    │   Gemini    │
  └─────────────┴─────────────┘

라벨링 완료:
  ✅ surface:N → claude (본인)
  ✅ surface:N → codex
  ✅ surface:N → gemini

(인증 안 된 CLI 있을 시) ⚠️ 안내 메시지.

다음 단계: 본인 (Claude) pane에서
  /crosstalk 1+1은 2다 동의해?       ← 단독 명령
  /crosstalk:debate <주제>            ← 명시적
  /crosstalk:review <PR번호>          ← PR 리뷰 토론
```

---

## 주의사항

- **외부 호출**: cmux 띄우기만 함. 자동 셋업은 cmux 안에서만 가능.
- **내부 호출**: 현재 워크스페이스에 split이 추가됨. **새 워크스페이스 만들지 않음** (기존 작업 영향 없음).
- 본인 pane은 그대로 유지 — 본인이 이미 claude면 claude 재실행 안 함.
- 본인이 unknown인 경우(셸 등) 자동 셋업 불가 — `/crosstalk:setup`으로 수동 라벨링 후 재실행.
- AI CLI 시작 시간은 시스템에 따라 다름. 15초로 부족하면 사용자가 *완료 후 /crosstalk:setup* 으로 라벨 다시 박기.
- 첫 실행 시 cmux/각 CLI가 OAuth 인증을 요구할 수 있음. 인증 후 `/crosstalk:setup`으로 라벨 다시 박기.
