---
description: 토론 룰 프리셋 관리 — 전환/생성/편집/삭제. 빌트인 default/brainstorm/debate + 사용자 커스텀.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: (인자 없음)
---

# /crosstalk:rules — 토론 룰 관리

토론 시 답변 형식, 금지 사항, 분위기를 정의하는 룰 프리셋을 관리한다.

## 1단계: 현재 상태 확인

```bash
CONFIG=~/.claude/crosstalk/config.json
RULES_DIR=~/.claude/crosstalk/rules

if [ ! -d "$RULES_DIR" ]; then
  echo "❌ Crosstalk 셋업이 안 되어 있습니다. /crosstalk:install 먼저 실행."
  exit 1
fi

ACTIVE=$(jq -r '.active_rules // "default"' "$CONFIG" 2>/dev/null || echo "default")
AVAILABLE=$(ls "$RULES_DIR"/*.md 2>/dev/null | xargs -n1 basename | sed 's/\.md$//')
```

## 2단계: 메뉴 표시 (AskUserQuestion)

```
header: 토론 룰 관리
question: 현재 active 룰: ${ACTIVE}

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
echo "✅ active 룰: $NEW_NAME"
```

### 새 룰 만들기

```bash
# 이름 받기 (사용자 입력)
NEW_NAME="<사용자 입력>"

# 검증
[[ "$NEW_NAME" =~ ^[a-z0-9-]+$ ]] || { echo "❌ 영문 소문자/숫자/하이픈만 허용"; exit 1; }
[ -f "$RULES_DIR/$NEW_NAME.md" ] && { echo "❌ 이미 존재"; exit 1; }

# default 복사
cp "$RULES_DIR/default.md" "$RULES_DIR/$NEW_NAME.md"

# 편집기 열기
${EDITOR:-vi} "$RULES_DIR/$NEW_NAME.md"

echo "✅ 새 룰 생성: $NEW_NAME"
echo "   active로 전환하려면: /crosstalk:rules → 다른 룰로 전환"
```

### 편집

```bash
${EDITOR:-vi} "$RULES_DIR/$ACTIVE.md"
echo "✅ 편집 완료: $ACTIVE"
```

### 삭제

```bash
# AskUserQuestion으로 삭제할 룰 선택 (default는 삭제 불가)

# 빌트인(default/brainstorm/debate)은 삭제 시 *복원 가능* 안내
# active 룰 삭제 시 active를 default로 자동 변경

rm "$RULES_DIR/$NAME.md"
if [ "$ACTIVE" = "$NAME" ]; then
  jq '.active_rules = "default"' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
  echo "ℹ️ active 룰을 default로 변경"
fi
echo "✅ 삭제: $NAME"
```

## 사용자 화면 표시

각 단계 진행 상황 간결하게. cmux 명령 출력은 노출 X.

## 주의사항

- 빌트인 룰(default/brainstorm/debate) 삭제 시 다음 `/crosstalk:install`에서 복원됨
- 룰 파일은 자유 마크다운 — 시스템이 메시지에 본문 그대로 주입
- *시스템 규칙*([AGREE]/[DISAGREE])은 룰 파일과 무관 — 코드가 자동 추가
