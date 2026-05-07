---
description: Label cmux panes for Crosstalk detection. User-facing prompts support en/ko.
allowed-tools: Bash, AskUserQuestion
argument-hint: (인자 없음)
---

# Crosstalk Setup — cmux 라벨링

`/crosstalk:debate`, `:review`가 옆 pane의 CLI 종류를 빠르고 정확하게 식별하도록 cmux 탭에 라벨(`ct-claude`, `ct-codex`, `ct-gemini`, `ct-shell`)을 박는다.

## 왜 필요한가

화면 푸터 패턴 매칭은 폴백이지만 한계 있음:
- CLI 버전 업그레이드 시 푸터 디자인 바뀌면 깨짐
- 셸 등 *CLI 아닌 pane*은 unknown으로만 분류
- 화면 본문에 다른 CLI 시그니처 텍스트가 섞이면 self-match 위험

해결: cmux 탭 이름에 `ct-<kind>` 라벨을 박고, detect는 라벨 우선 → 폴백으로 푸터 매칭.

## 동작

1. 모든 cmux pane 스캔
2. 라벨 이미 있으면 그대로 신뢰
3. 라벨 없는 surface:
   - 푸터 패턴으로 자동 감지 → 성공 시 라벨 박기
   - 실패(unknown) → 사용자에게 수동 선택
4. self surface도 라벨 박기 (claude로)

## 1단계: 환경 스캔

```bash
CONFIG=~/.claude/crosstalk/config.json
LANGUAGE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac

~/.claude/scripts/crosstalk_bridge.sh list-all
```

출력: `<surface>\t<kind>\t<self|peer>` 라인.

## 2단계: 분류

각 surface를 다음 4그룹으로:
- **A. 라벨 있음**: 그대로 유지
- **B. 자동 감지됨 (claude/codex/gemini)**: 자동 라벨링
- **C. 자동 감지 안 됨 (unknown)**: 사용자 수동 선택
- **D. self surface**: 본인 = claude로 자동 라벨

## 3단계: 사용자 수동 선택 (C 그룹)

각 unknown surface마다 `AskUserQuestion`. `LANGUAGE=en`:

```
header: Label <surface_ref>
question: Screen preview from <surface_ref>:
<first 5-10 lines>

Which process is running here?
options:
  - Claude Code
  - Codex
  - Gemini
  - Shell / Other
  - Skip
```

`LANGUAGE=ko`:

```
header: <surface_ref> 라벨링
question: <surface_ref> 의 화면 일부 미리보기:
<read-screen 처음 5~10줄>

여기엔 어떤 CLI/프로세스가 떠있나요?
options:
  - Claude Code
  - Codex
  - Gemini
  - 일반 셸 / 기타 (토론 후보 제외)
  - 건너뛰기
```

답변에 따라:
- Claude Code → `~/.claude/scripts/crosstalk_bridge.sh label <surface> claude`
- Codex → `... label <surface> codex`
- Gemini → `... label <surface> gemini`
- 일반 셸 → `... label <surface> shell`
- 건너뛰기 → 라벨링 안 함

## 4단계: self surface 라벨링

```bash
SELF=$(~/.claude/scripts/crosstalk_bridge.sh list-all | awk -F'\t' '$3=="self" {print $1; exit}')
~/.claude/scripts/crosstalk_bridge.sh label "$SELF" claude
```

## 5단계: 결과 표시

`LANGUAGE=en`:
```
━━━ /crosstalk:setup complete ━━━

Labeled panes:
  surface:1  → claude (self)
  surface:5  → gemini
  surface:8  → codex

You can now run:
  /crosstalk <topic>
  /crosstalk:debate <topic>
  /crosstalk:review [PR]
```

`LANGUAGE=ko`:
```
━━━ /crosstalk:setup 완료 ━━━

라벨링된 cmux pane:
  surface:1  → claude (self)
  surface:5  → gemini
  surface:8  → codex

이제 다음 명령을 사용할 수 있습니다:
  /crosstalk <주제>           — 단독 토론 (install 이후)
  /crosstalk:debate <주제>    — 일반 토론
  /crosstalk:review [PR번호]  — PR 리뷰 토론

cmux pane 구성을 바꾸면 다시 /crosstalk:setup 을 실행하세요.
```

남은 unknown / 건너뛴 surface 있으면 경고:
```
⚠️ 다음 surface는 라벨링되지 않았습니다 — /crosstalk 후보에서 제외:
  surface:N
```

## 주의사항

- 라벨은 cmux 세션 라이프사이클 동안만 유효. cmux 재시작 시 사라짐 → 다시 셋업 필요.
- 같은 surface에 다른 용도의 탭 이름이 있으면 덮어쓰여집니다.
- bridge 호출 실패 즉시 사용자에게 보고 + 종료.

## 사용자 화면 표시 형식

각 단계마다 진행 상황을 간결하게:
```
🔍 cmux pane 스캔 중...
   3개 발견: surface:1, surface:5, surface:8

[자동 감지]
  surface:1 → claude (self) ✓
  surface:5 → gemini ✓

[수동 확인 필요]
  surface:8 → 자동 감지 실패. 사용자에게 질문...
```

cmux 명령 결과/raw 출력은 노출 금지. 진행 상황 + 결과만.
