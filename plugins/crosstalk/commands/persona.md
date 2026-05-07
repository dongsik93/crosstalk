---
description: 토론 페르소나 프리셋 관리 — 전환/생성/편집/삭제. 빌트인 default/senior-junior/critic-builder/triple-perspective + 사용자 커스텀.
allowed-tools: Bash, AskUserQuestion, Read
argument-hint: (인자 없음)
---

# /crosstalk:persona — 토론 페르소나 관리

토론 참여자에게 부여할 캐릭터/시각을 정의하는 페르소나 프리셋을 관리한다.

페르소나 파일은 **역할(moderator / conservative / progressive / critic / builder / 등)**을 정의하고, 토론 시작 시 자동으로 참여자에 매핑된다:
- 사회자(호출자) → `moderator`
- 첫 참여자 → 페르소나 파일의 두 번째 역할
- 두 번째 참여자 → 세 번째 역할

## 1단계: 현재 상태 확인

```bash
CONFIG=~/.claude/crosstalk/config.json
PERSONAS_DIR=~/.claude/crosstalk/personas

if [ ! -d "$PERSONAS_DIR" ]; then
  echo "❌ Crosstalk 셋업이 안 되어 있습니다. /crosstalk:install 먼저 실행."
  exit 1
fi

ACTIVE=$(jq -r '.active_persona // "default"' "$CONFIG" 2>/dev/null || echo "default")
AVAILABLE=$(ls "$PERSONAS_DIR"/*.md 2>/dev/null | xargs -n1 basename | sed 's/\.md$//')
```

## 2단계: 메뉴 (AskUserQuestion)

```
header: 페르소나 관리
question: 현재 active 페르소나: ${ACTIVE}

options:
  - 다른 페르소나로 전환
  - 새 페르소나 만들기 (default 복사 후 편집기 열기)
  - 현재 페르소나 편집 (${ACTIVE})
  - 페르소나 삭제
  - 취소
```

## 3단계: 동작별 처리

### 전환

```bash
jq --arg name "$NEW_NAME" '.active_persona = $name' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
echo "✅ active 페르소나: $NEW_NAME"
```

### 새 페르소나 만들기

```bash
NEW_NAME="<사용자 입력>"
[[ "$NEW_NAME" =~ ^[a-z0-9-]+$ ]] || { echo "❌ 영문 소문자/숫자/하이픈만"; exit 1; }
[ -f "$PERSONAS_DIR/$NEW_NAME.md" ] && { echo "❌ 이미 존재"; exit 1; }

cp "$PERSONAS_DIR/default.md" "$PERSONAS_DIR/$NEW_NAME.md"
${EDITOR:-vi} "$PERSONAS_DIR/$NEW_NAME.md"
echo "✅ 새 페르소나 생성: $NEW_NAME"
```

### 편집

```bash
${EDITOR:-vi} "$PERSONAS_DIR/$ACTIVE.md"
```

### 삭제

```bash
rm "$PERSONAS_DIR/$NAME.md"
if [ "$ACTIVE" = "$NAME" ]; then
  jq '.active_persona = "default"' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
fi
```

## 페르소나 파일 작성 가이드

```markdown
# 페르소나 (이름)

## moderator
사회자 역할 — 양측 의견 종합.

## <역할_이름_1>
첫 참여자에게 매핑될 캐릭터.
- 시각/관점
- 강조점
- 자주 인용할 만한 것

## <역할_이름_2>
두 번째 참여자에게 매핑될 캐릭터.
...
```

- 역할은 `## 이름` 헤더로 구분
- moderator는 항상 첫 번째 역할
- 역할 이름은 자유 (영문 권장)
- 다자 토론(3+) 시 더 많은 역할 정의 가능

## 주의사항

- 빌트인 페르소나 삭제 시 다음 `/crosstalk:install`에서 복원됨
- *역할 매핑*은 자동 — 사용자가 호출하는 cmux 구성에 따라 동적 할당
- 정밀 제어 원하면 페르소나 파일에서 역할 이름을 CLI 종류로(예: `## codex`) 명시 가능
