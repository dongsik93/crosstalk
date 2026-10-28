---
description: Identify and label Ghostty or cmux panes; bind an existing Ghostty caller with --surface <ID>.
allowed-tools: Bash, AskUserQuestion
argument-hint: [--language en|ko] [--surface ghostty:<UUID>]
---

# Crosstalk Setup — 터미널 식별·라벨링 / 언어 전환

먼저 `~/.claude/scripts/crosstalk_bridge.sh backend`로 실제 백엔드를 확인한다. 환경변수 누락이나 self 실패를 cmux 실행 필요로 해석하지 않는다.

Ghostty의 논리 세션은 protocol 2 handshake로 연결한다. `bridge bind`와 라벨은 물리 주소 탐색 자료이며 세션 소유권이 아니다. 아래 Ghostty 절차를 사용하고 cmux 전용 화면 조회로 넘어가지 않는다. 포커스·제목·CLI 종류·cwd로 대상 pane을 추측하지 않는다.

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

CONFIG_ROOT="${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}"
CONFIG="$CONFIG_ROOT/config.json"
CURRENT_LANG=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")

# 언어 변경 요청이 있으면 config 업데이트
if [ -n "$LANG_REQUESTED" ] && [ "$LANG_REQUESTED" != "$CURRENT_LANG" ]; then
  mkdir -p "$CONFIG_ROOT"
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

## Ghostty — protocol 2 handshake

1. `~/.claude/scripts/crosstalk capabilities --json`과 `doctor --offline`을 확인한다. protocol 2와 정상 설치를 요구하고 capabilities의 `mailbox_instructions` 경로를 읽는다. 미이관 DB는 자동 변환하지 않고 업그레이드 절차를 안내한다.
2. `bridge strict-self`로 현재 pane을 확인한다. Claude/agy는 실제 TTY probe를 사용할 수 있다. Codex의 세션 ID만으로 pane 주소가 입증되지는 않는다. 확인 불가 시 Ghostty의 ID/제목/cwd 후보를 표시하고 사용자가 현재 CLI를 선택하게 한다. `--surface`를 이미 지정했다면 그 선택을 사용한다.
3. 선택한 CLI **자신의 도구 셸에서** 정확한 현재 `CROSSTALK_SURFACE_ID`와 공유 `CROSSTALK_CONFIG_DIR`를 명시한다. Codex는 매 tool 호출마다 이 환경을 다시 전달해야 하며 CODEX_THREAD_ID/bridge cache만으로 strict 식별이 되지 않는다. `bridge bind <EXACT_SURFACE>`는 레거시 transport cache일 뿐이다. 이어 신규 논리 참가자를 연결한다. 이미 검증된 현재 binding이 있으면 `session status`로 확인해 재사용하며 매번 새 challenge를 만들지 않는다.

```bash
CT="$HOME/.claude/scripts/crosstalk"
BRIDGE="$HOME/.claude/scripts/crosstalk_bridge.sh"
# SELF is the current execution's exact selected/probed address, never a previous thread cache.
# Repeat in every Codex tool invocation; CONFIG_ROOT is the shared state directory.
export CROSSTALK_CONFIG_DIR="$CONFIG_ROOT" CROSSTALK_SURFACE_ID="$SELF"
# KIND is this actual CLI kind.
"$BRIDGE" bind "$SELF"
CHALLENGE=$("$CT" session challenge --surface "$SELF" --kind "$KIND") || exit 1
NONCE=$(printf '%s' "$CHALLENGE" | jq -er '.challenge') || exit 1
"$CT" session bind --challenge "$NONCE" --kind "$KIND" --protocol 2
```

4. `bridge list-all`로 peer 후보를 보고 사용자가 선택했거나 직접 생성한 정확한 pane만 연결한다. Ghostty는 화면 캡처를 지원하지 않으므로 unknown 종류를 화면 텍스트로 추정하지 않는다. 라벨을 붙여도 아직 ready가 아니다. 각 peer에 `session challenge --surface <EXACT_SURFACE> --kind <KIND> --notify`로 challenge를 전달한다. peer가 자신의 실행 문맥에서 정확한 transport bind와 protocol-2 bind를 수행해야 한다. 같은 `CROSSTALK_CONFIG_DIR`를 전달하고 capabilities의 지시문을 읽게 한다. 다른 CLI가 대신 bind하지 않는다. shell pane에는 보내지 않는다.
5. `session status`에서 두 참가자의 실제 protocol-2 binding을 확인한 뒤만 준비 완료로 표시한다. 알림 제출 성공은 handshake 완료가 아니다. busy/login/approval 상태면 기존 pane을 남기고 완료를 기다린다. 새로운 topic을 먼저 보내거나 중복 pane을 열지 않는다.

Codex를 restart/resume하면 이전 대화에 기억된 pane ID나 상속된 과거 surface 값을 재사용하지 않는다. 현재 target을 다시 선택하고 handshake한 뒤 매 명령에 정확한 주소를 명시한다.

재시작·주소 변경은 신규 참가자 생성과 구분한다. `session status`/history로 기존 논리 세션을 확인하고 사용자에게 실제 인계를 승인받는다. 기존 pane이 살아 있거나 repository 문맥이 바뀌었으면 특히 자동 이전하지 않는다. `session challenge --surface <NEW_SURFACE> --kind <KIND> --session-id <LOGICAL_ID> --expected-generation <CURRENT_GENERATION>`으로 새 challenge를 만들고, 선택된 새 CLI에서 `session rebind --challenge <NONCE> --kind <KIND> --protocol 2 --confirm-transfer`를 실행한다. 이전 lease는 stale이므로 이후 사용자 승인된 recover가 필요하다. nonce/token은 일반 출력이나 로그에 남기지 않는다.

이 절차는 동일 OS 사용자의 정상 CLI 간 오배송을 막는 연결 규약이며 악성 동일 사용자 프로세스를 막는 보안 인증은 아니다. label/cwd 캐시는 기존 대화 소유권을 넘기는 근거가 아니다.

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
