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
#   crosstalk_bridge.sh wait <surface> <since-line>  → [LEGACY/DEPRECATED v0.1.4]
#                                                  화면 캡처 기반 대기. 새 흐름은 wait-turn 사용.
#                                                  외부 호환을 위해 남김. v0.2.0에서 제거 예정.
#   crosstalk_bridge.sh capture <surface>          → 현재 화면 텍스트 캡처
#   crosstalk_bridge.sh lines <surface>            → 현재 화면 라인 수
#   crosstalk_bridge.sh prompt-count <surface>     → [DEPRECATED v0.1.4] 화면 프롬프트 개수 카운트
#                                                  파일 기반 transport 도입으로 더 이상 내부에서 사용하지 않음.
#                                                  외부 호환을 위해 커맨드는 남김. v0.2.0에서 제거 예정.
#   crosstalk_bridge.sh wait-ready <surface> <expected-kind>
#                                                  → 해당 surface의 CLI(<expected-kind>: claude/codex/gemini)가
#                                                  실제로 떠서 입력 가능한 상태가 될 때까지 대기.
#                                                  ※ 라벨은 보지 않고 화면 푸터 패턴만 검사 (라벨이 미리 박혀있어도 무시).
#                                                  stderr 출력:
#                                                    STATE: ready kind=<kind>           (exit 0)
#                                                    STATE: auth-needed kind=<kind>     (exit 2)
#                                                    STATE: timeout kind=<kind>         (exit 1)
#                                                  env: READY_MAX_WAIT(기본 20), READY_INTERVAL(기본 2)
#   crosstalk_bridge.sh stop <surface>             → Ctrl+C 전송 (긴급 정지)
#   crosstalk_bridge.sh save <path> <text>         → 토론 로그를 마크다운 파일에 append
#   crosstalk_bridge.sh get-language               → ~/.claude/crosstalk/config.json 의 language(en/ko) 출력
#   crosstalk_bridge.sh ensure-presets <lang>      → ~/.claude/crosstalk/{rules,personas}/<lang>/ 가 비어있으면
#                                                  마켓플레이스 캐시에서 빌트인 프리셋을 자동 복사 (자가치유).
#                                                  이미 있는 파일은 보존. <lang>: en|ko
#                                                  stdout: 'OK' (정상) | 'SKIPPED reason=...' (마켓 캐시 못 찾음)
#
# v0.1.4 file-based transport:
#   crosstalk_bridge.sh start-run                       → 새 run-id 생성, /tmp/crosstalk/run-<id>/ 디렉토리 + manifest.json 생성
#                                                       stdout: <run-id>
#   crosstalk_bridge.sh make-msg-id <run-id> <round> <agent> <attempt>
#                                                       → run-<id>-r<NN>-<agent>-a<N> 형태의 msg-id 출력
#   crosstalk_bridge.sh wait-turn <surface> <run-id> <msg-id>
#                                                       → 해당 msg-id에 대한 응답 파일이 안정될 때까지 대기
#                                                       상태(clean|soft-complete|protocol-error|timeout) stderr 출력
#                                                       exit 0: clean / soft-complete
#                                                       exit 1: protocol-error / timeout
#   crosstalk_bridge.sh read-response <run-id> <msg-id> → 응답 파일 내용을 stdout에 출력 (MAX_RESPONSE_BYTES 제한)
#                                                       원문 파일은 변경하지 않음. 초과 시 stderr에 WARN 출력

set -euo pipefail

# 본인 surface_ref 추출 헬퍼 (caller 블록 내부에서)
self_surface() {
  cmux identify \
    | awk '/"caller"[[:space:]]*:/{flag=1} flag && /"surface_ref"/{print; exit}' \
    | sed 's/.*: "//; s/".*//'
}

# 화면 텍스트에서 CLI 종류 추정 (푸터 패턴 매칭). detect 와 wait-ready 가 공유.
# 라벨은 보지 않는다 — 호출 측에서 필요하면 별도로 합쳐 쓸 것.
detect_kind_from_screen() {
  local SCREEN="$1"
  if echo "$SCREEN" | grep -qE 'GEMINI\.md files|gemini-[0-9]+(\.[0-9]+)?[[:space:]]*\(default\)'; then
    echo "gemini"
  elif echo "$SCREEN" | grep -qE '\bgpt-[0-9]+(\.[0-9]+)?[[:space:]]+default[[:space:]]+·|Token usage: total='; then
    echo "codex"
  elif echo "$SCREEN" | grep -qE '◐ [a-z]+ · /effort|⏵⏵ accept edits on'; then
    echo "claude"
  else
    echo "unknown"
  fi
}

# 화면 텍스트에서 OAuth/로그인 화면 감지
detect_auth_from_screen() {
  local SCREEN="$1"
  echo "$SCREEN" | grep -qiE 'sign in|log ?in|authenticate|oauth|enter your token|paste.*url|open.*browser|verification code'
}

# ---------- validators ----------
# 모두 OK이면 0, 실패면 stderr에 ERROR 출력 후 비-0.

validate_run_id() {
  # mktemp -d run-XXXXXXXX 가 만든 8자리 영숫자, 또는 외부에서 넘긴 hex/영숫자.
  case "$1" in
    ''|*[!A-Za-z0-9_-]*) echo "ERROR: invalid run-id '$1' (allowed: A-Za-z0-9_-)" >&2; return 1 ;;
  esac
  # 길이 4~32
  local len=${#1}
  if [ "$len" -lt 4 ] || [ "$len" -gt 32 ]; then
    echo "ERROR: invalid run-id length ($len, expected 4..32)" >&2
    return 1
  fi
  return 0
}

validate_positive_int() {
  # 1 이상 정수
  case "$1" in
    ''|*[!0-9]*|0|0*) echo "ERROR: '$2' must be a positive integer (got '$1')" >&2; return 1 ;;
  esac
  return 0
}

validate_nonnegative_int() {
  case "$1" in
    ''|*[!0-9]*) echo "ERROR: '$2' must be a non-negative integer (got '$1')" >&2; return 1 ;;
  esac
  return 0
}

validate_agent() {
  case "$1" in
    claude|codex|gemini) return 0 ;;
    *) echo "ERROR: invalid agent '$1' (expected claude/codex/gemini)" >&2; return 1 ;;
  esac
}

# 마켓플레이스 캐시 root 찾기 (install.md 와 동일 로직 — 자가치유에서 공유).
# 못 찾으면 빈 줄 반환.
find_marketplace_root() {
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/../.." ]; then
    local cand
    cand=$(cd "$CLAUDE_PLUGIN_ROOT/../.." 2>/dev/null && pwd)
    if [ -n "$cand" ] && [ -d "$cand/assets/rules" ] && [ -d "$cand/assets/personas" ]; then
      echo "$cand"; return
    fi
  fi
  for dir in "$HOME"/.claude/plugins/marketplaces/*; do
    [ -d "$dir" ] || continue
    if [ -d "$dir/assets/rules" ] && [ -d "$dir/assets/personas" ] && [ -d "$dir/plugins/crosstalk" ]; then
      echo "$dir"; return
    fi
  done
  echo ""
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

    # 2순위: 푸터 매칭 (헬퍼 사용)
    FOOTER=$(cmux read-screen --surface "$SURFACE" --lines 80 2>/dev/null | tail -20)
    detect_kind_from_screen "$FOOTER"
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
    # → claude/codex 는 잠시 기다렸다가 한 번 더 Enter 보내 실제 전송 보장.
    # ⚠️ Gemini CLI는 두 번째 Enter를 *별도 submit*으로 받아들여 같은 메시지를
    #     여러 번 답하는 사고가 생김. 그래서 gemini는 Enter 1회만.
    #     gemini의 paste-bracket 흡수 사고는 SEND_GEMINI_RETRY=1 환경변수로 1회 재전송 가능.
    KIND=$("$0" detect "$SURFACE")
    case "$KIND" in
      codex|claude)
        sleep 0.5
        cmux send-key --surface "$SURFACE" enter >/dev/null
        ;;
      gemini)
        # 기본은 Enter 1회. SEND_GEMINI_RETRY=1 이면 안전한 1회 더 (paste 흡수 의심 시).
        if [ "${SEND_GEMINI_RETRY:-0}" = "1" ]; then
          sleep 0.8
          cmux send-key --surface "$SURFACE" enter >/dev/null
        fi
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
    # [LEGACY/DEPRECATED v0.1.4] 화면 캡처 기반 대기 — 신규 흐름은 wait-turn 사용.
    # 외부 호환을 위해 잔존. v0.2.0에서 제거 예정. 새 코드는 호출하지 말 것.
    # 출력이 N초간 변화 없으면 안정된 것으로 간주, 그 사이 새로 추가된 텍스트만 반환.
    # INTERVENTION 휴리스틱은 v0.1.4부터 의미가 없음(파일 transport가 진실).
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

  get-language)
    CONFIG="${CROSSTALK_CONFIG:-$HOME/.claude/crosstalk/config.json}"
    LANG_VALUE=$(jq -r '.language // "en"' "$CONFIG" 2>/dev/null || echo "en")
    case "$LANG_VALUE" in
      en|ko) echo "$LANG_VALUE" ;;
      *) echo "en" ;;
    esac
    ;;

  ensure-presets)
    LANG="${1:?language required (en|ko)}"
    case "$LANG" in en|ko) ;; *) echo "ERROR: invalid language '$LANG'" >&2; exit 1 ;; esac

    DEST_RULES="$HOME/.claude/crosstalk/rules/$LANG"
    DEST_PERSONAS="$HOME/.claude/crosstalk/personas/$LANG"
    mkdir -p "$DEST_RULES" "$DEST_PERSONAS"

    # 비어있지 않으면 자가치유 불필요 (사용자 편집 보존). 단, 누락된 빌트인은 보충한다.
    MARKETPLACE_ROOT=$(find_marketplace_root)
    if [ -z "$MARKETPLACE_ROOT" ]; then
      echo "SKIPPED reason=marketplace_cache_not_found"
      # 디렉토리 자체는 만들었으니 호출측이 "디렉토리 비었음" 분기로 빠지진 않게 함
      exit 0
    fi

    SRC_RULES="$MARKETPLACE_ROOT/assets/rules/$LANG"
    SRC_PERSONAS="$MARKETPLACE_ROOT/assets/personas/$LANG"
    if [ ! -d "$SRC_RULES" ] || [ ! -d "$SRC_PERSONAS" ]; then
      echo "SKIPPED reason=marketplace_lang_missing lang=$LANG"
      exit 0
    fi

    # 누락된 빌트인만 복사 (사용자 편집 보존)
    for f in "$SRC_RULES"/*.md; do
      [ -f "$f" ] || continue
      base=$(basename "$f")
      [ -f "$DEST_RULES/$base" ] || cp "$f" "$DEST_RULES/$base"
    done
    for f in "$SRC_PERSONAS"/*.md; do
      [ -f "$f" ] || continue
      base=$(basename "$f")
      [ -f "$DEST_PERSONAS/$base" ] || cp "$f" "$DEST_PERSONAS/$base"
    done

    echo "OK"
    ;;

  wait-ready)
    # 라벨 무시. 화면 푸터 패턴만으로 expected-kind와 일치하는지 확인.
    # 일치 → ready (exit 0). OAuth/로그인 화면 감지 → auth-needed (exit 2). 시간 초과 → timeout (exit 1).
    SURFACE="${1:?surface required}"
    KIND="${2:?expected-kind required (claude/codex/gemini)}"
    validate_agent "$KIND" || exit 1

    READY_MAX_WAIT="${READY_MAX_WAIT:-20}"
    READY_INTERVAL="${READY_INTERVAL:-2}"
    validate_positive_int "$READY_MAX_WAIT" "READY_MAX_WAIT" || exit 1
    validate_positive_int "$READY_INTERVAL" "READY_INTERVAL" || exit 1
    # interval > max 면 한 번만 체크하고 종료 (무한 대기 방지)
    if [ "$READY_INTERVAL" -gt "$READY_MAX_WAIT" ]; then
      READY_INTERVAL="$READY_MAX_WAIT"
    fi
    ELAPSED=0

    while [ "$ELAPSED" -lt "$READY_MAX_WAIT" ]; do
      sleep "$READY_INTERVAL"
      ELAPSED=$((ELAPSED + READY_INTERVAL))
      SCREEN=$(cmux read-screen --surface "$SURFACE" --lines 80 2>/dev/null | tail -20)

      # auth 화면 먼저 (CLI가 아직 푸터 안 띄운 상태에서도 잡아줌)
      if detect_auth_from_screen "$SCREEN"; then
        echo "STATE: auth-needed kind=$KIND" >&2
        exit 2
      fi

      DETECTED=$(detect_kind_from_screen "$SCREEN")
      if [ "$DETECTED" = "$KIND" ]; then
        echo "STATE: ready kind=$KIND" >&2
        exit 0
      fi
    done

    echo "STATE: timeout kind=$KIND" >&2
    exit 1
    ;;

  start-run)
    # mktemp 으로 충돌 없는 디렉토리 생성. 출력은 RUN_ID (run- 접두사 제외).
    CROSSTALK_ROOT="${CROSSTALK_ROOT:-/tmp/crosstalk}"
    mkdir -p "$CROSSTALK_ROOT"
    RUN_DIR=$(mktemp -d "$CROSSTALK_ROOT/run-XXXXXXXX") || {
      echo "ERROR: failed to allocate run dir under $CROSSTALK_ROOT" >&2
      exit 1
    }
    BASENAME=$(basename "$RUN_DIR")     # run-XXXXXXXX
    RID="${BASENAME#run-}"              # XXXXXXXX
    mkdir -p "$RUN_DIR/responses"
    cat > "$RUN_DIR/manifest.json" <<EOF
{
  "run_id": "$RID",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "version": "0.1.6"
}
EOF
    echo "$RID"
    ;;

  make-msg-id)
    # run-<id>-r<NN>-<agent>-a<N>
    RUN_ID="${1:?run-id required}"
    ROUND="${2:?round required}"
    AGENT="${3:?agent required (claude/codex/gemini)}"
    ATTEMPT="${4:?attempt required}"
    validate_run_id "$RUN_ID" || exit 1
    validate_positive_int "$ROUND" "round" || exit 1
    validate_positive_int "$ATTEMPT" "attempt" || exit 1
    validate_agent "$AGENT" || exit 1
    printf 'run-%s-r%02d-%s-a%d\n' "$RUN_ID" "$ROUND" "$AGENT" "$ATTEMPT"
    ;;

  wait-turn)
    # 응답 파일이 안정될 때까지 대기.
    #
    # TRANSPORT_MODE (env):
    #   file (기본)   — AI가 직접 RESP_FILE 에 답변 본문을 쓴다 (claude/codex 권장).
    #   screen        — AI는 화면에 'CROSSTALK_BEGIN <msg-id>' ~ 'CROSSTALK_END <msg-id>' 블록만 출력한다.
    #                   bridge가 매 tick scrollback에서 추출해서 RESP_FILE 에 직접 저장 (gemini 등 agentic CLI용).
    #
    # msg-id 형식: run-<id>-r<NN>-<agent>-a<N>
    # 응답 파일: /tmp/crosstalk/run-<id>/responses/<agent>-r<NN>-a<N>.md
    # 화면 푸터에 'DONE <msg-id>' 마커가 보이면 grace N초 후 파일 확인.
    # 상태:
    #   clean           — DONE 마커 + 파일 존재 + 크기/mtime 안정
    #   soft-complete   — 파일 존재 + 안정 / DONE 마커 없음
    #   protocol-error  — 파일 없음 또는 크기 0 (DONE 후 grace 초과)
    #   timeout         — MAX_WAIT 초과
    # exit code:
    #   clean / soft-complete  → 0
    #   protocol-error / timeout → 1
    SURFACE="${1:?surface required}"
    RUN_ID="${2:?run-id required}"
    MSG_ID="${3:?msg-id required}"

    validate_run_id "$RUN_ID" || exit 1

    TRANSPORT_MODE="${TRANSPORT_MODE:-file}"
    case "$TRANSPORT_MODE" in
      file|screen) ;;
      *) echo "ERROR: invalid TRANSPORT_MODE '$TRANSPORT_MODE' (expected file|screen)" >&2; exit 1 ;;
    esac

    CROSSTALK_ROOT="${CROSSTALK_ROOT:-/tmp/crosstalk}"
    STABLE_SECONDS="${STABLE_SECONDS:-5}"
    MAX_WAIT="${MAX_WAIT:-300}"
    DONE_GRACE="${DONE_GRACE:-5}"
    # 활동 감지: 화면 변화 / 응답 파일 변화가 최근 ACTIVITY_GRACE 초 안에 있으면 살아있다고 간주.
    # MAX_WAIT 초과 직전에 활동이 살아있으면 ACTIVITY_EXTEND_BY 만큼 추가 대기 (최대 ACTIVITY_EXTEND_MAX 회).
    # 0으로 두면 활동 감지 비활성 (기존 동작과 동일).
    ACTIVITY_GRACE="${ACTIVITY_GRACE:-30}"
    ACTIVITY_EXTEND_BY="${ACTIVITY_EXTEND_BY:-60}"
    ACTIVITY_EXTEND_MAX="${ACTIVITY_EXTEND_MAX:-3}"
    validate_positive_int "$STABLE_SECONDS" "STABLE_SECONDS" || exit 1
    validate_positive_int "$MAX_WAIT" "MAX_WAIT" || exit 1
    validate_nonnegative_int "$DONE_GRACE" "DONE_GRACE" || exit 1
    validate_nonnegative_int "$ACTIVITY_GRACE" "ACTIVITY_GRACE" || exit 1
    validate_nonnegative_int "$ACTIVITY_EXTEND_BY" "ACTIVITY_EXTEND_BY" || exit 1
    validate_nonnegative_int "$ACTIVITY_EXTEND_MAX" "ACTIVITY_EXTEND_MAX" || exit 1

    # run dir이 없으면 즉시 에러 (start-run 안 거치고 호출된 경우)
    RUN_DIR="$CROSSTALK_ROOT/run-$RUN_ID"
    if [ ! -d "$RUN_DIR/responses" ]; then
      echo "ERROR: run dir not found: $RUN_DIR (call start-run first)" >&2
      exit 1
    fi

    # msg-id 파싱: run-<rid>-r<NN>-<agent>-a<N>
    # RUN_ID 는 위에서 검증했으니 sed 안에 안전.
    RESP_BASENAME=$(echo "$MSG_ID" | sed -E "s/^run-${RUN_ID}-r([0-9]+)-([a-z]+)-a([0-9]+)$/\\2-r\\1-a\\3.md/")
    if [ "$RESP_BASENAME" = "$MSG_ID" ]; then
      echo "ERROR: malformed msg-id '$MSG_ID' (expected run-<rid>-r<NN>-<agent>-a<N>)" >&2
      exit 1
    fi

    RESP_FILE="$RUN_DIR/responses/$RESP_BASENAME"
    # mkdir 제거: start-run이 이미 responses/ 만들었음. AI가 다른 경로에 쓰면 그게 protocol-error.

    # size+mtime, 단 size==0이면 "없는 것과 동일"하게 취급해 빈 줄 반환.
    # 빈 파일을 안정 상태로 잘못 판정해 clean/soft-complete로 통과시키는 걸 막는다.
    file_stat() {
      [ -f "$1" ] || { echo ""; return; }
      local s
      s=$(stat -f '%z-%m' "$1" 2>/dev/null || stat -c '%s-%Y' "$1" 2>/dev/null || echo "")
      [ -z "$s" ] && { echo ""; return; }
      # size 추출 (앞쪽 숫자)
      case "$s" in
        0-*) echo "" ;;
        *)   echo "$s" ;;
      esac
    }

    PREV_STAT=""
    STABLE_FOR=0
    ELAPSED=0
    DONE_SEEN=0
    DONE_AT=0
    # 활동 감지 상태
    PREV_SCREEN_HASH=""
    LAST_ACTIVITY=0          # 마지막으로 변화 감지된 ELAPSED 값
    EFFECTIVE_MAX="$MAX_WAIT" # extension으로 늘어남
    EXTENSIONS_USED=0

    # 항상 1번은 SCREEN을 읽도록 — DONE 감지와 활동 감지 양쪽에서 사용
    while [ "$ELAPSED" -lt "$EFFECTIVE_MAX" ]; do
      sleep 2
      ELAPSED=$((ELAPSED + 2))

      SCREEN=$(cmux read-screen --surface "$SURFACE" --scrollback --lines 1000 2>/dev/null || echo "")

      # screen 모드: BEGIN/END 블록 추출 후 RESP_FILE 에 저장 (idempotent, 매번 덮어씀).
      # AI는 답변을 화면에만 쓰기 때문에 bridge가 파일 transport 인터페이스를 *대신* 만들어준다.
      if [ "$TRANSPORT_MODE" = "screen" ]; then
        # awk로 마지막 BEGIN/END 쌍을 추출 (가장 최신 답변).
        BLOCK=$(printf '%s\n' "$SCREEN" | awk -v mid="$MSG_ID" '
          $0 ~ "CROSSTALK_BEGIN " mid {capture=1; buf=""; next}
          $0 ~ "CROSSTALK_END " mid {if (capture) {final=buf}; capture=0; next}
          capture {buf = buf $0 "\n"}
          END {if (final) printf "%s", final}
        ')
        if [ -n "$BLOCK" ]; then
          # idempotent 덮어쓰기. 내용 동일하면 mtime만 갱신돼서 안정성 카운터에 영향 적음 → 비교 후 다를 때만 write.
          if [ ! -f "$RESP_FILE" ] || [ "$(cat "$RESP_FILE" 2>/dev/null)" != "$BLOCK" ]; then
            printf '%s' "$BLOCK" > "$RESP_FILE"
          fi
        fi
      fi

      # 화면 푸터에 DONE <msg-id> 마커 확인 — 긴 답변이 위로 밀려도 잡도록 scrollback 1000줄.
      # screen 모드에서는 END 마커가 곧 "답변 끝"이라 DONE 동등 처리.
      if [ "$DONE_SEEN" -eq 0 ]; then
        if echo "$SCREEN" | grep -qF "DONE $MSG_ID"; then
          DONE_SEEN=1
          DONE_AT=$ELAPSED
        elif [ "$TRANSPORT_MODE" = "screen" ] && echo "$SCREEN" | grep -qF "CROSSTALK_END $MSG_ID"; then
          DONE_SEEN=1
          DONE_AT=$ELAPSED
        fi
      fi

      # 활동 감지: 화면 해시 변화 또는 응답 파일 stat 변화
      CUR_STAT=$(file_stat "$RESP_FILE")
      CUR_SCREEN_HASH=$(printf '%s' "$SCREEN" | wc -c | tr -d ' ')
      if [ "$CUR_SCREEN_HASH" != "$PREV_SCREEN_HASH" ] || { [ -n "$CUR_STAT" ] && [ "$CUR_STAT" != "$PREV_STAT" ]; }; then
        LAST_ACTIVITY=$ELAPSED
      fi
      PREV_SCREEN_HASH="$CUR_SCREEN_HASH"

      # 파일 안정성 체크 (size==0 은 file_stat이 빈 줄로 처리)
      if [ -n "$CUR_STAT" ] && [ "$CUR_STAT" = "$PREV_STAT" ]; then
        STABLE_FOR=$((STABLE_FOR + 2))
      else
        STABLE_FOR=0
      fi
      PREV_STAT="$CUR_STAT"

      # MAX_WAIT 도달 직전에 활동 살아있으면 extension 부여
      if [ "$ELAPSED" -ge "$EFFECTIVE_MAX" ] 2>/dev/null; then
        :
      fi
      if [ "$((EFFECTIVE_MAX - ELAPSED))" -le 4 ] && \
         [ "$ACTIVITY_GRACE" -gt 0 ] && \
         [ "$ACTIVITY_EXTEND_BY" -gt 0 ] && \
         [ "$EXTENSIONS_USED" -lt "$ACTIVITY_EXTEND_MAX" ] && \
         [ "$((ELAPSED - LAST_ACTIVITY))" -lt "$ACTIVITY_GRACE" ]; then
        EFFECTIVE_MAX=$((EFFECTIVE_MAX + ACTIVITY_EXTEND_BY))
        EXTENSIONS_USED=$((EXTENSIONS_USED + 1))
        echo "INFO: activity detected near deadline, extending wait by ${ACTIVITY_EXTEND_BY}s (#${EXTENSIONS_USED}/${ACTIVITY_EXTEND_MAX}, total=${EFFECTIVE_MAX}s)" >&2
      fi

      # 종료 판정
      if [ "$DONE_SEEN" -eq 1 ]; then
        # DONE 본 후 grace 경과 + 비어있지 않은 파일이 안정 → clean
        if [ -n "$CUR_STAT" ] && [ "$STABLE_FOR" -ge "$STABLE_SECONDS" ]; then
          echo "STATE: clean msg-id=$MSG_ID" >&2
          exit 0
        fi
        # DONE 봤는데 grace 초과되도록 파일 없음/비어있음 → protocol-error
        if [ -z "$CUR_STAT" ] && [ $((ELAPSED - DONE_AT)) -ge "$DONE_GRACE" ]; then
          REASON="DONE_without_file"
          [ -f "$RESP_FILE" ] && REASON="DONE_with_empty_file"
          echo "STATE: protocol-error msg-id=$MSG_ID reason=$REASON" >&2
          exit 1
        fi
      else
        # DONE 못 봤지만 비어있지 않은 파일이 안정됨 → soft-complete
        if [ -n "$CUR_STAT" ] && [ "$STABLE_FOR" -ge "$STABLE_SECONDS" ]; then
          echo "STATE: soft-complete msg-id=$MSG_ID reason=file_stable_no_DONE" >&2
          exit 0
        fi
      fi
    done

    # MAX_WAIT 초과 (실제로는 EFFECTIVE_MAX). 마지막 활동까지의 idle 시간도 같이 표시.
    IDLE=$((ELAPSED - LAST_ACTIVITY))
    SUFFIX="after_${EFFECTIVE_MAX}s ext=${EXTENSIONS_USED} idle=${IDLE}s"
    if [ ! -f "$RESP_FILE" ]; then
      echo "STATE: timeout msg-id=$MSG_ID reason=no_file_${SUFFIX}" >&2
    elif [ -z "$(file_stat "$RESP_FILE")" ]; then
      echo "STATE: timeout msg-id=$MSG_ID reason=empty_file_${SUFFIX}" >&2
    else
      echo "STATE: timeout msg-id=$MSG_ID reason=unstable_${SUFFIX}" >&2
    fi
    exit 1
    ;;

  read-response)
    # 응답 파일을 stdout에 출력. 원문 파일은 절대 수정하지 않음.
    # MAX_RESPONSE_BYTES 초과 시 stdout만 잘라서 출력 + stderr에 WARN.
    RUN_ID="${1:?run-id required}"
    MSG_ID="${2:?msg-id required}"
    validate_run_id "$RUN_ID" || exit 1

    CROSSTALK_ROOT="${CROSSTALK_ROOT:-/tmp/crosstalk}"
    MAX_RESPONSE_BYTES="${MAX_RESPONSE_BYTES:-20000}"
    validate_positive_int "$MAX_RESPONSE_BYTES" "MAX_RESPONSE_BYTES" || exit 1

    RESP_BASENAME=$(echo "$MSG_ID" | sed -E "s/^run-${RUN_ID}-r([0-9]+)-([a-z]+)-a([0-9]+)$/\\2-r\\1-a\\3.md/")
    if [ "$RESP_BASENAME" = "$MSG_ID" ]; then
      echo "ERROR: malformed msg-id '$MSG_ID'" >&2
      exit 1
    fi

    RESP_FILE="$CROSSTALK_ROOT/run-$RUN_ID/responses/$RESP_BASENAME"
    if [ ! -f "$RESP_FILE" ]; then
      echo "ERROR: response file not found: $RESP_FILE" >&2
      exit 1
    fi
    SIZE=$(wc -c < "$RESP_FILE" | tr -d ' ')
    if [ "$SIZE" -eq 0 ]; then
      echo "ERROR: response file is empty: $RESP_FILE" >&2
      exit 1
    fi

    if [ "$SIZE" -gt "$MAX_RESPONSE_BYTES" ]; then
      echo "WARN: response truncated ($SIZE bytes > MAX_RESPONSE_BYTES=$MAX_RESPONSE_BYTES). Original file preserved at $RESP_FILE" >&2
      head -c "$MAX_RESPONSE_BYTES" "$RESP_FILE"
    else
      cat "$RESP_FILE"
    fi
    ;;

  *)
    echo "Usage: $0 {peer|detect|list-peers|list-all|label|get-label|send|wait|capture|lines|prompt-count|save|stop|get-language|ensure-presets|wait-ready|start-run|make-msg-id|wait-turn|read-response} [args...]" >&2
    exit 2
    ;;
esac
