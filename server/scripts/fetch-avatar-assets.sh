#!/usr/bin/env bash
# Fetch the free Ready Player Me female sample avatar used by the HUD's 3D layer.
# The model is hosted in the MIT-licensed readyplayerme/visage repository.
# Run once after install; it is not committed to git (see models/README.md).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HERE/../hud/avatar/models}"
BASE="https://raw.githubusercontent.com/readyplayerme/visage/v2.0.0/public"
mkdir -p "$DEST"
fetch() {
  local name="$1"
  if [ -s "$DEST/$name" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "already present: $DEST/$name"
    return
  fi
  echo "downloading $name"
  curl -fL --retry 3 --max-time 120 "$BASE/$name" -o "$DEST/$name.tmp"
  mv "$DEST/$name.tmp" "$DEST/$name"
}
fetch female.glb
fetch femaleIdle.glb
[ -f "$DEST/female.glb" ] && mv "$DEST/female.glb" "$DEST/mia-female.glb"
[ -f "$DEST/femaleIdle.glb" ] && mv "$DEST/femaleIdle.glb" "$DEST/mia-female-idle.glb"
echo "avatar assets ready in $DEST"
