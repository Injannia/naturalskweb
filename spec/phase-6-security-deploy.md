# Фаза 6 — Security & Deploy (Безопасность и деплой)

> Цель: финальное hardening, оптимизация, тестирование и подготовка к деплою на VPS.

---

## 🔧 Backend

### 6.1 Security Hardening

**CORS:**
- Разрешить только конкретный домен из `.env`
- Запретить `*` в production

**Заголовки безопасности (middleware):**
```python
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; img-src 'self' data: https://i.ytimg.com;
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

**Input Validation:**
- Все входные данные через Pydantic
- Длина строк ограничена
- URL-валидация для YouTube ссылок
- Запрет path traversal в именах файлов

**Rate Limiting (финальная настройка):**
- `/api/auth/login`: 10 req/min
- `/api/youtube/*`: 30 req/min  
- `/api/convert/*`: 30 req/min
- `/api/image/*`: 20 req/min
- `/api/admin/*`: 60 req/min

**Логирование:**
- Structured JSON logging (python-json-logger)
- Ротация логов (max 50MB, 5 файлов)
- Уровни: ERROR → файл, WARNING → файл, INFO → stdout

### 6.2 Оптимизация производительности
- Кэширование YouTube info (in-memory, TTL 5 мин)
- Async file I/O  
- Streaming file downloads (не загружать в память целиком)
- gzip compression middleware

### 6.3 Автоочистка файлов (финальная версия)
- APScheduler: каждые 30 мин сканировать `uploads/`
- Удалять папки старше 6 часов
- Логировать удалённые файлы
- Graceful: не удалять файлы с активными задачами

---

## 🎨 Frontend

### 6.4 Финальная оптимизация
- Code splitting (lazy loading страниц через React.lazy)
- Минимизация бандла через Vite
- Оптимизация изображений
- Service Worker для offline shell (опционально)

### 6.5 Meta-теги и SEO
- Title: "NaturalskWeb"
- Favicon
- manifest.json для PWA-like опыта

### 6.6 Error Boundaries
- Глобальный ErrorBoundary (ловит React crashes)
- Красивая страница ошибки в стиле дизайна

---

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
автоматически (entrypoint контейнера). БД НЕ пересоздаётся.

## ✅ Критерии завершения
- [x] Security-заголовки установлены (SecurityHeadersMiddleware: CSP/HSTS/nosniff/frame-deny)
- [x] Rate limiting настроен (RateLimitMiddleware)
- [x] gzip-сжатие (GZipMiddleware)
- [x] Structured JSON logging с ротацией
- [x] Файлы автоудаляются через 6 часов (APScheduler)
- [x] Схема БД через Alembic-миграции
- [x] Единый Docker-образ (app + cloudflared)
- [ ] install.sh поднимает стек на свежем VPS, домен открывается через CF Tunnel
- [ ] update.sh обновляет без потери данных
- [ ] Приложение работает стабильно 24/7
