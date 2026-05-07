#!/usr/bin/env bash
# crosstalk_bridge.sh — cmux 기반 AI 토론 헬퍼
#
# 명령:
#   crosstalk_bridge.sh peer                       → 상대 surface ID 자동 감지 (본인 제외, 첫 번째)
#   crosstalk_bridge.sh detect <surface>           → 해당 surface의 CLI 종류 (claude/codex/gemini/shell/unknown)
#                                                  1순위: cmux 탭 라벨 (ct-* 접두사)
#                                                  2순위: 화면 푸터 패턴 매칭
#                                                  3순위: unknown
#   crosstalk_bridge.sh list-peers                 → 본인 제외 모든 surface와 CLI 종류 (탭 구분)
#   crosstalk_bridge.sh list-all                   → 본인 포함 모든 surface (탭 구분, 본인은 self 마킹)
#   crosstalk_bridge.sh label <surface> <kind>     → cmux 탭에 ct-<kind> 라벨 박기 (kind: claude/codex/gemini/shell)
#   crosstalk_bridge.sh get-label <surface>        → 라벨에서 ct-* 부분 추출 (없으면 빈 줄)
#   crosstalk_bridge.sh send <surface> <text>      → 상대에게 텍스트 + Enter 전송 (Gemini/Codex는 Enter 2회)
#   crosstalk_bridge.sh wait <surface> <since-line>  → 새 출력이 안정될 때까지 대기, 새 텍스트 echo
#                                                  사용자 개입 감지 시 stderr에 INTERVENTION 표시
#   crosstalk_bridge.sh capture <surface>          → 현재 화면 텍스트 캡처
#   crosstalk_bridge.sh lines <surface>            → 현재 화면 라인 수
#   crosstalk_bridge.sh prompt-count <surface>     → 화면에 노출된 사용자 프롬프트 개수 (개입 감지용)
#   crosstalk_bridge.sh stop <surface>             → Ctrl+C 전송 (긴급 정지)
#   crosstalk_bridge.sh save <path> <text>         → 토론 로그를 마크다운 파일에 append

set -euo pipefail

# 본인 surface_ref 추출 헬퍼 (caller 블록 내부에서)
self_surface() {
  cmux identify \
    | awk '/"caller"[[:space:]]*:/{flag=1} flag && /"surface_ref"/{print; exit}' \
    | sed 's/.*: "//; s/".*//'
}

CMD="${1:-}"
shift || true

case "$CMD" in
  peer)
    SELF=$(self_surface)
    PEER=""
    for PANE in $(cmux list-panes 2>/dev/null | awk '/pane:/ {gsub("[*]",""); print $1}'); do
      for S in $(cmux list-pane-surfaces --pane "$PANE" 2>/dev/null | awk '/surface:/ {gsub("[*]",""); print $1}'); do
        if [ "$S" != "$SELF" ]; then
          PEER="$S"
          break 2
        fi
      done
    done
    if [ -z "$PEER" ]; then
      echo "ERROR: peer surface not found (split이 안 되어있거나 cmux 안에서 실행되지 않음)" >&2
      exit 1
    fi
    echo "$PEER"
    ;;

  detect)
    # 단일 surface가 어떤 CLI인지 감지
    # 1순위: cmux 탭 라벨 (ct-* 접두사) — /crosstalk:setup으로 박힌 라벨
    # 2순위: 화면 푸터 패턴 매칭 (폴백)
    # 3순위: unknown
    SURFACE="${1:?surface required}"

    # 1순위: 라벨 확인
    LABEL=$("$0" get-label "$SURFACE")
    if [ -n "$LABEL" ]; then
      echo "$LABEL"
      exit 0
    fi

    # 2순위: 푸터 매칭
    FOOTER=$(cmux read-screen --surface "$SURFACE" --lines 80 2>/dev/null | tail -20)
    if echo "$FOOTER" | grep -qE 'GEMINI\.md files|gemini-[0-9]+(\.[0-9]+)?[[:space:]]*\(default\)'; then
      echo "gemini"
    elif echo "$FOOTER" | grep -qE '\bgpt-[0-9]+(\.[0-9]+)?[[:space:]]+default[[:space:]]+·|Token usage: total='; then
      echo "codex"
    elif echo "$FOOTER" | grep -qE '◐ [a-z]+ · /effort|⏵⏵ accept edits on'; then
      echo "claude"
    else
      echo "unknown"
    fi
    ;;

  label)
    # cmux 탭 이름을 ct-<kind> 로 설정
    # kind: claude / codex / gemini / shell
    SURFACE="${1:?surface required}"
    KIND="${2:?kind required (claude/codex/gemini/shell)}"
    case "$KIND" in
      claude|codex|gemini|shell) ;;
      *) echo "ERROR: invalid kind '$KIND' (use claude/codex/gemini/shell)" >&2; exit 1 ;;
    esac
    cmux rename-tab --surface "$SURFACE" "ct-${KIND}" >/dev/null
    echo "OK: $SURFACE → ct-${KIND}"
    ;;

  get-label)
    # 탭 라벨에서 ct-<kind> 의 <kind> 부분만 추출
    # list-pane-surfaces 출력 형식: "* surface:N  <label>  [selected]"
    # 라벨에 "ct-" 접두사 있을 때만 그 뒤 부분 추출, 없으면 빈 줄
    SURFACE="${1:?surface required}"
    # 모든 pane을 돌며 해당 surface 행 찾기 (작은 환경 가정 — pane 몇 개 안 됨)
    LABEL=""
    for PANE in $(cmux list-panes 2>/dev/null | awk '/pane:/ {gsub("[*]",""); print $1}'); do
      LINE=$(cmux list-pane-surfaces --pane "$PANE" 2>/dev/null \
        | sed 's/^\*[[:space:]]*//' \
        | awk -v s="$SURFACE" '$1 == s { $1=""; sub(/^[[:space:]]+/, ""); sub(/[[:space:]]*\[selected\][[:space:]]*$/, ""); print; exit }')
      if [ -n "$LINE" ]; then
        # ct-<kind> 패턴이면 kind만 추출
        case "$LINE" in
          ct-claude*) LABEL="claude" ;;
          ct-codex*)  LABEL="codex" ;;
          ct-gemini*) LABEL="gemini" ;;
          ct-shell*)  LABEL="shell" ;;
        esac
        break
      fi
    done
    echo "$LABEL"
    ;;

  list-all)
    # 본인 포함 모든 surface 나열, 본인은 마지막 컬럼에 self 마킹
    # 출력 형식: <surface>\t<kind>\t<self|peer>
    SELF=$(self_surface)
    for PANE in $(cmux list-panes 2>/dev/null | awk '/pane:/ {gsub("[*]",""); print $1}'); do
      for S in $(cmux list-pane-surfaces --pane "$PANE" 2>/dev/null | awk '/surface:/ {gsub("[*]",""); print $1}'); do
        KIND=$("$0" detect "$S")
        ROLE="peer"
        [ "$S" = "$SELF" ] && ROLE="self"
        printf "%s\t%s\t%s\n" "$S" "$KIND" "$ROLE"
      done
    done
    ;;

  list-peers)
    # 본인 제외한 모든 surface + 감지된 CLI 종류
    # 출력 형식: <surface_ref>\t<cli_name>\n
    SELF=$(self_surface)
    for PANE in $(cmux list-panes 2>/dev/null | awk '/pane:/ {gsub("[*]",""); print $1}'); do
      for S in $(cmux list-pane-surfaces --pane "$PANE" 2>/dev/null | awk '/surface:/ {gsub("[*]",""); print $1}'); do
        if [ "$S" != "$SELF" ]; then
          KIND=$("$0" detect "$S")
          printf "%s\t%s\n" "$S" "$KIND"
        fi
      done
    done
    ;;

  send)
    SURFACE="${1:?surface required}"
    TEXT="${2:?text required}"
    cmux send --surface "$SURFACE" "$TEXT" >/dev/null
    cmux send-key --surface "$SURFACE" enter >/dev/null
    # paste-bracket / 입력 처리 안정화:
    # 긴 텍스트가 한 번에 들어가면 첫 Enter가 텍스트의 일부로 흡수되거나,
    # 입력창이 paste 종료 처리 중이라 첫 Enter가 무시되는 케이스가 있다.
    # → 잠시 기다렸다가 한 번 더 Enter 보내 실제 전송 보장.
    # Gemini/Codex/Claude 모두 발생 가능 (Claude pane이 받는 쪽일 때도 발생).
    KIND=$("$0" detect "$SURFACE")
    case "$KIND" in
      gemini|codex|claude)
        sleep 0.5
        cmux send-key --surface "$SURFACE" enter >/dev/null
        ;;
    esac
    ;;

  capture)
    SURFACE="${1:?surface required}"
    cmux read-screen --surface "$SURFACE" --lines 200 2>/dev/null || true
    ;;

  lines)
    SURFACE="${1:?surface required}"
    cmux read-screen --surface "$SURFACE" --lines 200 2>/dev/null | wc -l | tr -d ' '
    ;;

  prompt-count)
    # 화면에 노출된 사용자 프롬프트 마커 개수 — 사용자 개입 감지에 사용
    # 메시지 1번 보내면 마커 1개 추가되는 게 정상. 그 이상이면 사용자가 끼어든 것.
    SURFACE="${1:?surface required}"
    KIND=$("$0" detect "$SURFACE")
    CONTENT=$(cmux read-screen --surface "$SURFACE" --lines 500 2>/dev/null || echo "")
    case "$KIND" in
      codex)
        # Codex: 답변 시작에 "•" 불릿이 붙음. 그 개수 카운트
        echo "$CONTENT" | grep -c '^•[[:space:]]' || true
        ;;
      claude)
        # Claude: 사용자 입력 라인 앞에 "❯ " (있는 그대로의 라인)
        echo "$CONTENT" | grep -c '^❯[[:space:]]' || true
        ;;
      gemini)
        # Gemini: 사용자 메시지 앞에 "│ > " 또는 "✦" 등 — 가장 일관된 건 ✦ Working… 상태선
        # 답변마다 ✦ 가 하나씩 추가됨
        echo "$CONTENT" | grep -c '✦' || true
        ;;
      *)
        echo 0
        ;;
    esac
    ;;

  wait)
    # 출력이 N초간 변화 없으면 안정된 것으로 간주, 그 사이 새로 추가된 텍스트만 반환
    # 사용자 개입 감지: 보내기 전 prompt-count 와 비교해서 +1 초과면 stderr 에 INTERVENTION 표시
    SURFACE="${1:?surface required}"
    SINCE_LINES="${2:-0}"
    EXPECTED_PROMPTS="${3:-}"   # 선택: 이 시점의 정상 프롬프트 개수 (보낸 직후 +1 한 값)
    STABLE_SECONDS="${STABLE_SECONDS:-4}"
    MAX_WAIT="${MAX_WAIT:-300}"

    PREV_LINES=-1
    STABLE_FOR=0
    ELAPSED=0
    while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
      sleep 2
      ELAPSED=$((ELAPSED + 2))
      CUR_LINES=$(cmux read-screen --surface "$SURFACE" --lines 200 2>/dev/null | wc -l | tr -d ' ')
      if [ "$CUR_LINES" = "$PREV_LINES" ]; then
        STABLE_FOR=$((STABLE_FOR + 2))
        if [ "$STABLE_FOR" -ge "$STABLE_SECONDS" ] && [ "$CUR_LINES" -gt "$SINCE_LINES" ]; then
          break
        fi
      else
        STABLE_FOR=0
      fi
      PREV_LINES="$CUR_LINES"
    done

    # 사용자 개입 감지: 현재 프롬프트 개수가 기대치보다 많으면 경고
    if [ -n "$EXPECTED_PROMPTS" ]; then
      CUR_PROMPTS=$("$0" prompt-count "$SURFACE")
      if [ "$CUR_PROMPTS" -gt "$EXPECTED_PROMPTS" ]; then
        echo "INTERVENTION: prompts=$CUR_PROMPTS expected=$EXPECTED_PROMPTS" >&2
      fi
    fi

    # 새로 추가된 라인만 출력 (since-line 이후)
    cmux read-screen --surface "$SURFACE" --lines 200 2>/dev/null | tail -n +"$((SINCE_LINES + 1))"
    ;;

  save)
    # 토론 로그를 마크다운 파일에 append (디렉토리 없으면 생성)
    PATH_OUT="${1:?path required}"
    TEXT="${2:?text required}"
    mkdir -p "$(dirname "$PATH_OUT")"
    printf '%s\n\n' "$TEXT" >> "$PATH_OUT"
    ;;

  stop)
    SURFACE="${1:?surface required}"
    cmux send-key --surface "$SURFACE" c-c >/dev/null
    ;;

  *)
    echo "Usage: $0 {peer|detect|list-peers|list-all|label|get-label|send|wait|capture|lines|prompt-count|save|stop} [args...]" >&2
    exit 2
    ;;
esac
