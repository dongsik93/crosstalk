---
description: Crosstalk single entrypoint. Runs analyze on a topic, or shows a readiness doctor when called with no arguments. Inline-handles missing setup.
allowed-tools: Bash, AskUserQuestion
argument-hint: <분석 주제>
---

# /crosstalk (단일 entrypoint)

`/crosstalk <주제>` 한 줄로 끝나는 게 목표. 준비가 안 돼 있으면 *그 자리에서* 안내하고, 사용자는 토픽을 다시 입력하지 않는다.

준비가 부족할 때도 사용자를 다른 명령으로 돌려보내지 마라 — 이 명령 안에서 다음 한 행동만 보여준다.

## 동작

### 1) 인자 없음 → readiness doctor

현재 설치/cmux/peer 상태를 한 번에 점검해서 *한 줄*로 보여준다. 정적 usage 출력 금지.

```bash
LANGUAGE=$(~/.claude/scripts/crosstalk_bridge.sh get-language 2>/dev/null || echo en)

# bridge 설치 여부
[ -x "$HOME/.claude/scripts/crosstalk_bridge.sh" ] && INSTALLED="OK" || INSTALLED="missing"

# cmux 안인지
if [ "$INSTALLED" = "OK" ] && cmux identify >/dev/null 2>&1; then
  CMUX="inside"
else
  CMUX="outside"
fi

# peer 감지
if [ "$CMUX" = "inside" ]; then
  # awk 표현식은 single-quote로 감싸 셸 치환 방지 ($2는 awk 필드).
  PEERS=$(~/.claude/scripts/crosstalk_bridge.sh list-peers 2>/dev/null \
    | awk -F'\t' '$2 ~ /^(claude|codex|gemini)$/' \
    | wc -l | tr -d ' ')
else
  PEERS="?"
fi
```

언어별 출력 (KO 기준, EN은 동일 구조):

```
Crosstalk — readiness

  installed:  $INSTALLED
  cmux:       $CMUX
  peers:      $PEERS detected

다음 한 행동:
  $NEXT_HINT
```

`NEXT_HINT` 결정 로직:

| installed | cmux | peers | NEXT_HINT |
|-----------|------|-------|-----------|
| missing   | -    | -     | `/crosstalk <주제>` 입력 → 자동으로 install 진행 후 토론 시작 |
| OK        | outside | - | `/crosstalk <주제>` 입력 → cmux 자동 실행 + 토픽 보존 |
| OK        | inside  | 0 | `/crosstalk <주제>` 입력 → peer 자동 launch 후 토론 시작 |
| OK        | inside  | ≥1 | `/crosstalk <주제>` 입력 → 즉시 토론 시작 |

핵심: 어느 상태든 사용자가 다음에 칠 명령은 *항상 같은 하나* — `/crosstalk <주제>`.

### 2) 인자 있음 → 단일 happy path

`$ARGUMENTS` = `TOPIC`.

흐름:

1. **readiness 체크** (위와 동일 — 빠르게 한 번)
2. **준비 미완료면 인라인 처리**:
   - `installed=missing` → `/crosstalk:install` 본문을 *지금 실행*. 사용자에게 "1회 설치가 필요합니다. 계속할까요?" AskUserQuestion. 거부 시 종료.
   - `cmux=outside` → topic 보존 + cmux 진입 안내:
     ```bash
     ~/.claude/scripts/crosstalk_bridge.sh pending-save "$TOPIC"
     ```
     ```
     ⚠️  cmux 워크스페이스 밖입니다. topic을 보존했습니다.
        다음: cmux 안에서 /crosstalk:resume
     ```
     → 종료. 사용자가 cmux 안에서 `/crosstalk:resume` 호출 시 그대로 이어짐.
   - `cmux=inside, peers=0` → `/crosstalk:launch` 본문 실행 (peer 자동 띄우기). 완료 후 자동으로 다음 단계 진행.
3. **준비 완료** → `/crosstalk:analyze` 본문(`commands/analyze.md`)을 실행. `$ARGUMENTS`를 그대로 전달.

> v0.2.5 노트: `/crosstalk:debate`도 여전히 사용 가능하지만, 단일 entrypoint는 analyze로 라우팅한다. v0.3.0에서 debate 명령은 제거되고 analyze가 유일한 흐름이 된다.

### 3) 안내 메시지 원칙

준비 미완료 안내는 다음 형태:

```
⚠️  준비가 필요합니다.

  installed:  missing
  cmux:       outside
  peers:      ?

이번 호출에서 자동 처리:
  → bridge 설치 + 룰/페르소나 프리셋 보충
  → cmux 워크스페이스 시작 안내

토픽은 보존됩니다. 계속할까요?
```

AskUserQuestion으로 [계속 / 취소] 선택. 취소 시 종료, 토픽 분실 안 함 (v0.2.6: pending.json 도입).

## 주의

- 이 파일은 `/crosstalk:install`이 `~/.claude/commands/`로 복사한 사용자 레벨 슬래시 커맨드.
- 플러그인 자체 명령(`/crosstalk:analyze`, `/crosstalk:debate` 등)은 그대로 동작 — 고급 사용자가 명시적으로 부르기 위한 흐름.
- 일반 사용자에게 권장하는 명령은 **이거 하나**. 다른 명령 알 필요 없게 만드는 게 v0.2.5의 목표.
