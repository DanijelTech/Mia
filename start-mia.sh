#!/usr/bin/env bash
# Start Mia and open the HUD in your browser.
#
# Brings up the whole local stack, in order, skipping whatever already answers:
#   1. llama-server  (Gemma4-12B na GPU 0, port 18083 — stack.llama v server.yaml)
#   1b. chat model   (mali LLM za tekoč pogovor — stack.chat, neobvezno)
#   2. Hermes gateway (systemd unit ali `hermes gateway run`)
#   3. Mia voice server + Maya1 TTS (na GPU 1, ločen od LLM)
#   4. Piper fallback TTS (CPU, če ni GPU na voljo)
#
#   ./start-mia.sh                    # start (systemd if installed, else background), wait, open
#   ./start-mia.sh --no-open          # just start and print the URL/token
#   ./start-mia.sh --no-start         # assume it is running; only wait + open
#   ./start-mia.sh --host 192.168.1.10
#   ./start-mia.sh --wait 180         # longer wait (first run downloads the Whisper model)
#   ./start-mia.sh --no-token-in-url  # open /hud/ without the one-click login token
#
# Exit codes: 0 ok · 1 not installed · 2 server did not come up ·
#             3 HUD is up, but part of the stack (llama/chat/Hermes/dashboard) is not ready
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

journal_tail() {  # journal_tail <unit> <lines> — works for user and system units
  command -v journalctl >/dev/null 2>&1 || return 0
  if [ "$(id -u)" != "0" ]; then
    timeout 10 journalctl --user-unit "$1" -n "${2:-25}" --no-pager 2>/dev/null
  else
    timeout 10 journalctl -u "$1" -n "${2:-25}" --no-pager 2>/dev/null
  fi
}

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

cfgargv() {  # cfgargv <dotted.key> — a YAML list as NUL-separated argv (safe for regex/space args)
  [ "$CFG_OK" = 1 ] || return 1
  $PY - "$CFG" "$1" <<'PY' 2>/dev/null
import os, sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
cur = cfg
for part in sys.argv[2].split("."):
    cur = cur.get(part) if isinstance(cur, dict) else None
if not isinstance(cur, list) or not cur:
    raise SystemExit(1)
os.write(1, b"\0".join(str(a).encode() for a in cur) + b"\0")
PY
}

read_argv() {  # read_argv <dotted.key> <array-name>
  local -n _out="$2"
  _out=()
  local a
  while IFS= read -r -d '' a; do _out+=("$a"); done < <(cfgargv "$1") || true
}

HUD_PORT="$(cfg server.port 8765)"
TLS_PORT="$(cfglist server.tls_ports 443)"
TTS_PROVIDER="$(cfg tts.provider piper)"
TTS_URL="$(cfg tts.http.url '')"
TTS_ENGINE_CFG="$(cfg tts.http.engine gepard)"

# brain stack (see the `stack:` section in server.yaml; all optional)
LLAMA_HEALTH="$(cfg stack.llama.health '')"
LLAMA_TIMEOUT="$(cfg stack.llama.start_timeout 420)"
LLAMA_PIDFILE="$REPO/server/$(cfg stack.llama.pidfile logs/llama-server.pid)"
LLAMA_LOG="$REPO/server/$(cfg stack.llama.log logs/llama-server.out)"
CHAT_HEALTH="$(cfg stack.chat.health '')"
CHAT_TIMEOUT="$(cfg stack.chat.start_timeout 420)"
CHAT_PIDFILE="$REPO/server/$(cfg stack.chat.pidfile logs/chat-model.pid)"
CHAT_LOG="$REPO/server/$(cfg stack.chat.log logs/chat-model.out)"

LLAMA_SUPERVISOR="$(cfg stack.llama.supervisor '')"
HERMES_HEALTH="$(cfg stack.hermes.health '')"
HERMES_TIMEOUT="$(cfg stack.hermes.start_timeout 90)"
HERMES_UNIT="$(cfg stack.hermes.unit '')"
HERMES_PIDFILE="$REPO/server/$(cfg stack.hermes.pidfile logs/hermes-gateway.pid)"
HERMES_LOG="$REPO/server/$(cfg stack.hermes.log logs/hermes-gateway.out)"

TTS_MAYA1_GPU_ID="$(cfg tts.maya1.gpu_id '1')"
TTS_MAYA1_VOICE="$(cfg tts.maya1.voice 'zenski-nezni')"

DASH_HEALTH="$(cfg stack.dashboard.health '')"

DASH_TIMEOUT="$(cfg stack.dashboard.start_timeout 180)"
DASH_PIDFILE="$REPO/server/$(cfg stack.dashboard.pidfile logs/hermes-dashboard.pid)"
DASH_LOG="$REPO/server/$(cfg stack.dashboard.log logs/hermes-dashboard.out)"

# ------------------------------------------------------------------ utilities

port_open() { # port_open <url> — 0 if anything answers, even a 503 "loading model"
  curl -s -m 1 -o /dev/null "$1" 2>/dev/null
}

http_ready() { # http_ready <url> — 0 only when the service is usable
  # llama-server binds its port before the GGUF is loaded and answers
  # 503 {"error":{"message":"Loading model"}} until then; a bare TCP/HTTP
  # check would report "up" while the model is still on disk.
  local code
  code="$(curl -s -m 2 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true)"
  case "$code" in ''|000|5*) return 1 ;; *) return 0 ;; esac
}

wait_health() {  # wait_health <url> <seconds> [pidfile] — 0 ready · 1 timeout · 2 process died
  local deadline=$(( $(date +%s) + $2 )) pidfile="${3:-}" pid
  while [ "$(date +%s)" -lt "$deadline" ]; do
    http_ready "$1" && return 0
    if [ -n "$pidfile" ] && [ -f "$pidfile" ]; then
      pid="$(cat "$pidfile" 2>/dev/null)"
      if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
        return 2
      fi
    fi
    sleep 2
  done
  return 1
}

recent_log() { # recent_log <logfile> [lines] — output of the current start only
  [ -f "$1" ] || return 0
  awk '/^==> .* started /{buf=""} {buf = buf $0 "\n"} END{printf "%s", buf}' "$1" \
    | tail -n "${2:-15}"
}

tail_log() { # tail_log <label> <logfile> [lines]
  [ -f "$2" ] || return 0
  printf '    --- %s (last %s lines of %s) ---\n' "$1" "${3:-15}" "$2"
  recent_log "$2" "${3:-15}" | sed 's/^/    /'
}

hint_from_log() { # hint_from_log <logfile> — the usual llama-server launch failures
  [ -f "$1" ] || return 0
  local low
  low="$(recent_log "$1" 60 | tr '[:upper:]' '[:lower:]')"
  case "$low" in
    *"out of memory"*|*"failed to allocate"*|*"cudamalloc"*)
      warn "hint: not enough VRAM — lower -ngl/-c, or move this model to another GPU" ;;
    *"invalid device ordinal"*|*"no cuda devices"*|*"cuda error: invalid"*|*"cuda driver version"*)
      warn "hint: CUDA_VISIBLE_DEVICES in stack.*.argv names a GPU this machine does not have — check: nvidia-smi -L" ;;
    *"error loading model"*|*"failed to load model"*|*"no such file"*)
      warn "hint: the GGUF path in stack.*.argv is wrong or its disk is not mounted" ;;
    *"address already in use"*|*"couldn't bind"*|*"failed to bind"*)
      warn "hint: the port is already taken — run ./stop-mia.sh --free-ports, then retry" ;;
  esac
}

model_path_of() { # model_path_of <argv...> — the -m / --model value, if any
  local prev="" a
  for a in "$@"; do
    case "$prev" in -m|--model) printf '%s\n' "$a"; return 0 ;; esac
    case "$a" in -m=*|--model=*) printf '%s\n' "${a#*=}"; return 0 ;; esac
    prev="$a"
  done
  return 1
}

check_model_file() { # check_model_file <label> <argv...> — 0 when the GGUF exists
  local label="$1"; shift
  local path dir found
  path="$(model_path_of "$@")" || return 0
  [ -e "$path" ] && return 0
  warn "$label: model file not found — $path"
  dir="$(dirname "$path")"
  if [ -d "$dir" ]; then
    found="$(find "$dir" -maxdepth 4 -type f -name '*.gguf' 2>/dev/null | head -n 5)"
    if [ -n "$found" ]; then
      info "GGUF files that do exist under $dir:"
      printf '%s\n' "$found" | sed 's/^/      /'
      info "fix: point stack.*.argv in server/config/server.yaml at one of them"
    else
      info "no .gguf files under $dir — check the path or download the model"
    fi
  else
    info "directory $dir does not exist — is the disk mounted? (lsblk / mount | grep -i kameleon)"
  fi
  return 1
}

report_failed() { # report_failed <label> <logfile> <rc> <timeout> [pidfile]
  case "$3" in
    2) warn "$1 exited during startup — see $2" ;;
    *)
      warn "$1 did not become ready within ${4}s — see $2"
      if [ -n "${5:-}" ] && [ -f "$5" ] \
         && kill -0 "$(cat "$5" 2>/dev/null)" 2>/dev/null; then
        warn "hint: the process is still running — the model may still be loading; raise its stack.*.start_timeout"
      fi
      ;;
  esac
  tail_log "$1 log" "$2"
  hint_from_log "$2"
  DEGRADED+=("$1")
}

DEGRADED=()

start_background() { # $1 = label, $2 = pidfile, $3 = logfile, $4... = command
  local label="$1" pidfile="$2" logfile="$3"; shift 3
  mkdir -p "$(dirname "$pidfile")" "$(dirname "$logfile")"
  # marks where this run starts so failure hints never quote an older crash
  printf '\n==> %s started %s\n' "$label" "$(date '+%Y-%m-%d %H:%M:%S')" >>"$logfile"
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
  say "1/4 Starting the brain (llama-server + Hermes gateway)"

  if [ -z "$LLAMA_HEALTH" ] && [ -z "$HERMES_HEALTH" ]; then
    info "no stack: section in server.yaml — assuming the brain runs elsewhere"
  fi

  if [ -n "$LLAMA_HEALTH" ]; then
    if http_ready "$LLAMA_HEALTH"; then
      info "llama-server already answering"
    else
      LLAMA_ARGV=()
      read_argv stack.llama.argv LLAMA_ARGV
      if [ ${#LLAMA_ARGV[@]} -eq 0 ]; then
        warn "stack.llama.argv missing in server.yaml — Hermes will have no model"
      elif port_open "$LLAMA_HEALTH"; then
        # a previous start is still loading the GGUF: wait for it, never start a
        # second server on the same port
        info "llama-server is still loading its model — waiting for it to be ready…"
        wait_health "$LLAMA_HEALTH" "$LLAMA_TIMEOUT"; rc=$?
        [ "$rc" = 0 ] && info "llama-server is up" \
          || { warn "llama-server did not become ready within ${LLAMA_TIMEOUT}s"; DEGRADED+=("llama-server"); }
      elif ! check_model_file "llama-server" "${LLAMA_ARGV[@]}"; then
        DEGRADED+=("llama-server")
      else
        [ -n "$LLAMA_SUPERVISOR" ] && [ -x "$LLAMA_SUPERVISOR" ] \
          && LLAMA_ARGV=("$LLAMA_SUPERVISOR" "${LLAMA_ARGV[@]}")
        info "starting llama-server (Gemma4-12B, GPU 0) — loading GGUF takes minutes…"
        start_background "llama-server" "$LLAMA_PIDFILE" "$LLAMA_LOG" "${LLAMA_ARGV[@]}"
        wait_health "$LLAMA_HEALTH" "$LLAMA_TIMEOUT" "$LLAMA_PIDFILE"; rc=$?
        [ "$rc" = 0 ] && info "llama-server is up" \
          || report_failed "llama-server" "$LLAMA_LOG" "$rc" "$LLAMA_TIMEOUT" "$LLAMA_PIDFILE"
      fi
    fi
  fi

  if [ -n "$CHAT_HEALTH" ]; then
    if http_ready "$CHAT_HEALTH"; then
      info "chat model already answering"
    else
      CHAT_ARGV=()
      read_argv stack.chat.argv CHAT_ARGV
      if [ ${#CHAT_ARGV[@]} -eq 0 ]; then
        warn "stack.chat.health is set but stack.chat.argv is missing — chat stays off"
      elif port_open "$CHAT_HEALTH"; then
        info "chat model is still loading — waiting for it to be ready…"
        wait_health "$CHAT_HEALTH" "$CHAT_TIMEOUT"; rc=$?
        [ "$rc" = 0 ] && info "chat model is up" \
          || { warn "chat model did not become ready within ${CHAT_TIMEOUT}s"; DEGRADED+=("chat model"); }
      elif ! check_model_file "chat model" "${CHAT_ARGV[@]}"; then
        info "hint: a second model is optional — the main one can answer chat:"
        info "      python3 server/scripts/use_single_model.py"
        DEGRADED+=("chat model")
      else
        info "starting chat model (fast conversation)…"
        start_background "chat model" "$CHAT_PIDFILE" "$CHAT_LOG" "${CHAT_ARGV[@]}"
        wait_health "$CHAT_HEALTH" "$CHAT_TIMEOUT" "$CHAT_PIDFILE"; rc=$?
        [ "$rc" = 0 ] && info "chat model is up" \
          || report_failed "chat model" "$CHAT_LOG" "$rc" "$CHAT_TIMEOUT" "$CHAT_PIDFILE"
      fi
    fi
  fi

  if [ -n "$HERMES_HEALTH" ]; then
    if http_ready "$HERMES_HEALTH"; then
      info "Hermes gateway already answering"
    elif port_open "$HERMES_HEALTH"; then
      info "Hermes gateway is starting — waiting for it to be ready…"
      wait_health "$HERMES_HEALTH" "$HERMES_TIMEOUT"; rc=$?
      [ "$rc" = 0 ] && info "Hermes gateway is up" \
        || { warn "Hermes gateway did not become ready within ${HERMES_TIMEOUT}s"; DEGRADED+=("Hermes gateway"); }
    elif [ -n "$HERMES_UNIT" ] && unit_exists "$HERMES_UNIT"; then
      timeout 30 "${SCTL[@]}" start "$HERMES_UNIT" && info "systemd: $HERMES_UNIT started" \
        || warn "systemctl could not start $HERMES_UNIT"
      wait_health "$HERMES_HEALTH" "$HERMES_TIMEOUT"; rc=$?
      [ "$rc" = 0 ] && info "Hermes gateway is up" \
        || { warn "Hermes gateway did not become ready within ${HERMES_TIMEOUT}s"; DEGRADED+=("Hermes gateway"); }
    else
      HERMES_ARGV=()
      read_argv stack.hermes.argv HERMES_ARGV
      if [ ${#HERMES_ARGV[@]} -eq 0 ]; then
        warn "no Hermes unit and no stack.hermes.argv — start the gateway manually"
      else
        start_background "hermes gateway" "$HERMES_PIDFILE" "$HERMES_LOG" "${HERMES_ARGV[@]}"
        wait_health "$HERMES_HEALTH" "$HERMES_TIMEOUT" "$HERMES_PIDFILE"; rc=$?
        [ "$rc" = 0 ] && info "Hermes gateway is up" \
          || report_failed "Hermes gateway" "$HERMES_LOG" "$rc" "$HERMES_TIMEOUT" "$HERMES_PIDFILE"
      fi
    fi
  fi

  if [ -n "$DASH_HEALTH" ]; then
    if http_ready "$DASH_HEALTH"; then
      info "Hermes dashboard already answering"
    elif port_open "$DASH_HEALTH"; then
      info "Hermes dashboard is starting — waiting for it to be ready…"
      wait_health "$DASH_HEALTH" "$DASH_TIMEOUT"; rc=$?
      [ "$rc" = 0 ] && info "Hermes dashboard is up" \
        || { warn "Hermes dashboard did not become ready within ${DASH_TIMEOUT}s"; DEGRADED+=("Hermes dashboard"); }
    else
      DASH_ARGV=()
      read_argv stack.dashboard.argv DASH_ARGV
      if [ ${#DASH_ARGV[@]} -eq 0 ]; then
        warn "stack.dashboard.argv missing in server.yaml — HUD views will be dead"
      else
        start_background "hermes dashboard" "$DASH_PIDFILE" "$DASH_LOG" "${DASH_ARGV[@]}"
        wait_health "$DASH_HEALTH" "$DASH_TIMEOUT" "$DASH_PIDFILE"; rc=$?
        [ "$rc" = 0 ] && info "Hermes dashboard is up" \
          || report_failed "Hermes dashboard" "$DASH_LOG" "$rc" "$DASH_TIMEOUT" "$DASH_PIDFILE"
      fi
    fi
  fi

  say "2/4 Starting Mia"
  if unit_exists mia-voice; then
    timeout 20 "${SCTL[@]}" start mia-voice && info "systemd: mia-voice started" \
      || start_background "voice server" "$REPO/server/logs/mia.pid" "$REPO/server/logs/mia.out" \
           "$PY" "$REPO/server/server.py"
    sleep 2
    # a unit left in "failed"/"auto-restart" state after an earlier bad start
    if ! timeout 10 "${SCTL[@]}" is-active --quiet mia-voice; then
      info "unit is not active — restarting it once"
      timeout 20 "${SCTL[@]}" restart mia-voice 2>/dev/null \
        || warn "systemctl restart failed (see above)"
    fi
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
      sleep 2
      if ! timeout 10 "${SCTL[@]}" is-active --quiet mia-tts; then
        warn "mia-tts unit is not active — check: systemctl --user status mia-tts -l (or journalctl -u mia-tts)"
      fi
    elif [ -f "$REPO/server/scripts/gepard_tts.py" ]; then
      if [ "$TTS_ENGINE_CFG" = "maya1" ]; then
        info "starting TTS service (Maya1, GPU ${TTS_MAYA1_GPU_ID:-1}, voice: $TTS_MAYA1_VOICE)…"
        # Maya1 mora biti na GPU 1 — ne smemo ga mešati z llama-serverjem na GPU 0
        CUDA_VISIBLE_DEVICES="${TTS_MAYA1_GPU_ID:-1}" \
          start_background "Maya1 TTS" "$REPO/server/logs/mia-tts.pid" "$REPO/server/logs/mia-tts.out" \
            "$PY" "$REPO/server/scripts/gepard_tts.py" --serve --engine maya1 \
              --device cuda --maya-voice "${TTS_MAYA1_VOICE:-zenski-nezni}" \
              --fallback-piper
      else
        info "starting TTS service (engine: $TTS_ENGINE_CFG)…"
        TTS_ARGV=()
        read_argv tts.http.args TTS_ARGV
        start_background "TTS service" "$REPO/server/logs/mia-tts.pid" "$REPO/server/logs/mia-tts.out" \
          "$PY" "$REPO/server/scripts/gepard_tts.py" --serve --engine "$TTS_ENGINE_CFG" \
            --fallback-piper "${TTS_ARGV[@]}"
      fi
    else
      warn "tts.provider is http but no TTS service could be started"
    fi
  fi
else
  say "1/4 Skipping start (--no-start)"
fi

# ------------------------------------------------------------------- 2. wait
say "3/4 Waiting for the HUD (up to ${WAIT_S}s)"
READY=0
DEADLINE=$(( $(date +%s) + WAIT_S ))
PIDFILE="$REPO/server/logs/mia.pid"
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if curl -s -m 2 -o /dev/null "http://127.0.0.1:$HUD_PORT/api/hud-config"; then READY=1; break; fi
  if [ -f "$PIDFILE" ] && ! kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    warn "the voice server exited during startup"
    [ -f "$REPO/server/logs/mia.out" ] && tail -n 20 "$REPO/server/logs/mia.out" | sed 's/^/    /'
    die "fix the error above, then retry: ./start-mia.sh --no-start" 2
  fi
  sleep 2
done
if [ "$READY" != 1 ]; then
  warn "voice server did not answer on :$HUD_PORT within ${WAIT_S}s"
  if [ ${#SCTL[@]} -gt 0 ] && unit_exists mia-voice; then
    printf '\n    --- systemd status ---\n'
    timeout 10 "${SCTL[@]}" --no-pager status mia-voice 2>&1 | tail -n 12 | sed 's/^/    /' || true
    printf '\n    --- last log lines ---\n'
    journal_tail mia-voice 25 | sed 's/^/    /' \
      || printf '    (journalctl unavailable)\n'
  elif [ -f "$REPO/server/logs/mia.out" ]; then
    printf '\n    --- last log lines ---\n'
    tail -n 20 "$REPO/server/logs/mia.out" | sed 's/^/    /'
  fi
  die "fix the error above, then retry: ./start-mia.sh --no-start" 2
fi
info "voice server is up"

# ------------------------------------------------------------------- 3. open
if [ -z "$HOST" ]; then
  HOST="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -vE '^(127\.|::|$)' | head -n1)"
  [ -z "$HOST" ] && HOST="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
  [ -z "$HOST" ] && HOST="$(ipconfig getifaddr en0 2>/dev/null)"
  [ -z "$HOST" ] && HOST="127.0.0.1"
fi
SCHEME="https"; [ -f "$REPO/server/certs/cert.pem" ] || SCHEME="http"
# the HUD is served on the TLS port when certificates exist
URL="$SCHEME://$HOST"
[ -n "$TLS_PORT" ] && [ "$TLS_PORT" != "443" ] && [ "$SCHEME" = "https" ] && URL="$URL:$TLS_PORT"
URL="$URL/hud/"

TOKEN="${MIA_HUD_TOKEN:-${JARVIS_HUD_TOKEN:-}}"
TOKEN_FILES=("$HOME/.hermes/.env" "$REPO/server/.env")
# HERMES_HOME may be on another disk; install.sh writes a pointer for that.
if [ -f "$HOME/.config/mia/hermes_home" ]; then
  HERMES_HOME_PTR="$(cat "$HOME/.config/mia/hermes_home" 2>/dev/null)"
  [ -n "$HERMES_HOME_PTR" ] && TOKEN_FILES=("$HERMES_HOME_PTR/.env" "${TOKEN_FILES[@]}")
fi
[ -n "${HERMES_HOME:-}" ] && TOKEN_FILES=("$HERMES_HOME/.env" "${TOKEN_FILES[@]}")
for envfile in "${TOKEN_FILES[@]}"; do
  [ -n "$TOKEN" ] && break
  [ -f "$envfile" ] || continue
  TOKEN="$(grep -hE '^(MIA_HUD_TOKEN|JARVIS_HUD_TOKEN)=' "$envfile" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"
  [ -n "$TOKEN" ] && break
done

LOGIN_URL="$URL"
if [ "$TOKEN_IN_URL" = 1 ] && [ -n "$TOKEN" ]; then
  LOGIN_URL="$URL?token=$TOKEN"
fi

say "4/4 Opening the HUD"
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

if [ ${#DEGRADED[@]} -gt 0 ]; then
  printf '\n'
  warn "started with problems: ${DEGRADED[*]}"
  info "the HUD is up, but turns that need these services will fail — read the log above, fix it, then rerun: ./start-mia.sh"
  exit 3
fi

exit 0
