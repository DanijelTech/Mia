#!/usr/bin/env bash
# Mia — complete installer (no virtualenv).
#
# Installs Mia directly into the system (root) or user Python, exactly like a
# Hermes install that runs on the device itself. Everything it creates is
# recorded in a manifest so ./uninstall.sh can remove it again.
#
#   sudo ./install.sh                 # system-wide, root (Hermes runs as root)
#   ./install.sh                      # user mode: pip --user + systemd --user
#   ./install.sh --with-gepard        # also install the Gepard TTS service
#   ./install.sh --with-maya1         # ...or the Maya1 TTS service (better SL)
#   ./install.sh --dry-run            # show every action, change nothing
#   ./install.sh --yes --open         # install, start and open the HUD
#
# Common options:
#   --yes                 no prompts
#   --mode system|user    force install mode (default: root -> system)
#   --python PATH         interpreter to install into (default: python3)
#   --with-gepard         install Gepard TTS (accelerate/NeMo/gepard-inference)
#   --with-maya1          install Maya1 TTS (transformers/peft/snac/phonemizer + espeak-ng)
#   --tts-engine E        gepard | maya1 | piper | none
#   --no-system-pkgs      never call apt/dnf/brew (install espeak-ng yourself)
#   --no-stt-deps         skip RealtimeSTT/torch (if you already have them)
#   --no-deps             skip every pip step
#   --voice sl|sr|all|none
#   --stt-device cpu|cuda|auto   Whisper device (cpu keeps the GPU for your LLM)
#   --no-cert             skip TLS certificate generation
#   --no-service          do not install/enable a service
#   --no-start            install the unit but do not start it
#   --no-token            do not touch ~/.hermes/.env
#   --open                start Mia (if needed) and open the HUD in the browser
#   --service-dir DIR     where unit/plist files go (default: system-dependent)
#   --hermes-env PATH     env file for the HUD token (default: ~/.hermes/.env)
#
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$REPO_DIR/server"
VERSION="$(git -C "$REPO_DIR" describe --tags --always 2>/dev/null || echo unknown)"

MODE=""
PYTHON="${PYTHON:-python3}"
TTS_ENGINE=""
DO_SYSTEM_PKGS=1
DO_DEPS=1
DO_STT_DEPS=1
DO_VOICE=1
VOICE_LANG="sl"
STT_DEVICE=""
DO_CERT=1
DO_SERVICE=1
DO_START=1
DO_TOKEN=1
DO_OPEN=0
ASSUME_YES=0
DRY_RUN=0
SERVICE_DIR=""
HERMES_ENV=""
PORT_TTS=8770

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --mode) MODE="${2:-}"; shift ;;
    --python) PYTHON="${2:-}"; shift ;;
    --with-gepard) TTS_ENGINE="gepard" ;;
    --with-maya1) TTS_ENGINE="maya1" ;;
    --tts-engine) TTS_ENGINE="${2:-}"; shift ;;
    --no-system-pkgs) DO_SYSTEM_PKGS=0 ;;
    --no-stt-deps) DO_STT_DEPS=0 ;;
    --no-deps) DO_DEPS=0 ;;
    --voice) VOICE_LANG="${2:-}"; shift ;;
    --stt-device) STT_DEVICE="${2:-}"; shift ;;
    --no-cert) DO_CERT=0 ;;
    --no-service) DO_SERVICE=0 ;;
    --no-start) DO_START=0 ;;
    --no-token) DO_TOKEN=0 ;;
    --open) DO_OPEN=1 ;;
    --service-dir) SERVICE_DIR="${2:-}"; shift ;;
    --hermes-env) HERMES_ENV="${2:-}"; shift ;;
    --port-tts) PORT_TTS="${2:-}"; shift ;;
    -h|--help) sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

case "${TTS_ENGINE:-}" in
  ""|none) TTS_ENGINE="none" ;;
  gepard|maya1|piper) ;;
  *) echo "unknown --tts-engine: $TTS_ENGINE (gepard|maya1|piper|none)" >&2; exit 2 ;;
esac

# ------------------------------------------------------------------ plumbing
say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if [ "$DRY_RUN" = 1 ]; then printf '    [dry-run] %s\n' "$*"; return 0; fi
  "$@"
}
run_sh() {
  if [ "$DRY_RUN" = 1 ]; then printf '    [dry-run] sh -c: %s\n' "$*"; return 0; fi
  sh -c "$*"
}
confirm() {
  [ "$ASSUME_YES" = 1 ] && return 0
  printf '    %s [y/N] ' "$1"
  read -r answer || answer=""
  case "$answer" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# ------------------------------------------------------------------- manifest
if [ "$(id -u)" = "0" ]; then
  MODE="${MODE:-system}"
  STATE_DIR="${XDG_STATE_HOME:-/var/lib}/mia"
else
  MODE="${MODE:-user}"
  STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/mia"
fi
[ "$MODE" = "system" ] && [ "$(id -u)" != "0" ] && [ "$DRY_RUN" = 0 ] \
  && die "system mode needs root: sudo ./install.sh --mode system"
MANIFEST="$STATE_DIR/install-manifest.json"
TMP_MF="$(mktemp -d)"; trap 'rm -rf "$TMP_MF"' EXIT
: > "$TMP_MF/files"; : > "$TMP_MF/dirs"; : > "$TMP_MF/pkg"; : > "$TMP_MF/svc"
MF_TOKEN_ADDED=0; MF_TOKEN_VAR=""; MF_TOKEN_FILE=""; MF_TOKEN_SHA=""

add_file() { printf '%s\n' "$1" >> "$TMP_MF/files"; }
add_dir()  { printf '%s\n' "$1" >> "$TMP_MF/dirs"; }
add_pkg()  { printf '%s\n' "$1" >> "$TMP_MF/pkg"; }
add_svc()  { printf '%s\n' "$1" >> "$TMP_MF/svc"; }

write_manifest() {
  [ "$DRY_RUN" = 1 ] && return 0
  mkdir -p "$STATE_DIR"
  MF_MODE="$MODE" MF_PYTHON="$PYTHON" MF_ROOT="$REPO_DIR" MF_VERSION="$VERSION" \
  MF_TOKEN_ADDED="$MF_TOKEN_ADDED" MF_TOKEN_VAR="$MF_TOKEN_VAR" \
  MF_TOKEN_FILE="$MF_TOKEN_FILE" MF_TOKEN_SHA="$MF_TOKEN_SHA" \
  MF_SERVICE_KIND="${SERVICE_KIND:-none}" MF_SERVICE_DIR="${SERVICE_DIR:-}" \
  python3 - "$MANIFEST" "$TMP_MF" <<'PY'
import json, os, sys, pathlib, time
out, tmp = sys.argv[1], sys.argv[2]
def lines(name):
    p = pathlib.Path(tmp, name)
    return [l for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
data = {
    "tool": "mia", "version": os.environ.get("MF_VERSION", "unknown"),
    "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "mode": os.environ.get("MF_MODE"), "python": os.environ.get("MF_PYTHON"),
    "repo_dir": os.environ.get("MF_ROOT"),
    "service_kind": os.environ.get("MF_SERVICE_KIND"),
    "service_dir": os.environ.get("MF_SERVICE_DIR") or None,
    "token": {
        "added": os.environ.get("MF_TOKEN_ADDED") == "1",
        "var": os.environ.get("MF_TOKEN_VAR") or None,
        "file": os.environ.get("MF_TOKEN_FILE") or None,
        "sha256": os.environ.get("MF_TOKEN_SHA") or None,
    },
    "packages": sorted(set(lines("pkg"))),
    "files": sorted(set(lines("files"))),
    "dirs": sorted(set(lines("dirs")), key=len, reverse=True),
    "services": sorted(set(lines("svc"))),
}
pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(out).write_text(json.dumps(data, indent=2) + "\n")
PY
}


journal_tail() {  # journal_tail <unit> <lines> — works for user and system units
  command -v journalctl >/dev/null 2>&1 || return 0
  if [ "$(id -u)" != "0" ]; then
    timeout 10 journalctl --user-unit "$1" -n "${2:-25}" --no-pager 2>/dev/null
  else
    timeout 10 journalctl -u "$1" -n "${2:-25}" --no-pager 2>/dev/null
  fi
}

lan_ip() {  # first non-loopback IPv4 of this host
  local ip
  ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -vE '^(127\.|::|$)' | head -n1)"
  [ -n "$ip" ] || ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
  [ -n "$ip" ] || ip="$(ipconfig getifaddr en0 2>/dev/null)"
  [ -n "$ip" ] || ip="127.0.0.1"
  printf '%s\n' "$ip"
}

hud_url() {  # print the URL the HUD will live at (respects TLS port and cert presence)
  local out
  out="$($PYTHON - "$CFG" "$SERVER_DIR/certs/cert.pem" "$(lan_ip)" 2>/dev/null <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1])) or {}
server = cfg.get("server") or {}
has_cert = __import__("pathlib").Path(sys.argv[2]).exists()
ports = server.get("tls_ports") or ([server["tls_port"]] if server.get("tls_port") else [])
host = sys.argv[3] if len(sys.argv) > 3 else "127.0.0.1"
if has_cert and ports:
    port = int(ports[0])
    print(f"https://{host}/hud/" if port == 443 else f"https://{host}:{port}/hud/")
else:
    print(f"http://{host}:{int(server.get('port', 8765))}/hud/  (no TLS certificate)")
PY
)"
  [ -n "$out" ] || out="http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1):8765/hud/"
  printf '%s\n' "$out"
}

# ------------------------------------------------------------------ preflight
say "Mia installer — $VERSION ($MODE mode)"
info "repo:      $REPO_DIR"
info "python:    $PYTHON"
[ "$DRY_RUN" = 1 ] && info "dry-run:   nothing will be changed"

[ -f "$SERVER_DIR/server.py" ] || die "server/server.py not found — run this from the Mia repo root"
command -v "$PYTHON" >/dev/null 2>&1 || die "python not found: $PYTHON"
PYV="$($PYTHON -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
info "python version: $PYV"
$PYTHON -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || die "Python 3.10+ required (found $PYV)"

[ -n "$HERMES_ENV" ] || HERMES_ENV="$HOME/.hermes/.env"
info "hermes env: $HERMES_ENV"

if [ "$DRY_RUN" = 0 ] && [ "$DO_DEPS" = 1 ] && ! confirm "Install Python packages into $($PYTHON -c 'import sys;print(sys.prefix)')?"; then
  warn "package installation skipped by user"
  DO_DEPS=0
fi

# --------------------------------------------------------------- pip helpers
PIP_FLAGS=()
if [ "$(id -u)" != "0" ]; then PIP_FLAGS+=(--user); fi
PEP668=0

pip_install() {
  [ "$DO_DEPS" = 1 ] || { info "skip pip: $*"; return 0; }
  local attempt
  for attempt in 1 2; do
    if [ "$DRY_RUN" = 1 ]; then
      printf '    [dry-run] %s -m pip install %s %s %s\n' "$PYTHON" "${PIP_FLAGS[*]}" "$([ $attempt = 2 ] && echo '--break-system-packages')" "$*"
      return 0
    fi
    if $PYTHON -m pip install "${PIP_FLAGS[@]}" $([ $attempt = 2 ] && echo --break-system-packages) "$@" 2>&1 | tee "$TMP_MF/pip.log"; then
      local pkg
      for pkg in "$@"; do add_pkg "$pkg"; done
      return 0
    fi
    if grep -qE "externally-managed-environment|externally managed" "$TMP_MF/pip.log" && [ $attempt = 1 ]; then
      warn "system Python is externally managed (PEP 668) — retrying with --break-system-packages"
      PEP668=1
      continue
    fi
    warn "pip install failed: $*"
    return 1
  done
}

# ------------------------------------------------------------------- 1. deps
say "1/7 Python dependencies"
pip_install fastapi uvicorn requests pyyaml numpy
pip_install psutil || warn "psutil missing: the HUD machines panel will be degraded"
if [ "$DO_STT_DEPS" = 1 ]; then
  # RealtimeSTT treats these as optional extras but fails at runtime without them
  pip_install RealtimeSTT faster-whisper silero-vad \
    || die "RealtimeSTT + faster-whisper + silero-vad are required for speech-to-text"
else
  info "skip RealtimeSTT (--no-stt-deps)"
fi
pip_install piper-tts || warn "piper-tts missing: local voice unavailable"

if [ "$TTS_ENGINE" = "gepard" ]; then
  say "1b/7 Gepard TTS extras (heavy, ~3 GB)"
  pip_install accelerate || warn "accelerate missing: no GPU/RAM layer split"
  if confirm "Install NeMo toolkit for the NanoCodec (large download)?"; then
    pip_install "nemo_toolkit[tts]" || warn "nemo_toolkit failed — Gepard cannot decode audio"
  fi
  pip_install "git+https://github.com/nineninesix-ai/gepard-inference" \
    || warn "gepard-inference failed — start the TTS service with --engine piper instead"
elif [ "$TTS_ENGINE" = "maya1" ]; then
  say "1b/7 Maya1 TTS extras (transformers + SNAC + phonemizer)"
  pip_install accelerate transformers peft snac soundfile phonemizer \
    || warn "Maya1 Python deps incomplete — the service will fall back to Piper"
  if [ "$DO_SYSTEM_PKGS" = 1 ]; then
    if command -v espeak-ng >/dev/null 2>&1; then
      info "espeak-ng already installed"
    elif [ "$(id -u)" = "0" ] || [ "$MODE" = "system" ]; then
      if command -v apt-get >/dev/null 2>&1; then
        run apt-get update -qq && run apt-get install -y espeak-ng || warn "could not install espeak-ng"
      elif command -v dnf >/dev/null 2>&1; then
        run dnf install -y espeak-ng || warn "could not install espeak-ng"
      elif command -v pacman >/dev/null 2>&1; then
        run pacman -S --noconfirm espeak-ng || warn "could not install espeak-ng"
      elif command -v brew >/dev/null 2>&1; then
        run brew install espeak || warn "could not install espeak"
      else
        warn "unknown package manager — install espeak-ng manually (needed for Slovenian phonemes)"
      fi
    else
      warn "espeak-ng missing: run 'sudo apt-get install espeak-ng' (phonemizer needs it)"
    fi
  else
    info "skip system packages (--no-system-pkgs) — make sure espeak-ng is present"
  fi
  pip_install transformers || true
fi

if [ "$DRY_RUN" = 0 ] && [ "$DO_DEPS" = 1 ]; then
  $PYTHON - <<'PY' || die "dependency check failed"
import importlib, sys
missing = [m for m in ("fastapi", "uvicorn", "requests", "yaml", "numpy")
           if importlib.util.find_spec(m) is None]
if missing:
    print("missing modules:", ", ".join(missing)); sys.exit(1)
print("    core imports ok")
PY
fi

# -------------------------------------------------------------- 2. voices
say "2/7 Local voice models"
if [ "$DO_VOICE" = 1 ] && [ "$VOICE_LANG" != "none" ]; then
  run bash "$REPO_DIR/server/scripts/get-voice.sh" "$VOICE_LANG" || warn "voice download failed (offline? copy voices/ manually)"
else
  info "skip voice download"
fi

# ---------------------------------------------------------------- 3. config
say "3/7 Configuration"
CFG="$SERVER_DIR/config/server.yaml"
if [ -f "$CFG" ]; then
  info "keeping existing $CFG"
else
  run cp "$SERVER_DIR/config/server.example.yaml" "$CFG" && add_file "$CFG"
  info "created $CFG (review voice/tts/language settings)"
fi

# Whisper device: an explicit --stt-device wins; otherwise warn when the config
# will keep a CUDA context alive and steal VRAM from the LLM.
if [ "$DRY_RUN" = 0 ] && [ -f "$CFG" ]; then
  if [ -n "$STT_DEVICE" ]; then
    $PYTHON - "$CFG" "$STT_DEVICE" <<'PY'
import re, sys, pathlib
path, want = pathlib.Path(sys.argv[1]), sys.argv[2]
out, changed = [], False
for line in path.read_text().splitlines():
    if re.match(r"^  device:", line) and line.startswith("  device:"):
        out.append(f"  device: {want}")
        changed = True
    else:
        out.append(line)
if changed:
    path.write_text("\n".join(out) + "\n")
print(f"    stt.device -> {want}")
PY
  else
    CUR_STT="$(grep -m1 -E '^  device:' "$CFG" 2>/dev/null | awk '{print $2}')"
    case "${CUR_STT:-}" in
      cuda|auto)
        info "stt.device is '${CUR_STT}': Mia will hold a CUDA context and take VRAM"
        info "  from your LLM (a launcher that checks free VRAM may refuse to start)."
        info "  Use './install.sh --stt-device cpu' or the GPU worker if that happens."
        ;;
    esac
  fi
fi

# Port 443 needs root (or CAP_NET_BIND_SERVICE, which user services cannot get),
# so a user-mode install listens for HTTPS on 8766 instead of 443.
if [ "$DRY_RUN" = 0 ] && [ "$(id -u)" != "0" ]; then
  if grep -qE '^  tls_ports:[^#]*\b443\b' "$CFG"; then
    $PYTHON - "$CFG" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
lines = p.read_text().splitlines()
out, changed = [], False
for line in lines:
    if re.match(r"^  tls_ports:", line) and "443" in line:
        out.append("  tls_ports: [8766]           # not root: 443 needs privileges, HUD uses :8766")
        changed = True
    else:
        out.append(line)
if changed:
    p.write_text("\n".join(out) + "\n")
    print("    tls_ports -> [8766] (user install cannot bind :443)")
PY
  fi
fi

# ------------------------------------------------------------------ 4. certs
say "4/7 TLS certificate (required for the browser microphone)"
if [ "$DO_CERT" = 1 ]; then
  if [ -f "$SERVER_DIR/certs/cert.pem" ]; then
    LAN="$(lan_ip)"
    if command -v openssl >/dev/null 2>&1 \
       && ! openssl x509 -in "$SERVER_DIR/certs/cert.pem" -noout -text 2>/dev/null | grep -q "IP Address:$LAN"; then
      warn "existing certificate does not cover $LAN — regenerating (devices must trust the new one)"
      run bash "$SERVER_DIR/scripts/make-certs.sh" "$LAN" || warn "certificate regeneration failed"
    else
      info "certificate already present"
    fi
  else
    run bash "$SERVER_DIR/scripts/make-certs.sh" || warn "certificate generation failed"
    add_file "$SERVER_DIR/certs/cert.pem"
    add_file "$SERVER_DIR/certs/key.pem"
    add_file "$SERVER_DIR/hud/mia.cer"
  fi
else
  info "skip certificate (--no-cert)"
fi

# ------------------------------------------------------------------ 5. token
say "5/7 HUD access token"
if [ "$DO_TOKEN" = 1 ]; then
  if [ -f "$HERMES_ENV" ] && grep -qE '^(MIA_HUD_TOKEN|JARVIS_HUD_TOKEN)=' "$HERMES_ENV"; then
    info "token already present in $HERMES_ENV — keeping it"
  else
    TOKEN="mia-$($PYTHON -c 'import secrets;print(secrets.token_hex(3))')"
    if [ "$DRY_RUN" = 1 ]; then
      info "[dry-run] would append MIA_HUD_TOKEN to $HERMES_ENV"
    else
      mkdir -p "$(dirname "$HERMES_ENV")"
      printf '\n# Mia HUD access token (added by install.sh)\nMIA_HUD_TOKEN=%s\n' "$TOKEN" >> "$HERMES_ENV"
      MF_TOKEN_ADDED=1; MF_TOKEN_VAR="MIA_HUD_TOKEN"; MF_TOKEN_FILE="$HERMES_ENV"
      MF_TOKEN_SHA="$($PYTHON -c 'import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "$TOKEN")"
      info "token written to $HERMES_ENV (value: $TOKEN)"
    fi
  fi
else
  info "skip token (--no-token)"
fi

# Mia authenticates to Hermes with API_SERVER_KEY; it must live in the env file
# this user can read (running Mia as another user than Hermes is a common trap).
if [ -f "$HERMES_ENV" ] && ! grep -qE '^API_SERVER_KEY=' "$HERMES_ENV"; then
  warn "no API_SERVER_KEY in $HERMES_ENV — Mia will report 'Agent backend offline'"
  info "  fix: copy the key from the Hermes user's env file, e.g."
  info "       sudo grep '^API_SERVER_KEY=' /root/.hermes/.env >> $HERMES_ENV"
  info "  or run Mia as the same user that runs Hermes"
fi

# ---------------------------------------------------------------- 6. service
say "6/7 Service"
OS="$(uname -s)"
if [ "$DO_SERVICE" = 0 ]; then
  info "skip service (--no-service)"
elif [ "$OS" = "Darwin" ]; then
  SERVICE_KIND="launchd"
  SERVICE_DIR="${SERVICE_DIR:-$HOME/Library/LaunchAgents}"
  mkdir -p "$SERVICE_DIR" 2>/dev/null
  plist() { # $1 = label suffix, $2 = extra args
    local label="com.mia.$1"
    cat > "$SERVICE_DIR/$label.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>SoftResourceLimits</key><dict><key>NumberOfFiles</key><integer>8192</integer></dict>
  <key>HardResourceLimits</key><dict><key>NumberOfFiles</key><integer>8192</integer></dict>
  <key>ProgramArguments</key><array>
    <string>$($PYTHON -c 'import sys;print(sys.executable)')</string>
    <string>$SERVER_DIR/$2</string>
    $3
  </array>
  <key>WorkingDirectory</key><string>$SERVER_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/mia-$1.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/mia-$1.log</string>
</dict></plist>
PLIST
    add_file "$SERVICE_DIR/$label.plist"
    add_svc "$label"
  }
  if [ "$DRY_RUN" = 0 ]; then
    plist voice "server.py" ""
    if [ "$TTS_ENGINE" != "none" ] && [ "$TTS_ENGINE" != "piper" ]; then
      plist tts "scripts/gepard_tts.py" "<string>--serve</string><string>--port</string><string>$PORT_TTS</string><string>--engine</string><string>$TTS_ENGINE</string><string>--fallback-piper</string>"
    fi
    if [ "$DO_START" = 1 ]; then
      for s in $(cat "$TMP_MF/svc"); do
        launchctl bootout "gui/$(id -u)/$s" 2>/dev/null
        launchctl bootstrap "gui/$(id -u)" "$SERVICE_DIR/$s.plist" || warn "launchctl bootstrap failed for $s"
      done
    fi
  fi
else
  SERVICE_KIND="systemd"
  if [ "$MODE" = "system" ]; then
    SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"
    SCTL=(systemctl); WANTED="multi-user.target"
  else
    SERVICE_DIR="${SERVICE_DIR:-$HOME/.config/systemd/user}"
    SCTL=(systemctl --user); WANTED="default.target"
  fi
  unit() { # $1 = name, $2 = script, $3 = extra exec args
    local file="$SERVICE_DIR/mia-$1.service" caps="" deps=""
    # AmbientCapabilities is invalid for user services (systemd exits with
    # 218/CAPABILITIES); root does not need it either.
    if [ "$MODE" = "system" ] && [ "$(id -u)" != "0" ]; then
      caps="AmbientCapabilities=CAP_NET_BIND_SERVICE"
    fi
    # network-online.target only exists in the system manager; naming it from a
    # user unit just produces warnings.
    [ "$MODE" = "system" ] && deps="After=network-online.target
Wants=network-online.target"
    cat > "$file" <<UNIT
[Unit]
Description=Mia $1 ($REPO_DIR)
$deps

[Service]
Type=simple
WorkingDirectory=$SERVER_DIR
ExecStart=$($PYTHON -c 'import sys;print(sys.executable)') $SERVER_DIR/$2 $3
Restart=always
RestartSec=5
LimitNOFILE=8192
$caps
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=$WANTED
UNIT
    add_file "$file"
    add_svc "mia-$1"
  }
  if [ "$DRY_RUN" = 0 ]; then
    mkdir -p "$SERVICE_DIR"
    unit voice "server.py" ""
    if [ "$TTS_ENGINE" != "none" ] && [ "$TTS_ENGINE" != "piper" ]; then
      unit tts "scripts/gepard_tts.py" "--serve --port $PORT_TTS --engine $TTS_ENGINE --fallback-piper"
    fi
    if [ ! -d /run/systemd/system ]; then
      warn "systemd is not running here — unit written to $SERVICE_DIR, not activated"
    else
      run timeout 20 "${SCTL[@]}" daemon-reload 2>/dev/null || warn "daemon-reload failed"
      if [ "$DO_START" = 1 ]; then
        for s in $(cat "$TMP_MF/svc"); do
          run timeout 30 "${SCTL[@]}" enable --now "$s" || warn "could not start $s"
        done
      fi
    fi
  else
    printf '    [dry-run] would write units to %s for: mia-voice%s\n' "$SERVICE_DIR" \
      "$([ "$TTS_ENGINE" != "none" ] && [ "$TTS_ENGINE" != "piper" ] && echo ', mia-tts')"
  fi
fi

# --------------------------------------------------------------- 7. verify
say "7/7 Verification"
write_manifest
SERVICE_OK=""
HUD_TOKEN_VAL="$(grep -hE '^(MIA_HUD_TOKEN|JARVIS_HUD_TOKEN)=' "$HERMES_ENV" 2>/dev/null \
                 | tail -1 | cut -d= -f2- | tr -d '\"'"'"' ')"
if [ "$DRY_RUN" = 0 ] && [ "$DO_SERVICE" = 1 ] && [ "$DO_START" = 1 ]; then
  if command -v curl >/dev/null 2>&1; then
    info "waiting for the voice server to warm up (up to 60 s)…"
    SERVICE_OK="no"
    for _ in $(seq 1 20); do
      if curl -s -m 2 -H "X-Mia-Token: ${HUD_TOKEN_VAL:-}" \
           "http://127.0.0.1:8765/api/hud-config" 2>/dev/null | grep -q tts_provider; then
        SERVICE_OK="yes"; break
      fi
      sleep 3
    done
    if [ "$SERVICE_OK" = "yes" ]; then
      CUR_JSON="$(curl -s -m 3 -H "X-Mia-Token: ${HUD_TOKEN_VAL:-}" \
                     http://127.0.0.1:8765/api/hud-config || true)"
      info "voice server up: $CUR_JSON"
      [ -x "$SERVER_DIR/scripts/mia-health.sh" ] && bash "$SERVER_DIR/scripts/mia-health.sh" || true
    else
      warn "the voice server is not answering yet — here is what it says:"
      if [ ${#SCTL[@]} -gt 0 ] && [ -d /run/systemd/system ]; then
        timeout 10 "${SCTL[@]}" --no-pager status mia-voice 2>&1 | tail -n 15 | sed 's/^/    /' || true
        journal_tail mia-voice 25 | sed 's/^/    /' || true
      elif [ -f "$SERVER_DIR/logs/mia.out" ]; then
        tail -n 20 "$SERVER_DIR/logs/mia.out" | sed 's/^/    /'
      fi
      warn "fix the error above, then run: ./start.sh"
    fi
  fi
fi

cat <<DONE

$([ "$DRY_RUN" = 1 ] && printf '\033[1;33mDry run complete — nothing was changed.\033[0m'    || { [ "$SERVICE_OK" = "no" ] && printf '\033[1;33mInstalled, but the service is NOT running (see above).\033[0m'         || printf '\033[1;32mInstalled.\033[0m'; })

  config      $CFG
  manifest    $MANIFEST
  python      $($PYTHON -c 'import sys;print(sys.executable)')
  mode        $MODE
  voices      $(ls "$SERVER_DIR/voices" 2>/dev/null | grep -c '\.onnx$') model(s)
  service     ${SERVICE_KIND:-none}${SERVICE_DIR:+ ($SERVICE_DIR)}${SERVICE_OK:+ [running: $SERVICE_OK]}
  tts engine  $TTS_ENGINE
  HUD URL     $(hud_url)


Next steps
  1. Hermes: point your local model at it (Qwen3 with thinking disabled) —
     Mia only forces the reply language, the model lives in Hermes' config.
  2. Open the HUD and enter the token from $HERMES_ENV.
  3. If you switched TTS to Gepard: start the TTS service and set
     tts.provider: http (see docs/SETUP.md).

$( [ "$MODE" = "user" ] && printf 'Keep it running after logout/reboot:  loginctl enable-linger %s\n\n' "$(id -un)" )

Day to day:  ./start.sh   ·   ./stop.sh   ·   ./stop.sh --status
Remove everything again:  ./uninstall.sh --dry-run   then   ./uninstall.sh
DONE

if [ "$DO_OPEN" = 1 ] && [ "$DRY_RUN" = 0 ] && [ -x "$REPO_DIR/start.sh" ]; then
  exec "$REPO_DIR/start.sh"
fi
