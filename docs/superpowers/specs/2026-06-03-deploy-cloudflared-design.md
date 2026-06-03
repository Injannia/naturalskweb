# Деплой через Docker + Cloudflare Tunnel — дизайн

> Дата: 2026-06-03
> Статус: согласован, готов к написанию плана
> Контекст: проект готов к первому релизу. Заменяет устаревшую deploy-часть `spec/phase-6-security-deploy.md` (nginx + certbot + 2 контейнера + проброс порта).

## Цель

Развернуть NaturalskWeb на свежем VPS одной командой: установить всё необходимое, поднять приложение в Docker, опубликовать его наружу через **Cloudflare Tunnel** (без проброса портов, TLS на edge Cloudflare), настроить процесс дальнейших обновлений, дозакрыть оставшиеся security-дыры и перевести документацию из режима «стадия разработки» в продакшен-режим.

## Решения (зафиксированы в брейншторме)

| Вопрос | Решение |
|---|---|
| Модель Cloudflare | Домен уже в Cloudflare; скрипт создаёт туннель + DNS + ingress через **Cloudflare API** |
| Управление туннелем | **Remotely-managed (token)**: ingress настраивается через API, в compose только `TUNNEL_TOKEN` |
| Хост | Свежий VPS (Ubuntu/Debian); install.sh **idempotent**, ставит docker если нет |
| Обновление | `update.sh`: git pull → backup SQLite → rebuild → up |
| Cloudflare Access | **Опционально**, флаг `--enable-access` |
| Объём | Полный: deploy + security-заголовки + gzip + structured logging + переписать phase-6 + обновить CLAUDE.md |
| Backup retention | 10 файлов |
| Frontend build | `bun` через образ `oven/bun:1-slim` (build-stage) |

## Архитектура контейнеров

Один `docker-compose.yml` в корне репо, **два сервиса**, **ни одного опубликованного порта**:

```yaml
services:
  app:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data        # SQLite, avatars, backups, logs
      - ./uploads:/app/uploads  # временные файлы (TTL 6 ч)
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    # портов наружу НЕТ — cloudflared ходит к app по внутренней сети compose

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
    depends_on:
      app:
        condition: service_healthy
```

- TLS терминируется на edge Cloudflare. Origin (app) работает по http внутри docker-сети.
- `cloudflared` соединяется исходящим коннектом — на роутере/firewall **проброс портов не нужен**.
- Нужен health-эндпоинт `GET /api/health` (если ещё нет — добавить лёгкий, без auth, возвращает `{"status":"ok"}`).

### Образ app — multi-stage

```dockerfile
# Stage 1 — сборка фронта
FROM oven/bun:1-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/bun.lockb* ./
RUN bun install --frozen-lockfile   # см. примечание про lockfile ниже
COPY frontend/ ./
RUN bun run build            # → /fe/dist

# Stage 2 — runtime
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libreoffice-writer curl \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /fe/dist ./frontend_dist
# Пред-загрузка ML-моделей в слой образа, чтобы первый запрос их не качал:
RUN python -c "import rembg; rembg.new_session('u2netp')"  # + LaMa-warmup по факту API
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- `curl` ставится для healthcheck.
- Бэкенд должен раздавать статику из `frontend_dist` (проверить/настроить путь раздачи `dist` в `main.py` — он сейчас рассчитан на `frontend/dist` относительно cwd; зафиксировать путь через config или env).
- Модель-warmup в build-слое опционален; если сильно раздувает образ — оставить только runtime-warmup (он уже есть в lifespan). Решение по факту замера размера образа.
- **Lockfile**: `frontend/bun.lockb` сейчас в `.gitignore` → на свежем клоне его нет, `--frozen-lockfile` упадёт. На этапе плана выбрать: либо **закоммитить lockfile** (убрать из `.gitignore`, воспроизводимые билды — рекомендуется), либо использовать `bun install` без `--frozen-lockfile`.

### Альтернатива (отклонена)

Locally-managed туннель (`config.yml` + credentials-файл в томе) — ingress хранился бы в git, но усложняет и скрипт (генерация creds), и compose (монтирование). Token-вариант выбран за простоту.

## install.sh — установка на свежем VPS (idempotent)

Запускается на VPS из корня склонированного репо. Шаги:

**Шаг 0 — preflight (новое, по результату брейншторма):**
- Проверить хост-зависимости через `command -v`: **docker, docker compose plugin, git, curl, openssl, jq**.
- Отсутствующие ставить через `apt-get install -y` (docker — официальным get-docker скриптом / репо). Если не root или не apt-дистрибутив — остановиться с понятным сообщением, какие пакеты доустановить вручную.
- Зависимости **приложения** (ffmpeg, libreoffice, torch, rembg, yt-dlp, bun) на хост НЕ ставятся — они внутри образа.

**Шаг 1 — ввод параметров:**
- Промпт (или флаги/env): **домен** (`APP_DOMAIN`), **CF API-токен** (`CF_API_TOKEN`).
- Опц. флаг `--enable-access` + список email для Access-policy.
- Требуемые права токена: `Cloudflare Tunnel:Edit`, `DNS:Edit`, (`Access: Apps and Policies:Edit` если `--enable-access`).

**Шаг 2 — ранняя валидация (fail fast):**
- Пробный API-вызов: resolve **zone ID** по домену (`GET /zones?name=<root-domain>`).
- Если токен невалиден / нет прав / домен не в этом аккаунте — остановиться с внятной ошибкой ДО создания любых ресурсов.

**Шаг 3 — Cloudflare API (idempotent):**
- Создать или переиспользовать **туннель** по имени `naturalskweb` (проверка: `GET /accounts/{acc}/cfd_tunnel?name=naturalskweb`).
- Получить **tunnel token** (`GET .../cfd_tunnel/{id}/token`).
- PUT **ingress-конфиг** (`PUT .../cfd_tunnel/{id}/configurations`): `hostname=<domain> → service http://app:8000`, catch-all `http_status:404`.
- Создать/обновить **DNS CNAME** (proxied): `<domain> → <tunnel-id>.cfargotunnel.com`.

**Шаг 4 — генерация `.env`** (только если отсутствует, чтобы не перетереть SECRET_KEY при повторном запуске):
```
SECRET_KEY=<openssl rand -hex 32>
CORS_ORIGINS=https://<domain>
APP_DOMAIN=<domain>
TUNNEL_TOKEN=<tunnel token>
```

**Шаг 5 — поднять стек:** `docker compose build && docker compose up -d`.

**Шаг 6 — (опц.) Cloudflare Access:** при `--enable-access` создать Access-app на `<domain>` + policy (allow по списку email) через API.

**Шаг 7 — вывод:** URL приложения + путь к `data/initial_admin_password.txt` (стартовый superadmin-пароль).

Повторный запуск ничего не дублирует: проверки по имени туннеля, существованию DNS-записи, наличию `.env`.

## update.sh — обновление после релиза

1. Проверить чистоту git (нет незакоммиченных правок) — иначе стоп.
2. `git pull` (стоп при конфликте).
3. **Backup**: скопировать `data/naturalsk.db` → `data/backups/naturalsk-<UTC-timestamp>.db`; удалить всё кроме последних **10**.
4. `docker compose build`.
5. `docker compose up -d`.
6. (опц.) `docker image prune -f`.

Падает рано и внятно на каждом шаге.

## Security hardening (backend)

Доделать оставшиеся пункты phase-6 (rate limiting / CORS / audit уже есть):

- **SecurityHeadersMiddleware** — новый класс в `app/middleware/security.py` рядом с `RateLimitMiddleware`. Заголовки на всех ответах:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `Content-Security-Policy: default-src 'self'; img-src 'self' data: https://i.ytimg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; ...` (уточнить по факту реальных внешних ресурсов фронта — шрифты Google, ytimg).
  - X-XSS-Protection **пропускаем** — deprecated, может вредить.
- **GZipMiddleware** (`starlette.middleware.gzip`), `minimum_size=1000`.
- **Structured JSON logging**: `python-json-logger` (добавить в requirements) + `RotatingFileHandler` (50 МБ × 5) в `data/logs/`, INFO → stdout. Не ломать существующий audit-middleware.

Порядок middleware в `main.py` учесть: GZip снаружи, заголовки до отдачи, rate-limit до тяжёлой обработки.

## Alembic baseline (для прод-режима)

Сейчас БД пересоздаётся при изменении моделей — это dev-режим. Для прода:
- Создать **baseline-миграцию** (начальная revision, описывающая текущую схему) либо `alembic stamp head` на чистой БД.
- `lifespan`/деплой: применять `alembic upgrade head` вместо безусловного `create_tables` (или оставить `create_tables` для пустой БД + миграции поверх — выбрать на этапе плана).
- Цель: обновления не теряют данные, схема меняется миграциями.

Это отдельная задача внутри релиза — без неё пункт CLAUDE.md «не пересоздавать БД» неполноценен.

## Документация

- **Переписать `spec/phase-6-security-deploy.md`**: убрать nginx/certbot/2-контейнерную схему/проброс порта; вписать docker + cloudflared + install.sh/update.sh; отметить по факту кода что done (rate-limit, CORS, audit, автоочистка), что доделано в этом релизе (заголовки, gzip, logging), критерии завершения обновить.
- **Обновить `CLAUDE.md`**:
  - Секция Database: убрать «проект на стадии создания, миграции Alembic не применяй, БД пересоздаётся» → прод-режим: миграции применяются через Alembic, БД не пересоздавать, `clean.sh` только для локальной разработки.
  - Production layout: описать docker-compose (app + cloudflared), отсутствие проброса портов, TLS на edge.
  - Commands: добавить `./scripts/install.sh` и `./scripts/update.sh` с кратким описанием.

## Файлы (создать / изменить)

**Создать:**
- `/Dockerfile` (корневой, multi-stage; старый `backend/Dockerfile` — удалить или заменить им)
- `/docker-compose.yml`
- `/.dockerignore`
- `/scripts/install.sh`
- `/scripts/update.sh`
- `/.env.example` (шаблон без секретов)
- `backend/alembic/` + начальная revision (если выбран Alembic-путь)

**Изменить:**
- `backend/app/middleware/security.py` — добавить `SecurityHeadersMiddleware`
- `backend/app/main.py` — подключить SecurityHeaders + GZip middleware, JSON-logging, health-эндпоинт, путь раздачи `frontend_dist`
- `backend/requirements.txt` — `python-json-logger` (+ `alembic` уже есть)
- `backend/app/core/config.py` — путь к статике фронта через env/config, `data/logs` dir
- `spec/phase-6-security-deploy.md` — полный rewrite
- `CLAUDE.md` — Database / Production layout / Commands
- `.gitignore` — `data/backups/`, `data/logs/`, `.env` (проверить)

## Критерии готовности

- [ ] `install.sh` на чистом Ubuntu-VPS ставит docker+зависимости, поднимает стек, приложение открывается по `https://<domain>` через CF Tunnel без проброса портов.
- [ ] Повторный `install.sh` не дублирует туннель/DNS, не перетирает SECRET_KEY.
- [ ] Невалидный токен/домен → ранняя внятная ошибка, ресурсы не создаются.
- [ ] `update.sh` делает backup, пересобирает, поднимает; старые бэкапы обрезаются до 10.
- [ ] Security-заголовки присутствуют на ответах; gzip работает; JSON-логи пишутся с ротацией.
- [ ] `--enable-access` создаёт Access-app + policy; без флага домен пускает к своей login-странице.
- [ ] Alembic-миграции применяются; обновление не теряет данные.
- [ ] phase-6 и CLAUDE.md отражают реальность (прод-режим, docker+cloudflared).

## Известные ограничения / ручные шаги (скрипт не делает)

- Домен должен быть заранее делегирован на Cloudflare NS (смена NS у регистратора).
- CF API-токен с нужными правами создаётся пользователем в дашборде заранее.
- Размер образа app большой (torch + libreoffice) — первый build на VPS долгий; последующие используют кэш слоёв.
