#!/usr/bin/env bash
# Stop Mia — the voice server, the TTS service, and (when configured under
# `stack:` in server.yaml) the Hermes gateway and the llama-server behind it,
# so RAM/VRAM is actually freed. Nothing is removed: config, voices,
# certificates and the token stay in place.
#
#   ./stop-mia.sh                # graceful stop (systemd unit, launchd agent or background pid)
#   ./stop-mia.sh --status       # only show what is running
#   ./stop-mia.sh --restart      # stop, then ./start-mia.sh
#   ./stop-mia.sh --free-ports   # also kill whatever still holds Mia's ports
#   ./stop-mia.sh --wait 20      # seconds to wait for a graceful exit (default 10)
#   ./stop-mia.sh --version      # print the version and exit
#
# Exit codes: 0 stopped or was not running · 2 something is still running
set -uo pipefail
cd "$(dirname "$0")"
REPO="$PWD"
VERSION="$(cat "$REPO/VERSION" 2>/dev/null || git -C "$REPO" describe --tags --always 2>/dev/null || echo unknown)"

DO_RESTART=0
STATUS_ONLY=0
FREE_PORTS=0
WAIT_S=10
while [ $# -gt 0 ]; do
  case "$1" in
    --status) STATUS_ONLY=1 ;;
    --restart) DO_RESTART=1 ;;
    --free-ports) FREE_PORTS=1 ;;
    --wait) WAIT_S="${2:-10}"; shift ;;
    --version) printf 'Mia %s\n' "$VERSION"; exit 0 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

PY="${PYTHON:-python3}"
CFG="$REPO/server/config/server.yaml"
LOGDIR="$REPO/server/logs"

cfg() {  # cfg <dotted.key> [default] — tolerant, never fatal
  [ -f "$CFG" ] || { printf '%s\n' "${2:-}"; return; }
  $PY - "$CFG" "$1" "${2:-}" <<'PY' 2>/dev/null || printf '%s\n' "${2:-}"
import sys, yaml
d = yaml.safe_load(open(sys.argv[1])) or {}
cur = d
for part in sys.argv[2].split("."):
    cur = cur.get(part) if isinstance(cur, dict) else None
if isinstance(cur, list) and cur:
    print(cur[0])
elif cur is None:
    print(sys.argv[3])
else:
    print(cur)
PY
}

cfg_all() {  # cfg_all <dotted.key> [default] — every item of a YAML list
  [ -f "$CFG" ] || { printf '%s\n' "${2:-}"; return; }
  $PY - "$CFG" "$1" "${2:-}" <<'PY' 2>/dev/null || printf '%s\n' "${2:-}"
import sys, yaml
d = yaml.safe_load(open(sys.argv[1])) or {}
cur = d
for part in sys.argv[2].split("."):
    cur = cur.get(part) if isinstance(cur, dict) else None
if isinstance(cur, list) and cur:
    print(" ".join(str(x) for x in cur))
elif cur is None:
    print(sys.argv[3])
else:
    print(cur)
PY
}

WS_PORT="$(cfg server.port 8765)"; WS_PORT="${WS_PORT:-8765}"
TLS_PORTS="$(cfg_all server.tls_ports 443)"; TLS_PORTS="${TLS_PORTS:-443}"
PROXY_PORT="$(cfg server.dashboard_proxy.port 9443)"; PROXY_PORT="${PROXY_PORT:-9443}"
PORTS="$WS_PORT $TLS_PORTS $PROXY_PORT"
[ "$(cfg tts.provider piper)" = "http" ] && PORTS="$PORTS 8770"

# brain stack (optional `stack:` section — same keys start-mia.sh reads)
url_port() { printf '%s' "$1" | sed -nE 's|^[a-z]+://[^/:]+:([0-9]+).*|\1|p'; }
LLAMA_PORT="$(url_port "$(cfg stack.llama.health '')")"
HERMES_PORT="$(url_port "$(cfg stack.hermes.health '')")"
HERMES_UNIT="$(cfg stack.hermes.unit '')"
LLAMA_SUPERVISOR="$(cfg stack.llama.supervisor '')"
LLAMA_PIDFILE="$REPO/server/$(cfg stack.llama.pidfile logs/llama-server.pid)"
HERMES_PIDFILE="$REPO/server/$(cfg stack.hermes.pidfile logs/hermes-gateway.pid)"
CHAT_PORT="$(url_port "$(cfg stack.chat.health '')")"
CHAT_PIDFILE="$REPO/server/$(cfg stack.chat.pidfile logs/chat-model.pid)"
DASH_TARGET_PORT="$(url_port "$(cfg stack.dashboard.health '')")"
DASH_PIDFILE="$REPO/server/$(cfg stack.dashboard.pidfile logs/hermes-dashboard.pid)"
[ -n "$LLAMA_PORT" ] && PORTS="$PORTS $LLAMA_PORT"
[ -n "$HERMES_PORT" ] && PORTS="$PORTS $HERMES_PORT"
[ -n "$CHAT_PORT" ] && PORTS="$PORTS $CHAT_PORT"
[ -n "$DASH_TARGET_PORT" ] && PORTS="$PORTS $DASH_TARGET_PORT"

# --------------------------------------------------------------- environment
IS_MAC=0; [ "$(uname -s)" = "Darwin" ] && IS_MAC=1
HAVE_SYSTEMD=0; SCTL=()
if [ "$IS_MAC" = 0 ] && [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
  HAVE_SYSTEMD=1
  if [ "$(id -u)" = "0" ]; then SCTL=(systemctl); else SCTL=(systemctl --user); fi
fi

UNIT_DIRS=()
[ -d /etc/systemd/system ] && UNIT_DIRS+=(/etc/systemd/system)
[ -n "${HOME:-}" ] && UNIT_DIRS+=("$HOME/.config/systemd/user")
UNIT_DIRS+=("/var/lib/mia/units")

unit_path() {  # unit_path <name> -> path of the unit file, non-zero if absent
  local dir
  for dir in "${UNIT_DIRS[@]}"; do
    [ -f "$dir/$1.service" ] && { printf '%s\n' "$dir/$1.service"; return 0; }
  done
  return 1
}

listening() {  # works without lsof/ss/fuser (bash /dev/tcp connect test)
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null || return 1
  exec 3<&- 3>&- 2>/dev/null
  return 0
}

port_pids() {  # port_pids <port> -> pids listening on it (lsof -> ss -> fuser -> /proc)
  local p="$1" out=""
  if command -v lsof >/dev/null 2>&1; then
    out="$(lsof -ti "tcp:$p" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ')"
  fi
  if [ -z "$out" ] && command -v ss >/dev/null 2>&1; then
    out="$(ss -ltnp 2>/dev/null | awk -v p=":$p" '$4 ~ (p"$") {print}' \
           | grep -oE 'pid=[0-9]+' | cut -d= -f2 | tr '\n' ' ')"
  fi
  if [ -z "$out" ] && command -v fuser >/dev/null 2>&1; then
    out="$(fuser -n tcp "$p" 2>/dev/null | tr -s ' ' ' ')"
  fi
  if [ -z "$out" ] && [ -d /proc ]; then
    out="$($PY - "$p" 2>/dev/null <<'PY'
import glob, os, sys
port = int(sys.argv[1])
inodes = set()
for f in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        lines = open(f).read().splitlines()[1:]
    except OSError:
        continue
    for line in lines:
        parts = line.split()
        if len(parts) < 10 or parts[3] != "0A":   # 0A = LISTEN
            continue
        try:
            if int(parts[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(parts[9])
        except (ValueError, IndexError):
            continue
if inodes:
    pids = set()
    for fd in glob.glob("/proc/[0-9]*/fd/*"):
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            pids.add(fd.split("/")[2])
    print(" ".join(sorted(pids)))
PY
)"
  fi
  printf '%s' "$out"
}

show_status() {
  local unit state
  say "Mia status"
  if [ "$IS_MAC" = 1 ]; then
    for unit in com.mia.voice com.mia.tts; do
      if launchctl print "gui/$(id -u)/$unit" >/dev/null 2>&1; then info "launchd  $unit: loaded"; else info "launchd  $unit: not loaded"; fi
    done
  elif [ "$HAVE_SYSTEMD" = 1 ]; then
    for unit in mia-voice mia-tts $HERMES_UNIT; do
      [ -n "$unit" ] || continue
      if unit_path "$unit" >/dev/null; then
        state="$(timeout 5 "${SCTL[@]}" is-active "$unit" 2>/dev/null || true)"
        info "systemd  $unit: ${state:-unknown} ($(unit_path "$unit"))"
      fi
    done
  else
    info "systemd  not available in this session"
  fi
  local p pidfile
  for p in $PORTS; do
    if listening "$p"; then info "port     $p: listening (pid $(port_pids "$p"))"; else info "port     $p: free"; fi
  done
  for pidfile in "$LOGDIR/mia.pid" "$LOGDIR/mia-tts.pid"; do
    if [ -f "$pidfile" ]; then
      local pid; pid="$(cat "$pidfile" 2>/dev/null)"
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then info "pidfile  $pidfile: pid $pid running"
      else info "pidfile  $pidfile: stale"; fi
    fi
  done
}

if [ "$STATUS_ONLY" = 1 ]; then
  show_status
  exit 0
fi

# ------------------------------------------------------------------- stop it
say "Stopping Mia v$VERSION"
STOPPED=0

# 1) macOS launchd agents
if [ "$IS_MAC" = 1 ]; then
  for unit in com.mia.tts com.mia.voice; do
    if launchctl print "gui/$(id -u)/$unit" >/dev/null 2>&1; then
      launchctl bootout "gui/$(id -u)/$unit" 2>/dev/null && { info "launchd: $unit stopped"; STOPPED=1; }
    fi
  done
fi

# 2) systemd units (system or --user) — Mia first, then the Hermes gateway
if [ "$HAVE_SYSTEMD" = 1 ]; then
  for unit in mia-tts mia-voice $HERMES_UNIT; do
    [ -n "$unit" ] || continue
    if unit_path "$unit" >/dev/null; then
      if timeout 90 "${SCTL[@]}" stop "$unit" 2>/dev/null; then
        info "systemd: $unit stopped"
        STOPPED=1
      else
        warn "systemd: could not stop $unit (need 'sudo ./stop-mia.sh' for a system unit?)"
      fi
    fi
  done
  timeout 10 "${SCTL[@]}" daemon-reload 2>/dev/null || true
elif [ "$IS_MAC" = 0 ] && [ -n "$(unit_path mia-voice 2>/dev/null)" ]; then
  warn "a systemd unit is installed but systemd is not running here — falling back to pidfiles"
fi

# 3) background processes started by start-mia.sh (incl. gateway/llama/dashboard)
for pidfile in "$LOGDIR/mia-tts.pid" "$LOGDIR/mia.pid" "$HERMES_PIDFILE" "$LLAMA_PIDFILE" "$DASH_PIDFILE" "$CHAT_PIDFILE"; do
  [ -f "$pidfile" ] || continue
  pid="$(cat "$pidfile" 2>/dev/null)"
  if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && info "sent SIGTERM to pid $pid ($(basename "$pidfile"))"
    for _ in $(seq 1 "$WAIT_S"); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    if kill -0 "$pid" 2>/dev/null; then
      warn "pid $pid did not exit after ${WAIT_S}s — sending SIGKILL"
      kill -9 "$pid" 2>/dev/null
    fi
    STOPPED=1
  fi
  rm -f "$pidfile"
done

# 3b) llama-server started outside start-mia.sh: the supervisor traps SIGTERM
# and takes the model down with it; without this the RAM stays allocated.
if [ -n "$LLAMA_SUPERVISOR" ] && [ -n "$LLAMA_PORT" ] && listening "$LLAMA_PORT"; then
  SUP_PIDS="$(pgrep -f "$LLAMA_SUPERVISOR" 2>/dev/null)"
  for pid in $SUP_PIDS; do
    kill "$pid" 2>/dev/null && info "sent SIGTERM to llama supervisor (pid $pid)"
  done
  for _ in $(seq 1 "$WAIT_S"); do listening "$LLAMA_PORT" || break; sleep 1; done
  if listening "$LLAMA_PORT"; then
    for pid in $SUP_PIDS; do kill -9 "$pid" 2>/dev/null; done
    for pid in $(port_pids "$LLAMA_PORT"); do
      warn "llama-server (pid $pid) ignored SIGTERM — sending SIGKILL"
      kill -9 "$pid" 2>/dev/null
    done
  fi
  [ -n "$SUP_PIDS" ] && STOPPED=1
fi

# 4) wait until the ports are actually free
for p in $PORTS; do
  for _ in $(seq 1 "$WAIT_S"); do listening "$p" || break; sleep 1; done
done

# 5) last resort: whoever still holds a Mia port
STILL=""
for p in $PORTS; do listening "$p" && STILL="$STILL $p"; done
if [ -n "$STILL" ]; then
  if [ "$FREE_PORTS" = 1 ]; then
    for p in $STILL; do
      pids="$(port_pids "$p")"
      warn "port $p still held by pid(s): $pids — killing (--free-ports)"
      for pid in $pids; do
        kill -9 "$pid" 2>/dev/null
      done
    done
    sleep 1
    STILL=""
    for p in $PORTS; do listening "$p" && STILL="$STILL $p"; done
    [ -z "$STILL" ] && STOPPED=1
  else
    warn "still listening on:$STILL — rerun with --free-ports to kill the holders"
  fi
fi

if [ "$DO_RESTART" = 1 ]; then
  say "Restarting"
  exec "$REPO/start-mia.sh"
fi

if [ -n "$STILL" ]; then
  say "Not stopped completely"
  show_status
  exit 2
fi

if [ "$STOPPED" = 1 ]; then
  say "Stopped"
else
  say "Mia was not running"
fi
info "config, voices, certificates and the token were left untouched"
info "start again with: ./start-mia.sh"
exit 0
