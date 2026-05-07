#!/usr/bin/env bash
# Reset NaturalskWeb dev state: stop servers, drop DB + uploads + avatars,
# wipe playwright-cli artefacts. Safe to re-run.
#
# Usage:
#   ./scripts/clean.sh           # default — clean everything below
#   ./scripts/clean.sh --keep-snapshots   # keep playwright snapshots
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

echo "==> Removing avatar files (keeping the dir)"
if [[ -d backend/data/avatars ]]; then
  run "find backend/data/avatars -type f -delete"
fi

echo "==> Removing temporary uploads"
if [[ -d backend/uploads ]]; then
  run "find backend/uploads -mindepth 1 -delete"
fi

if [[ $KEEP_SNAPSHOTS -eq 0 ]]; then
  echo "==> Removing playwright-cli snapshots and caches"
  run "rm -rf .playwright-cli backend/.playwright-cli frontend/.playwright-cli .playwright"
  run "rm -f backend/*.yml frontend/*.yml"
else
  echo "==> Keeping playwright snapshots (--keep-snapshots)"
fi

echo "Done."
echo
echo "Next: cd backend && .venv/bin/uvicorn app.main:app --reload"
echo "      → fresh DB will be created and the superadmin password will land in"
echo "        backend/data/initial_admin_password.txt"
