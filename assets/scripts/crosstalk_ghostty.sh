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
    if op is "wd-list" then
      set rows to ""
      repeat with term in terminals
        set rows to rows & id of term & (character id 9) & (working directory of term as text) & linefeed
      end repeat
      return rows
    end if
    if op is "tty-list" then
      set rows to ""
      repeat with term in terminals
        set rows to rows & id of term & (character id 9) & (tty of term as text) & linefeed
      end repeat
      return rows
    end if
    if op is "cwd-list" then
      set rows to ""
      repeat with term in terminals
        if working directory of term is (item 2 of argv) then set rows to rows & id of term & linefeed
      end repeat
      return rows
    end if
    set tid to item 2 of argv
    if not (exists terminal id tid) then error "Ghostty terminal no longer exists: " & tid
    set targetTerm to terminal id tid
    if op is "exists" then return tid
    if op is "tty" then return (tty of targetTerm as text)
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
  local pid="$$" parent tty device="" caller=""
  # Codex runs tool commands in a daemon owned by its *first* instance, so the process tree
  # points at the wrong pane. The session id is the only per-pane identity it passes through.
  # ponytail: a resumed session in a new pane keeps its id; re-run bind there.
  if [ -n "${CODEX_THREAD_ID:-}" ] && [[ ! "$CODEX_THREAD_ID" =~ ^[A-Za-z0-9_-]{1,128}$ ]]; then
    echo "ERROR: invalid Codex session ID" >&2; return 1
  fi
  if [ -n "${CODEX_THREAD_ID:-}" ]; then printf 'codex-%s\tcodex\tsession\n' "$CODEX_THREAD_ID"; return; fi
  # The caller is the lowest process on the outermost TTY: agy runs tools in its own inner pty,
  # so the first TTY seen from the tool shell is not the pane's.
  while [[ "$pid" =~ ^[0-9]+$ ]] && [ "$pid" -gt 1 ]; do
    read -r parent tty <<< "$(ps -o ppid=,tty= -p "$pid")"
    if [[ "$tty" =~ ^ttys[0-9]+$ ]] && [ "$tty" != "$device" ]; then caller="$pid"; device="$tty"; fi
    [ "$parent" != "$pid" ] || break
    pid="$parent"
  done
  pid="$caller"
  if [[ ! "${device:-}" =~ ^ttys[0-9]+$ ]]; then
    echo "ERROR: no caller TTY. Run inside Ghostty or set CROSSTALK_SURFACE_ID=ghostty:<UUID>." >&2
    return 1
  fi
  printf '%s\t%s\t%s\n' "$pid" "$device" "$(ps -o lstart= -p "$pid")"
}

ghostty_bind() {
  local id context pid device stamp cache temporary evidence="${2:-explicit}"
  id=$(ghostty_id "$1") || return
  ghostty_rpc exists "$id" >/dev/null || return
  context=$(ghostty_caller) || return
  IFS=$'\t' read -r pid device stamp <<< "$context"
  cache="${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}/ghostty/bind-$pid.json"
  (umask 077; mkdir -p "$(dirname "$cache")")
  temporary=$(mktemp "$cache.XXXXXXXX") || return
  if ! jq -n --arg id "$id" --arg stamp "$stamp" --arg tty "$device" --arg evidence "$evidence" \
    '{id: $id, stamp: $stamp, tty: $tty, evidence: $evidence}' > "$temporary"; then
    rm -f "$temporary"; return 1
  fi
  mv -f "$temporary" "$cache"
  printf 'ghostty:%s\n' "$id"
}

# Prints the one cwd-matching terminal labelled with this caller's CLI kind (labels are
# written by `setup` from any pane); falls back to the one unlabelled terminal. Fails otherwise.
ghostty_unique_by_kind() {
  local want="" id kind hits=() blank=()
  case "$1" in
    codex-*) want=codex ;;
    *) case "$(ps -o command= -p "$1")" in
         *codex*) want=codex ;; *agy*|*antigravity*) want=antigravity ;; *claude*) want=claude ;;
       esac ;;
  esac
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    kind=$(ghostty_get_label "$id" 2>/dev/null || true)
    if [ -z "$kind" ]; then blank+=("$id"); elif [ "$kind" = "$want" ]; then hits+=("$id"); fi
  done < <(ghostty_rpc cwd-list "$PWD")
  [ "${#hits[@]}" -gt 0 ] || hits=(${blank[@]+"${blank[@]}"})
  [ "${#hits[@]}" -eq 1 ] || return 1
  printf '%s\n' "${hits[0]}"
}

# Legacy caller discovery briefly reports a unique OSC 7 directory, then restores it.
# Protocol 2 separately verifies the selected pane's TTY and foreground CLI.
# Runs only when the caller has no binding yet; ghostty_bind caches the result.
ghostty_probe() {
  local tty="$1"
  [[ "$tty" =~ ^ttys[0-9]+$ ]] && [ -w "/dev/$tty" ] || return 1
  python3 - "$tty" "${BASH_SOURCE[0]}" "${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}" <<'PYPROBE'
import fcntl, json, os, signal, subprocess, sys, time, urllib.parse, uuid
from pathlib import Path

tty, script, config = sys.argv[1:]
root = Path(config) / 'ghostty'
root.mkdir(mode=0o700, parents=True, exist_ok=True)
lock_path = root / ('probe-' + tty + '.lock')
record = root / ('probe-' + tty + '.json')
fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
deadline = time.monotonic() + 3
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except BlockingIOError:
        if time.monotonic() >= deadline:
            sys.exit('ERROR: caller TTY probe is busy')
        time.sleep(.05)
if record.exists() or record.is_symlink():
    sys.exit('ERROR: an interrupted TTY probe needs doctor inspection before another probe')

def rows():
    child = subprocess.Popen(['/bin/bash', '-c', 'source "$1"; ghostty_rpc wd-list',
                              'crosstalk-probe', script], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        output, _ = child.communicate(timeout=2)
    except BaseException:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.communicate()
        raise
    if child.returncode:
        raise RuntimeError('Cannot read terminal directories')
    return dict(line.split('\t', 1) for line in output.splitlines() if '\t' in line)

def report(path):
    with open('/dev/' + tty, 'w') as device:
        device.write('\x1b]7;file://' + os.uname().nodename + urllib.parse.quote(path) + '\x1b\\')
        device.flush()

def interrupted(signum, frame):
    raise RuntimeError('TTY probe interrupted')

before, token, selected, touched = {}, '/crosstalk-probe-' + uuid.uuid4().hex, None, False
try:
    before = rows()
    # Keep the pre-probe mapping for diagnosis after SIGKILL, when no finally can run.
    temporary = record.with_suffix('.tmp-' + uuid.uuid4().hex)
    with open(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
        json.dump({'tty': tty, 'token': token, 'before': before, 'fallback': os.getcwd(), 'pid': os.getpid()}, out)
    os.replace(temporary, record)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    touched = True
    report(token)
    probe_deadline = time.monotonic() + 3
    for _ in range(10):
        if time.monotonic() >= probe_deadline:
            raise RuntimeError('TTY probe timed out')
        matches = [key for key, value in rows().items() if value == token]
        if len(matches) == 1:
            selected = matches[0]
            break
        if len(matches) > 1:
            raise RuntimeError('Ambiguous probe response')
        time.sleep(.1)
    if not selected:
        raise RuntimeError('Caller pane did not acknowledge TTY probe')
except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
    print('ERROR: ' + str(error), file=sys.stderr)
    selected = None
finally:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    restored = not touched
    if touched:
        target = selected
        if target is None:
            try:
                matches = [key for key, value in rows().items() if value == token]
                target = matches[0] if len(matches) == 1 else None
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
        original = before.get(target) if target else None
        report(original or os.getcwd())
        if target:
            try:
                for _ in range(5):
                    if rows().get(target) == (original or os.getcwd()):
                        restored = True
                        break
                    time.sleep(.05)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
    if restored:
        record.unlink(missing_ok=True)
    os.close(fd)
if selected:
    print(selected)
else:
    sys.exit(1)
PYPROBE
}

ghostty_self() {
  local context pid device id cache stamp evidence rows matches
  if [ -n "${CROSSTALK_SURFACE_ID:-}" ]; then
    id=$(ghostty_id "$CROSSTALK_SURFACE_ID") || return
    ghostty_rpc exists "$id" >/dev/null || return
  else
    context=$(ghostty_caller) || return
    IFS=$'\t' read -r pid device stamp <<< "$context"
    if [ "${CROSSTALK_STRICT_IDENTITY:-0}" = 1 ] && [ "$device" = codex ]; then
      echo "ERROR: Codex protocol 2 commands require the current pane's explicit CROSSTALK_SURFACE_ID; a resumed thread cache is not address evidence" >&2
      return 1
    fi
    cache="${CROSSTALK_CONFIG_DIR:-$HOME/.claude/crosstalk}/ghostty/bind-$pid.json"
    id=$(jq -r --arg stamp "$stamp" --arg tty "$device" 'select(.stamp == $stamp and .tty == $tty) | .id' "$cache" 2>/dev/null || true)
    evidence=$(jq -r '.evidence // "legacy"' "$cache" 2>/dev/null || true)
    if [ "${CROSSTALK_STRICT_IDENTITY:-0}" = 1 ] && [ "$evidence" != explicit ] && [ "$evidence" != probe ] && [ "$evidence" != tty ]; then
      id=""
    fi
    # A cached pane that is gone (e.g. `codex resume` in a new pane) is re-resolved, not an error.
    if [ -n "$id" ] && ghostty_id "$id" >/dev/null && ghostty_rpc exists "$id" >/dev/null 2>&1; then
      :
    else
      # Current Ghostty exposes the actual TTY; directory reporting is not identity evidence.
      if [[ "$device" =~ ^ttys[0-9]+$ ]]; then
        if rows=$(ghostty_rpc tty-list); then
          matches=$(awk -F'\t' -v tty="/dev/$device" '$2 == tty {print $1}' <<< "$rows")
          if [ "$(printf '%s\n' "$matches" | grep -c .)" -ne 1 ]; then
            echo "ERROR: caller TTY /dev/$device does not identify exactly one Ghostty pane" >&2
            return 1
          fi
          ghostty_bind "$matches" tty
          return
        fi
      fi
      # Older Ghostty without TTY enumeration retains the exact OSC 7 compatibility probe.
      evidence=probe
      if ! id=$(ghostty_probe "$device"); then
        if [ "${CROSSTALK_STRICT_IDENTITY:-0}" = 1 ]; then
          echo "ERROR: no exact caller address; complete a handshake in the selected pane" >&2
          return 1
        fi
        evidence=legacy
        id=$(ghostty_unique_by_kind "$pid") || { ghostty_rpc find-cwd "$PWD"; return 1; }
      fi
      ghostty_bind "$id" "$evidence"
      return
    fi
  fi
  printf 'ghostty:%s\n' "$id"
}

ghostty_context() {
  local surface device
  surface="ghostty:$(ghostty_id "$1")" || return
  device=$(ghostty_rpc tty "${surface#ghostty:}") || return
  python3 - "$surface" "$device" <<'PYCONTEXT'
import json, re, subprocess, sys
surface, device = sys.argv[1:]
if not re.fullmatch(r'/dev/(ttys[0-9]+|pts/[0-9]+)', device):
    sys.exit('ERROR: invalid terminal TTY')
try:
    rows = subprocess.run(['ps', '-t', device.removeprefix('/dev/'), '-o',
                           'pid=,pgid=,tpgid=,stat=,comm='], capture_output=True,
                          text=True, timeout=2, check=True).stdout.splitlines()
    processes = []
    for line in rows:
        row = line.split(None, 4)
        if len(row) != 5 or row[1] != row[2] or not row[2].isdigit() or int(row[2]) <= 1 or 'T' in row[3] or 'Z' in row[3]:
            continue
        stamp = subprocess.run(['ps', '-o', 'lstart=', '-p', row[0]], capture_output=True,
                               text=True, timeout=2, check=True).stdout.strip()
        if stamp:
            processes.append({'process_id': row[0], 'process_start': stamp, 'executable': row[4]})
    print(json.dumps({'surface_id': surface, 'tty': device, 'processes': processes}))
except (OSError, subprocess.SubprocessError):
    sys.exit('ERROR: cannot inspect terminal foreground context')
PYCONTEXT
}

ghostty_identity() {
  local surface device cli=""
  if [ "$#" -gt 0 ]; then
    surface="ghostty:$(ghostty_id "$1")" || return
  else
    surface=$(CROSSTALK_STRICT_IDENTITY=1 ghostty_self) || return
    cli="${CODEX_THREAD_ID:-}"
  fi
  device=$(ghostty_rpc tty "${surface#ghostty:}") || return
  python3 - "$surface" "$device" "$cli" <<'PYIDENTITY'
import json, os, re, subprocess, sys
surface, device, cli = sys.argv[1:]
if not re.fullmatch(r'/dev/(ttys[0-9]+|pts/[0-9]+)', device):
    sys.exit('ERROR: invalid terminal TTY')
try:
    # Ghostty's pid can be a login wrapper; ps exposes the TTY's actual foreground group.
    result = subprocess.run(['ps', '-t', device.removeprefix('/dev/'), '-o',
                             'pid=,pgid=,tpgid=,stat=,comm='], capture_output=True,
                            text=True, timeout=2, check=True)
    candidates = []
    for line in result.stdout.splitlines():
        row = line.split(None, 4)
        if len(row) != 5 or row[1] != row[2] or not row[2].isdigit() or int(row[2]) <= 1:
            continue
        if 'T' in row[3] or 'Z' in row[3]:
            continue
        name = os.path.basename(row[4])
        kind = {'claude': 'claude', 'claude.exe': 'claude', 'codex': 'codex',
                'agy': 'antigravity', 'antigravity': 'antigravity'}.get(name)
        if kind:
            candidates.append((row[0], kind))
    if len(candidates) != 1:
        raise RuntimeError('Foreground TTY group does not contain exactly one supported CLI')
    pid, kind = candidates[0]
    stamp = subprocess.run(['ps', '-o', 'lstart=', '-p', pid], capture_output=True, text=True, timeout=2, check=True).stdout.strip()
    if not stamp:
        raise RuntimeError('Foreground CLI disappeared')
    print(json.dumps({'surface_id': surface, 'kind': kind, 'cli_session_id': cli,
                      'process_id': pid, 'process_start': stamp}))
except (OSError, RuntimeError, subprocess.SubprocessError) as error:
    sys.exit('ERROR: cannot verify foreground CLI: ' + str(error))
PYIDENTITY
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
  case "$kind" in claude|codex|antigravity|shell) printf '%s\n' "$kind" ;; esac
}

ghostty_launch() {
  [ "$#" -ne 2 ] || [ -n "$2" ] || set -- "$1"
  local scripts
  scripts=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  PYTHONPATH="$scripts${PYTHONPATH:+:$PYTHONPATH}" python3 -m crosstalk_lib.adapters launch "$@"
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
