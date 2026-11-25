#!/bin/bash
# One-time generation of the boot greeting with the LOCAL Piper voice.
#   scripts/make-boot-audio.sh            # generic greeting
#   scripts/make-boot-audio.sh YourName    # greets by name
cd "$(dirname "$0")/.."
VOICE="${PIPER_MODEL:-voices/sl_SI-artur-medium.onnx}"
BIN="${PIPER_BIN:-piper}"
NAME="${1:-}"

if [ ! -f "$VOICE" ]; then
  echo "Missing voice: $VOICE - run scripts/get-voice.sh sl" >&2
  exit 1
fi
command -v "$BIN" >/dev/null 2>&1 || { echo "piper not found in PATH (pip install piper-tts)" >&2; exit 1; }

mkdir -p hud/audio
gen() {
  printf '%s' "$2" | "$BIN" -m "$VOICE" -f "hud/audio/boot_$1.wav"
  echo "hud/audio/boot_$1.wav"
}
SUFFIX=""
[ -n "$NAME" ] && SUFFIX=", $NAME"
gen morning   "Sistemi so na voljo. Dobro jutro$SUFFIX."
gen afternoon "Sistemi so na voljo. Dober dan$SUFFIX."
gen evening   "Sistemi so na voljo. Dober večer$SUFFIX."
ls -la hud/audio/
