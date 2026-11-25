#!/usr/bin/env bash
# Pull the latest Mia into this clone and refresh the running install.
# Your own files (server.yaml, voices, certs, logs, token) are gitignored and are
# never touched.
#
#   ./update.sh                 # fetch, fast-forward, restart if needed, remind about the HUD
#   ./update.sh --check         # only show what is new
#   ./update.sh --no-restart    # pull, do not touch the service
#   ./update.sh --branch main   # different branch
#
# Exit codes: 0 updated or already current · 1 dirty tree · 2 git error
set -uo pipefail
cd "$(dirname "$0")"

BRANCH="main"
CHECK_ONLY=0
DO_RESTART=1
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --no-restart) DO_RESTART=0 ;;
    --branch) BRANCH="${2:-main}"; shift ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

command -v git >/dev/null 2>&1 || { echo "git not installed" >&2; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git clone: $PWD" >&2; exit 2; }

# ---------------------------------------------------------------- dirty tree
DIRTY="$(git status --porcelain --untracked-files=no 2>/dev/null)"
if [ -n "$DIRTY" ]; then
  warn "you have local changes in tracked files:"
  printf '%s\n' "$DIRTY" | sed 's/^/      /'
  info "keep them:   git stash && ./update.sh && git stash pop"
  info "drop them:   git checkout -- .   (your server.yaml/voices/certs are safe)"
  exit 1
fi

# ----------------------------------------------------------------- fetch/new
CURRENT="$(git rev-parse --short HEAD 2>/dev/null || echo "(brez commitov)")"
say "Mia update ($(git rev-parse --abbrev-ref HEAD) @ $CURRENT)"
git fetch --quiet origin "$BRANCH" || { echo "git fetch failed" >&2; exit 2; }

NEW="$(git rev-parse --short "origin/$BRANCH")"
BEHIND="$(git rev-list --count "HEAD..origin/$BRANCH" 2>/dev/null || echo "")"
[ -z "$BEHIND" ] && BEHIND="$(git rev-list --count "origin/$BRANCH" 2>/dev/null || echo 0)"
if [ "${BEHIND:-0}" = "0" ]; then
  info "already up to date ($CURRENT)"
  exit 0
fi

old="$(git rev-parse HEAD 2>/dev/null || echo "")"
info "$BEHIND new commit(s) on origin/$BRANCH:"
git --no-pager log --oneline "HEAD..origin/$BRANCH" | sed 's/^/      /'
echo
info "files touched:"
git --no-pager diff --name-status "$old..origin/$BRANCH" | sed 's/^/      /'

if [ "$CHECK_ONLY" = 1 ]; then
  echo
  info "nothing changed (--check). Run ./update.sh to apply."
  exit 0
fi

# -------------------------------------------------------------------- pull
echo
say "Fast-forwarding $CURRENT -> $NEW"
git merge --ff-only --quiet "origin/$BRANCH" || { echo "fast-forward failed (diverged history?)" >&2; exit 2; }
CHANGED="$([ -n "$old" ] && git diff --name-only "$old..HEAD" || git ls-tree -r --name-only HEAD)"

needs_install=0
grep -qE '^(install\.sh|launchd/|server/scripts/mia-(start|stop|restart|health)\.sh|server/scripts/make-certs\.sh)' <<<"$CHANGED" && needs_install=1
hud_changed=0
grep -qE '^server/(hud/|server\.py|tts\.py)' <<<"$CHANGED" && hud_changed=1

# ----------------------------------------------------------------- restart
if [ "$DO_RESTART" = 1 ]; then
  if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
    if [ "$(id -u)" = "0" ]; then SCTL=(systemctl); else SCTL=(systemctl --user); fi
    RESTARTED=0
    for unit in mia-tts mia-voice; do
      if timeout 5 "${SCTL[@]}" is-active --quiet "$unit" 2>/dev/null; then
        if timeout 20 "${SCTL[@]}" restart "$unit" 2>/dev/null; then
          info "restarted $unit"
          RESTARTED=1
        else
          warn "could not restart $unit"
        fi
      fi
    done
    if [ "$RESTARTED" = 0 ]; then
      info "no active Mia unit to restart (start it with ./start-mia.sh)"
    fi
  elif [ -f server/logs/mia.pid ]; then
    info "background mode detected — restarting via stop-mia.sh/start-mia.sh"
    ./stop-mia.sh >/dev/null 2>&1 && ./start-mia.sh --no-open >/dev/null 2>&1 \
      && info "restarted in the background" || warn "restart failed, run ./start-mia.sh"
  else
    info "nothing running (start it with ./start-mia.sh)"
  fi
fi

echo
say "Updated to $(git rev-parse --short HEAD)"
[ "$needs_install" = 1 ] && warn "installer/service files changed — run: ./install.sh --yes"
[ "$hud_changed" = 1 ] && info "HUD files changed — hard-refresh the page: Ctrl+Shift+R"
info "check with: ./stop-mia.sh --status   ·   server/scripts/mia-health.sh"
exit 0
