#!/usr/bin/env bash
# Terminal-only transport driver. No workflow, engine or mailbox command dispatch.
# Target IDs carry their backend so callbacks work even from a different environment.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/crosstalk_ghostty.sh"

# CLI subprocesses may omit TERM_PROGRAM or retain variables from an old terminal.
terminal_process_backend() {
  local pid="$$" parent executable
  while [ "$pid" -gt 1 ]; do
    read -r parent executable <<< "$(ps -o ppid=,comm= -p "$pid" 2>/dev/null)"
    case "${executable##*/}" in
      ghostty|Ghostty) echo ghostty; return 0 ;;
      cmux) echo cmux; return 0 ;;
    esac
    case "$parent" in ''|*[!0-9]*) break ;; esac
    [ "$parent" != "$pid" ] || break
    pid="$parent"
  done
  return 1
}

terminal_backend() {
  local detected
  case "${CROSSTALK_BACKEND:-}" in
    ghostty|cmux) echo "$CROSSTALK_BACKEND"; return ;;
    "") ;;
    *) echo "ERROR: CROSSTALK_BACKEND must be ghostty or cmux" >&2; return 1 ;;
  esac
  if [[ "${CROSSTALK_SURFACE_ID:-}" = ghostty:* ]]; then
    echo ghostty
  elif detected=$(terminal_process_backend); then
    echo "$detected"
  elif [ "${TERM_PROGRAM:-}" = ghostty ] || [ -n "${GHOSTTY_RESOURCES_DIR:-}" ] || [ -n "${GHOSTTY_BIN_DIR:-}" ]; then
    echo ghostty
  elif { [ -n "${CMUX_SURFACE_ID:-}" ] || [ -n "${CMUX_WORKSPACE_ID:-}" ] || [ "${TERM_PROGRAM:-}" = cmux ]; } && \
       cmux identify 2>/dev/null | jq -e '.caller.surface_ref | strings | select(length > 0)' >/dev/null; then
    echo cmux
  else
    echo "ERROR: cannot identify the caller terminal. No live Ghostty/cmux evidence; a leftover socket is not enough. Set CROSSTALK_BACKEND explicitly if needed." >&2
    return 1
  fi
}

terminal_surfaces() {
  local self="$1" pane
  if [[ "$self" = ghostty:* ]]; then
    ghostty_rpc list "$(ghostty_id "$self")" | sed '/^$/d; s/^/ghostty:/'
  else
    for pane in $(cmux list-panes | awk '/pane:/ {gsub("[*]", ""); print $1}'); do
      cmux list-pane-surfaces --pane "$pane" | awk '/surface:/ {gsub("[*]", ""); print $1}'
    done
  fi
}

terminal_text() {
  local id
  if [[ "$1" = ghostty:* ]]; then
    id=$(ghostty_id "$1") || return
    ghostty_rpc text "$id" "$2"
  else cmux send --surface "$1" "$2"; fi
}

terminal_key() {
  local id
  if [[ "$1" = ghostty:* ]]; then
    id=$(ghostty_id "$1") || return
    ghostty_rpc key "$id" "$2"
  else cmux send-key --surface "$1" "$2"; fi
}

terminal_screen() {
  if [[ "$1" = ghostty:* ]]; then
    echo "ERROR: Ghostty 1.3 has no screen-read API; use file responses and ping." >&2
    return 1
  fi
  cmux read-screen --surface "$1" ${3:+--scrollback} --lines "${2:-200}"
}

# 본인 surface_ref 추출 헬퍼 (caller 블록 내부에서)
self_surface() {
  local backend
  backend=$(terminal_backend) || return
  if [ "$backend" = ghostty ]; then ghostty_self; return; fi
  cmux identify \
    | awk '/"caller"[[:space:]]*:/{flag=1} flag && /"surface_ref"/{print; exit}' \
    | sed 's/.*: "//; s/".*//'
}


validate_positive_int() {
  case "$1" in ''|*[!0-9]*|0|0*) echo "ERROR: invalid $2" >&2; return 1 ;; esac
}

# Sourcing exposes shared low-level helpers to the legacy wrapper, without dispatch.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then return; fi
set -euo pipefail
umask 077
operation="${1:-}"
shift || true
case "$operation" in
  backend) terminal_backend ;;
  self) self_surface ;;
  strict-self)
    [ "$(terminal_backend)" = ghostty ] || { echo "ERROR: exact mailbox identity requires Ghostty" >&2; exit 1; }
    CROSSTALK_STRICT_IDENTITY=1 ghostty_self ;;
  bind) ghostty_bind "${1:?surface required}" ;;
  context) ghostty_context "${1:?surface required}" ;;
  list-surfaces) terminal_surfaces "${1:?anchor required}" ;;
  exists)
    if [[ "$1" = ghostty:* ]]; then ghostty_rpc exists "$(ghostty_id "$1")";
    else terminal_surfaces "$1" | awk -v wanted="$1" '$0==wanted {found=1} END {exit !found}'; fi ;;
  label)
    if [[ "$1" = ghostty:* ]]; then ghostty_label "$1" "$2";
    else cmux rename-tab --surface "$1" "ct-$2" >/dev/null; fi ;;
  get-label)
    if [[ "$1" = ghostty:* ]]; then
      path=$(ghostty_label_path "$1")
      ghostty_rpc exists "$(ghostty_id "$1")" >/dev/null
      [ ! -f "$path" ] || cat "$path"
    else
      for pane in $(cmux list-panes | awk '/pane:/ {gsub("[*]", ""); print $1}'); do
        cmux list-pane-surfaces --pane "$pane" | awk -v id="$1" '{gsub("^[*]", ""); if($1==id && $2 ~ /^ct-/){sub("^ct-", "", $2); print $2}}'
      done
    fi ;;
  split)
    ghostty_rpc split "$(ghostty_id "$1")" "$2" "$3" "$4" ;;
  send)
    count="${3:-2}"
    case "$count" in 1|2) ;; *) echo "ERROR: submission key count must be 1 or 2" >&2; exit 1 ;; esac
    terminal_text "$1" "$2" >/dev/null
    terminal_key "$1" enter >/dev/null
    if [ "$count" = 2 ]; then sleep 0.5; terminal_key "$1" enter >/dev/null; fi ;;
  text) terminal_text "$1" "$2" ;;
  key) terminal_key "$1" "$2" ;;
  capture) terminal_screen "$1" "${2:-200}" "${3:-}" ;;
  *) echo "ERROR: unsupported terminal operation: $operation" >&2; exit 2 ;;
esac
