#!/usr/bin/env bash
# Sourced by the bridge. Ghostty 1.3+ macOS automation; no clipboard or focus-based targeting.
ghostty_rpc() {
  osascript - "$@" <<'APPLESCRIPT'
on run argv
  set op to item 1 of argv
  tell application "Ghostty"
    if op is "find-cwd" then
      set matches to {}
      set candidates to ""
      repeat with term in terminals
        if working directory of term is (item 2 of argv) then
          set end of matches to id of term
          set candidates to candidates & "ghostty:" & id of term & " | " & name of term & linefeed
        end if
      end repeat
      if (count of matches) is not 1 then error "Cannot identify caller uniquely in this directory. Candidates:" & linefeed & candidates & "From the intended CLI, run crosstalk_bridge.sh bind ghostty:<UUID> once. Do not guess the focused pane."
      return item 1 of matches
    end if
    set tid to item 2 of argv
    if not (exists terminal id tid) then error "Ghostty terminal no longer exists: " & tid
    set targetTerm to terminal id tid
    if op is "exists" then return tid
    if op is "list" then
      repeat with win in windows
        repeat with tb in tabs of win
          if tid is in (id of terminals of tb) then
            set rows to ""
            repeat with term in terminals of tb
              set rows to rows & id of term & linefeed
            end repeat
            return rows
          end if
        end repeat
      end repeat
      error "Ghostty tab not found"
    else if op is "text" then
      input text (item 3 of argv) to targetTerm
    else if op is "key" then
      if item 3 of argv is "c-c" then
        send key "c" modifiers "control" to targetTerm
      else if item 3 of argv is "enter" then
        send key "enter" to targetTerm
      else
        error "Unsupported key"
      end if
    else if op is "split" then
      set cfg to new surface configuration
      set initial working directory of cfg to item 3 of argv
      set command of cfg to item 4 of argv
      set environment variables of cfg to {"PATH=" & (item 5 of argv)}
      set childTerm to split targetTerm direction right with configuration cfg
      return id of childTerm
    else
      error "Unsupported Ghostty operation: " & op
    end if
  end tell
end run
APPLESCRIPT
}

ghostty_id() {
  local id="${1#ghostty:}"
  if [[ ! "$id" =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]; then
    echo "ERROR: invalid Ghostty terminal ID" >&2
    return 1
  fi
  printf '%s\n' "$id"
}

ghostty_caller() {
  local pid="$$" device parent
  while [ "$pid" -gt 1 ]; do
    read -r parent device <<< "$(ps -o ppid=,tty= -p "$pid")"
    if [[ "$device" =~ ^ttys[0-9]+$ ]]; then break; fi
    case "$parent" in ''|*[!0-9]*) break ;; esac
    [ "$parent" != "$pid" ] || break
    pid="$parent"
  done
  if [[ ! "${device:-}" =~ ^ttys[0-9]+$ ]]; then
    echo "ERROR: no caller TTY. Run inside Ghostty or set CROSSTALK_SURFACE_ID=ghostty:<UUID>." >&2
    return 1
  fi
  printf '%s\t%s\t%s\n' "$pid" "$device" "$(ps -o lstart= -p "$pid")"
}

ghostty_bind() {
  local id context pid device stamp cache
  id=$(ghostty_id "$1") || return
  ghostty_rpc exists "$id" >/dev/null || return
  context=$(ghostty_caller) || return
  IFS=$'\t' read -r pid device stamp <<< "$context"
  cache="${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}/ghostty/bind-$pid.json"
  mkdir -p "$(dirname "$cache")"
  jq -n --arg id "$id" --arg stamp "$stamp" --arg tty "$device" \
    '{id: $id, stamp: $stamp, tty: $tty}' > "$cache"
  printf 'ghostty:%s\n' "$id"
}

ghostty_self() {
  local context pid device id cache stamp
  if [ -n "${CROSSTALK_SURFACE_ID:-}" ]; then
    id=$(ghostty_id "$CROSSTALK_SURFACE_ID") || return
    ghostty_rpc exists "$id" >/dev/null || return
  else
    context=$(ghostty_caller) || return
    IFS=$'\t' read -r pid device stamp <<< "$context"
    cache="${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}/ghostty/bind-$pid.json"
    id=$(jq -r --arg stamp "$stamp" --arg tty "$device" 'select(.stamp == $stamp and .tty == $tty) | .id' "$cache" 2>/dev/null || true)
    if [ -n "$id" ]; then
      ghostty_id "$id" >/dev/null || return
      ghostty_rpc exists "$id" >/dev/null || return
    else
      # ponytail: initial binding needs a unique cwd; use bind <ID> for ambiguous tabs.
      id=$(ghostty_rpc find-cwd "$PWD") || return
      ghostty_bind "$id"
      return
    fi
  fi
  printf 'ghostty:%s\n' "$id"
}

ghostty_label_path() {
  local id
  id=$(ghostty_id "$1") || return
  printf '%s/ghostty/%s.kind\n' "${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}" "$id"
}

ghostty_label() {
  local id path
  id=$(ghostty_id "$1") || return
  ghostty_rpc exists "$id" >/dev/null || return
  path=$(ghostty_label_path "$1") || return
  mkdir -p "$(dirname "$path")"
  printf '%s\n' "$2" > "$path"
}

ghostty_get_label() {
  local id path kind
  id=$(ghostty_id "$1") || return
  ghostty_rpc exists "$id" >/dev/null || return
  path=$(ghostty_label_path "$1") || return
  kind=$(cat "$path" 2>/dev/null || true)
  case "$kind" in claude|codex|shell) printf '%s\n' "$kind" ;; esac
}

ghostty_launch() {
  local kind="${1:?kind required}" self id binary ready prompt command child binding launcher max_wait
  case "$kind" in claude|codex) ;; *) echo "ERROR: Ghostty launch supports claude or codex" >&2; return 1 ;; esac
  max_wait="${READY_MAX_WAIT:-60}"
  validate_positive_int "$max_wait" READY_MAX_WAIT || return
  binary=$(command -v "$kind") || { echo "ERROR: $kind is not installed" >&2; return 1; }
  self=$(self_surface) || return
  id=$(ghostty_id "$self") || return
  ready=$(mktemp "${TMPDIR:-/tmp}/crosstalk-ready.XXXXXXXX") || return
  binding="$ready.surface"
  launcher="$ready.launch"
  # The first real AI turn acknowledges startup; a title/label alone is not readiness.
  printf -v prompt 'printf ready > %q' "$ready"
  prompt="Crosstalk startup check. Run exactly: $prompt . Then say Crosstalk ready and finish this turn. Do not modify project files. Later [crosstalk] mailbox messages tell you to run crosstalk receive ID and reply ID; use those tools without MD files or ping. Legacy messages may still name task files."
  # The child waits for its exact ID before starting the CLI (same cwd is now ambiguous).
  # Keep the program in a private script: Ghostty only parses an executable and one path.
  (umask 077
    printf '#!/bin/bash\nset -euo pipefail\n' > "$launcher"
    printf 'for i in {1..100}; do if [ -s %q ]; then export CROSSTALK_SURFACE_ID="$(cat %q)"; rm -f %q "$0"; exec %q %q; fi; sleep 0.1; done; echo "Crosstalk launch binding timed out" >&2; rm -f "$0"; exit 1\n' "$binding" "$binding" "$binding" "$binary" "$prompt" >> "$launcher"
  )
  printf -v command '/bin/bash %q' "$launcher"
  child=$(ghostty_rpc split "$id" "$PWD" "$command" "$PATH") || { rm -f "$ready" "$launcher"; return 1; }
  child="ghostty:$child"
  printf '%s\n' "$child" > "$binding"
  ghostty_label "$child" "$kind" || return
  printf '%s\n' "$ready" > "$(ghostty_label_path "$child").ready"
  echo "STATE: launched surface=$child kind=$kind" >&2
  ghostty_wait_ready "$child" || return
  echo "$child"
}

# A timed-out launch remains discoverable, but is never reported ready just because it has a label.
ghostty_wait_ready() {
  local state ready elapsed=0 max_wait="${READY_MAX_WAIT:-60}"
  validate_positive_int "$max_wait" READY_MAX_WAIT || return
  state="$(ghostty_label_path "$1").ready"
  [ -f "$state" ] || return 0
  ready=$(cat "$state")
  while [ "$elapsed" -lt "$max_wait" ]; do
    if [ "$(cat "$ready" 2>/dev/null)" = ready ]; then
      rm -f "$ready" "$state"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  echo "ERROR: peer $1 has not acknowledged startup; check login/trust prompts there." >&2
  return 1
}
