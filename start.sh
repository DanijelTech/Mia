#!/usr/bin/env bash
# Start Mia and open the HUD in your browser.
#
#   ./start.sh                    # start (systemd if installed, else background), wait, open
#   ./start.sh --no-open          # just start and print the URL/token
#   ./start.sh --no-start         # assume it is running; only wait + open
#   ./start.sh --host 192.168.1.10
#   ./start.sh --wait 180         # longer wait (first run downloads the Whisper model)
#   ./start.sh --no-token-in-url  # open /hud/ without the one-click login token
#
# Exit codes: 0 ok · 1 not installed · 2 server did not come up
set -uo pipefail
cd "$(dirname "$0")"
REPO="$PWD"

DO_START=1
DO_OPEN=1
WAIT_S=90
TOKEN_IN_URL=1
HOST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-start) DO_START=0 ;;
    --no-open) DO_OPEN=0 ;;
    --no-token-in-url) TOKEN_IN_URL=0 ;;
    --wait) WAIT_S="${2:-90}"; shift ;;
    --host) HOST="${2:-}"; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit "${2:-1}"; }

PY="${PYTHON:-python3}"
CFG="$REPO/server/config/server.yaml"
[ -f "$CFG" ] || die "Mia is not installed yet (no server/config/server.yaml). Run: ./install.sh" 1
[ -f "$REPO/server/server.py" ] || die "server/server.py missing — run this from the Mia repo" 1

CFG_OK=1
if ! $PY -c 'import yaml' >/dev/null 2>&1; then
  CFG_OK=0
  printf '    [warn] %s cannot import PyYAML — using config defaults\n' "$PY" >&2
fi

cfg() {  # cfg <dotted.key> [default]
  local out
  if [ "$CFG_OK" != 1 ]; then printf '%s\n' "${2:-}"; return; fi
  out="$($PY - "$CFG" "$1" "${2:-}" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
cur = cfg
for part in sys.argv[2].split("."):
    if not isinstance(cur, dict) or part not in cur:
        print(sys.argv[3]); raise SystemExit
    cur = cur[part]
print(cur if cur is not None else sys.argv[3])
PY
)" || out=""
  [ -z "$out" ] && out="${2:-}"
  printf '%s\n' "$out"
}

cfglist() {  # first item of a YAML list, e.g. server.tls_ports
  [ "$CFG_OK" = 1 ] || { printf '%s\n' "${2:-}"; return; }
  $PY -c 'import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
cur = cfg
for part in sys.argv[2].split("."):
    cur = cur.get(part) if isinstance(cur, dict) else None
print(cur[0] if isinstance(cur, list) and cur else sys.argv[3])' "$CFG" "$1" "${2:-}" 2>/dev/null \
    || printf '%s\n' "${2:-}"
}

HUD_PORT="$(cfg server.port 8765)"
TLS_PORT="$(cfglist server.tls_ports 443)"
TTS_PROVIDER="$(cfg tts.provider piper)"
TTS_URL="$(cfg tts.http.url '')"
TTS_ENGINE_CFG="$(cfg tts.http.engine gepard)"

# ------------------------------------------------------------------ 1. start
port_open() { curl -s -m 1 -o /dev/null "$1" 2>/dev/null; }

start_background() { # $1 = label, $2 = pidfile, $3 = logfile, $4... = command
  local label="$1" pidfile="$2" logfile="$3"; shift 3
  mkdir -p "$(dirname "$pidfile")" "$(dirname "$logfile")"
  nohup "$@" >>"$logfile" 2>&1 &
  echo $! > "$pidfile"
  info "$label started in the background (pid $(cat "$pidfile"), log $logfile)"
}

# systemd is only usable when it is actually PID 1's manager (not in containers/WSL)
HAVE_SYSTEMD=0
SCTL=()
if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
  HAVE_SYSTEMD=1
  if [ "$(id -u)" = "0" ]; then SCTL=(systemctl); else SCTL=(systemctl --user); fi
fi
unit_exists() {  # ask the filesystem, never systemd (a dead manager would hang)
  [ "$HAVE_SYSTEMD" = 1 ] || return 1
  local f
  for f in /etc/systemd/system "$HOME/.config/systemd/user" "/var/lib/mia/units"; do
    [ -f "$f/$1.service" ] && return 0
  done
  return 1
}

if [ "$DO_START" = 1 ]; then
  say "1/3 Starting Mia"
  if unit_exists mia-voice; then
    timeout 20 "${SCTL[@]}" start mia-voice && info "systemd: mia-voice started" \
      || start_background "voice server" "$REPO/server/logs/mia.pid" "$REPO/server/logs/mia.out" \
           "$PY" "$REPO/server/server.py"
  elif port_open "http://127.0.0.1:$HUD_PORT/api/hud-config"; then
    info "voice server already answering on :$HUD_PORT"
  else
    start_background "voice server" "$REPO/server/logs/mia.pid" "$REPO/server/logs/mia.out" \
      "$PY" "$REPO/server/server.py"
  fi

  if [ "$TTS_PROVIDER" = "http" ] && [ -n "$TTS_URL" ]; then
    TTS_HEALTH="${TTS_URL%/tts}/health"
    if port_open "$TTS_HEALTH"; then
      info "TTS service already answering"
    elif unit_exists mia-tts; then
      timeout 20 "${SCTL[@]}" start mia-tts && info "systemd: mia-tts started"
    elif [ -f "$REPO/server/scripts/gepard_tts.py" ]; then
      info "starting TTS service (engine: $TTS_ENGINE_CFG)…"
      start_background "TTS service" "$REPO/server/logs/mia-tts.pid" "$REPO/server/logs/mia-tts.out" \
        "$PY" "$REPO/server/scripts/gepard_tts.py" --serve --engine "$TTS_ENGINE_CFG" --fallback-piper
    else
      warn "tts.provider is http but no TTS service could be started"
    fi
  fi
else
  say "1/3 Skipping start (--no-start)"
fi

# ------------------------------------------------------------------- 2. wait
say "2/3 Waiting for the HUD (up to ${WAIT_S}s)"
READY=0
DEADLINE=$(( $(date +%s) + WAIT_S ))
PIDFILE="$REPO/server/logs/mia.pid"
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if curl -s -m 2 -o /dev/null "http://127.0.0.1:$HUD_PORT/api/hud-config"; then READY=1; break; fi
  if [ -f "$PIDFILE" ] && ! kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    warn "the voice server exited during startup"
    [ -f "$REPO/server/logs/mia.out" ] && tail -n 20 "$REPO/server/logs/mia.out" | sed 's/^/    /'
    die "fix the error above, then retry: ./start.sh --no-start" 2
  fi
  sleep 2
done
if [ "$READY" != 1 ]; then
  warn "voice server did not answer on :$HUD_PORT within ${WAIT_S}s"
  if [ -f "$REPO/server/logs/mia.out" ]; then
    printf '\n    --- last log lines ---\n'
    tail -n 15 "$REPO/server/logs/mia.out" | sed 's/^/    /'
  fi
  die "check the log above, then retry: ./start.sh --no-start" 2
fi
info "voice server is up"

# ------------------------------------------------------------------- 3. open
if [ -z "$HOST" ]; then
  HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -z "$HOST" ] && HOST="$(ipconfig getifaddr en0 2>/dev/null)"
  [ -z "$HOST" ] && HOST="127.0.0.1"
fi
SCHEME="https"; [ -f "$REPO/server/certs/cert.pem" ] || SCHEME="http"
# the HUD is served on the TLS port when certificates exist
URL="$SCHEME://$HOST"
[ -n "$TLS_PORT" ] && [ "$TLS_PORT" != "443" ] && [ "$SCHEME" = "https" ] && URL="$URL:$TLS_PORT"
URL="$URL/hud/"

TOKEN="${MIA_HUD_TOKEN:-${JARVIS_HUD_TOKEN:-}}"
for envfile in "$HOME/.hermes/.env" "$REPO/server/.env"; do
  [ -n "$TOKEN" ] && break
  [ -f "$envfile" ] || continue
  TOKEN="$(grep -hE '^(MIA_HUD_TOKEN|JARVIS_HUD_TOKEN)=' "$envfile" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
  [ -n "$TOKEN" ] && break
done

LOGIN_URL="$URL"
if [ "$TOKEN_IN_URL" = 1 ] && [ -n "$TOKEN" ]; then
  LOGIN_URL="$URL?token=$TOKEN"
fi

say "3/3 Opening the HUD"
cat <<INFO

    HUD:    $URL
    token:  ${TOKEN:-<not set — auth disabled>}
            (one-click login is included in the URL below)

    The certificate is self-signed: accept the browser warning once
    (Chrome: Advanced -> Proceed; Safari: Show Details -> visit website).

INFO

OPENED=0
if [ "$DO_OPEN" = 1 ]; then
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}${WSL_DISTRO_NAME:-}" ] || [ "$(uname -s)" = "Darwin" ]; then
    if command -v xdg-open >/dev/null 2>&1; then
      (xdg-open "$LOGIN_URL" >/dev/null 2>&1 &) && OPENED=1
    elif [ "$(uname -s)" = "Darwin" ] && command -v open >/dev/null 2>&1; then
      (open "$LOGIN_URL" >/dev/null 2>&1 &) && OPENED=1
    elif command -v wslview >/dev/null 2>&1; then
      (wslview "$LOGIN_URL" >/dev/null 2>&1 &) && OPENED=1
    elif command -v sensible-browser >/dev/null 2>&1; then
      (sensible-browser "$LOGIN_URL" >/dev/null 2>&1 &) && OPENED=1
    fi
  fi
  if [ "$OPENED" = 1 ]; then
    info "browser opened"
  else
    warn "no graphical session detected — open this on your phone/laptop:"
    printf '\n    %s\n\n' "$LOGIN_URL"
  fi
else
  info "not opening a browser (--no-open)"
  printf '\n    %s\n\n' "$LOGIN_URL"
fi

exit 0
