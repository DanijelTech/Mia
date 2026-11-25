#!/bin/bash
# Health check for every Mia component. Reads ports from config/server.yaml so it
# also works for a user install (HUD on :8766 instead of :443).
cd "$(dirname "$0")/.." || exit 1
ok(){ printf "%-24s %s\n" "$1" "$2"; }

cfg() {  # cfg <dotted.key|list.key> [default]
  python3 - "$1" "${2:-}" <<'PY' 2>/dev/null
import sys, yaml
d = yaml.safe_load(open("config/server.yaml")) or {}
cur = d
for part in sys.argv[1].split("."):
    cur = cur.get(part) if isinstance(cur, dict) else None
if isinstance(cur, list) and cur:
    print(cur[0])
elif cur is None:
    print(sys.argv[2])
else:
    print(cur)
PY
}

WS_PORT="$(cfg server.port 8765)"; WS_PORT="${WS_PORT:-8765}"
TLS_PORT="$(cfg server.tls_ports 443)"; TLS_PORT="${TLS_PORT:-443}"
DASH_PORT="$(cfg server.dashboard_proxy.port 9443)"; DASH_PORT="${DASH_PORT:-9443}"
TOKEN="$(grep -hE '^(MIA_HUD_TOKEN|JARVIS_HUD_TOKEN)=' ~/.hermes/.env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')"

API="http://127.0.0.1:$WS_PORT"
HUD="https://127.0.0.1"
[ "$TLS_PORT" != "443" ] && HUD="https://127.0.0.1:$TLS_PORT"

# voice server: a token answer of 401 still proves it is listening
CODE=$(curl -s -m 3 -o /dev/null -w '%{http_code}' -H "X-Mia-Token: ${TOKEN:-}" "$API/api/hud-config")
case "$CODE" in
  200) ok "voice ws ($WS_PORT)" "OK" ;;
  401) ok "voice ws ($WS_PORT)" "OK (token mismatch?)" ;;
  *)   ok "voice ws ($WS_PORT)" "DOWN" ;;
esac
curl -sk -m 3 -o /dev/null "$HUD/hud/" && ok "HUD (${TLS_PORT})" OK || ok "HUD (${TLS_PORT})" DOWN
curl -sk -m 3 -o /dev/null "https://127.0.0.1:$DASH_PORT/" && ok "dash proxy ($DASH_PORT)" OK || ok "dash proxy ($DASH_PORT)" DOWN
curl -s  -m 3 -o /dev/null http://127.0.0.1:9119/ && ok "hermes dashboard (lo)" OK || ok "hermes dashboard (lo)" "DOWN (optional)"

KEY=$(grep '^API_SERVER_KEY=' ~/.hermes/.env 2>/dev/null | cut -d= -f2)
if [ -n "$KEY" ] && curl -s -m 5 -H "Authorization: Bearer $KEY" http://127.0.0.1:8642/health | grep -q ok; then
  ok "hermes api (8642)" OK
else
  ok "hermes api (8642)" "DOWN (start: hermes gateway)"
fi

# optional external TTS service (tts.provider: http)
TTS_URL="$(cfg tts.http.url '')"
if [ "$(cfg tts.provider piper)" = "http" ] && [ -n "$TTS_URL" ]; then
  BODY=$(curl -s -m 3 "${TTS_URL%/tts}/health")
  if [ -n "$BODY" ]; then
    ok "tts service" "OK $(printf '%s' "$BODY" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("engine","?"),d.get("device","?"))' 2>/dev/null)"
  else
    ok "tts service" "DOWN (${TTS_URL%/tts}/health)"
  fi
fi

# GPU note: if the LLM lives on this box, Whisper should stay on CPU
STT_DEV="$(cfg stt.device cpu)"
if command -v nvidia-smi >/dev/null 2>&1; then
  used=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null | tr '\n' ' ')
  [ -n "$used" ] && ok "gpu processes" "$used"
  [ "$STT_DEV" = "cpu" ] || ok "stt.device" "$STT_DEV (holds VRAM the LLM may want)"
fi
