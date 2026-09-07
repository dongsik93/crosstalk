---
description: Identify and label Ghostty or cmux panes; bind an existing Ghostty caller with --surface <ID>.
allowed-tools: Bash, AskUserQuestion
argument-hint: [--language en|ko] [--surface ghostty:<UUID>]
---

# Crosstalk Setup — 터미널 식별·라벨링 / 언어 전환

먼저 `~/.claude/scripts/crosstalk_bridge.sh backend`로 실제 백엔드를 확인한다. 환경변수 누락이나 self 실패를 cmux 실행 필요로 해석하지 않는다.

Ghostty에서 `--surface ghostty:<UUID>`를 지정하면 현재 CLI의 도구 셸에서 `~/.claude/scripts/crosstalk_bridge.sh bind ghostty:<UUID>`를 실행한다. 이 연결은 현재 CLI 프로세스가 살아 있는 동안 유지된다. 명령을 다른 CLI에서 대신 실행하지 않는다.

Ghostty의 `self`가 같은 디렉터리의 여러 후보를 반환하면 ID와 제목을 보여주고 사용자가 현재 CLI에 해당하는 후보를 고르게 한다. 선택한 ID로 `bind`한 뒤 `list-all`과 라벨링을 계속한다. 포커스나 첫 후보를 임의로 고르지 않는다. 이 경우 cmux 실행이나 CLI 재시작을 요구하지 않는다.

두 가지 용도:

1. **cmux 라벨링** (기본): `/crosstalk:analyze`, `:review`가 옆 pane의 CLI 종류를 빠르고 정확하게 식별하도록 cmux 탭에 라벨(`ct-claude`, `ct-codex`, `ct-antigravity`, `ct-shell`)을 박는다.
2. **언어 전환**: `/crosstalk:setup --language ko` 또는 `--language en` 으로 UI 언어를 즉시 토글. 인자 없이 호출하면 `AskUserQuestion`으로 묻는다. 토글 후엔 라벨링도 그대로 진행.

## 0단계: 옵션 파싱 — `--language`

```bash
ARGS="$ARGUMENTS"
LANG_REQUESTED=""

# --language en|ko
if echo "$ARGS" | grep -qE -- '--language[[:space:]]+(en|ko)\b'; then
  LANG_REQUESTED=$(echo "$ARGS" | sed -E 's/.*--language[[:space:]]+(en|ko).*/\1/')
  ARGS=$(echo "$ARGS" | sed -E 's/--language[[:space:]]+(en|ko)//' | tr -s ' ')
fi

# 단독 'en'/'ko' (인자 1개)도 호환 — 사용자가 '/crosstalk:setup ko'로 친 케이스
if [ -z "$LANG_REQUESTED" ]; then
  case "$(echo "$ARGS" | tr -d '[:space:]')" in
    en|ko) LANG_REQUESTED=$(echo "$ARGS" | tr -d '[:space:]'); ARGS="" ;;
  esac
fi

CONFIG=~/.claude/crosstalk/config.json
CURRENT_LANG=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")

# 언어 변경 요청이 있으면 config 업데이트
if [ -n "$LANG_REQUESTED" ] && [ "$LANG_REQUESTED" != "$CURRENT_LANG" ]; then
  mkdir -p ~/.claude/crosstalk
  if [ -f "$CONFIG" ]; then
    jq --arg lang "$LANG_REQUESTED" '.language = $lang' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
  else
    cat > "$CONFIG" <<EOF
{
  "active_rules": "default",
  "active_persona": "default",
  "language": "$LANG_REQUESTED"
}
EOF
  fi
  CURRENT_LANG="$LANG_REQUESTED"
  [ "$CURRENT_LANG" = "ko" ] && echo "✅ 언어를 한국어(ko)로 변경했습니다." || echo "✅ Language switched to English (en)."
fi

LANGUAGE="$CURRENT_LANG"
case "$LANGUAGE" in en|ko) ;; *) LANGUAGE="en" ;; esac
```

> 언어만 바꾸고 라벨링은 건너뛰고 싶으면 `--language ko --skip-labeling` 같은 식으로 쓸 수 있게 하지 않았다. 라벨링 자체가 빠르고 idempotent하므로 한 번에 처리한다.

## 왜 필요한가

화면 푸터 패턴 매칭은 폴백이지만 한계 있음:
- CLI 버전 업그레이드 시 푸터 디자인 바뀌면 깨짐
- 셸 등 *CLI 아닌 pane*은 unknown으로만 분류
- 화면 본문에 다른 CLI 시그니처 텍스트가 섞이면 self-match 위험

해결: cmux 탭 이름에 `ct-<kind>` 라벨을 박고, detect는 라벨 우선 → 폴백으로 푸터 매칭.

## Ghostty

Use `bridge list-all` and `bridge label` with `ghostty:<UUID>` IDs. Labels are stored separately and do not replace terminal titles. Ghostty has no screen preview API: for an unknown pane show its ID and ask for Claude, Codex, shell, or skip. Do not call capture/read-screen or offer Antigravity on this backend. Newly launched peers are labelled automatically by `bridge ensure-peer`.

## 동작

1. 모든 cmux pane 스캔
2. 라벨 이미 있으면 그대로 신뢰
3. 라벨 없는 surface:
   - 푸터 패턴으로 자동 감지 → 성공 시 라벨 박기
   - 실패(unknown) → 사용자에게 수동 선택
4. self surface도 라벨 박기 (claude로)

## 1단계: 환경 스캔

`LANGUAGE` 는 0단계에서 이미 결정됨.

```bash
~/.claude/scripts/crosstalk_bridge.sh list-all
```

출력: `<surface>\t<kind>\t<self|peer>` 라인.

## 2단계: 분류

각 surface를 다음 4그룹으로:
- **A. 라벨 있음**: 그대로 유지
- **B. 자동 감지됨 (claude/codex/antigravity)**: 자동 라벨링
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
  - Antigravity
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
  - Antigravity
  - 일반 셸 / 기타 (토론 후보 제외)
  - 건너뛰기
```

답변에 따라:
- Claude Code → `~/.claude/scripts/crosstalk_bridge.sh label <surface> claude`
- Codex → `... label <surface> codex`
- Antigravity → `... label <surface> antigravity`
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
  surface:5  → antigravity
  surface:8  → codex

You can now run:
  /crosstalk <topic>
  /crosstalk:analyze <topic>
  /crosstalk:review [PR]
```

`LANGUAGE=ko`:
```
━━━ /crosstalk:setup 완료 ━━━

라벨링된 cmux pane:
  surface:1  → claude (self)
  surface:5  → antigravity
  surface:8  → codex

이제 다음 명령을 사용할 수 있습니다:
  /crosstalk <주제>           — 단일 entrypoint (권장)
  /crosstalk:analyze <주제>   — 명시적 호출
  /crosstalk:review [PR번호]  — PR 리뷰 (advanced)

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
  surface:5 → antigravity ✓

[수동 확인 필요]
  surface:8 → 자동 감지 실패. 사용자에게 질문...
```

cmux 명령 결과/raw 출력은 노출 금지. 진행 상황 + 결과만.
