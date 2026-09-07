---
description: Show current Crosstalk status, language, rules/personas, and terminal pane labels.
allowed-tools: Bash, Read
argument-hint: (인자 없음)
---

# /crosstalk:status — 현재 셋업 상태

읽기 전용. 현재 Crosstalk 셋업을 한눈에 보여준다.

## 1단계: 정보 수집

```bash
CONFIG=~/.claude/crosstalk/config.json

if [ ! -f "$CONFIG" ]; then
  echo "❌ Crosstalk is not installed. Run /crosstalk:install first."
  exit 1
fi

LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac

# 자가치유 — 디렉토리 비어있으면 마켓 캐시에서 자동 보충
~/.claude/scripts/crosstalk_bridge.sh ensure-presets "$LANGUAGE" >/dev/null 2>&1 || true

RULES_DIR=~/.claude/crosstalk/rules/${LANGUAGE}
PERSONAS_DIR=~/.claude/crosstalk/personas/${LANGUAGE}
ACTIVE_RULES=$(jq -r '.active_rules // "default"' "$CONFIG")
ACTIVE_PERSONA=$(jq -r '.active_persona // "default"' "$CONFIG")

AVAILABLE_RULES=$(ls "$RULES_DIR"/*.md 2>/dev/null | xargs -n1 basename | sed 's/\.md$//')
AVAILABLE_PERSONAS=$(ls "$PERSONAS_DIR"/*.md 2>/dev/null | xargs -n1 basename | sed 's/\.md$//')
```

각 룰/페르소나 본문에서 첫 번째 `## 1.` 또는 첫 단락을 한 줄 요약으로 추출 (선택 사항).

## 2단계: terminal 상태 (Ghostty 또는 cmux)

```bash
if ~/.claude/scripts/crosstalk_bridge.sh self >/dev/null 2>&1; then
  PEERS=$(~/.claude/scripts/crosstalk_bridge.sh list-peers 2>/dev/null)
fi
```

## 3단계: 사용자에게 표시

`LANGUAGE=en`:
```text
Crosstalk status

[Current setup]
  interface language: English
  active rules:      ${ACTIVE_RULES}
  active persona:    ${ACTIVE_PERSONA}

[Available rules]
  ✅ ${ACTIVE_RULES} (current)
  - default
  - brainstorm
  - debate
  - <custom presets>

[Available personas]
  ✅ ${ACTIVE_PERSONA} (current)
  - default
  - senior-junior
  - critic-builder
  - triple-perspective

[terminal panes]
  surface:1 → claude (self)
  surface:4 → codex
  or "caller terminal not identified"

[Start]
  /crosstalk <topic>
  /crosstalk --rules brainstorm <topic>
  /crosstalk --persona senior-junior <topic>
  $crosstalk <topic>   (Codex caller, experimental)
```

`LANGUAGE=ko`:
```text
🎭 Crosstalk 상태

[현재 셋업]
  인터페이스 언어: 한국어
  active 룰:      ${ACTIVE_RULES}
  active 페르소나: ${ACTIVE_PERSONA}

[사용 가능한 룰]
  ✅ ${ACTIVE_RULES} (현재)
  - default     — 자연스러운 흐름, 안전 모드, 건전 토론
  - brainstorm  — 짧고 빠르게, 합의 우선, Yes-and
  - debate      — 깊이있게, 데빌즈 어드보킷, 합의 신중
  - <사용자 커스텀들>

[사용 가능한 페르소나]
  ✅ ${ACTIVE_PERSONA} (현재)
  - default              — 페르소나 없음, 본연의 시각
  - senior-junior        — 시니어 vs 주니어 (보수 vs 진보)
  - critic-builder       — 비판가 vs 빌더
  - triple-perspective   — 보수/혁신/실용 (3분할 전용)

[terminal pane 상태]              ← terminal 식별 가능 시
  surface:1 → claude (self)
  surface:4 → codex
  (또는 "terminal을 식별할 수 없음" 안내)

[관리 명령]
  /crosstalk:rules    — 룰 전환/생성/편집
  /crosstalk:persona  — 페르소나 전환/생성/편집

[토론 시작]
  /crosstalk <주제>                              현재 셋업으로
  /crosstalk --rules brainstorm <주제>            룰 일회성
  /crosstalk --persona senior-junior <주제>       페르소나 일회성
  /crosstalk --rules debate --persona critic-builder <주제>   둘 다
  $crosstalk <주제>                               Codex caller (experimental)
```

cmux 명령 raw 출력은 노출 X. 깔끔한 요약만.

## 주의사항

- 읽기 전용 — 이 명령은 설정을 변경하지 않음
- 언어별 프리셋 디렉토리(`rules/${LANGUAGE}`, `personas/${LANGUAGE}`)를 기준으로 표시
- terminal 식별 불가 시 terminal pane 상태 섹션은 *외부에서 호출됨*으로 표시
