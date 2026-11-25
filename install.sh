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
#   ./install.sh --dry-run            # show every action, change nothing
#
# Common options:
#   --yes                 no prompts
#   --mode system|user    force install mode (default: root -> system)
#   --python PATH         interpreter to install into (default: python3)
#   --with-gepard         install accelerate/NeMo/gepard-inference + TTS service
#   --no-stt-deps         skip RealtimeSTT/torch (if you already have them)
#   --no-deps             skip every pip step
#   --voice sl|sr|all|none
#   --no-cert             skip TLS certificate generation
#   --no-service          do not install/enable a service
#   --no-start            install the unit but do not start it
#   --no-token            do not touch ~/.hermes/.env
#   --service-dir DIR     where unit/plist files go (default: system-dependent)
#   --hermes-env PATH     env file for the HUD token (default: ~/.hermes/.env)
#
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$REPO_DIR/server"
VERSION="$(git -C "$REPO_DIR" describe --tags --always 2>/dev/null || echo unknown)"

MODE=""
PYTHON="${PYTHON:-python3}"
WITH_GEPARD=0
DO_DEPS=1
DO_STT_DEPS=1
DO_VOICE=1
VOICE_LANG="sl"
DO_CERT=1
DO_SERVICE=1
DO_START=1
DO_TOKEN=1
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
    --with-gepard) WITH_GEPARD=1 ;;
    --no-stt-deps) DO_STT_DEPS=0 ;;
    --no-deps) DO_DEPS=0 ;;
    --voice) VOICE_LANG="${2:-}"; shift ;;
    --no-cert) DO_CERT=0 ;;
    --no-service) DO_SERVICE=0 ;;
    --no-start) DO_START=0 ;;
    --no-token) DO_TOKEN=0 ;;
    --service-dir) SERVICE_DIR="${2:-}"; shift ;;
    --hermes-env) HERMES_ENV="${2:-}"; shift ;;
    --port-tts) PORT_TTS="${2:-}"; shift ;;
    -h|--help) sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

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
  pip_install RealtimeSTT || die "RealtimeSTT is required for speech-to-text"
else
  info "skip RealtimeSTT (--no-stt-deps)"
fi
pip_install piper-tts || warn "piper-tts missing: local voice unavailable"

if [ "$WITH_GEPARD" = 1 ]; then
  say "1b/7 Gepard TTS extras (heavy, ~3 GB)"
  pip_install accelerate || warn "accelerate missing: no GPU/RAM layer split"
  if confirm "Install NeMo toolkit for the NanoCodec (large download)?"; then
    pip_install "nemo_toolkit[tts]" || warn "nemo_toolkit failed — Gepard cannot decode audio"
  fi
  pip_install "git+https://github.com/nineninesix-ai/gepard-inference" \
    || warn "gepard-inference failed — start the TTS service with --engine piper instead"
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

# ------------------------------------------------------------------ 4. certs
say "4/7 TLS certificate (required for the browser microphone)"
if [ "$DO_CERT" = 1 ]; then
  if [ -f "$SERVER_DIR/certs/cert.pem" ]; then
    info "certificate already present"
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
    if [ "$WITH_GEPARD" = 1 ]; then
      plist tts "scripts/gepard_tts.py" "<string>--serve</string><string>--port</string><string>$PORT_TTS</string><string>--engine</string><string>gepard</string><string>--fallback-piper</string>"
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
    local file="$SERVICE_DIR/mia-$1.service"
    cat > "$file" <<UNIT
[Unit]
Description=Mia $1 ($REPO_DIR)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SERVER_DIR
ExecStart=$($PYTHON -c 'import sys;print(sys.executable)') $SERVER_DIR/$2 $3
Restart=always
RestartSec=5
LimitNOFILE=8192
AmbientCapabilities=CAP_NET_BIND_SERVICE
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
    if [ "$WITH_GEPARD" = 1 ]; then
      unit tts "scripts/gepard_tts.py" "--serve --port $PORT_TTS --engine gepard --fallback-piper"
    fi
    run "${SCTL[@]}" daemon-reload 2>/dev/null || warn "systemctl not available here (unit written, not activated)"
    if [ "$DO_START" = 1 ]; then
      for s in $(cat "$TMP_MF/svc"); do run "${SCTL[@]}" enable --now "$s"; done
    fi
  else
    printf '    [dry-run] would write units to %s for: mia-voice%s\n' "$SERVICE_DIR" \
      "$([ "$WITH_GEPARD" = 1 ] && echo ', mia-tts')"
  fi
fi

# --------------------------------------------------------------- 7. verify
say "7/7 Verification"
write_manifest
if [ "$DRY_RUN" = 0 ] && [ "$DO_SERVICE" = 1 ] && [ "$DO_START" = 1 ]; then
  if command -v curl >/dev/null 2>&1; then
    info "waiting for the voice server to warm up (up to 60 s)…"
    for _ in $(seq 1 20); do
      curl -s -m 2 http://127.0.0.1:8765/api/hud-config >/dev/null 2>&1 && break
      sleep 3
    done
    curl -s -m 3 http://127.0.0.1:8765/api/hud-config || warn "voice server not answering yet"
    echo
    [ -x "$SERVER_DIR/scripts/mia-health.sh" ] && bash "$SERVER_DIR/scripts/mia-health.sh" || true
  fi
fi

cat <<DONE

$([ "$DRY_RUN" = 1 ] && printf '\033[1;33mDry run complete — nothing was changed.\033[0m' || printf '\033[1;32mInstalled.\033[0m')

  config      $CFG
  manifest    $MANIFEST
  python      $($PYTHON -c 'import sys;print(sys.executable)')
  mode        $MODE
  voices      $(ls "$SERVER_DIR/voices" 2>/dev/null | grep -c '\.onnx$') model(s)
  service     ${SERVICE_KIND:-none}${SERVICE_DIR:+ ($SERVICE_DIR)}
  HUD         https://$(hostname 2>/dev/null || echo localhost)/hud/

Next steps
  1. Hermes: point your local model at it (Qwen3 with thinking disabled) —
     Mia only forces the reply language, the model lives in Hermes' config.
  2. Open the HUD and enter the token from $HERMES_ENV.
  3. If you switched TTS to Gepard: start the TTS service and set
     tts.provider: http (see docs/SETUP.md).

Remove everything again:  ./uninstall.sh --dry-run   then   ./uninstall.sh
DONE
