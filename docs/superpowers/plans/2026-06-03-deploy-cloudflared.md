# Docker + Cloudflare Tunnel Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Развернуть NaturalskWeb на свежем VPS одной командой через единый Docker-контейнер, опубликованный наружу Cloudflare Tunnel (без проброса портов, TLS на edge), с idempotent install.sh / update.sh, дозакрытым security-hardening, Alembic-миграциями и переведённой в прод-режим документацией.

**Architecture:** Один `app`-контейнер (multi-stage: `oven/bun` собирает фронт → `python:3.11-slim` с ffmpeg/libreoffice раздаёт FastAPI + статику) + сервис `cloudflared` (официальный образ, remotely-managed туннель с токеном). `docker-compose.yml` без публикуемых портов. `install.sh` ставит docker и хост-зависимости, через Cloudflare API создаёт туннель/DNS/ingress, генерит `.env`, поднимает стек. `update.sh` делает git pull → backup SQLite → rebuild → up. Схема БД переходит с самописного `create_tables`+ALTER на Alembic (baseline-ревизия + `alembic upgrade head` в entrypoint).

**Tech Stack:** Docker / docker compose v2, cloudflared, Cloudflare API (curl + jq), FastAPI/Starlette middleware, Alembic (async), python-json-logger, bun, bash.

---

## File Structure

**Создаются:**
- `Dockerfile` (корень репо, multi-stage) — заменяет `backend/Dockerfile`
- `.dockerignore` (корень)
- `docker-compose.yml` (корень)
- `.env.example` (корень, шаблон без секретов)
- `scripts/install.sh`
- `scripts/update.sh`
- `scripts/docker-entrypoint.sh` (применяет миграции, затем запускает uvicorn)
- `backend/alembic.ini`
- `backend/alembic/env.py`, `backend/alembic/script.py.mako`
- `backend/alembic/versions/0001_baseline.py`
- `backend/tests/test_static_serving.py`
- `backend/tests/test_security_headers.py`

**Изменяются:**
- `backend/app/main.py` — статика (SPA mount), SecurityHeaders + GZip middleware, JSON-logging setup, lifespan без `create_tables`
- `backend/app/middleware/security.py` — добавить `SecurityHeadersMiddleware`
- `backend/app/core/config.py` — `FRONTEND_DIST_DIR`, `LOGS_DIR`
- `backend/app/core/logging_config.py` (новый) — настройка JSON-логгера
- `backend/requirements.txt` — `python-json-logger`
- `spec/phase-6-security-deploy.md` — полный rewrite
- `CLAUDE.md` — Database / Production layout / Commands
- `.gitignore` — добавить `data/backups/`, `data/logs/`; убрать `frontend/bun.lockb`
- `backend/Dockerfile` — удалить (заменён корневым)

---

## Task 0: Backend раздаёт SPA-статику (frontend_dist)

**Goal:** FastAPI отдаёт собранный фронт из `frontend_dist`, с SPA-fallback на `index.html`, не перехватывая `/api/*`.

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_static_serving.py`

**Acceptance Criteria:**
- [ ] `GET /` отдаёт `index.html`, если `FRONTEND_DIST_DIR` существует.
- [ ] `GET /me` (клиентский роут) отдаёт `index.html` (SPA-fallback), а не 404.
- [ ] `GET /api/health` по-прежнему возвращает `{"status":"ok"}` (статика не перехватывает API).
- [ ] Если `FRONTEND_DIST_DIR` не существует (dev без билда) — приложение стартует без падения, статика просто не монтируется.

**Verify:** `backend/.venv/bin/python -m pytest tests/test_static_serving.py -v` → all PASS

**Steps:**

- [ ] **Step 1: Добавить путь к статике в config**

В `backend/app/core/config.py`, в класс `Settings` рядом с `AVATARS_DIR`:

```python
    FRONTEND_DIST_DIR: str = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend_dist")
    )
    LOGS_DIR: str = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "logs")
    )
```

- [ ] **Step 2: Написать падающий тест**

Создать `backend/tests/test_static_serving.py`:

```python
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_dist(tmp_path, monkeypatch):
    # Точечный dist-каталог с index.html
    dist = tmp_path / "frontend_dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('app')")

    monkeypatch.setenv("FRONTEND_DIST_DIR", str(dist))
    # Пересобрать settings и приложение с новым путём
    import importlib
    import app.core.config as config_mod
    importlib.reload(config_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_root_serves_index(client_with_dist):
    resp = client_with_dist.get("/")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_client_route_falls_back_to_index(client_with_dist):
    resp = client_with_dist.get("/me")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_api_not_shadowed_by_static(client_with_dist):
    resp = client_with_dist.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_asset_served(client_with_dist):
    resp = client_with_dist.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text
```

- [ ] **Step 3: Запустить тест — убедиться что падает**

Run: `backend/.venv/bin/python -m pytest tests/test_static_serving.py -v`
Expected: FAIL (статика не смонтирована, `/` → 404, `/me` → 404).

- [ ] **Step 4: Реализовать раздачу статики в main.py**

В `backend/app/main.py` добавить импорты вверху:

```python
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
```

В конец файла (ПОСЛЕ всех `include_router` и health-эндпоинтов, чтобы API-роуты имели приоритет):

```python
# --- Статика фронтенда (single-container prod). API-роуты объявлены выше и
# имеют приоритет; этот блок ловит всё остальное и отдаёт SPA. ---
if os.path.isdir(settings.FRONTEND_DIST_DIR):
    _assets_dir = os.path.join(settings.FRONTEND_DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    _index_file = os.path.join(settings.FRONTEND_DIST_DIR, "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str, request: Request):
        # Реальные файлы из dist (favicon, manifest и т.п.)
        candidate = os.path.join(settings.FRONTEND_DIST_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        # Иначе — SPA index (клиентский роутинг)
        return FileResponse(_index_file)
```

> Примечание: `/api/*`, `/health` объявлены роутерами выше и не попадают в catch-all, т.к. FastAPI матчит более ранние маршруты первыми. Catch-all регистрируется последним.

- [ ] **Step 5: Запустить тест — убедиться что проходит**

Run: `backend/.venv/bin/python -m pytest tests/test_static_serving.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Прогнать весь backend-набор (регрессия маршрутов)**

Run: `backend/.venv/bin/python -m pytest -q`
Expected: всё зелёное (catch-all не сломал существующие эндпоинты).

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/main.py backend/tests/test_static_serving.py
git commit -m "feat(backend): serve frontend SPA from dist with API-priority routing"
```

---

## Task 1: SecurityHeaders + GZip middleware

**Goal:** На всех ответах присутствуют security-заголовки; ответы сжимаются gzip.

**Files:**
- Modify: `backend/app/middleware/security.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_security_headers.py`

**Acceptance Criteria:**
- [ ] Каждый ответ несёт `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security`, `Content-Security-Policy`.
- [ ] `X-XSS-Protection` НЕ устанавливается (deprecated).
- [ ] GZip активен для ответов > 1000 байт.

**Verify:** `backend/.venv/bin/python -m pytest tests/test_security_headers.py -v` → all PASS

**Steps:**

- [ ] **Step 1: Написать падающий тест**

Создать `backend/tests/test_security_headers.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_security_headers_present():
    resp = client.get("/api/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in resp.headers["Strict-Transport-Security"]
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]


def test_xss_header_absent():
    resp = client.get("/api/health")
    assert "X-XSS-Protection" not in resp.headers
```

- [ ] **Step 2: Запустить — убедиться что падает**

Run: `backend/.venv/bin/python -m pytest tests/test_security_headers.py -v`
Expected: FAIL (KeyError на заголовках).

- [ ] **Step 3: Добавить SecurityHeadersMiddleware**

В `backend/app/middleware/security.py` дописать в конец файла:

```python
from starlette.middleware.base import RequestResponseEndpoint

CSP_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: https://i.ytimg.com; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to every response.

    X-XSS-Protection is intentionally omitted — deprecated and can introduce
    XS-Leak vulnerabilities in legacy browsers. CSP covers what it tried to do.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = CSP_POLICY
        return response
```

- [ ] **Step 4: Подключить middleware в main.py**

В `backend/app/main.py` добавить импорты:

```python
from starlette.middleware.gzip import GZipMiddleware
from app.middleware.security import RateLimitMiddleware, SecurityHeadersMiddleware
```

(заменив существующую строку `from app.middleware.security import RateLimitMiddleware`)

Рядом с прочими `add_middleware` (порядок: последний добавленный — внешний; GZip должен быть внешним, заголовки — поверх ответа):

```python
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

Разместить эти две строки ПОСЛЕ `app.add_middleware(RequestLoggerMiddleware)`.

- [ ] **Step 5: Запустить тест**

Run: `backend/.venv/bin/python -m pytest tests/test_security_headers.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/middleware/security.py backend/app/main.py backend/tests/test_security_headers.py
git commit -m "feat(backend): add security headers + gzip middleware"
```

---

## Task 2: Structured JSON logging с ротацией

**Goal:** Логи пишутся в JSON в `data/logs/` с ротацией (50 МБ × 5), INFO дублируется в stdout.

**Files:**
- Create: `backend/app/core/logging_config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/requirements.txt`

**Acceptance Criteria:**
- [ ] `python-json-logger` добавлен в requirements и установлен.
- [ ] При старте создаётся `data/logs/naturalsk.log`, записи — валидный JSON с полями `asctime`, `levelname`, `message`.
- [ ] RotatingFileHandler: `maxBytes=50*1024*1024`, `backupCount=5`.
- [ ] INFO+ идёт в stdout (видно в `docker logs`).

**Verify:** `backend/.venv/bin/python -c "from app.core.logging_config import setup_logging; setup_logging(); import logging; logging.getLogger('naturalsk').info('hi'); import os,json; from app.core.config import settings; p=os.path.join(settings.LOGS_DIR,'naturalsk.log'); line=open(p).read().strip().splitlines()[-1]; print(json.loads(line)['message'])"` → печатает `hi`

**Steps:**

- [ ] **Step 1: Добавить зависимость**

В `backend/requirements.txt` добавить строку:

```
python-json-logger>=2.0.0
```

Установить: `backend/.venv/bin/pip install "python-json-logger>=2.0.0"`

- [ ] **Step 2: Создать logging_config.py**

Создать `backend/app/core/logging_config.py`:

```python
import logging
import os
from logging.handlers import RotatingFileHandler

from pythonjsonlogger import jsonlogger

from app.core.config import settings

_LOG_FILE = "naturalsk.log"


def setup_logging() -> None:
    """Configure root logging: JSON file (rotating) + plain stdout.

    Idempotent — safe to call multiple times (clears existing handlers first).
    """
    os.makedirs(settings.LOGS_DIR, exist_ok=True)
    log_path = os.path.join(settings.LOGS_DIR, _LOG_FILE)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Убрать ранее настроенные хендлеры (basicConfig и повторные вызовы)
    for h in list(root.handlers):
        root.removeHandler(h)

    json_fmt = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.WARNING)  # WARNING/ERROR → файл
    file_handler.setFormatter(json_fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)  # INFO+ → stdout
    stream_handler.setFormatter(json_fmt)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)
```

> Примечание: спека требует «ERROR/WARNING → файл, INFO → stdout». Для acceptance-теста Verify пишет INFO в файл — поправить: чтобы файл ловил и проверочную запись, временно во Verify используется логгер на уровне WARNING. Если хочешь проверить именно файл — замени в Verify `.info(` на `.warning(`. Файл по дизайну хранит WARNING+; INFO живёт в stdout/docker logs.

- [ ] **Step 3: Скорректировать Verify под уровни**

Verify-команда выше использует `.info`, но файл ловит WARNING+. Использовать для проверки записи в файл:

Run: `backend/.venv/bin/python -c "from app.core.logging_config import setup_logging; setup_logging(); import logging; logging.getLogger('naturalsk').warning('hi'); import os,json; from app.core.config import settings; p=os.path.join(settings.LOGS_DIR,'naturalsk.log'); line=open(p).read().strip().splitlines()[-1]; print(json.loads(line)['message'])"`
Expected: печатает `hi`, и `json.loads` не падает (валидный JSON).

- [ ] **Step 4: Вызвать setup_logging в main.py**

В `backend/app/main.py` заменить блок:

```python
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("naturalsk")
```

на:

```python
from app.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("naturalsk")
```

- [ ] **Step 5: Прогнать backend-набор (логгер не ломает тесты)**

Run: `backend/.venv/bin/python -m pytest -q`
Expected: всё зелёное.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/logging_config.py backend/app/main.py backend/requirements.txt
git commit -m "feat(backend): structured JSON logging with rotation"
```

---

## Task 3: Alembic-миграции (baseline) + entrypoint

**Goal:** Схема БД управляется Alembic: baseline-ревизия создаёт текущую схему; `alembic upgrade head` применяется на старте контейнера; lifespan больше не вызывает `create_tables`.

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_baseline.py`
- Create: `scripts/docker-entrypoint.sh`
- Modify: `backend/app/main.py` (lifespan)

**Acceptance Criteria:**
- [ ] `alembic upgrade head` на пустой БД создаёт все таблицы (users, audit_log, download_tasks, shared_files, active_sessions, convert/image-таски и пр.).
- [ ] Схема после `alembic upgrade head` идентична схеме после `Base.metadata.create_all` (sanity-проверка).
- [ ] lifespan не вызывает `create_tables`; тесты (используют `Base.metadata.create_all` в conftest) не затронуты.
- [ ] `docker-entrypoint.sh` запускает `alembic upgrade head`, затем `exec uvicorn`.

**Verify:** `cd backend && rm -f /tmp/alembic_test.db && DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_test.db" .venv/bin/alembic upgrade head && .venv/bin/python -c "import sqlite3; t=[r[0] for r in sqlite3.connect('/tmp/alembic_test.db').execute(\"select name from sqlite_master where type='table'\")]; print(sorted(t)); assert 'users' in t and 'audit_log' in t"` → печатает список таблиц, assert проходит

**Steps:**

- [ ] **Step 1: Инициализировать Alembic-скелет**

Run: `cd backend && .venv/bin/alembic init -t async alembic`
Это создаст `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`.

- [ ] **Step 2: Настроить env.py под проект**

Заменить содержимое `backend/alembic/env.py` на:

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from alembic import context

from app.core.config import settings
from app.core.database import Base
# Импорт всех моделей, чтобы Base.metadata знал о таблицах:
from app.models import (  # noqa: F401
    user, audit, download_task, shared_file,
)
# Подтянуть остальные модели, если есть отдельные модули:
import app.models.convert_task  # noqa: F401
import app.models.image_task  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

> Перед написанием env.py выполнить `ls backend/app/models/` и привести список импортов в соответствие реальным модулям (модели должны все импортироваться, иначе autogenerate их пропустит). Проверить также имя ActiveSession-модуля.

- [ ] **Step 3: Сгенерировать baseline-ревизию автогеном**

Run: `cd backend && rm -f /tmp/baseline.db && DATABASE_URL="sqlite+aiosqlite:////tmp/baseline.db" .venv/bin/alembic revision --autogenerate -m "baseline"`
Это создаст файл в `alembic/versions/`. Переименовать его в `0001_baseline.py` и выставить `revision = "0001"`, `down_revision = None` (для предсказуемого имени).

- [ ] **Step 4: Проверить ревизию глазами**

Открыть сгенерированный `alembic/versions/0001_baseline.py`. Убедиться: все таблицы из моделей присутствуют в `upgrade()` (`create_table` для users, audit_log, download_tasks, shared_files, active_sessions, convert/image-таски). Удалить мусорные no-op изменения, если autogenerate их вставил.

- [ ] **Step 5: Запустить Verify (upgrade на чистой БД)**

Run: `cd backend && rm -f /tmp/alembic_test.db && DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_test.db" .venv/bin/alembic upgrade head && .venv/bin/python -c "import sqlite3; t=[r[0] for r in sqlite3.connect('/tmp/alembic_test.db').execute(\"select name from sqlite_master where type='table'\")]; print(sorted(t)); assert 'users' in t and 'audit_log' in t"`
Expected: печатает таблицы, assert проходит.

- [ ] **Step 6: Убрать create_tables из lifespan**

В `backend/app/main.py` в функции `lifespan` удалить строку `await create_tables()`. Импорт `create_tables` можно оставить (используется тестами) или убрать. Схема теперь применяется entrypoint'ом до старта uvicorn.

> Тесты используют отдельную фикстуру (`Base.metadata.create_all`) в `conftest.py` и lifespan не вызывают — Verify ниже это подтверждает.

- [ ] **Step 7: Создать docker-entrypoint.sh**

Создать `scripts/docker-entrypoint.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Применить миграции до старта приложения. Идемпотентно: на свежей БД создаёт
# схему из baseline, на существующей применяет недостающие ревизии.
echo "==> Applying database migrations (alembic upgrade head)"
alembic upgrade head

echo "==> Starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Сделать исполняемым: `chmod +x scripts/docker-entrypoint.sh`

- [ ] **Step 8: Прогнать backend-набор (lifespan-правка не сломала тесты)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: всё зелёное.

- [ ] **Step 9: Commit**

```bash
git add backend/alembic.ini backend/alembic backend/app/main.py scripts/docker-entrypoint.sh
git commit -m "feat(backend): manage schema with Alembic baseline + migration entrypoint"
```

---

## Task 4: Dockerfile (multi-stage) + .dockerignore + lockfile

**Goal:** Корневой multi-stage Dockerfile собирает фронт (bun) и runtime (python + ffmpeg + libreoffice), запускается через entrypoint. Lockfile закоммичен.

**Files:**
- Create: `Dockerfile`, `.dockerignore`
- Modify: `.gitignore`
- Delete: `backend/Dockerfile`
- Commit: `frontend/bun.lockb`

**Acceptance Criteria:**
- [ ] `docker build -t naturalskweb .` собирается без ошибок.
- [ ] В образе присутствуют `ffmpeg`, `libreoffice`, `curl`; статика лежит в `/app/frontend_dist`.
- [ ] `frontend/bun.lockb` отслеживается git; `.gitignore` его больше не игнорирует.
- [ ] `.dockerignore` исключает `.venv`, `node_modules`, `data`, `uploads`, `.git`.

**Verify:** `docker build -t naturalskweb . && docker run --rm naturalskweb sh -c "which ffmpeg && which libreoffice && ls frontend_dist/index.html"` → печатает пути ffmpeg/libreoffice и `frontend_dist/index.html`

**Steps:**

- [ ] **Step 1: Закоммитить lockfile**

Убрать из `.gitignore` строку `frontend/bun.lockb`.
Затем:

```bash
git add -f frontend/bun.lockb
```

(Если файла нет — сначала `cd frontend && bun install` сгенерирует его.)

- [ ] **Step 2: Создать корневой Dockerfile**

Создать `Dockerfile` в корне:

```dockerfile
# syntax=docker/dockerfile:1

# --- Stage 1: сборка фронтенда ---
FROM oven/bun:1-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/bun.lockb ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

# --- Stage 2: runtime ---
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libreoffice-writer \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /fe/dist ./frontend_dist
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
```

> ML-модели (rembg/LaMa) НЕ пекутся в образ — warmup в lifespan на старте (зафиксировано в дизайне).

- [ ] **Step 3: Создать .dockerignore**

Создать `.dockerignore` в корне:

```
**/.venv
**/__pycache__
**/*.pyc
frontend/node_modules
frontend/dist
backend/data
backend/uploads
data
uploads
.git
.worktrees
.playwright-cli
docs
spec
*.md
Screenshot_*.png
```

- [ ] **Step 4: Удалить старый backend/Dockerfile**

```bash
git rm backend/Dockerfile
```

- [ ] **Step 5: Добавить backups/logs в .gitignore**

В `.gitignore` в секцию «Database & uploads» добавить:

```
backend/data/backups/
backend/data/logs/
data/backups/
data/logs/
```

- [ ] **Step 6: Запустить Verify (build)**

Run: `docker build -t naturalskweb . && docker run --rm naturalskweb sh -c "which ffmpeg && which libreoffice && ls frontend_dist/index.html"`
Expected: пути `/usr/bin/ffmpeg`, `/usr/bin/libreoffice` (или симлинк), `frontend_dist/index.html`.

> Сборка долгая (torch + libreoffice). Это ожидаемо.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile .dockerignore .gitignore frontend/bun.lockb
git rm --cached backend/Dockerfile 2>/dev/null || true
git commit -m "build: root multi-stage Dockerfile + dockerignore, commit bun lockfile"
```

---

## Task 5: docker-compose.yml + .env.example

**Goal:** Compose поднимает `app` + `cloudflared` без публикуемых портов, с томами data/uploads и healthcheck.

**Files:**
- Create: `docker-compose.yml`, `.env.example`

**Acceptance Criteria:**
- [ ] `docker compose config` валиден (без ошибок парсинга).
- [ ] У `app` нет секции `ports`; том `./data` и `./uploads` смонтированы; есть healthcheck на `/api/health`.
- [ ] `cloudflared` использует `cloudflare/cloudflared`, команда с `--token ${TUNNEL_TOKEN}`, `depends_on app` по `service_healthy`.
- [ ] `.env.example` перечисляет `SECRET_KEY`, `CORS_ORIGINS`, `APP_DOMAIN`, `TUNNEL_TOKEN` без реальных значений.

**Verify:** `TUNNEL_TOKEN=x SECRET_KEY=x CORS_ORIGINS=x APP_DOMAIN=x docker compose config >/dev/null && echo OK` → печатает `OK`

**Steps:**

- [ ] **Step 1: Создать docker-compose.yml**

Создать `docker-compose.yml` в корне:

```yaml
services:
  app:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    depends_on:
      app:
        condition: service_healthy
```

- [ ] **Step 2: Создать .env.example**

Создать `.env.example` в корне:

```
# Скопируй в .env (install.sh делает это автоматически).
# SECRET_KEY: случайная hex-строка >= 32 байт (openssl rand -hex 32)
SECRET_KEY=
# Публичный origin приложения (https://<домен>)
CORS_ORIGINS=https://example.com
APP_DOMAIN=example.com
# Токен подключения cloudflared (выдаётся при создании туннеля через CF API)
TUNNEL_TOKEN=
```

- [ ] **Step 3: Запустить Verify**

Run: `TUNNEL_TOKEN=x SECRET_KEY=x CORS_ORIGINS=x APP_DOMAIN=x docker compose config >/dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "build: docker-compose (app + cloudflared, no host ports)"
```

---

## Task 6: install.sh — preflight + Cloudflare API + поднятие стека

**Goal:** Idempotent-скрипт ставит хост-зависимости, через CF API создаёт/переиспользует туннель + DNS + ingress, генерит `.env`, поднимает compose.

**Files:**
- Create: `scripts/install.sh`

**Acceptance Criteria:**
- [ ] `bash -n scripts/install.sh` и `shellcheck scripts/install.sh` — без ошибок.
- [ ] Preflight проверяет docker, compose, git, curl, openssl, jq; отсутствующее ставит через apt (или внятно падает).
- [ ] Ранняя валидация: невалидный CF-токен / домен не в аккаунте → стоп до создания ресурсов.
- [ ] Создание туннеля идемпотентно (переиспользует по имени `naturalskweb`); DNS-запись создаётся/обновляется; ingress указывает на `http://app:8000`.
- [ ] `.env` генерится только если отсутствует (не перетирает `SECRET_KEY`).
- [ ] В конце `docker compose up -d` и вывод URL.

**Verify:** `bash -n scripts/install.sh && shellcheck scripts/install.sh && echo SYNTAX_OK` → `SYNTAX_OK` (реальный e2e — только вручную на VPS, см. финальный критерий)

**Steps:**

- [ ] **Step 1: Создать scripts/install.sh**

Создать `scripts/install.sh`:

```bash
#!/usr/bin/env bash
# NaturalskWeb installer — fresh VPS bootstrap.
# Idempotent: re-running won't duplicate the tunnel/DNS or overwrite .env.
#
# Usage:
#   ./scripts/install.sh                 # interactive prompts
#   APP_DOMAIN=app.example.com CF_API_TOKEN=xxx ./scripts/install.sh
#   ./scripts/install.sh --enable-access  # also gate domain behind Cloudflare Access
set -euo pipefail

TUNNEL_NAME="naturalskweb"
ENABLE_ACCESS=0
for arg in "$@"; do
  case "$arg" in
    --enable-access) ENABLE_ACCESS=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"
cd "$REPO_ROOT"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# --- Step 0: preflight ---------------------------------------------------
apt_install() {
  command -v apt-get >/dev/null 2>&1 || die "Не apt-дистрибутив. Установи вручную: $*"
  [ "$(id -u)" -eq 0 ] || die "Нужны root-права для установки пакетов ($*). Запусти через sudo."
  apt-get update -y
  apt-get install -y "$@"
}

ensure_cmd() {
  local cmd="$1" pkg="${2:-$1}"
  command -v "$cmd" >/dev/null 2>&1 && return 0
  log "Устанавливаю $pkg (нет $cmd)"
  apt_install "$pkg"
}

install_docker() {
  command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && return 0
  log "Устанавливаю Docker + compose plugin"
  [ "$(id -u)" -eq 0 ] || die "Нужны root-права для установки Docker. Запусти через sudo."
  curl -fsSL https://get.docker.com | sh
  docker compose version >/dev/null 2>&1 || apt_install docker-compose-plugin
}

log "Preflight: проверяю хост-зависимости"
ensure_cmd git
ensure_cmd curl
ensure_cmd openssl
ensure_cmd jq
install_docker

# --- Step 1: параметры ---------------------------------------------------
APP_DOMAIN="${APP_DOMAIN:-}"
CF_API_TOKEN="${CF_API_TOKEN:-}"
[ -n "$APP_DOMAIN" ]   || read -rp "Домен (например app.example.com): " APP_DOMAIN
[ -n "$CF_API_TOKEN" ] || read -rsp "Cloudflare API token: " CF_API_TOKEN && echo
[ -n "$APP_DOMAIN" ]   || die "Домен обязателен"
[ -n "$CF_API_TOKEN" ] || die "CF API token обязателен"

CF_API="https://api.cloudflare.com/client/v4"
cf() {  # cf METHOD PATH [JSON-body]
  local method="$1" path="$2" body="${3:-}"
  local args=(-fsS -X "$method" "${CF_API}${path}"
              -H "Authorization: Bearer ${CF_API_TOKEN}"
              -H "Content-Type: application/json")
  [ -n "$body" ] && args+=(--data "$body")
  curl "${args[@]}"
}
cf_ok() { jq -e '.success == true' >/dev/null 2>&1; }

# Корневой домен (zone) = последние две метки. Для app.example.co.uk поправь вручную.
ROOT_DOMAIN="$(echo "$APP_DOMAIN" | awk -F. '{print $(NF-1)"."$NF}')"

# --- Step 2: ранняя валидация (resolve zone) -----------------------------
log "Проверяю токен и зону для $ROOT_DOMAIN"
ZONE_RESP="$(cf GET "/zones?name=${ROOT_DOMAIN}")" || die "CF API недоступен / токен невалиден"
echo "$ZONE_RESP" | cf_ok || die "CF API вернул ошибку: $(echo "$ZONE_RESP" | jq -c '.errors')"
ZONE_ID="$(echo "$ZONE_RESP" | jq -r '.result[0].id // empty')"
ACCOUNT_ID="$(echo "$ZONE_RESP" | jq -r '.result[0].account.id // empty')"
[ -n "$ZONE_ID" ]    || die "Зона $ROOT_DOMAIN не найдена в этом аккаунте. Делегируй домен на Cloudflare NS."
[ -n "$ACCOUNT_ID" ] || die "Не удалось определить account id"

# --- Step 3: туннель (idempotent) ----------------------------------------
log "Создаю/переиспользую туннель $TUNNEL_NAME"
LIST="$(cf GET "/accounts/${ACCOUNT_ID}/cfd_tunnel?name=${TUNNEL_NAME}&is_deleted=false")"
TUNNEL_ID="$(echo "$LIST" | jq -r '.result[0].id // empty')"
if [ -z "$TUNNEL_ID" ]; then
  CREATE="$(cf POST "/accounts/${ACCOUNT_ID}/cfd_tunnel" \
            "{\"name\":\"${TUNNEL_NAME}\",\"config_src\":\"cloudflare\"}")"
  echo "$CREATE" | cf_ok || die "Не удалось создать туннель: $(echo "$CREATE" | jq -c '.errors')"
  TUNNEL_ID="$(echo "$CREATE" | jq -r '.result.id')"
fi
TUNNEL_TOKEN="$(cf GET "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/token" | jq -r '.result')"
[ -n "$TUNNEL_TOKEN" ] && [ "$TUNNEL_TOKEN" != "null" ] || die "Не удалось получить tunnel token"

log "Настраиваю ingress туннеля → http://app:8000"
cf PUT "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
   "{\"config\":{\"ingress\":[{\"hostname\":\"${APP_DOMAIN}\",\"service\":\"http://app:8000\"},{\"service\":\"http_status:404\"}]}}" \
   | cf_ok || die "Не удалось задать ingress"

log "Создаю/обновляю DNS CNAME $APP_DOMAIN"
CNAME_CONTENT="${TUNNEL_ID}.cfargotunnel.com"
EXISTING="$(cf GET "/zones/${ZONE_ID}/dns_records?name=${APP_DOMAIN}&type=CNAME")"
REC_ID="$(echo "$EXISTING" | jq -r '.result[0].id // empty')"
DNS_BODY="{\"type\":\"CNAME\",\"name\":\"${APP_DOMAIN}\",\"content\":\"${CNAME_CONTENT}\",\"proxied\":true}"
if [ -n "$REC_ID" ]; then
  cf PUT "/zones/${ZONE_ID}/dns_records/${REC_ID}" "$DNS_BODY" | cf_ok || die "Не удалось обновить DNS"
else
  cf POST "/zones/${ZONE_ID}/dns_records" "$DNS_BODY" | cf_ok || die "Не удалось создать DNS"
fi

# --- Step 4: .env (не перетираем существующий) ---------------------------
if [ -f .env ]; then
  log ".env уже есть — обновляю только TUNNEL_TOKEN и домен, SECRET_KEY сохраняю"
  tmp="$(mktemp)"
  grep -v -E '^(TUNNEL_TOKEN|CORS_ORIGINS|APP_DOMAIN)=' .env > "$tmp" || true
  {
    echo "CORS_ORIGINS=https://${APP_DOMAIN}"
    echo "APP_DOMAIN=${APP_DOMAIN}"
    echo "TUNNEL_TOKEN=${TUNNEL_TOKEN}"
  } >> "$tmp"
  mv "$tmp" .env
else
  log "Генерирую .env"
  cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
CORS_ORIGINS=https://${APP_DOMAIN}
APP_DOMAIN=${APP_DOMAIN}
TUNNEL_TOKEN=${TUNNEL_TOKEN}
EOF
  chmod 600 .env
fi

# --- Step 6: (опц.) Cloudflare Access ------------------------------------
if [ "$ENABLE_ACCESS" -eq 1 ]; then
  read -rp "Email'ы для Access (через запятую): " ACCESS_EMAILS
  log "Настраиваю Cloudflare Access для $APP_DOMAIN"
  APP_RESP="$(cf POST "/accounts/${ACCOUNT_ID}/access/apps" \
    "{\"name\":\"NaturalskWeb\",\"domain\":\"${APP_DOMAIN}\",\"type\":\"self_hosted\",\"session_duration\":\"24h\"}")"
  ACCESS_APP_ID="$(echo "$APP_RESP" | jq -r '.result.id // empty')"
  [ -n "$ACCESS_APP_ID" ] || die "Не удалось создать Access app: $(echo "$APP_RESP" | jq -c '.errors')"
  INCLUDE="$(echo "$ACCESS_EMAILS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' \
            | jq -R '{email:{email:.}}' | jq -s '.')"
  cf POST "/accounts/${ACCOUNT_ID}/access/apps/${ACCESS_APP_ID}/policies" \
    "{\"name\":\"allow-listed-emails\",\"decision\":\"allow\",\"include\":${INCLUDE}}" \
    | cf_ok || die "Не удалось создать Access policy"
fi

# --- Step 5: поднять стек ------------------------------------------------
log "Собираю и поднимаю стек (первый build долгий — torch + libreoffice)"
docker compose build
docker compose up -d

log "Готово. Приложение: https://${APP_DOMAIN}"
log "Стартовый superadmin-пароль появится в: data/initial_admin_password.txt (после старта app)"
log "Посмотреть: docker compose logs -f app"
```

> ВАЖНО: порядок секций в коде — preflight → params → validate → tunnel → dns → .env → access → up. Comment-метки (Step N) исторические, не влияют на исполнение.

- [ ] **Step 2: Сделать исполняемым**

```bash
chmod +x scripts/install.sh
```

- [ ] **Step 3: Запустить Verify (синтаксис + shellcheck)**

Run: `bash -n scripts/install.sh && shellcheck scripts/install.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK` (если `shellcheck` не установлен — `ensure_cmd shellcheck` или `apt-get install -y shellcheck` локально; допустимы info-уровня замечания, ошибок быть не должно).

- [ ] **Step 4: Commit**

```bash
git add scripts/install.sh
git commit -m "feat(deploy): idempotent install.sh (preflight + CF API tunnel/DNS + compose up)"
```

---

## Task 7: update.sh — backup + pull + rebuild

**Goal:** Скрипт обновления: проверка чистоты git → pull → backup SQLite (ротация 10) → миграции применятся entrypoint'ом при старте → rebuild → up.

**Files:**
- Create: `scripts/update.sh`

**Acceptance Criteria:**
- [ ] `bash -n scripts/update.sh && shellcheck scripts/update.sh` — без ошибок.
- [ ] Падает рано при незакоммиченных изменениях git.
- [ ] Делает backup `data/naturalsk.db` → `data/backups/naturalsk-<UTC>.db`, оставляя последние 10.
- [ ] Backup происходит ДО rebuild/up (т.е. до применения миграций).
- [ ] `docker compose build && docker compose up -d` в конце.

**Verify:** `bash -n scripts/update.sh && shellcheck scripts/update.sh && echo SYNTAX_OK` → `SYNTAX_OK`. Плюс точечный тест ротации (Step 3).

**Steps:**

- [ ] **Step 1: Создать scripts/update.sh**

Создать `scripts/update.sh`:

```bash
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
```

- [ ] **Step 2: Сделать исполняемым**

```bash
chmod +x scripts/update.sh
```

- [ ] **Step 3: Проверить ротацию backup'ов изолированно**

Run:
```bash
cd /tmp && rm -rf utest && mkdir -p utest/data/backups && cd utest
for i in $(seq 1 13); do touch -d "2026-01-$(printf %02d "$i")" "data/backups/naturalsk-2026010${i}.db" 2>/dev/null || touch "data/backups/naturalsk-fake${i}.db"; done
ls -1t data/backups/naturalsk-*.db | tail -n +11 | xargs -r rm -f
echo "осталось: $(ls -1 data/backups | wc -l)"
```
Expected: `осталось: 10`.

- [ ] **Step 4: Запустить Verify (синтаксис)**

Run: `bash -n scripts/update.sh && shellcheck scripts/update.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK`.

- [ ] **Step 5: Commit**

```bash
git add scripts/update.sh
git commit -m "feat(deploy): update.sh (git pull + SQLite backup rotation + rebuild)"
```

---

## Task 8: Переписать spec/phase-6 + обновить CLAUDE.md

**Goal:** Документация отражает реальность: docker + cloudflared deploy, прод-режим БД (Alembic), новые команды.

**Files:**
- Modify: `spec/phase-6-security-deploy.md`
- Modify: `CLAUDE.md`

**Acceptance Criteria:**
- [ ] `spec/phase-6-security-deploy.md` не содержит nginx/certbot/2-контейнерной схемы/проброса портов; описывает docker+cloudflared+install.sh/update.sh; отмечает что реализовано (rate-limit, CORS, audit, автоочистка, заголовки, gzip, JSON-логи).
- [ ] `CLAUDE.md` секция Database: убрано «проект на стадии создания / миграции не применяй / БД пересоздаётся»; вписано: прод управляет схемой Alembic (`alembic upgrade head`), `clean.sh` — только dev.
- [ ] `CLAUDE.md` Production layout: docker-compose (app + cloudflared), нет проброса портов, TLS на edge.
- [ ] `CLAUDE.md` Commands: добавлены `./scripts/install.sh` и `./scripts/update.sh`.

**Verify:** `! rg -iq 'nginx|certbot' spec/phase-6-security-deploy.md && rg -q 'cloudflared' spec/phase-6-security-deploy.md && rg -q 'install.sh' CLAUDE.md && echo DOCS_OK` → `DOCS_OK`

**Steps:**

- [ ] **Step 1: Переписать spec/phase-6-security-deploy.md**

Заменить разделы «🚀 Деплой» (6.7–6.10) и «Критерии завершения» на описание новой схемы. Сохранить разделы Security/Оптимизация, но отметить статусы. Содержание раздела деплоя (вставить вместо 6.7–6.10):

```markdown
## 🚀 Деплой (Docker + Cloudflare Tunnel)

Единый `app`-контейнер (FastAPI + собранный фронт) + сервис `cloudflared`.
Наружу публикуется ТОЛЬКО через Cloudflare Tunnel — проброс портов на
роутере/firewall не нужен, TLS терминируется на edge Cloudflare.

### Образ (корневой Dockerfile, multi-stage)
- Stage 1 `oven/bun:1-slim`: `bun install --frozen-lockfile && bun run build` → dist.
- Stage 2 `python:3.11-slim`: ffmpeg + libreoffice-writer + curl, pip-зависимости,
  бэкенд + dist в `frontend_dist`. Entrypoint: `alembic upgrade head` → uvicorn.

### docker-compose.yml
- `app`: без `ports`, тома `./data` и `./uploads`, healthcheck на `/api/health`.
- `cloudflared`: `cloudflare/cloudflared`, `tunnel run --token ${TUNNEL_TOKEN}`,
  depends_on app по `service_healthy`.

### scripts/install.sh (свежий VPS, idempotent)
Preflight (docker/git/curl/openssl/jq) → ранняя валидация CF-токена/домена →
создание/переиспользование туннеля + ingress + DNS через Cloudflare API →
генерация `.env` (SECRET_KEY, CORS_ORIGINS, APP_DOMAIN, TUNNEL_TOKEN) →
`docker compose up -d`. Флаг `--enable-access` ставит Cloudflare Access.

### scripts/update.sh
git pull → backup SQLite (`data/backups/`, ротация 10) → rebuild → up.
Миграции применяются entrypoint'ом на старте.

### База данных (прод)
Схема управляется Alembic. Обновления применяют `alembic upgrade head`
автоматически (entrypoint). БД НЕ пересоздаётся.
```

Обновить «✅ Критерии завершения» под новую схему (убрать NGINX/HTTPS-certbot пункты, добавить cloudflared/install.sh/update.sh/заголовки/gzip/JSON-логи).

- [ ] **Step 2: Обновить CLAUDE.md — секция Database**

Найти в `CLAUDE.md` блок «### Database» с текстом «**Миграции Alembic не применяй** — проект на стадии создания…». Заменить на:

```markdown
### Database

**Прод-режим: схему держит Alembic.** После изменения моделей создавай ревизию
(`cd backend && .venv/bin/alembic revision --autogenerate -m "..."`), проверяй её
и коммить. Деплой применяет `alembic upgrade head` автоматически (entrypoint
контейнера / при старте). **БД не пересоздавай** — это потеря данных.

`./scripts/clean.sh` — ТОЛЬКО для локальной разработки (сносит dev-БД, uploads,
аватары, snapshots; есть `--dry-run` и `--keep-snapshots`). На проде не запускать.
Стартовый superadmin кладётся в `backend/data/initial_admin_password.txt`.
```

- [ ] **Step 3: Обновить CLAUDE.md — Production layout**

Найти секцию «### Production layout» и заменить/дополнить:

```markdown
### Production layout

Единый Docker-образ (корневой `Dockerfile`, multi-stage): `oven/bun` собирает
фронт → `python:3.11-slim` с ffmpeg/libreoffice раздаёт FastAPI + статику из
`frontend_dist`. `docker-compose.yml` поднимает `app` + `cloudflared`.

Публикация наружу — только через **Cloudflare Tunnel** (`cloudflared`), проброс
портов НЕ используется, TLS на edge Cloudflare. У `app` нет публикуемых портов.
Vite proxy `/api → :8000` работает только в dev. APScheduler чистит `uploads/`
(TTL 6 ч). Avatars без TTL.

Деплой: `./scripts/install.sh` (свежий VPS), обновление: `./scripts/update.sh`.
```

- [ ] **Step 4: Обновить CLAUDE.md — Commands**

В секцию Commands (рядом с Backend/Frontend) добавить блок:

```markdown
### Deploy
```bash
./scripts/install.sh                 # свежий VPS: ставит docker+зависимости,
                                     # создаёт CF-туннель/DNS, поднимает стек
./scripts/install.sh --enable-access # + Cloudflare Access (email allowlist)
./scripts/update.sh                  # git pull + backup БД + rebuild + up
```
```

- [ ] **Step 5: Запустить Verify**

Run: `! rg -iq 'nginx|certbot' spec/phase-6-security-deploy.md && rg -q 'cloudflared' spec/phase-6-security-deploy.md && rg -q 'install.sh' CLAUDE.md && echo DOCS_OK`
Expected: `DOCS_OK`.

- [ ] **Step 6: Commit**

```bash
git add spec/phase-6-security-deploy.md CLAUDE.md
git commit -m "docs: deploy via docker+cloudflared, switch DB docs to prod/Alembic mode"
```

---

## Финальный критерий (ручной, на VPS)

Не автоматизируется в этой сессии — выполняется при реальном деплое:
- [ ] На чистом Ubuntu-VPS `./scripts/install.sh` (с реальным доменом в CF + API-токеном) поднимает стек; `https://<domain>` открывает приложение через CF Tunnel; логин работает; `data/initial_admin_password.txt` создан.
- [ ] Повторный `./scripts/install.sh` не дублирует туннель/DNS, не перетирает SECRET_KEY.
- [ ] `./scripts/update.sh` делает backup и пересобирает без потери данных.

---

## Self-Review

**Spec coverage:**
- Архитектура контейнеров → Task 4, 5. Раздача статики (дыра в коде) → Task 0.
- install.sh (preflight + CF API + .env + up) → Task 6. update.sh → Task 7.
- Security headers + gzip → Task 1. JSON logging → Task 2.
- Alembic baseline + entrypoint → Task 3. Lockfile commit → Task 4.
- CF Access опционально → Task 6 (`--enable-access`).
- Переписать phase-6 + CLAUDE.md → Task 8.
- Все пункты спеки покрыты.

**Зависимости задач:** 1, 2 независимы (backend middleware/logging). 0 независим. 3 зависит от наличия моделей (есть). 4 зависит от 0,1,2,3 (образ должен содержать готовый backend + entrypoint). 5 зависит от 4. 6,7 зависят от 5 (compose). 8 — последняя (документирует всё). 

**Note:** реальный e2e install.sh против CF API не TDD-абелен — проверяется shellcheck + синтаксис + ручной VPS-критерий. Это инфраструктурный код, не бизнес-логика; ограничение явно зафиксировано.
