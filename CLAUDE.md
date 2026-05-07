# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**NaturalskWeb** — закрытое веб-приложение для малых команд (1–5 чел.) с 4 модулями: YouTube-загрузчик, конвертер файлов, обработка изображений (фон/водяные знаки) и админ-панель с мониторингом.

Монорепозиторий: `/frontend` (React SPA) + `/backend` (FastAPI). Спеки фаз — в `/spec/` на русском.

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
.venv/bin/uvicorn app.main:app --reload   # FastAPI на :8000
.venv/bin/python -m pytest -q             # Все тесты (~150 шт.)
.venv/bin/python -m pytest tests/test_admin_users.py -v   # Один файл
```

### UI/E2E проверки

Используй **skill `playwright-cli`** (не пиши .spec.ts тесты вручную). Сценарий: `playwright-cli open URL` → `snapshot` → `click eN` / `fill eN ...` → `snapshot`. См. `feedback_playwright` в memory.

### Database

**Миграции через Alembic не применяй** — проект на стадии создания. После изменения моделей: запусти `./scripts/clean.sh` (или удали `backend/data/naturalsk.db`) и перезапусти uvicorn — БД пересоздастся, стартовый superadmin кладётся в `backend/data/initial_admin_password.txt`.

`./scripts/clean.sh` дополнительно сносит uploads, аватары и playwright-cli snapshots; есть `--dry-run` и `--keep-snapshots`.

## Architecture

### Backend (`backend/app/`)

**Стек:** FastAPI + SQLAlchemy 2.0 async + aiosqlite + PyJWT + APScheduler + bcrypt + Pillow + psutil + yt-dlp + FFmpeg + LibreOffice + rembg (u2netp) + OpenCV.

**Routers:**
- `auth` — login/logout/refresh, change-password, /auth/me (фронт пуллит каждые 15 с)
- `me` — профиль (`/api/me`, PATCH username, sessions CRUD, avatar upload/delete)
- `users` — `/api/users/{id}/avatar` (раздача WebP-аватаров для авторизованных)
- `admin` — это **package** `routers/admin/` со своим APIRouter в `__init__.py` и под-роутерами в `users.py` (CRUD + reset/toggle), `sessions.py`, `monitoring.py` (stats/system/storage), `audit.py`. Helpers вынесены в `_shared.py` (role-проверки) и `_filesystem.py` (size/count). `__init__.py` re-export'ит endpoint-функции, чтобы `from app.routers.admin import list_users, kill_session, ...` продолжал работать в тестах
- `youtube` / `convert` / `image` — модульные эндпоинты

**Auth-инвариант (важно):**
- JWT содержит `iat`. У `User` есть `kicked_at` (timezone-aware UTC). При каждом запросе `dependencies.get_current_user` сравнивает `iat` с `kicked_at` и возвращает 401, если токен старее. **Это используется и для kill-session, и для удаления пользователя, и для reset-password — все они ставят `kicked_at = now()`.** SQLite отдаёт naive datetime, поэтому в auth-логике делается `replace(tzinfo=utc)` перед сравнением — не сломайте этот код.
- `is_deleted` — soft-delete; `get_current_user` отвергает удалённого юзера; `auth.login` для удалённого возвращает тот же generic «invalid credentials» (не утечка существования).

**Role hierarchy:** `user < admin < superadmin`. Helper'ы в `routers/admin/_shared.py`:
- `_is_visible(actor, target)` — soft-deleted виден только superadmin'у; используй в `get_user`/`update_user` для согласованного 404
- `_can_admin_modify(actor, target)` — admin не правит superadmin/себя; superadmin — любого. Reuse, а не дублируй
- `require_admin` / `require_superadmin` (в `dependencies.py`) — dependency-инжекторы

**Audit log:** `app/utils/audit.py:log_audit(db, user_id, action, request, details)` без коммита (вызывающий коммитит вместе со своими изменениями). Action-константы — `app/utils/audit_actions.py` (используй их, не magic strings). CSV-экспорт сериализует `details` через `json.dumps(..., ensure_ascii=False)` — не возвращайся к `str(dict)`.

**Storage paths (`app/core/config.py`):**
- `DATA_DIR` и `AVATARS_DIR` — абсолютные пути, рассчитанные от `__file__` (НЕ относительные к cwd)
- `AVATARS_DIR` лежит ВНУТРИ `DATA_DIR` (`data/avatars/`). `/admin/storage` использует `_dir_size_mb_excluding(DATA_DIR, AVATARS_DIR)` (helper из `routers/admin/_filesystem.py`) — иначе аватары посчитаются дважды
- `/admin/system` смотрит `psutil.disk_usage(settings.DATA_DIR)` (с fallback на `/`), а не корневой раздел — это даёт реальный «свободно на data-партиции»
- В тестах оба пути переопределяются через env (`/tmp/naturalsk_test_avatars`)

**Avatar pipeline:** POST `/api/me/avatar` → проверка mime → размер ≤5 МБ → `Image.verify()` → re-open → composite alpha на белый (для прозрачных PNG) → thumbnail 256×256 → WEBP quality 88 → `data/avatars/{user.id}.webp` → инкремент `avatar_version` → audit. Ловим только `(UnidentifiedImageError, OSError, ValueError, SyntaxError)`, не bare `Exception`.

**Active sessions invariant:**
- Все мутации (`logout`, kill-session, delete-user, reset-password) удаляют ActiveSession и/или ставят `kicked_at`. `/admin/sessions` фильтрует `expires_at > now_naive` в SQL, не в Python.
- `ActiveSession.user_id` объявлен с `ON DELETE CASCADE`, а в `_set_sqlite_pragma` (в `core/database.py`) включен `PRAGMA foreign_keys=ON` — поэтому хард-удаление `User` каскадно сносит его сессии на уровне схемы. **Тестовая фикстура `db_session` намеренно отключает FK** (некоторые старые тесты вставляют объекты без FK-родителей), поэтому регрессионный тест на каскад поднимает свой engine с `foreign_keys=ON`.

### Frontend (`frontend/src/`)

**Стек:** React 18 + TypeScript + Vite + React Router 6 + Axios + react-toastify + lucide-react + react-easy-crop.

**Routes:**
```
/login, /change-password    — публичные
/                           — HomePage с плитками (по permissions + ЛК/Admin Panel)
/me                         — ProfilePage (avatar, usage bars, sessions, security)
/youtube /converter /image  — модули (по permission)
/admin?tab=users|audit|monitoring|profile  — admin/superadmin
*                           — Navigate to "/"
```

**Auth & polling:**
- `api/client.ts` — Axios; 401 interceptor рефрешит токен. `forceLogout()` чистит storage, тостит «Сессия завершена» и редиректит — но **подавляет себя на /login** (иначе двойной toast и self-redirect).
- `hooks/useAuthProvider.ts` — после mount setInterval(15 с) на `/auth/me`, обновляет `user`. Skip когда `document.visibilityState !== 'visible'`. Это даёт фронту реагировать на admin-side изменения permissions/role/kicked_at в течение ≤16 с.
- Токены в `localStorage` (`access_token`, `refresh_token`).

**Avatars (`components/AvatarImage`):**
- `useAuthedImage(url)` качает blob через api-клиент (с авторизацией), оборачивает в `URL.createObjectURL`, ревокает на размонтировании/смене URL.
- `<AvatarImage userId version size>` — пропускает fetch когда `version === 0` (нет аватара) и сразу рендерит fallback-иконку, чтобы не спамить 404 в консоль.
- `version` в URL (`?v=N`) важен — это cache-bust. После upload бэкенд инкрементит `avatar_version`, фронт перерефетчит `/auth/me` и AvatarImage перезагружается.

### Test pattern (backend) — ВАЖНО

В `backend/tests/conftest.py` есть **только фикстура `db_session`** (in-memory SQLite). HTTP TestClient/httpx инфраструктуры НЕТ. **Все тесты вызывают функции роутера напрямую**, минуя FastAPI/HTTP-слой:

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

`_make_request()` собирает scope `{"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)}`. Это формат, который понимает `log_audit`.

Для проверки 401/403/404 используй `pytest.raises(HTTPException)` и `exc.value.status_code`. Для проверки записи в `audit_log` — `select(AuditLog).where(...)` после вызова и до db_session teardown.

### Lifespan

`backend/app/main.py:lifespan` запускает: `create_tables` → `_create_superadmin` → APScheduler (auto-cleanup) → background-таски прогрева моделей (`_warmup_image_models`: rembg + LaMa) и `_warmup_tool_versions` (subprocess-вызовы `ffmpeg --version` и `yt-dlp --version` идут в кэш `get_tool_versions` сразу при старте, чтобы первый `/admin/system` не платил cold-cost).

### Production layout

Backend раздаёт собранный `frontend/dist`. Vite proxy `/api → :8000` работает только в dev. APScheduler чистит `uploads/` (TTL 6 ч). Avatars не имеют TTL — живут пока пользователь не удалит.
