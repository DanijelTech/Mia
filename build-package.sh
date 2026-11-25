#!/usr/bin/env bash
# Build a distributable tarball of Mia (source + installers) for an offline machine.
#   ./build-package.sh [VERSION]
# Excludes local state: voices, certs, logs, boot audio, dist/, caches, server.yaml.
set -uo pipefail
cd "$(dirname "$0")"
REPO="$PWD"
VER="${1:-$(git describe --tags --always 2>/dev/null || date +%Y%m%d)}"
NAME="mia-$VER"
OUT="$REPO/dist/$NAME.tar.gz"
mkdir -p "$REPO/dist"
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$NAME"
tar -cf - \
  --exclude='./.git' --exclude='./dist' --exclude='__pycache__' \
  --exclude='./server/voices' --exclude='./server/certs' --exclude='./server/logs' \
  --exclude='./server/hud/audio' --exclude='./server/config/server.yaml' . \
  | tar -xf - -C "$STAGE/$NAME" || { echo "staging failed" >&2; exit 1; }
tar -czf "$OUT" -C "$STAGE" "$NAME"
echo "built $OUT ($(du -h "$OUT" | cut -f1))"
echo
echo "install on the target (offline is fine):"
echo "  tar xzf $(basename "$OUT") && cd $NAME"
echo "  sudo ./install.sh --voice none      # then copy server/voices/*.onnx manually"
