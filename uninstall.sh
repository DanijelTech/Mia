#!/usr/bin/env bash
# Mia — uninstaller. Removes what ./install.sh created (services, units, certs,
# voices, token line, optionally pip packages), using the install manifest.
#
#   ./uninstall.sh --dry-run        # show exactly what would be removed
#   sudo ./uninstall.sh --yes       # root/system install: services + files
#   ./uninstall.sh --purge-deps     # also pip-uninstall the packages it added
#   ./uninstall.sh --keep-data      # keep voices/certs/audio/logs/config
#
# What it never touches: Hermes itself, its sessions/memory, your models, the
# Mia source tree (delete the folder yourself if you want that too).
set -uo pipefail

ASSUME_YES=0
DRY_RUN=0
PURGE_DEPS=0
KEEP_DATA=0
MANIFEST=""
PYTHON="${PYTHON:-python3}"

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --purge-deps) PURGE_DEPS=1 ;;
    --keep-data) KEEP_DATA=1 ;;
    --manifest) MANIFEST="${2:-}"; shift ;;
    --python) PYTHON="${2:-}"; shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if [ "$DRY_RUN" = 1 ]; then printf '    [dry-run] %s\n' "$*"; return 0; fi
  "$@"
}
confirm() {
  [ "$ASSUME_YES" = 1 ] && return 0
  printf '    %s [y/N] ' "$1"
  read -r a || a=""
  case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$MANIFEST" ]; then
  if [ -f "${XDG_STATE_HOME:-/var/lib}/mia/install-manifest.json" ] && [ "$(id -u)" = "0" ]; then
    MANIFEST="${XDG_STATE_HOME:-/var/lib}/mia/install-manifest.json"
  elif [ -f "${XDG_STATE_HOME:-$HOME/.local/state}/mia/install-manifest.json" ]; then
    MANIFEST="${XDG_STATE_HOME:-$HOME/.local/state}/mia/install-manifest.json"
  elif [ -f "$REPO_DIR/.mia-install-manifest.json" ]; then
    MANIFEST="$REPO_DIR/.mia-install-manifest.json"
  fi
fi

say "Mia uninstaller"
if [ -n "$MANIFEST" ] && [ -f "$MANIFEST" ]; then
  info "manifest: $MANIFEST"
else
  warn "no install manifest found — falling back to known locations inside $REPO_DIR"
fi
[ "$DRY_RUN" = 1 ] && info "dry-run: nothing will be removed"

# Read the manifest into shell-friendly files (never eval it).
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
: > "$TMP/files"; : > "$TMP/dirs"; : > "$TMP/pkg"; : > "$TMP/svc"
MF_MODE=""; MF_KIND=""; MF_SVC_DIR=""; MF_TOKEN_FILE=""; MF_TOKEN_VAR=""; MF_TOKEN_SHA=""; MF_TOKEN_ADDED=0

if [ -n "$MANIFEST" ] && [ -f "$MANIFEST" ]; then
  $PYTHON - "$MANIFEST" "$TMP" <<'PY' || die "cannot parse manifest"
import json, pathlib, sys
m = json.loads(pathlib.Path(sys.argv[1]).read_text())
tmp = pathlib.Path(sys.argv[2])
for key, name in (("files", "files"), ("dirs", "dirs"), ("packages", "pkg"), ("services", "svc")):
    (tmp / name).write_text("\n".join(m.get(key) or []) + ("\n" if m.get(key) else ""))
tok = m.get("token") or {}
scalars = {
    "MF_MODE": m.get("mode") or "",
    "MF_KIND": m.get("service_kind") or "",
    "MF_SVC_DIR": m.get("service_dir") or "",
    "MF_TOKEN_FILE": tok.get("file") or "",
    "MF_TOKEN_VAR": tok.get("var") or "",
    "MF_TOKEN_SHA": tok.get("sha256") or "",
    "MF_TOKEN_ADDED": "1" if tok.get("added") else "0",
}
(tmp / "scalars").write_text("\n".join(f"{k}={v}" for k, v in scalars.items()) + "\n")
print(f"    mode={m.get('mode')} version={m.get('version')} packages={len(m.get('packages') or [])} files={len(m.get('files') or [])}")
PY
  # shellcheck disable=SC1091
  while IFS='=' read -r k v; do [ -n "$k" ] && export "$k=$v"; done < "$TMP/scalars"
else
  # Best-effort fallback: the paths install.sh would have created in this repo.
  printf '%s\n' \
    "$REPO_DIR/server/voices" \
    "$REPO_DIR/server/certs" \
    "$REPO_DIR/server/hud/audio" \
    "$REPO_DIR/server/logs" > "$TMP/dirs"
  printf '%s\n' \
    "$REPO_DIR/server/hud/mia.cer" \
    "$REPO_DIR/server/config/server.yaml" > "$TMP/files"
fi

# ----------------------------------------------------------- path validation
ALLOWED_PREFIXES=("/etc/systemd/system" "/etc/systemd/user" "/var/lib/mia"
                  "$HOME" "$REPO_DIR")
[ -n "${MF_SVC_DIR:-}" ] && ALLOWED_PREFIXES+=("$MF_SVC_DIR")

path_ok() {
  local p="$1" prefix
  case "$p" in ""|"/"|"/etc"|"/usr"|"/var"|"$HOME"|"$REPO_DIR"|"$REPO_DIR/server") return 1 ;; esac
  case "$p" in "$HOME"/.hermes|"$HOME"/.hermes/*) return 1 ;; esac   # Hermes credentials live there
  for prefix in "${ALLOWED_PREFIXES[@]}"; do
    [ -n "$prefix" ] || continue
    case "$p" in "$prefix"/*) return 0 ;; esac
  done
  return 1
}

# ------------------------------------------------------------------ 1. services
say "1/5 Services"
if [ -s "$TMP/svc" ]; then
  SVC_COUNT="$(grep -c . "$TMP/svc")"
  if [ "$MF_KIND" = "launchd" ]; then
    while IFS= read -r svc; do
      [ -n "$svc" ] || continue
      info "stopping $svc"
      run launchctl bootout "gui/$(id -u)/$svc" 2>/dev/null || true
    done < "$TMP/svc"
  else
    if [ "$(id -u)" = "0" ]; then SCTL=(systemctl); else SCTL=(systemctl --user); fi
    while IFS= read -r svc; do
      [ -n "$svc" ] || continue
      info "stopping and disabling $svc"
      run "${SCTL[@]}" disable --now "$svc" 2>/dev/null || true
    done < "$TMP/svc"
    run "${SCTL[@]}" daemon-reload 2>/dev/null || true
  fi
  info "$SVC_COUNT service(s) handled"
else
  info "no services recorded"
  # still try the well-known names, in case the manifest is missing
  SYSTEMCTL="systemctl"; [ "$(id -u)" != "0" ] && SYSTEMCTL="systemctl --user"
  for svc in mia-voice mia-tts; do
    $SYSTEMCTL is-enabled "$svc" >/dev/null 2>&1 && {
      info "stopping leftover $svc"
      run "${SCTL[@]}" disable --now "$svc" 2>/dev/null || true
    }
  done
fi

# --------------------------------------------------------------------- 2. files
say "2/5 Files created by the installer"
REMOVED=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if ! path_ok "$f"; then warn "refusing to delete outside allowed roots: $f"; continue; fi
  [ -e "$f" ] || continue
  case "$f" in
    */server/config/server.yaml) [ "$KEEP_DATA" = 1 ] && { info "keep $f"; continue; } ;;
    */voices/*|*/certs/*|*/hud/audio/*|*/logs/*) [ "$KEEP_DATA" = 1 ] && { info "keep $f"; continue; } ;;
  esac
  run rm -f -- "$f" && REMOVED=$((REMOVED+1))
done < "$TMP/files"

if [ -s "$TMP/dirs" ]; then
  # deepest first, then drop the dirs themselves when empty (or when not --keep-data)
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    path_ok "$d" || { warn "refusing to delete outside allowed roots: $d"; continue; }
    [ -d "$d" ] || continue
    if [ "$KEEP_DATA" = 1 ]; then
      info "keep $d"
    else
      run rm -rf -- "$d" && REMOVED=$((REMOVED+1))
    fi
  done < "$TMP/dirs"
fi
info "$REMOVED path(s) processed"

# --------------------------------------------------------------------- 3. token
say "3/5 HUD token in the Hermes env file"
if [ "${MF_TOKEN_ADDED:-0}" = "1" ] && [ -n "${MF_TOKEN_FILE:-}" ] && [ -f "$MF_TOKEN_FILE" ]; then
  CUR_HASH=""
  if [ -n "${MF_TOKEN_VAR:-}" ]; then
    CUR="$($PYTHON - "$MF_TOKEN_FILE" "$MF_TOKEN_VAR" <<'PY'
import pathlib, sys
path, var = sys.argv[1], sys.argv[2]
for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
    if line.startswith(var + "="):
        print(line.split("=", 1)[1].strip().strip('"').strip("'")); break
PY
)"
    [ -n "$CUR" ] && CUR_HASH="$($PYTHON -c 'import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "$CUR")"
  fi
  if [ -n "$CUR_HASH" ] && [ "$CUR_HASH" = "${MF_TOKEN_SHA:-}" ]; then
    info "removing $MF_TOKEN_VAR from $MF_TOKEN_FILE"
    if [ "$DRY_RUN" = 1 ]; then
      printf '    [dry-run] strip %s line(s) from %s\n' "$MF_TOKEN_VAR" "$MF_TOKEN_FILE"
    else
      $PYTHON - "$MF_TOKEN_FILE" "$MF_TOKEN_VAR" <<'PY'
import pathlib, sys
path, var = pathlib.Path(sys.argv[1]), sys.argv[2]
lines = path.read_text().splitlines()
kept, dropped = [], 0
for line in lines:
    if line.startswith(var + "=") or line.strip() == "# Mia HUD access token (added by install.sh)":
        dropped += 1
        continue
    kept.append(line)
while kept and kept[-1].strip() == "":
    kept.pop()
path.write_text("\n".join(kept) + "\n")
print(f"    removed {dropped} line(s)")
PY
    fi
  else
    warn "token in $MF_TOKEN_FILE changed since install — leaving it in place"
  fi
elif [ "${MF_TOKEN_ADDED:-0}" = "1" ]; then
  warn "token file $MF_TOKEN_FILE is gone — nothing to clean"
else
  info "installer did not create a token — nothing to clean"
fi

# ------------------------------------------------------------------ 4. packages
say "4/5 Python packages"
if [ "$PURGE_DEPS" = 0 ]; then
  if [ -s "$TMP/pkg" ]; then
    info "kept (use --purge-deps to remove):"
    sed 's/^/      /' "$TMP/pkg"
  else
    info "none recorded"
  fi
else
  if [ -s "$TMP/pkg" ]; then
    warn "pip packages can be shared with other software on this machine."
    if confirm "Uninstall $(grep -c . "$TMP/pkg") package(s) from $($PYTHON -c 'import sys;print(sys.prefix)')?"; then
      PIP_FLAGS=(); [ "$(id -u)" != "0" ] && PIP_FLAGS+=(--user)
      while IFS= read -r pkg; do
        [ -n "$pkg" ] || continue
        info "uninstalling $pkg"
        if [ "$DRY_RUN" = 1 ]; then
          printf '    [dry-run] %s -m pip uninstall -y %s %s\n' "$PYTHON" "${PIP_FLAGS[*]}" "$pkg"
        else
          $PYTHON -m pip uninstall -y "${PIP_FLAGS[@]}" "$pkg" >/dev/null 2>&1 \
            || $PYTHON -m pip uninstall -y --break-system-packages "$pkg" >/dev/null 2>&1 \
            || warn "could not uninstall $pkg"
        fi
      done < "$TMP/pkg"
    else
      info "skipped by user"
    fi
  else
    info "none recorded"
  fi
fi

# ------------------------------------------------------------------ 5. manifest
say "5/5 Manifest and state"
if [ -n "$MANIFEST" ] && [ -f "$MANIFEST" ]; then
  run rm -f -- "$MANIFEST"
  run rmdir "$(dirname "$MANIFEST")" 2>/dev/null || true
  [ "$DRY_RUN" = 1 ] && info "would remove $MANIFEST" || info "removed $MANIFEST"
else
  info "no manifest to remove"
fi

cat <<DONE

$([ "$DRY_RUN" = 1 ] && printf '\033[1;33mDry run complete — nothing was removed.\033[0m' || printf '\033[1;32mUninstalled.\033[0m')

Left untouched on purpose:
  • Hermes Agent and its data (~/.hermes, sessions, memory)
  • your LLM models
  • the Mia source tree: $REPO_DIR
    (delete it yourself with: rm -rf "$REPO_DIR")

Check leftovers manually if you used --keep-data or skipped packages:
  ls -la "$REPO_DIR/server/certs" "$REPO_DIR/server/voices" 2>/dev/null
DONE
