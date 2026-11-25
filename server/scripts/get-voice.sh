#!/bin/bash
# Download local Piper voices into server/voices/ (gitignored, ~63-77 MB each).
#   scripts/get-voice.sh            # sl + sr
#   scripts/get-voice.sh sl         # Slovenian only
set -u
cd "$(dirname "$0")/.."
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"
mkdir -p voices

fetch() {  # $1 = repo subpath, $2 = model name
  local rel="$1" name="$2" ext
  for ext in onnx onnx.json; do
    if [ -s "voices/$name.$ext" ]; then
      echo "have voices/$name.$ext"
      continue
    fi
    curl -fL --progress-bar "$BASE/$rel/$name.$ext" -o "voices/$name.$ext" || return 1
  done
  echo "OK voices/$name.onnx"
}

case "${1:-all}" in
  sl|all) fetch sl/sl_SI/artur/medium sl_SI-artur-medium || exit 1 ;;
esac
case "${1:-all}" in
  sr|all) fetch sr/sr_RS/serbski_institut/medium sr_RS-serbski_institut-medium || exit 1 ;;
esac

echo
echo "Voices carry their own licenses (see voices/*.onnx.json and MODEL_CARD upstream)."
echo "Piper itself is GPL-3.0; this repo runs it as a separate process (tts.piper.mode: cli)."
