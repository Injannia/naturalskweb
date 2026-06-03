# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NaturalskWeb** — закрытое веб-приложение для малых команд (1–5 чел.), 4 модуля: YouTube-загрузчик, конвертер файлов, обработка изображений (фон/водяные знаки), админ-панель с мониторингом.

Монорепо: `/frontend` (React SPA) + `/backend` (FastAPI). Спеки фаз — `/spec/`, русский.

## Commands

### Frontend (`/frontend`)
```bash
bun run dev                  # Vite на :5173, проксирует /api → :8000
bun run build                # tsc + vite build (тип-чек делается здесь, отдельного lint нет)
bun run preview              # Превью production-сборки
bun run test:run             # Vitest (unit-тесты компонентов)
```

### Backend (`/backend`)
```bash
.venv/bin/alembic upgrade head            # применить миграции (создаёт/обновляет БД)
.venv/bin/uvicorn app.main:app --reload   # FastAPI на :8000
.venv/bin/python -m pytest -q             # Все тесты (~150 шт.)
.venv/bin/python -m pytest tests/test_admin_users.py -v   # Один файл
```

### Deploy
```bash
./scripts/install.sh                 # свежий VPS: ставит docker+зависимости,
                                     # создаёт CF-туннель/DNS, поднимает стек
./scripts/install.sh --enable-access # + Cloudflare Access (email allowlist)
./scripts/update.sh                  # git pull + backup БД + rebuild + up
```

### UI/E2E проверки

Юзай **skill `camoufox-cli`** (не пиши .spec.ts вручную). Сценарий: `camoufox-cli open URL` → `snapshot -i` → `click @eN` / `fill @eN ...` → `snapshot -i`. Anti-detect Firefox, `navigator.webdriver=false`.

### Database

**Прод-режим: схему держит Alembic.** После изменения моделей создавай ревизию
(`cd backend && .venv/bin/alembic revision --autogenerate -m "..."`), проверяй её
и коммить. Деплой применяет `alembic upgrade head` автоматически (entrypoint
контейнера). **БД не пересоздавай** — это потеря данных.

`./scripts/clean.sh` — ТОЛЬКО для локальной разработки (сносит dev-БД, uploads,
аватары, camoufox-cli snapshots; есть `--dry-run` и `--keep-snapshots`). На проде
не запускать. Стартовый superadmin кладётся в `backend/data/initial_admin_password.txt`. После `clean.sh` подними БД заново: `cd backend && .venv/bin/alembic upgrade head`.

## Architecture

### Backend (`backend/app/`)

**Стек:** FastAPI + SQLAlchemy 2.0 async + aiosqlite + PyJWT + APScheduler + bcrypt + Pillow + psutil + yt-dlp + FFmpeg + LibreOffice + rembg (u2netp) + OpenCV.

**Routers:**
- `auth` — login/logout/refresh, change-password, /auth/me (фронт пуллит каждые 15 с)
- `me` — профиль (`/api/me`, PATCH username, sessions CRUD, avatar upload/delete)
- `users` — `/api/users/{id}/avatar` (раздача WebP-аватаров авторизованным)
- `admin` — **package** `routers/admin/`: свой APIRouter в `__init__.py`, под-роутеры `users.py` (CRUD + reset/toggle), `sessions.py`, `monitoring.py` (stats/system/storage), `audit.py`. Helpers — `_shared.py` (role-проверки), `_filesystem.py` (size/count). `__init__.py` re-export'ит endpoint-функции, чтобы `from app.routers.admin import list_users, kill_session, ...` работал в тестах
- `youtube` / `convert` / `image` — модульные эндпоинты

**Auth-инвариант (важно):**
- JWT содержит `iat`. `User` имеет `kicked_at` (timezone-aware UTC). На каждом запросе `dependencies.get_current_user` сравнивает `iat` с `kicked_at`, возвращает 401 если токен старее. **Юзается для kill-session, удаления пользователя, reset-password — все ставят `kicked_at = now()`.** SQLite отдаёт naive datetime, потому auth-логика делает `replace(tzinfo=utc)` перед сравнением — не сломайте.
- `is_deleted` — soft-delete; `get_current_user` отвергает удалённого; `auth.login` для удалённого возвращает тот же generic «invalid credentials» (не утечка существования).

**Role hierarchy:** `user < admin < superadmin`. Helpers `routers/admin/_shared.py`:
- `_is_visible(actor, target)` — soft-deleted виден только superadmin'у; юзай в `get_user`/`update_user` для согласованного 404
- `_can_admin_modify(actor, target)` — admin не правит superadmin/себя; superadmin — любого. Reuse, не дублируй
- `require_admin` / `require_superadmin` (`dependencies.py`) — dependency-инжекторы

**Audit log:** `app/utils/audit.py:log_audit(db, user_id, action, request, details)` без коммита (вызывающий коммитит со своими изменениями). Action-константы — `app/utils/audit_actions.py` (юзай их, не magic strings). CSV-экспорт сериализует `details` через `json.dumps(..., ensure_ascii=False)` — не возвращайся к `str(dict)`.

**Storage paths (`app/core/config.py`):**
- `DATA_DIR`, `AVATARS_DIR` — абсолютные пути от `__file__` (НЕ относительные к cwd)
- `AVATARS_DIR` лежит ВНУТРИ `DATA_DIR` (`data/avatars/`). `/admin/storage` юзает `_dir_size_mb_excluding(DATA_DIR, AVATARS_DIR)` (helper `routers/admin/_filesystem.py`) — иначе аватары посчитаются дважды
- `/admin/system` смотрит `psutil.disk_usage(settings.DATA_DIR)` (fallback на `/`), не корневой раздел — даёт реальный «свободно на data-партиции»
- В тестах оба пути переопределяются через env (`/tmp/naturalsk_test_avatars`)

**Avatar pipeline:** POST `/api/me/avatar` → проверка mime → размер ≤5 МБ → `Image.verify()` → re-open → composite alpha на белый (прозрачные PNG) → thumbnail 256×256 → WEBP quality 88 → `data/avatars/{user.id}.webp` → инкремент `avatar_version` → audit. Ловим только `(UnidentifiedImageError, OSError, ValueError, SyntaxError)`, не bare `Exception`.

**Active sessions invariant:**
- Все мутации (`logout`, kill-session, delete-user, reset-password) удаляют ActiveSession и/или ставят `kicked_at`. `/admin/sessions` фильтрует `expires_at > now_naive` в SQL, не в Python.
- `ActiveSession.user_id` объявлен `ON DELETE CASCADE`, в `_set_sqlite_pragma` (`core/database.py`) включён `PRAGMA foreign_keys=ON` — хард-удаление `User` каскадно сносит его сессии на уровне схемы. **Тестовая фикстура `db_session` намеренно отключает FK** (старые тесты вставляют объекты без FK-родителей), потому регрессионный тест на каскад поднимает свой engine с `foreign_keys=ON`.

### Frontend (`frontend/src/`)

**Стек:** React 18 + TypeScript + Vite + React Router 6 + Axios + react-toastify + lucide-react + react-easy-crop. Шрифты — Space Grotesk + Inter + JetBrains Mono через Google Fonts (preload-link в `index.html`).

**Routes:**
```
/login, /change-password    — публичные
/                           — HomePage с плитками (по permissions + ЛК/Admin Panel)
/me                         — ProfilePage (avatar, usage bars, sessions, security)
/youtube /converter /image  — модули (по permission)
/admin?tab=users|audit|monitoring|profile  — admin/superadmin
*                           — Navigate to "/"
```

**Дизайн-язык — Indigo Nebula (cosmic redesign):**
- Все токены в `styles/variables.css`. Цвета: `--bg-base/surface/elevated/input/hover` (поверхности с прозрачностью + blur), `--accent-1/2/3` (`#6366F1`/`#A855F7`/`#EC4899`), `--accent-gradient` (135° → primary CTA, активные элементы), `--border-glow` + `--glow-sm/md/lg` (свечение). Шрифты: `--font-display` (Space Grotesk, заголовки), `--font-ui` (Inter, тело), `--font-mono` (JBM, код/чипсы). Радиус — `--radius-pill` (был `--radius-full`).
- **Старые токены удалены** (`--bg-card`, `--bg-primary`, `--bg-secondary`, `--accent`, `--accent-hover`, `--radius-full`, `--shadow-glow`, `--border-focus`, `--border-accent`, `--bottombar-height`, `--sidebar-collapsed`). Не возвращай в новом CSS — юзай cosmic-токены.
- **Слои фона:** `AuroraBackground` (mesh + 2 aurora-blob'а, `z-index: 0`) + `StarryBackground` v2 (3-tier яркость, `z-index: 1`). Контент в `MainLayout` через `position: relative; z-index: 2`. Публичные `/login` и `/change-password` рендерят оба фона сами (они вне `MainLayout`).
- **Reduced motion:** глобально в `global.css` через `@media (prefers-reduced-motion: reduce)` + локально в `*.module.css` для тяжёлых анимаций (mesh flow, blob drift, `pulseGlow`). Не вводи новые `@keyframes` без отдельного reduced-motion-блока.

**UI-kit (`components/ui/`)** — обязательно юзай для новых форм/кнопок:
- `<Button variant="primary|secondary|ghost|danger|dangerOutline" size="sm|md|lg" loading? leftIcon? rightIcon?>` — primary = `--accent-gradient` + glow на hover, dangerOutline = красная обводка.
- `<Card variant="glass|elevated" interactive?>` — glass = `--bg-surface` + blur 20px, elevated = `--bg-elevated` + blur 24px + `--shadow-aurora`.
- `<Input label error helper>` — стеклянный фокус-ринг через `--accent-1`, ошибка с иконкой `AlertCircle`.
- `<DropZone onFiles accept multiple?>` — пунктирная aurora-рамка, animated dash при drag-over.
- Импорт через barrel: `import { Button, Card, Input, DropZone } from '../../components/ui'`.

**Layout-компоненты:**
- `Sidebar` — desktop-only (≤768px скрыт через `display: none`). Стеклянный фон, gradient-логотип, активный пункт — `pill` с `::before`-точкой и `--glow-sm`.
- `Topbar` — стеклянный с `backdrop-filter`, scroll-listener даёт класс `topbarScrolled` (фон плотнее). Хамбургер `menuBtn` оставлен в JSX для тестовой совместимости, скрыт CSS.
- `BottomNav` — mobile-only (≤768px), floating glass-pill, фильтрация по permissions, активная иконка с aurora-glow и пульсирующей точкой. `padding-bottom: env(safe-area-inset-bottom)` для iOS.

**Auth & polling:**
- `api/client.ts` — Axios; 401 interceptor рефрешит токен. `forceLogout()` чистит storage, тостит «Сессия завершена», редиректит — но **подавляет себя на /login** (иначе двойной toast и self-redirect).
- `hooks/useAuthProvider.ts` — после mount setInterval(15 с) на `/auth/me`, обновляет `user`. Skip когда `document.visibilityState !== 'visible'`. Даёт фронту реагировать на admin-side изменения permissions/role/kicked_at в ≤16 с.
- Токены в `localStorage` (`access_token`, `refresh_token`).

**Avatars (`components/AvatarImage`):**
- `useAuthedImage(url)` качает blob через api-клиент (с авторизацией), оборачивает в `URL.createObjectURL`, ревокает на размонтировании/смене URL.
- `<AvatarImage userId version size accentBorder?>` — пропускает fetch когда `version === 0` (нет аватара), сразу рендерит fallback-иконку, чтоб не спамить 404. `accentBorder` оборачивает аватар в gradient-ring (юзается в `Topbar`; `AvatarUploader` делает свой ring через `.avatarRing` в Profile.module.css).
- `version` в URL (`?v=N`) важен — cache-bust. После upload бэкенд инкрементит `avatar_version`, фронт перерефетчит `/auth/me`, AvatarImage перезагружается.

### Test pattern (backend) — ВАЖНО

В `backend/tests/conftest.py` — **только фикстура `db_session`** (in-memory SQLite). HTTP TestClient/httpx инфраструктуры НЕТ. **Все тесты вызывают функции роутера напрямую**, минуя FastAPI/HTTP-слой:

```python
from app.routers.admin import create_user
from fastapi import HTTPException
import pytest

@pytest.mark.asyncio
async def test_admin_creates_user(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    result = await create_user(
        body=CreateUserRequest(username="bob", role="user"),
        request=_make_request(),  # минимальный starlette Request с headers/client.host
        actor=admin,
        db=db_session,
    )
    assert result.username == "bob"
```

`_make_request()` собирает scope `{"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)}`. Формат, который понимает `log_audit`.

Для 401/403/404 юзай `pytest.raises(HTTPException)` и `exc.value.status_code`. Для проверки записи в `audit_log` — `select(AuditLog).where(...)` после вызова и до db_session teardown.

### Lifespan

`backend/app/main.py:lifespan` запускает: `create_tables` → `_create_superadmin` → APScheduler (auto-cleanup) → background-таски прогрева моделей (`_warmup_image_models`: rembg + LaMa) и `_warmup_tool_versions` (subprocess `ffmpeg --version`, `yt-dlp --version` идут в кэш `get_tool_versions` сразу на старте, чтоб первый `/admin/system` не платил cold-cost).

### Production layout

Единый Docker-образ (корневой `Dockerfile`, multi-stage): `oven/bun` собирает
фронт → `python:3.11-slim` с ffmpeg/libreoffice раздаёт FastAPI + статику из
`frontend_dist`. `docker-compose.yml` поднимает `app` + `cloudflared`.

Публикация наружу — только через **Cloudflare Tunnel** (`cloudflared`), проброс
портов НЕ используется, TLS на edge Cloudflare. У `app` нет публикуемых портов.
Vite proxy `/api → :8000` работает только в dev. APScheduler чистит `uploads/`
(TTL 6 ч). Avatars без TTL.

Деплой: `./scripts/install.sh` (свежий VPS), обновление: `./scripts/update.sh`.