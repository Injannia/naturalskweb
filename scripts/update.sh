#!/usr/bin/env bash
# NaturalskWeb updater — pull latest, back up DB, rebuild, restart.
# Migrations are applied by the container entrypoint (alembic upgrade head)
# on startup; the DB backup below runs BEFORE that.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
cd "$REPO_ROOT"

log() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

BACKUP_KEEP=10
DB_PATH="data/naturalsk.db"
BACKUP_DIR="data/backups"

# --- guard: чистый git ---------------------------------------------------
[ -z "$(git status --porcelain)" ] || die "Есть незакоммиченные изменения. Закоммить/стэшни перед обновлением."

log "git pull"
git pull --ff-only || die "git pull не удался (конфликт/не fast-forward). Разреши вручную."

# --- backup БД ДО миграций -----------------------------------------------
if [ -f "$DB_PATH" ]; then
  mkdir -p "$BACKUP_DIR"
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  cp "$DB_PATH" "${BACKUP_DIR}/naturalsk-${TS}.db"
  log "Backup: ${BACKUP_DIR}/naturalsk-${TS}.db"
  # Ротация: оставить последние BACKUP_KEEP
  ls -1t "${BACKUP_DIR}"/naturalsk-*.db 2>/dev/null | tail -n +$((BACKUP_KEEP + 1)) | xargs -r rm -f
else
  log "БД ещё нет ($DB_PATH) — пропускаю backup"
fi

log "Пересобираю и перезапускаю стек"
docker compose build
docker compose up -d

log "Готово. Логи: docker compose logs -f app"
