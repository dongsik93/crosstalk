---
description: Install Crosstalk components, choose interface language, validate environment, and optionally install missing AI CLIs.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: (인자 없음)
---

# Crosstalk Install — Setup Automation (v0.1.5)

마켓에서 플러그인 설치 직후 한 번 실행. 다음을 수행:

1. 사전 도구 검증 (Node.js, npm, cmux, gh, jq)
2. 토론 참여자 CLI 검증 (claude/codex/gemini), 누락 시 npm 자동 설치 안내
3. 인터페이스 언어 선택 (`en` / `ko`)
4. Crosstalk 컴포넌트 사용자 홈에 복사
   - `~/.claude/scripts/crosstalk_bridge.sh` (cmux 통신 헬퍼)
   - `~/.claude/commands/crosstalk.md` (단독 명령 `/crosstalk` 활성화)
   - `~/.claude/crosstalk/{rules,personas}/*.md` (토론 룰/페르소나 빌트인)
   - `~/.claude/crosstalk/config.json` (active 프리셋 추적)
5. 인증 안내 (gh / 각 CLI 첫 실행 시 OAuth)

## v0.1.5 범위

- ✅ Claude Code 측 컴포넌트 자동 설치
- ✅ AI CLI npm 자동 설치 (claude/codex/gemini)
- ⚠️ Codex Skill 자동 설치는 v0.2.0에서 지원 예정
  - v0.1에서는 사용자가 Codex CLI를 설치해도 *Codex가 사회자가 되는 시나리오*는 미지원
  - Codex pane은 *참여자*로만 동작 (Claude 사회자 토론에 응답)

---

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
which gemini || echo "GEMINI_MISSING"
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
  ❌ gemini 미설치
```

**필수 도구 누락 처리**:
- Node.js / npm 누락 → 자동 설치 불가, 안내만 (Node 공식 사이트 권장)
- cmux 누락 → `brew install --cask cmux` 안내, 설치 진행은 가능 (사용 시 cmux 필요)
- gh 누락 → `brew install gh && gh auth login` 안내, install 자체는 진행
- jq 누락 → `brew install jq` 안내. 룰/페르소나 config 파싱에 필수이므로 install 차단 + 사용자에게 설치 권장 후 재실행 안내

## 2단계: AI CLI 자동 설치 (선택)

claude/codex/gemini 중 누락된 게 있으면 `AskUserQuestion`:

```
header: AI CLI 자동 설치
question: 다음 AI CLI가 미설치입니다. npm으로 자동 설치할까요?
(설치 후 첫 실행 시 OAuth 인증이 필요합니다.)

options (동적 구성):
  - 모두 설치 (codex + gemini)
  - codex만
  - gemini만
  - 건너뛰기 (Crosstalk 컴포넌트만 설치)
  - 취소
```

선택에 따라:
```bash
# claude
npm install -g @anthropic-ai/claude-code@latest

# codex
npm install -g @openai/codex@latest

# gemini
npm install -g @google/gemini-cli@latest
```

각 명령 실행 진행 상황을 사용자에게 표시:
```
📦 npm install 진행 중... (각 1~3분)
  [1/2] @openai/codex@latest 설치 중...
  ✅ @openai/codex 0.128.0
  [2/2] @google/gemini-cli@latest 설치 중...
  ✅ @google/gemini-cli 0.41.2
```

설치 실패 시 사용자에게 표시 + 진행 여부 결정.

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

# bridge 스크립트
cp "$MARKETPLACE_ROOT/assets/scripts/crosstalk_bridge.sh" ~/.claude/scripts/
chmod +x ~/.claude/scripts/crosstalk_bridge.sh

# 단독 명령 활성화 (/crosstalk)
cp "$MARKETPLACE_ROOT/assets/user-commands/crosstalk.md" ~/.claude/commands/

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
✅ Crosstalk v0.1.5 installed!

설치된 항목:
  - ~/.claude/scripts/crosstalk_bridge.sh
  - ~/.claude/commands/crosstalk.md
  - interface language: ${LANGUAGE}

(npm 자동 설치 진행 시) 추가 설치된 AI CLI:
  - @openai/codex
  - @google/gemini-cli

⚠️ Manual next steps when needed:
  - cmux (미설치 시): brew install --cask cmux
  - gh 인증: gh auth login
  - codex 첫 실행 시 OAuth 인증
  - gemini 첫 실행 시 OAuth 인증

Next:
  /crosstalk:launch
  /crosstalk <topic>

Customize rules/personas:
  /crosstalk:status    ← 현재 active 룰/페르소나 확인
  /crosstalk:rules     ← 룰 전환/생성/편집 (default / brainstorm / debate)
  /crosstalk:persona   ← 페르소나 전환/생성/편집
```

## 주의사항

- 이 명령은 사용자 홈 디렉토리(~/.claude/, ~/.codex/는 v0.2)에 파일을 씁니다.
  Bash 도구 실행 권한 다이얼로그가 한 번 뜰 수 있음. 승인 시 자동 진행.
- 기존 `crosstalk_*` 파일이 있으면 덮어쓰기 전 사용자 확인.
- 룰/페르소나 파일은 언어별 디렉토리에 설치. 사용자 편집 우선 — 이미 있으면 덮어쓰지 않음.
- npm 글로벌 설치는 시스템에 따라 권한 문제 가능 (sudo 필요한 환경 등). 실패 시 사용자에게 표시.
- v0.2.0에서 추가 예정: Codex Skill 자동 설치 (~/.codex/skills/crosstalk-*/), `/crosstalk:uninstall` 강화.

## 사용자 노출 형식

cmux 명령/raw 출력은 노출 금지. 진행 상황 + 결과만.
