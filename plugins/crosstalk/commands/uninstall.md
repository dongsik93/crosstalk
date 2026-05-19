---
description: Remove user-level Crosstalk components. User-facing prompts support en/ko.
allowed-tools: Bash, AskUserQuestion
argument-hint: (인자 없음)
---

# Crosstalk Uninstall

`/crosstalk:install`이 사용자 홈에 깔아둔 컴포넌트를 제거.

**제거 대상**:
- `~/.claude/scripts/crosstalk_bridge.sh`
- `~/.claude/commands/crosstalk.md` (단독 명령)
- (v0.5 이후) `~/.codex/skills/crosstalk/`

**제거 안 함**:
- 플러그인 자체 (마켓에서 install된 것) → `/plugin uninstall crosstalk` 사용
- npm 글로벌 패키지 (claude/codex) → 사용자가 직접 `npm uninstall -g`
- antigravity(`agy`) standalone 바이너리 → 사용자가 직접 삭제 (보통 `~/.local/bin/agy`)
- 토론 로그 (`~/Documents/crosstalk/`) → 사용자가 직접
- cmux 자체 → 사용자가 직접

## 1단계: 제거 항목 확인

```bash
CONFIG=~/.claude/crosstalk/config.json
LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac

ITEMS=()
[ -f ~/.claude/scripts/crosstalk_bridge.sh ] && ITEMS+=("~/.claude/scripts/crosstalk_bridge.sh")
[ -f ~/.claude/commands/crosstalk.md ] && ITEMS+=("~/.claude/commands/crosstalk.md")

if [ ${#ITEMS[@]} -eq 0 ]; then
  [ "$LANGUAGE" = "ko" ] && echo "ℹ️ 제거할 Crosstalk 컴포넌트가 없습니다." || echo "ℹ️ No Crosstalk components found."
  exit 0
fi
```

표시:
```
🗑️  다음 항목을 제거합니다:
  - ~/.claude/scripts/crosstalk_bridge.sh
  - ~/.claude/commands/crosstalk.md
```

## 2단계: 사용자 확인

`AskUserQuestion`:
```
en:
header: Confirm removal
question: Remove the listed Crosstalk components? npm packages, cmux, logs, and the marketplace plugin are kept.
options:
  - Remove
  - Cancel

ko:
header: 제거 확인
question: 위 항목을 제거하시겠습니까? (npm 패키지/cmux/플러그인 자체는 유지됩니다)
options:
  - 제거
  - 취소
```

## 3단계: 제거 실행

```bash
rm -f ~/.claude/scripts/crosstalk_bridge.sh
rm -f ~/.claude/commands/crosstalk.md
```

## 4단계: 결과 안내

en:
```text
✅ Crosstalk components removed.

To remove the marketplace plugin itself:
  /plugin uninstall crosstalk

These remain installed unless removed manually:
  - npm packages: claude / codex
  - antigravity (agy): standalone binary (e.g. ~/.local/bin/agy)
  - Codex skill: ~/.codex/skills/crosstalk/
  - cmux
  - logs: ~/Documents/crosstalk/
```

ko:
```text
✅ Crosstalk 컴포넌트 제거 완료.

플러그인 자체를 제거하려면:
  /plugin uninstall crosstalk

다음 항목은 그대로 남아있습니다 (필요시 직접 제거):
  - npm 패키지: claude / codex  (npm uninstall -g)
  - antigravity(agy): standalone 바이너리 직접 삭제 (보통 ~/.local/bin/agy)
  - Codex skill: ~/.codex/skills/crosstalk/
  - cmux: brew uninstall --cask cmux
  - 토론 로그: ~/Documents/crosstalk/  (필요시 rm -rf)
```

## 주의사항

- 이 명령은 사용자 홈에 *Crosstalk가 만든* 파일만 제거. 다른 도구가 만든 파일은 건드리지 않음.
- `~/Documents/crosstalk/` 토론 로그는 의도적으로 보존 (사용자 가치 자료).
- `/plugin uninstall`을 호출하는 게 아니라 `/crosstalk:uninstall`만 실행하면 *마켓 플러그인 + 사용자 컴포넌트* 둘 다 처리하려면 두 명령을 모두 실행해야 함.
