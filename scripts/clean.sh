#!/usr/bin/env bash
# Reset NaturalskWeb dev state: stop servers, drop DB + uploads + avatars,
# stop camoufox-cli browser daemon. Safe to re-run.
#
# Usage:
#   ./scripts/clean.sh           # default — clean everything below
#   ./scripts/clean.sh --keep-snapshots   # keep camoufox browser sessions open
#   ./scripts/clean.sh --dry-run          # show what would be removed

set -euo pipefail

# Resolve repo root from this script's location, so `cd anywhere && scripts/clean.sh` works.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
cd "$REPO_ROOT"

KEEP_SNAPSHOTS=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --keep-snapshots) KEEP_SNAPSHOTS=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,9p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  [dry-run] %s\n' "$*"
  else
    eval "$@"
  fi
}

echo "==> Stopping dev servers (uvicorn, vite)"
run "pkill -f 'uvicorn app.main' 2>/dev/null || true"
run "pkill -f 'vite' 2>/dev/null || true"

echo "==> Removing SQLite DB and initial password"
run "rm -f backend/data/naturalsk.db backend/data/naturalsk.db-shm backend/data/naturalsk.db-wal"
run "rm -f backend/data/initial_admin_password.txt"

echo "==> Removing app logs"
run "rm -rf backend/data/logs"

echo "==> Removing avatar files (keeping the dir and .gitkeep)"
if [[ -d backend/data/avatars ]]; then
  run "find backend/data/avatars -type f ! -name .gitkeep -delete"
fi

echo "==> Removing temporary uploads"
if [[ -d backend/uploads ]]; then
  run "find backend/uploads -mindepth 1 -delete"
fi

if [[ $KEEP_SNAPSHOTS -eq 0 ]]; then
  echo "==> Closing camoufox-cli browser sessions and daemon"
  run "camoufox-cli close --all 2>/dev/null || true"
else
  echo "==> Keeping camoufox browser sessions (--keep-snapshots)"
fi

echo "Done."
echo
echo "Next: cd backend && .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --reload"
echo "      → migrations recreate the DB; the superadmin password lands in"
echo "        backend/data/initial_admin_password.txt"
