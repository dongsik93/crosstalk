---
description: Crosstalk 컴포넌트(bridge 스크립트, 단독 명령) 설치 + 환경 검증. 미설치 AI CLI(codex/gemini) 자동 설치 안내. 마켓 install 직후 한 번 실행.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: (인자 없음)
---

# Crosstalk Install — 셋업 자동화 (v0.1.0)

마켓에서 플러그인 설치 직후 한 번 실행. 다음을 수행:

1. 사전 도구 검증 (Node.js, npm, cmux, gh)
2. 토론 참여자 CLI 검증 (claude/codex/gemini), 누락 시 npm 자동 설치 안내
3. Crosstalk 컴포넌트 사용자 홈에 복사
   - `~/.claude/scripts/crosstalk_bridge.sh` (cmux 통신 헬퍼)
   - `~/.claude/commands/crosstalk.md` (단독 명령 `/crosstalk` 활성화)
4. 인증 안내 (gh / 각 CLI 첫 실행 시 OAuth)

## v0.1.0 범위

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

# gh
which gh || echo "GH_MISSING"

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

## 3단계: Crosstalk 컴포넌트 설치

플러그인 디렉토리에서 사용자 홈으로 복사. 플러그인 위치 추정:

```bash
# CLAUDE_PLUGIN_ROOT 환경변수 우선
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"

# 없으면 마켓 캐시 디렉토리에서 찾기
if [ -z "$PLUGIN_ROOT" ]; then
  for dir in ~/.claude/plugins/marketplaces/*/plugins/crosstalk; do
    if [ -d "$dir" ]; then
      PLUGIN_ROOT="${dir%/plugins/crosstalk}"
      break
    fi
  done
fi

if [ -z "$PLUGIN_ROOT" ]; then
  echo "ERROR: Crosstalk 플러그인 디렉토리를 찾을 수 없습니다."
  exit 1
fi
```

복사 작업:
```bash
# bridge 스크립트
mkdir -p ~/.claude/scripts
cp "$PLUGIN_ROOT/assets/scripts/crosstalk_bridge.sh" ~/.claude/scripts/
chmod +x ~/.claude/scripts/crosstalk_bridge.sh

# 단독 명령 활성화 (/crosstalk)
cp "$PLUGIN_ROOT/assets/user-commands/crosstalk.md" ~/.claude/commands/
```

각 단계 사용자에게 표시:
```
📦 Crosstalk 컴포넌트 설치 중...
  ✅ ~/.claude/scripts/crosstalk_bridge.sh
  ✅ ~/.claude/commands/crosstalk.md (단독 명령 /crosstalk 활성화)
```

기존 파일이 있으면 덮어쓰기 전 확인:
- 동일 내용 → 그대로
- 다른 내용 → AskUserQuestion: *덮어쓸까요? / 건너뛸까요? / 취소*

## 4단계: 검증

```bash
~/.claude/scripts/crosstalk_bridge.sh 2>&1 | head -1
# → "Usage: ..." 로 시작하면 정상
```

## 5단계: 완료 안내 + 다음 단계

```
✅ Crosstalk v0.1.0 설치 완료!

설치된 항목:
  - ~/.claude/scripts/crosstalk_bridge.sh
  - ~/.claude/commands/crosstalk.md

(npm 자동 설치 진행 시) 추가 설치된 AI CLI:
  - @openai/codex
  - @google/gemini-cli

⚠️ 다음 항목은 사용자가 직접 처리해야 합니다:
  - cmux (미설치 시): brew install --cask cmux
  - gh 인증: gh auth login
  - codex 첫 실행 시 OAuth 인증
  - gemini 첫 실행 시 OAuth 인증

다음 단계:
  /crosstalk:launch    ← cmux 자동 실행 + 분할 + AI CLI 시작 + 라벨링
  또는 직접 cmux 띄우고:
  /crosstalk:setup     ← 라벨링만
  /crosstalk 주제      ← 토론 시작
```

## 주의사항

- 이 명령은 사용자 홈 디렉토리(~/.claude/, ~/.codex/는 v0.2)에 파일을 씁니다.
  Bash 도구 실행 권한 다이얼로그가 한 번 뜰 수 있음. 승인 시 자동 진행.
- 기존 `fight_*` 또는 `crosstalk_*` 파일이 있으면 덮어쓰기 전 사용자 확인.
- npm 글로벌 설치는 시스템에 따라 권한 문제 가능 (sudo 필요한 환경 등). 실패 시 사용자에게 표시.
- v0.2.0에서 추가 예정: Codex Skill 자동 설치 (~/.codex/skills/crosstalk-*/), `/crosstalk:uninstall` 강화.

## 사용자 노출 형식

cmux 명령/raw 출력은 노출 금지. 진행 상황 + 결과만.
