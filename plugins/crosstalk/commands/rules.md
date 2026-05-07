---
description: Manage debate rule presets for the selected interface language.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: (인자 없음)
---

# /crosstalk:rules — 토론 룰 관리

토론 시 답변 형식, 금지 사항, 분위기를 정의하는 룰 프리셋을 관리한다.

## 1단계: 현재 상태 확인

```bash
CONFIG=~/.claude/crosstalk/config.json
LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac

# 자가치유 — 빈 디렉토리면 마켓 캐시에서 빌트인 룰 자동 보충
~/.claude/scripts/crosstalk_bridge.sh ensure-presets "$LANGUAGE" >/dev/null 2>&1 || true

RULES_DIR=~/.claude/crosstalk/rules/${LANGUAGE}

if [ ! -d "$RULES_DIR" ] || [ -z "$(ls -A "$RULES_DIR" 2>/dev/null)" ]; then
  [ "$LANGUAGE" = "ko" ] && echo "❌ 룰 프리셋을 찾지 못했습니다. /crosstalk:install 또는 /crosstalk:install --presets-only 실행." || echo "❌ No rule presets found. Run /crosstalk:install or /crosstalk:install --presets-only."
  exit 1
fi

ACTIVE=$(jq -r '.active_rules // "default"' "$CONFIG" 2>/dev/null || echo "default")
AVAILABLE=$(ls "$RULES_DIR"/*.md 2>/dev/null | xargs -n1 basename | sed 's/\.md$//')
```

## 2단계: 메뉴 표시 (AskUserQuestion)

```
en:
header: Rules
question: Current active rules preset: ${ACTIVE} (language: ${LANGUAGE})
options:
  - Switch rules
  - Create new rules preset
  - Edit current rules (${ACTIVE})
  - Delete rules
  - Cancel

ko:
header: 토론 룰 관리
question: 현재 active 룰: ${ACTIVE} (언어: ${LANGUAGE})

options:
  - 다른 룰로 전환
  - 새 룰 만들기 (default 복사 후 편집기 열기)
  - 현재 룰 편집 (${ACTIVE})
  - 룰 삭제
  - 취소
```

## 3단계: 동작별 처리

### 전환

다시 `AskUserQuestion`으로 전환할 룰 선택 (사용 가능한 룰 목록 동적 구성, 현재 active는 표시만 X):

```bash
# 선택 후
jq --arg name "$NEW_NAME" '.active_rules = $name' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
[ "$LANGUAGE" = "ko" ] && echo "✅ active 룰: $NEW_NAME" || echo "✅ Active rules: $NEW_NAME"
```

### 새 룰 만들기

```bash
# 이름 받기 (사용자 입력)
NEW_NAME="<사용자 입력>"

# 검증
[[ "$NEW_NAME" =~ ^[a-z0-9-]+$ ]] || { [ "$LANGUAGE" = "ko" ] && echo "❌ 영문 소문자/숫자/하이픈만 허용" || echo "❌ Use lowercase letters, numbers, and hyphens only"; exit 1; }
[ -f "$RULES_DIR/$NEW_NAME.md" ] && { [ "$LANGUAGE" = "ko" ] && echo "❌ 이미 존재" || echo "❌ Already exists"; exit 1; }

# default 복사
cp "$RULES_DIR/default.md" "$RULES_DIR/$NEW_NAME.md"

# 편집기 열기
${EDITOR:-vi} "$RULES_DIR/$NEW_NAME.md"

[ "$LANGUAGE" = "ko" ] && echo "✅ 새 룰 생성: $NEW_NAME" || echo "✅ Created rules preset: $NEW_NAME"
[ "$LANGUAGE" = "ko" ] && echo "   active로 전환하려면: /crosstalk:rules → 다른 룰로 전환" || echo "   To activate it: /crosstalk:rules → Switch rules"
```

### 편집

```bash
${EDITOR:-vi} "$RULES_DIR/$ACTIVE.md"
[ "$LANGUAGE" = "ko" ] && echo "✅ 편집 완료: $ACTIVE" || echo "✅ Edited: $ACTIVE"
```

### 삭제

```bash
# AskUserQuestion으로 삭제할 룰 선택 (default는 삭제 불가)

# 빌트인(default/brainstorm/debate)은 삭제 시 *복원 가능* 안내
# active 룰 삭제 시 active를 default로 자동 변경

rm "$RULES_DIR/$NAME.md"
if [ "$ACTIVE" = "$NAME" ]; then
  jq '.active_rules = "default"' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
  [ "$LANGUAGE" = "ko" ] && echo "ℹ️ active 룰을 default로 변경" || echo "ℹ️ Active rules reset to default"
fi
[ "$LANGUAGE" = "ko" ] && echo "✅ 삭제: $NAME" || echo "✅ Deleted: $NAME"
```

## 사용자 화면 표시

각 단계 진행 상황 간결하게. cmux 명령 출력은 노출 X.

## 주의사항

- 현재 인터페이스 언어의 디렉토리(`~/.claude/crosstalk/rules/${LANGUAGE}`)만 관리
- 빌트인 룰(default/brainstorm/debate) 삭제 시 다음 `/crosstalk:install`에서 복원됨
- 룰 파일은 자유 마크다운 — 시스템이 메시지에 본문 그대로 주입
- *시스템 규칙*([AGREE]/[DISAGREE])은 룰 파일과 무관 — 코드가 자동 추가
