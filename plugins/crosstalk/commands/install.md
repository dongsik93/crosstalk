---
description: Install Crosstalk components, choose interface language, validate environment, and optionally install missing AI CLIs.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: [--presets-only [--language en|ko]]
---

# Crosstalk Install — Setup Automation

마켓에서 플러그인 설치 직후 한 번 실행. 다음을 수행:

1. 사전 도구 검증 (Node.js, npm, cmux, gh, jq)
2. 토론 참여자 CLI 검증 (claude/codex는 npm, antigravity는 standalone 바이너리 `agy`), 누락 시 안내
3. 인터페이스 언어 선택 (`en` / `ko`)
4. Crosstalk 컴포넌트 사용자 홈에 복사
   - `~/.claude/scripts/crosstalk_bridge.sh` (cmux 통신 헬퍼)
   - `~/.claude/commands/crosstalk.md` (단독 명령 `/crosstalk` 활성화)
   - `~/.claude/crosstalk/{rules,personas}/*.md` (토론 룰/페르소나 빌트인)
   - `~/.claude/crosstalk/config.json` (active 프리셋 추적)
   - `~/.codex/skills/crosstalk/` (Codex caller용 `$crosstalk` skill)
   - `~/.gemini/commands/crosstalk-peer.toml` (Antigravity peer 트리거 핸들러 `/crosstalk-peer`, agy 설치 시)
5. 인증 안내 (gh / 각 CLI 첫 실행 시 OAuth)

## 현재 범위

- ✅ Claude Code 측 컴포넌트 자동 설치
- ✅ Codex caller용 `$crosstalk` skill 설치
- ✅ AI CLI npm 자동 설치 (claude/codex). antigravity(`agy`)는 npm 패키지가 아니라 standalone 바이너리 — 설치 안내만
- ⚠️ Codex caller는 experimental
  - `$crosstalk` skill + bridge callback으로 동작
  - 실제 callback 자동 진행은 cmux/Codex 버전 조합에서 확인 필요
  - Codex CLI가 아직 없어도 skill 파일 설치 자체는 성공해야 함

---

## 0단계: 플랫폼 검증 (게이트)

Crosstalk은 cmux에 의존하므로 macOS에서만 동작한다. 다른 플랫폼이면 즉시 명확히 차단:

```bash
PLATFORM=$(uname -s 2>/dev/null || echo "unknown")
if [ "$PLATFORM" != "Darwin" ]; then
  echo "❌ Crosstalk은 macOS만 지원합니다. (감지된 플랫폼: $PLATFORM)" >&2
  echo "Next: cmux는 macOS-only입니다. 다른 OS에서는 Crosstalk을 사용할 수 없습니다." >&2
  echo "      tmux/zellij 어댑터는 로드맵의 미래 작업 — https://github.com/dongsik93/crosstalk" >&2
  exit 1
fi
```

## 0단계-B: 옵션 파싱 — `--presets-only` 빠른 경로

전체 install 안 돌리고 빌트인 룰/페르소나만 보충하고 싶을 때 사용.

```bash
ARGS="$ARGUMENTS"
PRESETS_ONLY=false
LANG_REQUESTED=""

if echo "$ARGS" | grep -q -- '--presets-only'; then
  PRESETS_ONLY=true
  ARGS=$(echo "$ARGS" | sed 's/--presets-only//' | tr -s ' ')
fi

if echo "$ARGS" | grep -qE -- '--language[[:space:]]+(en|ko)\b'; then
  LANG_REQUESTED=$(echo "$ARGS" | sed -E 's/.*--language[[:space:]]+(en|ko).*/\1/')
fi
```

`PRESETS_ONLY=true` 면 환경 검증 / AI CLI 설치 / 언어 선택 / bridge·command 복사를 모두 건너뛰고 곧장 *프리셋 보충* 단계로 점프:

```bash
if $PRESETS_ONLY; then
  CONFIG=~/.claude/crosstalk/config.json
  if [ -n "$LANG_REQUESTED" ]; then
    TARGET_LANG="$LANG_REQUESTED"
  else
    TARGET_LANG=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
  fi
  case "$TARGET_LANG" in en|ko) ;; *) TARGET_LANG="en" ;; esac

  RESULT=$(~/.claude/scripts/crosstalk_bridge.sh ensure-presets "$TARGET_LANG" 2>&1)
  case "$RESULT" in
    OK)
      echo "✅ Presets refreshed for language: $TARGET_LANG"
      echo "   ~/.claude/crosstalk/rules/${TARGET_LANG}/"
      echo "   ~/.claude/crosstalk/personas/${TARGET_LANG}/"
      ;;
    SKIPPED*)
      echo "⚠️  $RESULT"
      echo "   Marketplace cache not found. Run /plugin install crosstalk@dongsik93/crosstalk first."
      ;;
    *)
      echo "ERROR: $RESULT"
      ;;
  esac
  exit 0
fi
```

> 일반 install (옵션 없이)은 1단계부터 그대로 진행.

## 1단계: 환경 검증

각 도구 검증 + 결과를 사용자에게 표 형태로 표시:

```bash
# Node.js / npm
node --version || echo "NODE_MISSING"
npm --version || echo "NPM_MISSING"

# cmux
which cmux || echo "CMUX_MISSING"
cmux version 2>/dev/null || echo ""

# gh (review 명령에 필요)
which gh || echo "GH_MISSING"

# jq (config.json 파싱에 필요)
which jq || echo "JQ_MISSING"

# AI CLI
which claude || echo "CLAUDE_CLI_MISSING"   # @anthropic-ai/claude-code
which codex || echo "CODEX_MISSING"
which agy || echo "AGY_MISSING"              # antigravity — standalone 바이너리 (npm 아님)
```

표시:
```
🔍 환경 검증 중...

[필수 도구]
  ✅ Node.js v20.x
  ✅ npm 10.x
  ✅ cmux 1.3.1
  ✅ jq 1.7
  ⚠️ gh 미설치 — review 명령 사용 시 필요
       설치: brew install gh && gh auth login

[AI CLI — 토론 참여자]
  ✅ claude (현재 사용 중)
  ❌ codex 미설치
  ❌ antigravity (agy) 미설치
```

**필수 도구 누락 처리**:
- Node.js / npm 누락 → 자동 설치 불가, 안내만 (Node 공식 사이트 권장)
- cmux 누락 → `brew install --cask cmux` 안내, 설치 진행은 가능 (사용 시 cmux 필요)
- gh 누락 → `brew install gh && gh auth login` 안내, install 자체는 진행
- jq 누락 → `brew install jq` 안내. 룰/페르소나 config 파싱에 필수이므로 install 차단 + 사용자에게 설치 권장 후 재실행 안내

## 2단계: AI CLI 설치 (선택)

설치 방식이 둘로 갈린다:
- **claude / codex**: npm 패키지 → 자동 설치 가능.
- **antigravity (`agy`)**: standalone 바이너리 → npm 설치 불가. 자동 설치 대상에서 제외하고, 누락 시 안내만.

**npm 대상(claude/codex) 중 누락**이 있으면 `AskUserQuestion`:

```
header: AI CLI 자동 설치
question: 다음 AI CLI가 미설치입니다. npm으로 자동 설치할까요?
(설치 후 첫 실행 시 OAuth 인증이 필요합니다.)

options (누락된 npm CLI에 맞춰 동적 구성):
  - codex만
  - 건너뛰기 (Crosstalk 컴포넌트만 설치)
  - 취소
```

선택에 따라:
```bash
# claude
npm install -g @anthropic-ai/claude-code@latest

# codex
npm install -g @openai/codex@latest
```

각 명령 실행 진행 상황을 사용자에게 표시:
```
📦 npm install 진행 중... (각 1~3분)
  [1/1] @openai/codex@latest 설치 중...
  ✅ @openai/codex 0.128.0
```

설치 실패 시 사용자에게 표시 + 진행 여부 결정.

**antigravity(`agy`) 누락 시** — npm 설치 없이 안내만 (자동 설치 안 함):
```
ℹ️ Antigravity CLI(agy)가 설치되어 있지 않습니다.
   agy는 npm 패키지가 아닌 standalone 바이너리입니다.
   공식 배포 경로에서 `agy`를 설치한 뒤(보통 ~/.local/bin/agy) 다시 /crosstalk:install 또는 /crosstalk:setup을 실행하세요.
   (agy 없이 claude/codex만으로도 Crosstalk은 동작합니다.)
```

## 3단계: 인터페이스 언어 선택

`AskUserQuestion`:

```
header: Language
question: Choose Crosstalk interface language.

options:
  - English (Recommended)
  - 한국어
```

선택 결과:

```bash
LANGUAGE="en"  # English
# or
LANGUAGE="ko"  # 한국어
```

기존 config가 있고 `.language`가 이미 있으면 업데이트 여부를 묻는다:

```
header: Language
question: Existing Crosstalk config found. Update interface language?
options:
  - Update language
  - Keep existing
```

새 config 또는 업데이트 시:

```bash
CONFIG=~/.claude/crosstalk/config.json
mkdir -p ~/.claude/crosstalk
if [ -f "$CONFIG" ]; then
  jq --arg lang "$LANGUAGE" '.language = $lang | .active_rules //= "default" | .active_persona //= "default"' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
else
  cat > "$CONFIG" <<EOF
{
  "active_rules": "default",
  "active_persona": "default",
  "language": "$LANGUAGE"
}
EOF
fi
```

모든 이후 사용자-facing 출력은 `LANGUAGE`에 따라 `en`/`ko`로 표시한다. 내부 transport 핵심 지시는 영어 고정.

## 4단계: Crosstalk 컴포넌트 설치

마켓플레이스 캐시 디렉토리에서 사용자 홈으로 복사. **레포 root에 `assets/`가 있고, 그 위에 `plugins/crosstalk/`가 있는 구조** (마켓 install이 repo 전체를 보존하기 때문).

```bash
# 마켓플레이스 캐시 디렉토리 찾기
# 구조: ~/.claude/plugins/marketplaces/<marketplace-name>/
#         ├── assets/scripts/crosstalk_bridge.sh
#         ├── assets/user-commands/crosstalk.md
#         ├── assets/rules/{en,ko}/*.md
#         ├── assets/personas/{en,ko}/*.md
#         └── plugins/crosstalk/

MARKETPLACE_ROOT=""

# 1순위: CLAUDE_PLUGIN_ROOT 환경변수가 plugins/crosstalk 를 가리키면 부모의 부모
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/../.." ]; then
  CANDIDATE=$(cd "$CLAUDE_PLUGIN_ROOT/../.." && pwd)
  [ -d "$CANDIDATE/assets/scripts" ] && MARKETPLACE_ROOT="$CANDIDATE"
fi

# 2순위: 마켓 캐시 패턴으로 찾기
if [ -z "$MARKETPLACE_ROOT" ]; then
  for dir in ~/.claude/plugins/marketplaces/*; do
    if [ -d "$dir/assets/scripts" ] && [ -d "$dir/plugins/crosstalk" ]; then
      MARKETPLACE_ROOT="$dir"
      break
    fi
  done
fi

if [ -z "$MARKETPLACE_ROOT" ]; then
  echo "❌ Crosstalk 마켓플레이스 디렉토리를 찾을 수 없습니다."
  echo "   /plugin install crosstalk@dongsik93/crosstalk 으로 플러그인을 먼저 설치해주세요."
  exit 1
fi

echo "📍 마켓플레이스 위치: $MARKETPLACE_ROOT"
```

복사 작업:
```bash
# 사용자 홈 디렉토리들 생성 (없을 수 있음)
mkdir -p ~/.claude/scripts
mkdir -p ~/.claude/commands
mkdir -p ~/.claude/crosstalk/rules/en ~/.claude/crosstalk/rules/ko
mkdir -p ~/.claude/crosstalk/personas/en ~/.claude/crosstalk/personas/ko
mkdir -p ~/.codex/skills/crosstalk

# bridge 스크립트
cp "$MARKETPLACE_ROOT/assets/scripts/crosstalk_bridge.sh" ~/.claude/scripts/
chmod +x ~/.claude/scripts/crosstalk_bridge.sh

# VERSION (bridge가 manifest 작성 시 읽음)
[ -f "$MARKETPLACE_ROOT/VERSION" ] && cp "$MARKETPLACE_ROOT/VERSION" ~/.claude/crosstalk/VERSION

# 단독 명령 활성화 (/crosstalk)
cp "$MARKETPLACE_ROOT/assets/user-commands/crosstalk.md" ~/.claude/commands/

# Codex caller skill 활성화 ($crosstalk)
# 사용자 편집 보존: 이미 있는 파일은 덮어쓰지 않고, 새 파일만 보충.
if [ -d "$MARKETPLACE_ROOT/assets/codex-skills/crosstalk" ]; then
  (cd "$MARKETPLACE_ROOT/assets/codex-skills/crosstalk" && find . -type f) | while read -r rel; do
    src="$MARKETPLACE_ROOT/assets/codex-skills/crosstalk/$rel"
    dst="$HOME/.codex/skills/crosstalk/$rel"
    mkdir -p "$(dirname "$dst")"
    if [ ! -f "$dst" ]; then
      cp "$src" "$dst"
    fi
  done
fi

# Antigravity(agy) peer 슬래시 커맨드 활성화 (/crosstalk-peer)
# agy는 claude/codex와 달리 plain 트리거를 가로채는 상주 규약이 없어서,
# bridge가 antigravity peer에게는 트리거를 '/crosstalk-peer ...' 슬래시 호출로 감싸 보낸다.
# 이 커맨드는 우리가 관리하는 프로토콜이므로(사용자 편집 대상 아님) 항상 최신본으로 덮어쓴다.
# agy가 설치돼 있을 때(~/.gemini 존재)만 설치. 없으면 조용히 건너뜀.
if [ -d "$HOME/.gemini" ] && [ -f "$MARKETPLACE_ROOT/assets/agy-commands/crosstalk-peer.toml" ]; then
  mkdir -p ~/.gemini/commands
  cp "$MARKETPLACE_ROOT/assets/agy-commands/crosstalk-peer.toml" ~/.gemini/commands/
fi

# 빌트인 룰/페르소나 (언어별, 이미 있으면 덮어쓰지 않음 — 사용자 편집 보존)
for lang in en ko; do
  for f in default brainstorm debate; do
    if [ ! -f ~/.claude/crosstalk/rules/${lang}/${f}.md ]; then
      cp "$MARKETPLACE_ROOT/assets/rules/${lang}/${f}.md" ~/.claude/crosstalk/rules/${lang}/
    fi
  done

  for f in default senior-junior critic-builder triple-perspective; do
    if [ ! -f ~/.claude/crosstalk/personas/${lang}/${f}.md ]; then
      cp "$MARKETPLACE_ROOT/assets/personas/${lang}/${f}.md" ~/.claude/crosstalk/personas/${lang}/
    fi
  done
done

# legacy flat preset은 삭제하지 않음. 새 로더는 rules/<language>, personas/<language>를 우선 사용.
```

각 단계 사용자에게 표시:
```
📦 Crosstalk 컴포넌트 설치 중...
  ✅ ~/.claude/scripts/crosstalk_bridge.sh
  ✅ ~/.claude/commands/crosstalk.md (단독 명령 /crosstalk 활성화)
  ✅ ~/.claude/crosstalk/rules/{en,ko}/
  ✅ ~/.claude/crosstalk/personas/{en,ko}/
  ✅ ~/.codex/skills/crosstalk/ (Codex $crosstalk skill)
  ✅ ~/.gemini/commands/crosstalk-peer.toml (Antigravity peer handler, agy 설치 시)
  ✅ ~/.claude/crosstalk/config.json (language + active presets)
```

기존 파일이 있으면 덮어쓰기 전 확인:
- bridge / 단독 명령: 동일 내용이면 그대로, 다르면 사용자에게 물어봄
- 룰/페르소나: 이미 있으면 보존 (사용자 편집 우선) — 새 빌트인만 추가

## 5단계: 검증

```bash
~/.claude/scripts/crosstalk_bridge.sh 2>&1 | head -1
# → "Usage: ..." 로 시작하면 정상
```

## 6단계: 완료 안내 + 다음 단계

```
✅ Crosstalk installed!

설치된 항목:
  - ~/.claude/scripts/crosstalk_bridge.sh
  - ~/.claude/commands/crosstalk.md
  - ~/.codex/skills/crosstalk/SKILL.md
  - interface language: ${LANGUAGE}

(npm 자동 설치 진행 시) 추가 설치된 AI CLI:
  - @openai/codex

⚠️ Manual next steps when needed:
  - cmux (미설치 시): brew install --cask cmux
  - gh 인증: gh auth login
  - codex 첫 실행 시 OAuth 인증
  - antigravity(agy): standalone 바이너리 직접 설치 + 첫 실행 시 trust 프롬프트/OAuth

Next:
  /crosstalk:launch
  /crosstalk <topic>
  $crosstalk <topic>   # Codex caller (experimental)

Customize rules/personas:
  /crosstalk:status    ← 현재 active 룰/페르소나 확인
  /crosstalk:rules     ← 룰 전환/생성/편집 (default / brainstorm / debate)
  /crosstalk:persona   ← 페르소나 전환/생성/편집
```

## 주의사항

- 이 명령은 사용자 홈 디렉토리(`~/.claude/`)에 파일을 씁니다.
  Bash 도구 실행 권한 다이얼로그가 한 번 뜰 수 있음. 승인 시 자동 진행.
- 기존 `crosstalk_*` 파일이 있으면 덮어쓰기 전 사용자 확인.
- 룰/페르소나 파일은 언어별 디렉토리에 설치. 사용자 편집 우선 — 이미 있으면 덮어쓰지 않음.
- npm 글로벌 설치는 시스템에 따라 권한 문제 가능 (sudo 필요한 환경 등). 실패 시 사용자에게 표시.

## 사용자 노출 형식

cmux 명령/raw 출력은 노출 금지. 진행 상황 + 결과만.
