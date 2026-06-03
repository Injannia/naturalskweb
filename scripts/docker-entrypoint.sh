#!/usr/bin/env bash
set -euo pipefail

echo "==> Applying database migrations (alembic upgrade head)"
alembic upgrade head

echo "==> Starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
