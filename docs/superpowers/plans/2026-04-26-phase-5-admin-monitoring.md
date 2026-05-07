# Phase 5 — Admin Panel, Monitoring, Личный кабинет, Главная страница — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Полная реализация фазы 5 NaturalskWeb: новая главная страница, личный кабинет с аватарами, админ-панель с управлением пользователями/аудитом/мониторингом, polling прав в реальном времени.

**Architecture:** Backend сначала — модель User + helpers + новые роутеры (`me.py`, `users.py`, расширенный `admin.py`). Затем frontend — общие компоненты (AvatarImage, polling), главная, личный кабинет, админка. БД пересоздаётся (без Alembic). UI-проверки делаются через skill `playwright-cli`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 (async) / SQLite / Pillow / psutil / pytest+httpx — backend. React 18 / TypeScript / Vite / React Router 6 / Axios / lucide-react / react-toastify / react-easy-crop — frontend. Playwright (через playwright-cli skill) — UI-тесты.

**Источник требований:** `docs/superpowers/specs/2026-04-26-phase-5-admin-monitoring-design.md`

---

## Task 0: Изменения модели User и пересоздание БД

**Goal:** Расширить `User` четырьмя новыми полями и пересоздать БД, чтобы все следующие задачи могли работать с актуальной схемой.

**Files:**
- Modify: `backend/app/models/user.py`
- Delete: `backend/data/naturalsk.db`, `backend/data/naturalsk.db-shm`, `backend/data/naturalsk.db-wal`, `backend/data/initial_admin_password.txt`

**Acceptance Criteria:**
- [ ] В модели `User` добавлены поля `avatar_path`, `avatar_version`, `is_deleted`, `kicked_at`.
- [ ] После старта backend БД создана заново, в `users` есть все новые колонки.
- [ ] `_create_superadmin` создаёт нового admin, пароль записан в `data/initial_admin_password.txt`.

**Verify:**
```bash
sqlite3 backend/data/naturalsk.db "PRAGMA table_info(users);" | grep -E "avatar_path|avatar_version|is_deleted|kicked_at"
```
Ожидается: 4 строки с указанными колонками.

**Steps:**

- [ ] **Step 1: Добавить поля в `backend/app/models/user.py`**

После строки `locked_until: Mapped[datetime | None] = ...` добавить:

```python
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    kicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Удалить старую БД**

```bash
rm -f backend/data/naturalsk.db backend/data/naturalsk.db-shm backend/data/naturalsk.db-wal backend/data/initial_admin_password.txt
```

- [ ] **Step 3: Запустить backend для пересоздания схемы**

```bash
cd backend && uvicorn app.main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/api/health
kill %1
```

Ожидается: `{"status":"ok"}`. В `backend/data/initial_admin_password.txt` должен появиться пароль.

- [ ] **Step 4: Проверить схему**

```bash
sqlite3 backend/data/naturalsk.db "PRAGMA table_info(users);"
```

Ожидается: видны колонки `avatar_path`, `avatar_version`, `is_deleted`, `kicked_at`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/user.py
git commit -m "feat(user): add avatar, soft-delete and kicked_at fields"
```

---

## Task 1: Утилиты — audit logging, версии, парсинг user-agent

**Goal:** Вынести и создать общие helper'ы, нужные нескольким роутерам: запись audit-лога, константы actions, парсер user-agent, чтение версий ffmpeg/yt-dlp.

**Files:**
- Create: `backend/app/utils/audit.py`
- Create: `backend/app/utils/audit_actions.py`
- Create: `backend/app/utils/user_agent.py`
- Create: `backend/app/utils/system_info.py`
- Test: `backend/tests/test_utils.py`

**Acceptance Criteria:**
- [ ] `log_audit(db, user_id, action, request, details)` пишет в `audit_logs` без коммита.
- [ ] Константы action'ов экспортируются из `audit_actions.py`.
- [ ] `parse_user_agent("Mozilla/5.0 ... Chrome/120 ...")` возвращает «Chrome 120 · Linux» или подобное.
- [ ] `get_tool_versions()` кэширует результат на 1 час.

**Verify:** `cd backend && pytest tests/test_utils.py -v`

**Steps:**

- [ ] **Step 1: Написать тесты `backend/tests/test_utils.py`**

```python
import time
from unittest.mock import patch, MagicMock

import pytest
from app.utils.user_agent import parse_user_agent
from app.utils.system_info import get_tool_versions


def test_parse_user_agent_chrome_linux():
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    assert parse_user_agent(ua) == "Chrome 120 · Linux"


def test_parse_user_agent_firefox_windows():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
    assert parse_user_agent(ua) == "Firefox 121 · Windows"


def test_parse_user_agent_unknown():
    assert parse_user_agent("") == "Неизвестно"
    assert parse_user_agent("curl/8.0") == "Иное"


def test_get_tool_versions_caches(monkeypatch):
    calls = {"n": 0}
    def fake_run(*args, **kwargs):
        calls["n"] += 1
        result = MagicMock()
        result.stdout = "Python 3.12.3\n"
        result.returncode = 0
        return result
    monkeypatch.setattr("subprocess.run", fake_run)
    # Сбросим кэш
    from app.utils import system_info
    system_info._cache = None
    system_info._cache_at = 0.0
    v1 = get_tool_versions()
    v2 = get_tool_versions()
    assert v1 == v2
    assert calls["n"] == 3  # python + ffmpeg + yt-dlp один раз
```

- [ ] **Step 2: Реализовать `backend/app/utils/audit_actions.py`**

```python
LOGIN = "login"
LOGOUT = "logout"
LOGIN_FAILED = "login_failed"
ACCOUNT_LOCKED = "account_locked"
CHANGE_PASSWORD = "change_password"

USER_CREATED = "user_created"
USER_UPDATED = "user_updated"
USER_DELETED = "user_deleted"
USER_PASSWORD_RESET = "user_password_reset"
USER_TOGGLED_ACTIVE = "user_toggled_active"
SESSION_KILLED_BY_ADMIN = "session_killed_by_admin"
USERNAME_CHANGED = "username_changed"
AVATAR_UPDATED = "avatar_updated"
AVATAR_REMOVED = "avatar_removed"
```

- [ ] **Step 3: Реализовать `backend/app/utils/audit.py`**

```python
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_audit(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    request: Request,
    details: dict | None = None,
) -> None:
    log = AuditLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")[:256],
    )
    db.add(log)
```

- [ ] **Step 4: Реализовать `backend/app/utils/user_agent.py`**

```python
import re

_BROWSERS = [
    (re.compile(r"Firefox/(\d+)"), "Firefox"),
    (re.compile(r"Edg/(\d+)"), "Edge"),
    (re.compile(r"Chrome/(\d+)"), "Chrome"),
    (re.compile(r"Safari/(\d+)"), "Safari"),
]
_OS = [
    (re.compile(r"Windows"), "Windows"),
    (re.compile(r"Mac OS X|Macintosh"), "macOS"),
    (re.compile(r"Android"), "Android"),
    (re.compile(r"iPhone|iPad|iOS"), "iOS"),
    (re.compile(r"Linux"), "Linux"),
]


def parse_user_agent(ua: str) -> str:
    if not ua:
        return "Неизвестно"
    browser = None
    for rx, name in _BROWSERS:
        m = rx.search(ua)
        if m:
            browser = f"{name} {m.group(1)}"
            break
    os_name = None
    for rx, name in _OS:
        if rx.search(ua):
            os_name = name
            break
    if not browser and not os_name:
        return "Иное"
    parts = [p for p in (browser, os_name) if p]
    return " · ".join(parts)
```

- [ ] **Step 5: Реализовать `backend/app/utils/system_info.py`**

```python
import subprocess
import time

_CACHE_TTL = 3600
_cache: dict | None = None
_cache_at: float = 0.0


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.stdout.strip().splitlines()[0] if result.stdout else "недоступно"
    except Exception:
        return "недоступно"


def get_tool_versions() -> dict:
    global _cache, _cache_at
    now = time.time()
    if _cache is not None and now - _cache_at < _CACHE_TTL:
        return _cache
    _cache = {
        "python_version": _run(["python", "--version"]).replace("Python ", ""),
        "ffmpeg_version": _run(["ffmpeg", "-version"]).split(" ")[2] if _run(["ffmpeg", "-version"]) != "недоступно" else "недоступно",
        "yt_dlp_version": _run(["yt-dlp", "--version"]),
    }
    _cache_at = now
    return _cache
```

- [ ] **Step 6: Прогнать тесты**

```bash
cd backend && pytest tests/test_utils.py -v
```

Ожидается: 4 теста PASS.

- [ ] **Step 7: Заменить `_log_audit` в `routers/auth.py` на импорт из utils**

В `backend/app/routers/auth.py` удалить локальную функцию `_log_audit` (строки ~37–45), заменить:

```python
from app.utils.audit import log_audit
from app.utils import audit_actions
```

И во всех вызовах `_log_audit(db, ...)` заменить на `log_audit(db, ...)`. Action-строки вроде `"login"` заменить на `audit_actions.LOGIN`, `"login_failed"` → `audit_actions.LOGIN_FAILED`, `"account_locked"` → `audit_actions.ACCOUNT_LOCKED`, `"logout"` → `audit_actions.LOGOUT`, `"change_password"` → `audit_actions.CHANGE_PASSWORD`.

- [ ] **Step 8: Прогнать существующие auth-тесты**

```bash
cd backend && pytest tests/test_auth.py -v
```

Ожидается: все существующие тесты по-прежнему PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/utils/ backend/app/routers/auth.py backend/tests/test_utils.py
git commit -m "feat(backend): add audit/system_info/user_agent utilities"
```

---

## Task 2: Auth-зависимости — kicked_at, is_deleted, require_superadmin

**Goal:** Расширить проверки в `get_current_user` (kicked_at, is_deleted), скрыть факт удаления при логине, добавить `require_superadmin`.

**Files:**
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/routers/auth.py:48-104`
- Test: `backend/tests/test_auth_extras.py`

**Acceptance Criteria:**
- [ ] `is_deleted=True` пользователь получает 401 на любой запрос с токеном.
- [ ] При попытке логина под удалённым — то же сообщение «Неверный логин или пароль» (не палим факт).
- [ ] Если `kicked_at > token.iat` → 401.
- [ ] `require_superadmin` отдаёт 403 для admin и user.

**Verify:** `cd backend && pytest tests/test_auth_extras.py -v`

**Steps:**

- [ ] **Step 1: Написать тесты `backend/tests/test_auth_extras.py`**

```python
import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from app.models.user import User


@pytest.mark.asyncio
async def test_login_deleted_user_returns_invalid_credentials(client, db_session):
    # создать пользователя, пометить удалённым
    from app.core.security import hash_password
    user = User(username="ghost", password_hash=hash_password("Pass1234"), is_deleted=True)
    db_session.add(user)
    await db_session.commit()

    r = await client.post("/api/auth/login", json={"username": "ghost", "password": "Pass1234"})
    assert r.status_code == 401
    assert "Неверный логин" in r.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_deleted_user_returns_401(client, user_token, db_session):
    # выставить is_deleted, токен должен перестать работать
    result = await db_session.execute(select(User).where(User.username == "user1"))
    u = result.scalar_one()
    u.is_deleted = True
    await db_session.commit()

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_kicked_at_invalidates_old_tokens(client, user_token, db_session):
    result = await db_session.execute(select(User).where(User.username == "user1"))
    u = result.scalar_one()
    u.kicked_at = datetime.now(timezone.utc)
    await db_session.commit()

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_require_superadmin_blocks_admin(client, admin_token):
    # нужно использовать любой эндпоинт, который потом будет под require_superadmin;
    # пока — мокаем через /api/admin/system (он будет добавлен в Task 10).
    # Здесь делаем placeholder — тест включится после Task 10.
    pass
```

- [ ] **Step 2: Обновить `backend/app/dependencies.py`**

Заменить целиком:

```python
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt

from app.core.database import get_db
from app.core.security import decode_token
from app.core import token_blacklist
from app.models.user import User
from app.models.audit import ActiveSession  # noqa: F401

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен истёк")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный тип токена")

    jti = payload.get("jti")
    if jti and token_blacklist.contains(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен отозван")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active or user.is_deleted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден или отключён")

    if user.kicked_at:
        iat = payload.get("iat")
        if iat and datetime.fromtimestamp(iat, tz=timezone.utc) < user.kicked_at:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия завершена администратором")

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права администратора")
    return user


async def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права суперадминистратора")
    return user
```

- [ ] **Step 3: Учесть `is_deleted` в `auth.login`**

В `backend/app/routers/auth.py` в функции `login`, после получения `user` и проверки `if not user`, добавить:

```python
    if user.is_deleted:
        await log_audit(db, user.id, audit_actions.LOGIN_FAILED, request, {"reason": "deleted"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
```

- [ ] **Step 4: Прогнать тесты**

```bash
cd backend && pytest tests/test_auth.py tests/test_auth_extras.py -v
```

Ожидается: все существующие + 3 новых PASS (4-й skip / placeholder).

- [ ] **Step 5: Commit**

```bash
git add backend/app/dependencies.py backend/app/routers/auth.py backend/tests/test_auth_extras.py
git commit -m "feat(auth): is_deleted, kicked_at and require_superadmin"
```

---

## Task 3: Раздача аватаров — `routers/users.py`

**Goal:** Эндпоинт `GET /api/users/{id}/avatar`, отдающий WebP залогиненному. Создание директории `data/avatars/`.

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py:227-243`
- Create: `backend/app/routers/users.py`
- Test: `backend/tests/test_avatar_serve.py`

**Acceptance Criteria:**
- [ ] `Settings.AVATARS_DIR` указывает на `backend/data/avatars`, директория создаётся при старте.
- [ ] `GET /api/users/{id}/avatar` без токена → 401.
- [ ] `GET /api/users/999/avatar` (нет файла) → 404.
- [ ] `GET /api/users/{id}/avatar` с существующим файлом → 200 + `image/webp`.

**Verify:** `cd backend && pytest tests/test_avatar_serve.py -v`

**Steps:**

- [ ] **Step 1: Добавить `AVATARS_DIR` в `backend/app/core/config.py`**

В классе `Settings` после `UPLOAD_DIR`:

```python
    AVATARS_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "avatars"))
```

- [ ] **Step 2: Создать директорию при старте — `backend/app/main.py`**

В `lifespan`, перед `await create_tables()`:

```python
    os.makedirs(settings.AVATARS_DIR, exist_ok=True)
```

- [ ] **Step 3: Написать тесты `backend/tests/test_avatar_serve.py`**

```python
import os
import pytest
from PIL import Image

from app.core.config import settings


@pytest.mark.asyncio
async def test_avatar_404_when_no_file(client, user_token):
    r = await client.get(
        "/api/users/1/avatar",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_avatar_401_without_token(client):
    r = await client.get("/api/users/1/avatar")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_avatar_200_when_file_exists(client, user_token, db_session):
    from sqlalchemy import select
    from app.models.user import User
    result = await db_session.execute(select(User).where(User.username == "user1"))
    user = result.scalar_one()

    img = Image.new("RGB", (256, 256), color=(50, 50, 200))
    path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    os.makedirs(settings.AVATARS_DIR, exist_ok=True)
    img.save(path, "WEBP", quality=88)

    user.avatar_path = f"avatars/{user.id}.webp"
    user.avatar_version = 1
    await db_session.commit()

    r = await client.get(
        f"/api/users/{user.id}/avatar",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    os.remove(path)
```

- [ ] **Step 4: Реализовать `backend/app/routers/users.py`**

```python
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == user_id, User.is_deleted == False))
    user = result.scalar_one_or_none()
    if not user or not user.avatar_path:
        raise HTTPException(status_code=404, detail="Аватар не найден")
    abs_path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Файл аватара отсутствует")
    return FileResponse(abs_path, media_type="image/webp")
```

- [ ] **Step 5: Подключить роутер в `backend/app/main.py`**

```python
from app.routers import auth, admin, youtube, convert, image, users
...
app.include_router(users.router)
```

- [ ] **Step 6: Прогнать тесты**

```bash
cd backend && pytest tests/test_avatar_serve.py -v
```

Ожидается: 3 теста PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/main.py backend/app/routers/users.py backend/tests/test_avatar_serve.py
git commit -m "feat(backend): avatar serving endpoint"
```

---

## Task 4: Schemas + базовые `/api/me` эндпоинты (без аватара)

**Goal:** Создать `schemas/me.py`, реализовать роутер `routers/me.py` с `GET /me`, `PATCH /me`, `GET /me/sessions`, `DELETE /me/sessions/{id}`, `DELETE /me/sessions`.

**Files:**
- Create: `backend/app/schemas/me.py`
- Create: `backend/app/routers/me.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_me.py`

**Acceptance Criteria:**
- [ ] `GET /api/me` возвращает расширенный `UserMeResponse` (avatar_version, created_at, last_login, usage_reset_date).
- [ ] `PATCH /api/me` меняет username; занятый username → 409; невалидный (regex) → 422.
- [ ] `GET /api/me/sessions` возвращает свои сессии с флагом `is_current`.
- [ ] `DELETE /api/me/sessions/{id}` удаляет именно свою сессию (чужую → 404).
- [ ] `DELETE /api/me/sessions` удаляет все, кроме текущей.

**Verify:** `cd backend && pytest tests/test_me.py -v`

**Steps:**

- [ ] **Step 1: Тесты `backend/tests/test_me.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_get_me_returns_extended_profile(client, user_token):
    r = await client.get("/api/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "avatar_version" in data
    assert "created_at" in data
    assert "last_login" in data
    assert "usage_reset_date" in data


@pytest.mark.asyncio
async def test_patch_me_changes_username(client, user_token):
    r = await client.patch(
        "/api/me",
        json={"username": "newname"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 200
    assert r.json()["username"] == "newname"


@pytest.mark.asyncio
async def test_patch_me_username_conflict(client, user_token, admin_token):
    r = await client.patch(
        "/api/me",
        json={"username": "admin"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_get_my_sessions(client, user_token):
    r = await client.get("/api/me/sessions", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) >= 1
    assert any(s["is_current"] for s in sessions)


@pytest.mark.asyncio
async def test_delete_all_other_sessions(client, user_token):
    r = await client.delete("/api/me/sessions", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    listed = await client.get("/api/me/sessions", headers={"Authorization": f"Bearer {user_token}"})
    assert all(s["is_current"] for s in listed.json())
```

- [ ] **Step 2: Реализовать `backend/app/schemas/me.py`**

```python
from datetime import datetime, date
from pydantic import BaseModel, Field


class UserMeResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool
    permissions: dict
    limits: dict
    usage_today: dict
    usage_reset_date: date
    avatar_version: int
    created_at: datetime
    last_login: datetime | None

    model_config = {"from_attributes": True}


class UpdateMeRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")


class MySessionItem(BaseModel):
    id: int
    ip_address: str
    user_agent: str
    created_at: datetime
    expires_at: datetime
    is_current: bool


class AvatarUploadResponse(BaseModel):
    avatar_path: str
    avatar_version: int


class MessageResponse(BaseModel):
    message: str
```

- [ ] **Step 3: Реализовать `backend/app/routers/me.py` (без avatar — будет в Task 5)**

```python
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.dependencies import get_current_user
from app.models.audit import ActiveSession
from app.models.user import User
from app.schemas.me import (
    UserMeResponse,
    UpdateMeRequest,
    MySessionItem,
    MessageResponse,
)
from app.utils.audit import log_audit
from app.utils import audit_actions

router = APIRouter(prefix="/api/me", tags=["me"])
security_scheme = HTTPBearer()


def _current_jti(credentials: HTTPAuthorizationCredentials) -> str | None:
    try:
        return decode_token(credentials.credentials).get("jti")
    except Exception:
        return None


@router.get("", response_model=UserMeResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("", response_model=UserMeResponse)
async def update_me(
    body: UpdateMeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.username == user.username:
        return user
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Имя занято")
    old = user.username
    user.username = body.username
    await log_audit(db, user.id, audit_actions.USERNAME_CHANGED, request, {"old_username": old, "new_username": body.username})
    return user


@router.get("/sessions", response_model=list[MySessionItem])
async def list_my_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # current jti decoded from access — но сессии хранятся по refresh jti.
    # Помечаем все как not current кроме той, что соответствует наибольшему created_at — самая свежая.
    # Лучше: сравниваем по сравнению с access-токеном через user_id; current = последняя по created_at.
    result = await db.execute(
        select(ActiveSession).where(ActiveSession.user_id == user.id).order_by(ActiveSession.created_at.desc())
    )
    sessions = list(result.scalars().all())
    items: list[MySessionItem] = []
    for i, s in enumerate(sessions):
        items.append(
            MySessionItem(
                id=s.id,
                ip_address=s.ip_address,
                user_agent=s.user_agent,
                created_at=s.created_at,
                expires_at=s.expires_at,
                is_current=(i == 0),
            )
        )
    return items


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def delete_my_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActiveSession).where(ActiveSession.id == session_id, ActiveSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    await db.delete(session)
    return MessageResponse(message="Сессия завершена")


@router.delete("/sessions", response_model=MessageResponse)
async def delete_all_my_sessions_except_current(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActiveSession).where(ActiveSession.user_id == user.id).order_by(ActiveSession.created_at.desc())
    )
    sessions = list(result.scalars().all())
    if len(sessions) <= 1:
        return MessageResponse(message="Других сессий нет")
    # Самая свежая — текущая, остальные удаляем
    for s in sessions[1:]:
        await db.delete(s)
    return MessageResponse(message="Остальные сессии завершены")
```

- [ ] **Step 4: Подключить роутер в `backend/app/main.py`**

```python
from app.routers import auth, admin, youtube, convert, image, users, me
...
app.include_router(me.router)
```

- [ ] **Step 5: Прогнать тесты**

```bash
cd backend && pytest tests/test_me.py -v
```

Ожидается: 5 тестов PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/me.py backend/app/routers/me.py backend/app/main.py backend/tests/test_me.py
git commit -m "feat(me): /api/me profile and sessions endpoints"
```

---

## Task 5: Avatar upload/delete (`/api/me/avatar`)

**Goal:** Реализовать загрузку и удаление аватара через Pillow с конверсией в WebP 256×256, инкрементом `avatar_version` и аудит-логом.

**Files:**
- Modify: `backend/app/routers/me.py`
- Test: `backend/tests/test_avatar_upload.py`

**Acceptance Criteria:**
- [ ] `POST /api/me/avatar` с PNG/JPG/WebP → 200, файл сохранён как `data/avatars/{id}.webp`, `avatar_version` инкрементирован.
- [ ] Файл > 5 МБ → 413.
- [ ] Не-картинка (text/binary) → 400.
- [ ] `DELETE /api/me/avatar` удаляет файл и обнуляет `avatar_path`.
- [ ] В audit_log появляются action'ы `avatar_updated` / `avatar_removed`.

**Verify:** `cd backend && pytest tests/test_avatar_upload.py -v`

**Steps:**

- [ ] **Step 1: Тесты `backend/tests/test_avatar_upload.py`**

```python
import io
import os
import pytest
from PIL import Image

from app.core.config import settings


def _png_bytes(size=(300, 200)) -> bytes:
    img = Image.new("RGB", size, color=(120, 50, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_avatar_upload_creates_webp_and_bumps_version(client, user_token, db_session):
    from sqlalchemy import select
    from app.models.user import User

    files = {"file": ("a.png", _png_bytes(), "image/png")}
    r = await client.post("/api/me/avatar", files=files, headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["avatar_version"] == 1

    result = await db_session.execute(select(User).where(User.username == "user1"))
    user = result.scalar_one()
    abs_path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    assert os.path.exists(abs_path)
    img = Image.open(abs_path)
    assert img.size[0] <= 256 and img.size[1] <= 256
    assert img.format == "WEBP"


@pytest.mark.asyncio
async def test_avatar_upload_rejects_too_large(client, user_token):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 1)
    files = {"file": ("big.png", big, "image/png")}
    r = await client.post("/api/me/avatar", files=files, headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_avatar_upload_rejects_non_image(client, user_token):
    files = {"file": ("a.txt", b"hello world", "text/plain")}
    r = await client.post("/api/me/avatar", files=files, headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_avatar_delete_removes_file(client, user_token, db_session):
    from sqlalchemy import select
    from app.models.user import User
    files = {"file": ("a.png", _png_bytes(), "image/png")}
    await client.post("/api/me/avatar", files=files, headers={"Authorization": f"Bearer {user_token}"})

    r = await client.delete("/api/me/avatar", headers={"Authorization": f"Bearer {user_token}"})
    assert r.status_code == 200

    result = await db_session.execute(select(User).where(User.username == "user1"))
    user = result.scalar_one()
    abs_path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    assert not os.path.exists(abs_path)
    assert user.avatar_path is None
```

- [ ] **Step 2: Добавить эндпоинты в `backend/app/routers/me.py`**

В верх файла:

```python
import io
import os
from PIL import Image, UnidentifiedImageError
from fastapi import UploadFile, File

from app.core.config import settings
from app.schemas.me import AvatarUploadResponse

MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
```

В конец роутера добавить:

```python
@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    request: Request = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Допустимы JPG, PNG, WebP")
    contents = await file.read(MAX_AVATAR_BYTES + 1)
    if len(contents) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 5 МБ")
    try:
        img = Image.open(io.BytesIO(contents))
        img.verify()
    except (UnidentifiedImageError, Exception):
        raise HTTPException(status_code=400, detail="Не валидное изображение")
    img = Image.open(io.BytesIO(contents)).convert("RGB")
    img.thumbnail((256, 256))
    os.makedirs(settings.AVATARS_DIR, exist_ok=True)
    abs_path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    img.save(abs_path, "WEBP", quality=88)

    user.avatar_path = f"avatars/{user.id}.webp"
    user.avatar_version = (user.avatar_version or 0) + 1

    await log_audit(db, user.id, audit_actions.AVATAR_UPDATED, request, {})
    return AvatarUploadResponse(avatar_path=user.avatar_path, avatar_version=user.avatar_version)


@router.delete("/avatar", response_model=MessageResponse)
async def delete_avatar(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    abs_path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    if os.path.exists(abs_path):
        os.remove(abs_path)
    user.avatar_path = None
    user.avatar_version = (user.avatar_version or 0) + 1
    await log_audit(db, user.id, audit_actions.AVATAR_REMOVED, request, {})
    return MessageResponse(message="Аватар удалён")
```

- [ ] **Step 3: Прогнать тесты**

```bash
cd backend && pytest tests/test_avatar_upload.py -v
```

Ожидается: 4 теста PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/me.py backend/tests/test_avatar_upload.py
git commit -m "feat(me): avatar upload and delete with Pillow"
```

---

## Task 6: Admin — schemas + расширенные пользовательские эндпоинты (list/get/patch/delete)

**Goal:** Создать `schemas/admin.py`, переписать `routers/admin.py` с пагинацией/фильтрами, добавить PATCH и DELETE с ролевыми правилами.

**Files:**
- Create: `backend/app/schemas/admin.py`
- Modify: `backend/app/routers/admin.py` (целиком переработать)
- Test: `backend/tests/test_admin_users.py`

**Acceptance Criteria:**
- [ ] `GET /api/admin/users?offset&limit&search&role&status&include_deleted` отдаёт пагинацию с `total`.
- [ ] `GET /api/admin/users/{id}` отдаёт полный объект с avatar_version, created_at, last_login.
- [ ] `PATCH /api/admin/users/{id}` меняет роль/permissions/limits/is_active, проверяет ролевые ограничения (см. §7.3 spec).
- [ ] `DELETE /api/admin/users/{id}` (только superadmin) делает soft delete, инвалидирует сессии.
- [ ] admin не может: править superadmin, править себя, ставить роль admin/superadmin.
- [ ] superadmin не может удалить себя.
- [ ] `?include_deleted=true` доступен только superadmin.

**Verify:** `cd backend && pytest tests/test_admin_users.py -v`

**Steps:**

- [ ] **Step 1: Тесты `backend/tests/test_admin_users.py`**

```python
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_list_users_paginated(client, admin_token):
    r = await client.get(
        "/api/admin/users?offset=0&limit=10",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body


@pytest.mark.asyncio
async def test_admin_creates_user_only(client, admin_token):
    r = await client.post(
        "/api/admin/users",
        json={"username": "newone", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201
    r2 = await client.post(
        "/api/admin/users",
        json={"username": "anotheradmin", "role": "admin"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r2.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_creates_any(client, superadmin_token):
    r = await client.post(
        "/api/admin/users",
        json={"username": "newadm", "role": "admin"},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_admin_cannot_edit_superadmin(client, admin_token, superadmin_id):
    r = await client.patch(
        f"/api/admin/users/{superadmin_id}",
        json={"limits": {"youtube_daily": 999}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_promote_anyone_to_admin(client, admin_token, regular_user_id):
    r = await client.patch(
        f"/api/admin/users/{regular_user_id}",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_edit_self(client, admin_token, admin_id):
    r = await client.patch(
        f"/api/admin/users/{admin_id}",
        json={"permissions": {"youtube": False, "converter": False, "image": False}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_soft_delete_user(client, superadmin_token, regular_user_id):
    r = await client.delete(
        f"/api/admin/users/{regular_user_id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert r.status_code == 200

    listed = await client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    ids = [u["id"] for u in listed.json()["items"]]
    assert regular_user_id not in ids

    listed2 = await client.get(
        "/api/admin/users?include_deleted=true",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    ids2 = [u["id"] for u in listed2.json()["items"]]
    assert regular_user_id in ids2


@pytest.mark.asyncio
async def test_superadmin_cannot_delete_self(client, superadmin_token, superadmin_id):
    r = await client.delete(
        f"/api/admin/users/{superadmin_id}",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_use_include_deleted(client, admin_token):
    r = await client.get(
        "/api/admin/users?include_deleted=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 403
```

(`superadmin_id`, `admin_id`, `regular_user_id`, `superadmin_token` — фикстуры в `tests/conftest.py`. Если их нет — добавить вместе с фикстурой `client` / `db_session`. Существующие auth-тесты подскажут структуру.)

- [ ] **Step 2: Создать `backend/app/schemas/admin.py`**

```python
from datetime import datetime, date
from pydantic import BaseModel, Field


class UserListItemAdmin(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    is_deleted: bool
    avatar_version: int
    created_at: datetime
    last_login: datetime | None
    usage_today: dict
    limits: dict

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserListItemAdmin]
    total: int


class UserDetailResponse(UserListItemAdmin):
    permissions: dict


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    role: str = Field(default="user", pattern=r"^(user|admin|superadmin)$")
    permissions: dict | None = None
    limits: dict | None = None


class CreateUserResponse(BaseModel):
    id: int
    username: str
    password: str
    role: str


class UpdateUserRequest(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(user|admin|superadmin)$")
    permissions: dict | None = None
    limits: dict | None = None
    is_active: bool | None = None


class ResetPasswordResponse(BaseModel):
    user_id: int
    username: str
    password: str


class ToggleActiveResponse(BaseModel):
    id: int
    is_active: bool


class MessageResponse(BaseModel):
    message: str
```

- [ ] **Step 3: Переписать `backend/app/routers/admin.py`**

Полностью заменить содержимое (отдельные эндпоинты на сессии/мониторинг будут добавлены в Tasks 8-11):

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, generate_random_password
from app.dependencies import require_admin, require_superadmin, get_current_user
from app.models.user import User
from app.models.audit import ActiveSession
from app.schemas.admin import (
    UserListItemAdmin,
    UserListResponse,
    UserDetailResponse,
    CreateUserRequest,
    CreateUserResponse,
    UpdateUserRequest,
    MessageResponse,
)
from app.utils.audit import log_audit
from app.utils import audit_actions

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _can_admin_modify(actor: User, target: User) -> bool:
    if actor.role == "superadmin":
        return True
    if actor.role != "admin":
        return False
    if target.role == "superadmin":
        return False
    if target.id == actor.id:
        return False
    return True


def _diff_changes(target: User, body: UpdateUserRequest) -> dict:
    changes: dict = {}
    if body.role is not None and body.role != target.role:
        changes["role"] = [target.role, body.role]
    if body.permissions is not None and body.permissions != target.permissions:
        changes["permissions"] = [target.permissions, body.permissions]
    if body.limits is not None and body.limits != target.limits:
        changes["limits"] = [target.limits, body.limits]
    if body.is_active is not None and body.is_active != target.is_active:
        changes["is_active"] = [target.is_active, body.is_active]
    return changes


@router.get("/users", response_model=UserListResponse, dependencies=[Depends(require_admin)])
async def list_users(
    offset: int = 0,
    limit: int = Query(default=20, le=100),
    search: str | None = None,
    role: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    include_deleted: bool = False,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if include_deleted and actor.role != "superadmin":
        raise HTTPException(status_code=403, detail="Только superadmin")

    stmt = select(User)
    count_stmt = select(func.count(User.id))
    if not include_deleted:
        stmt = stmt.where(User.is_deleted == False)
        count_stmt = count_stmt.where(User.is_deleted == False)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(User.username.ilike(like))
        count_stmt = count_stmt.where(User.username.ilike(like))
    if role:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)
    if status_filter == "active":
        stmt = stmt.where(User.is_active == True, User.is_deleted == False)
        count_stmt = count_stmt.where(User.is_active == True, User.is_deleted == False)
    elif status_filter == "inactive":
        stmt = stmt.where(User.is_active == False, User.is_deleted == False)
        count_stmt = count_stmt.where(User.is_active == False, User.is_deleted == False)
    elif status_filter == "deleted":
        if actor.role != "superadmin":
            raise HTTPException(status_code=403, detail="Только superadmin")
        stmt = stmt.where(User.is_deleted == True)
        count_stmt = count_stmt.where(User.is_deleted == True)

    stmt = stmt.order_by(User.id).offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar() or 0
    return UserListResponse(items=[UserListItemAdmin.model_validate(u) for u in items], total=total)


@router.get("/users/{user_id}", response_model=UserDetailResponse, dependencies=[Depends(require_admin)])
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.post("/users", response_model=CreateUserResponse, status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.role == "admin" and body.role != "user":
        raise HTTPException(status_code=403, detail="Admin может создавать только user")

    existing = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Пользователь с таким именем уже существует")

    password = generate_random_password()
    user = User(
        username=body.username,
        password_hash=hash_password(password),
        role=body.role,
        must_change_password=True,
        permissions=body.permissions or {"youtube": True, "converter": True, "image": True},
        limits=body.limits or {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50},
    )
    db.add(user)
    await db.flush()

    await log_audit(
        db, actor.id, audit_actions.USER_CREATED, request,
        {"target_user_id": user.id, "target_username": user.username, "role": user.role,
         "permissions": user.permissions, "limits": user.limits},
    )
    return CreateUserResponse(id=user.id, username=user.username, password=password, role=user.role)


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if not _can_admin_modify(actor, target):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    if actor.role == "admin" and body.role and body.role != "user":
        raise HTTPException(status_code=403, detail="Admin может назначать только роль user")

    changes = _diff_changes(target, body)
    if body.role is not None:
        target.role = body.role
    if body.permissions is not None:
        target.permissions = body.permissions
    if body.limits is not None:
        target.limits = body.limits
    if body.is_active is not None:
        target.is_active = body.is_active

    if changes:
        await log_audit(
            db, actor.id, audit_actions.USER_UPDATED, request,
            {"target_user_id": target.id, "target_username": target.username, "changes": changes},
        )
    return target


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    request: Request,
    actor: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == actor.id:
        raise HTTPException(status_code=403, detail="Нельзя удалить себя")
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    target.is_deleted = True
    target.kicked_at = datetime.now(timezone.utc)
    # удаляем все refresh-сессии
    sessions = (await db.execute(select(ActiveSession).where(ActiveSession.user_id == target.id))).scalars().all()
    for s in sessions:
        await db.delete(s)

    await log_audit(
        db, actor.id, audit_actions.USER_DELETED, request,
        {"target_user_id": target.id, "target_username": target.username},
    )
    return MessageResponse(message="Пользователь удалён")
```

- [ ] **Step 4: Прогнать тесты**

```bash
cd backend && pytest tests/test_admin_users.py -v
```

Ожидается: 9 тестов PASS. Если падают на отсутствующих фикстурах — добавить в `tests/conftest.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/routers/admin.py backend/tests/test_admin_users.py backend/tests/conftest.py
git commit -m "feat(admin): users CRUD with role-based rules and pagination"
```

---

## Task 7: Admin — reset-password и toggle-active

**Goal:** Добавить эндпоинты для сброса пароля (с возвратом нового) и переключения активности с правильными ролевыми правилами и аудитом.

**Files:**
- Modify: `backend/app/routers/admin.py`
- Test: `backend/tests/test_admin_user_actions.py`

**Acceptance Criteria:**
- [ ] `POST /api/admin/users/{id}/reset-password` возвращает новый пароль один раз, выставляет `must_change_password=true`, инвалидирует сессии (kicked_at = now).
- [ ] admin не может сбросить пароль superadmin или себе через эту админку.
- [ ] superadmin может сбросить любому, включая себя.
- [ ] `POST /api/admin/users/{id}/toggle-active` переключает `is_active`; admin не трогает superadmin/себя; superadmin не себя.
- [ ] Оба действия логируются (`USER_PASSWORD_RESET`, `USER_TOGGLED_ACTIVE`).

**Verify:** `cd backend && pytest tests/test_admin_user_actions.py -v`

**Steps:**

- [ ] **Step 1: Тесты `backend/tests/test_admin_user_actions.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_reset_password_returns_new_password(client, superadmin_token, regular_user_id):
    r = await client.post(
        f"/api/admin/users/{regular_user_id}/reset-password",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "password" in body and len(body["password"]) >= 12


@pytest.mark.asyncio
async def test_admin_cannot_reset_superadmin_password(client, admin_token, superadmin_id):
    r = await client.post(
        f"/api/admin/users/{superadmin_id}/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_toggle_active_flips_state(client, superadmin_token, regular_user_id, db_session):
    from sqlalchemy import select
    from app.models.user import User
    r = await client.post(
        f"/api/admin/users/{regular_user_id}/toggle-active",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_superadmin_cannot_toggle_self(client, superadmin_token, superadmin_id):
    r = await client.post(
        f"/api/admin/users/{superadmin_id}/toggle-active",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert r.status_code == 403
```

- [ ] **Step 2: Добавить эндпоинты в `backend/app/routers/admin.py`**

После `delete_user`:

```python
from app.schemas.admin import ResetPasswordResponse, ToggleActiveResponse
from datetime import datetime, timezone


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    user_id: int,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if actor.role == "admin":
        if target.role == "superadmin" or target.id == actor.id:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
    new_password = generate_random_password()
    target.password_hash = hash_password(new_password)
    target.must_change_password = True
    target.kicked_at = datetime.now(timezone.utc)
    sessions = (await db.execute(select(ActiveSession).where(ActiveSession.user_id == target.id))).scalars().all()
    for s in sessions:
        await db.delete(s)

    await log_audit(
        db, actor.id, audit_actions.USER_PASSWORD_RESET, request,
        {"target_user_id": target.id, "target_username": target.username},
    )
    return ResetPasswordResponse(user_id=target.id, username=target.username, password=new_password)


@router.post("/users/{user_id}/toggle-active", response_model=ToggleActiveResponse)
async def toggle_active(
    user_id: int,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.id == actor.id:
        raise HTTPException(status_code=403, detail="Нельзя переключать самого себя")
    if actor.role == "admin" and target.role == "superadmin":
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    target.is_active = not target.is_active

    await log_audit(
        db, actor.id, audit_actions.USER_TOGGLED_ACTIVE, request,
        {"target_user_id": target.id, "target_username": target.username, "new_state": target.is_active},
    )
    return ToggleActiveResponse(id=target.id, is_active=target.is_active)
```

- [ ] **Step 3: Прогнать тесты**

```bash
cd backend && pytest tests/test_admin_user_actions.py -v
```

Ожидается: 4 теста PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/admin.py backend/tests/test_admin_user_actions.py
git commit -m "feat(admin): reset-password and toggle-active endpoints"
```

---

## Task 8: Admin — сессии (`/admin/sessions`, kill)

**Goal:** Эндпоинты для просмотра всех активных сессий и их завершения с инвалидацией access-токена через `kicked_at`.

**Files:**
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/app/schemas/admin.py`
- Test: `backend/tests/test_admin_sessions.py`

**Acceptance Criteria:**
- [ ] `GET /api/admin/sessions` возвращает список с `id, user_id, username, ip_address, user_agent, created_at, expires_at`.
- [ ] `DELETE /api/admin/sessions/{id}` удаляет запись из `active_sessions` и устанавливает `users.kicked_at = now`.
- [ ] После kill старый access-токен жертвы → 401.
- [ ] В audit_log запись `SESSION_KILLED_BY_ADMIN`.

**Verify:** `cd backend && pytest tests/test_admin_sessions.py -v`

**Steps:**

- [ ] **Step 1: Добавить схему в `backend/app/schemas/admin.py`**

```python
class AdminSessionItem(BaseModel):
    id: int
    user_id: int
    username: str
    ip_address: str
    user_agent: str
    created_at: datetime
    expires_at: datetime
```

- [ ] **Step 2: Тесты `backend/tests/test_admin_sessions.py`**

```python
import pytest
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_list_sessions(client, admin_token):
    r = await client.get("/api/admin/sessions", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_kill_session_invalidates_old_access_token(client, admin_token, user_token, db_session):
    from sqlalchemy import select
    from app.models.audit import ActiveSession
    from app.models.user import User
    user = (await db_session.execute(select(User).where(User.username == "user1"))).scalar_one()
    sess = (await db_session.execute(select(ActiveSession).where(ActiveSession.user_id == user.id))).scalars().all()[0]

    r = await client.delete(
        f"/api/admin/sessions/{sess.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200

    r2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert r2.status_code == 401
```

- [ ] **Step 3: Эндпоинты в `backend/app/routers/admin.py`**

```python
from app.schemas.admin import AdminSessionItem


@router.get("/sessions", response_model=list[AdminSessionItem], dependencies=[Depends(require_admin)])
async def list_all_sessions(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(ActiveSession, User.username)
            .join(User, User.id == ActiveSession.user_id)
            .order_by(ActiveSession.created_at.desc())
        )
    ).all()
    return [
        AdminSessionItem(
            id=s.id, user_id=s.user_id, username=username,
            ip_address=s.ip_address, user_agent=s.user_agent,
            created_at=s.created_at, expires_at=s.expires_at,
        )
        for (s, username) in rows
    ]


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def kill_session(
    session_id: int,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    session = (await db.execute(select(ActiveSession).where(ActiveSession.id == session_id))).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    target = (await db.execute(select(User).where(User.id == session.user_id))).scalar_one_or_none()
    if target and actor.role == "admin" and target.role == "superadmin":
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    target_user_id = session.user_id
    target_username = target.username if target else "?"
    await db.delete(session)
    if target:
        target.kicked_at = datetime.now(timezone.utc)

    await log_audit(
        db, actor.id, audit_actions.SESSION_KILLED_BY_ADMIN, request,
        {"target_user_id": target_user_id, "target_username": target_username, "session_id": session_id},
    )
    return MessageResponse(message="Сессия завершена")
```

- [ ] **Step 4: Прогнать тесты**

```bash
cd backend && pytest tests/test_admin_sessions.py -v
```

Ожидается: 2 теста PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin.py backend/app/schemas/admin.py backend/tests/test_admin_sessions.py
git commit -m "feat(admin): list and kill sessions with kicked_at"
```

---

## Task 9: Admin — расширенная статистика `/api/admin/stats`

**Goal:** Заменить минимальный stats на полный (downloads/conversions/image_ops_today, storage_used_mb, active_sessions, top_users, deleted_users).

**Files:**
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/app/schemas/admin.py`
- Test: `backend/tests/test_admin_stats.py`

**Acceptance Criteria:**
- [ ] `GET /api/admin/stats` возвращает все поля из spec §6.5.
- [ ] `total_downloads_today` = sum по `usage_today.youtube` (не удалённых).
- [ ] `top_users` — список из 5 пользователей с наибольшей суммой `usage_today`.
- [ ] `storage_used_mb` корректно считает размер `data/` + `uploads/`.

**Verify:** `cd backend && pytest tests/test_admin_stats.py -v`

**Steps:**

- [ ] **Step 1: Схемы в `backend/app/schemas/admin.py`**

```python
class TopUser(BaseModel):
    user_id: int
    username: str
    avatar_version: int
    total_today: int


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    deleted_users: int
    total_downloads_today: int
    total_conversions_today: int
    total_image_ops_today: int
    storage_used_mb: float
    active_sessions: int
    top_users: list[TopUser]
    total_audit_logs: int
```

- [ ] **Step 2: Тесты `backend/tests/test_admin_stats.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_stats_returns_full_shape(client, admin_token):
    r = await client.get("/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    for key in [
        "total_users", "active_users", "deleted_users",
        "total_downloads_today", "total_conversions_today", "total_image_ops_today",
        "storage_used_mb", "active_sessions", "top_users", "total_audit_logs",
    ]:
        assert key in body, f"missing {key}"
    assert isinstance(body["top_users"], list)


@pytest.mark.asyncio
async def test_stats_aggregates_usage(client, admin_token, db_session):
    from sqlalchemy import select
    from app.models.user import User
    users = (await db_session.execute(select(User).where(User.is_deleted == False))).scalars().all()
    for u in users[:3]:
        u.usage_today = {"youtube": 5, "converter": 2, "image": 1}
    await db_session.commit()

    r = await client.get("/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
    body = r.json()
    assert body["total_downloads_today"] >= 15
```

- [ ] **Step 3: Реализовать в `backend/app/routers/admin.py`**

Заменить существующий `get_stats`:

```python
import os
from app.core.config import settings
from app.models.audit import AuditLog
from app.schemas.admin import AdminStats, TopUser


def _dir_size_mb(path: str) -> float:
    if not os.path.isdir(path):
        return 0.0
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)


@router.get("/stats", response_model=AdminStats, dependencies=[Depends(require_admin)])
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_users = (await db.execute(select(func.count(User.id)).where(User.is_deleted == False))).scalar() or 0
    active_users = (await db.execute(
        select(func.count(User.id)).where(User.is_active == True, User.is_deleted == False)
    )).scalar() or 0
    deleted_users = (await db.execute(select(func.count(User.id)).where(User.is_deleted == True))).scalar() or 0

    users = (await db.execute(select(User).where(User.is_deleted == False))).scalars().all()
    dl = sum(int(u.usage_today.get("youtube", 0)) for u in users)
    cv = sum(int(u.usage_today.get("converter", 0)) for u in users)
    im = sum(int(u.usage_today.get("image", 0)) for u in users)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    active_sess = (await db.execute(
        select(func.count(ActiveSession.id)).where(ActiveSession.expires_at > now)
    )).scalar() or 0

    storage_mb = _dir_size_mb(settings.UPLOAD_DIR) + _dir_size_mb(os.path.dirname(settings.UPLOAD_DIR.rstrip("/")) + "/data")

    top_sorted = sorted(
        users,
        key=lambda u: int(u.usage_today.get("youtube", 0)) + int(u.usage_today.get("converter", 0)) + int(u.usage_today.get("image", 0)),
        reverse=True,
    )[:5]
    top_users = [
        TopUser(
            user_id=u.id, username=u.username, avatar_version=u.avatar_version,
            total_today=int(u.usage_today.get("youtube", 0)) + int(u.usage_today.get("converter", 0)) + int(u.usage_today.get("image", 0)),
        )
        for u in top_sorted
    ]

    total_logs = (await db.execute(select(func.count(AuditLog.id)))).scalar() or 0

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        deleted_users=deleted_users,
        total_downloads_today=dl,
        total_conversions_today=cv,
        total_image_ops_today=im,
        storage_used_mb=storage_mb,
        active_sessions=active_sess,
        top_users=top_users,
        total_audit_logs=total_logs,
    )
```

- [ ] **Step 4: Прогнать тесты**

```bash
cd backend && pytest tests/test_admin_stats.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin.py backend/app/schemas/admin.py backend/tests/test_admin_stats.py
git commit -m "feat(admin): extended stats with top_users and aggregations"
```

---

## Task 10: Admin — system info и storage (psutil, superadmin only)

**Goal:** Эндпоинты `/api/admin/system` (CPU/RAM/disk/uptime/версии) и `/api/admin/storage` (детальный размер директорий) — только superadmin.

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/app/schemas/admin.py`
- Test: `backend/tests/test_admin_monitoring.py`

**Acceptance Criteria:**
- [ ] `psutil` добавлен в `requirements.txt`.
- [ ] admin → 403 на `/system`, superadmin → 200 с CPU/RAM/disk/uptime/версии.
- [ ] `/storage` возвращает данные по `data/`, `uploads/`, `avatars/` и общему количеству файлов.

**Verify:** `cd backend && pytest tests/test_admin_monitoring.py -v`

**Steps:**

- [ ] **Step 1: Добавить psutil**

В `backend/requirements.txt` добавить строку:
```
psutil>=5.9.0
```
Установить:
```bash
cd backend && pip install psutil
```

- [ ] **Step 2: Схемы**

В `backend/app/schemas/admin.py`:

```python
class SystemInfo(BaseModel):
    cpu_percent: float
    ram_used_mb: float
    ram_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: int
    python_version: str
    ffmpeg_version: str
    yt_dlp_version: str


class StorageInfo(BaseModel):
    data_size_mb: float
    uploads_size_mb: float
    avatars_size_mb: float
    total_files: int
```

- [ ] **Step 3: Тесты `backend/tests/test_admin_monitoring.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_system_admin_forbidden(client, admin_token):
    r = await client.get("/api/admin/system", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_system_superadmin_ok(client, superadmin_token):
    r = await client.get("/api/admin/system", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["ram_total_mb"] > 0
    assert "python_version" in body


@pytest.mark.asyncio
async def test_storage_superadmin_ok(client, superadmin_token):
    r = await client.get("/api/admin/storage", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert "data_size_mb" in body
    assert "total_files" in body
```

- [ ] **Step 4: Реализовать в `backend/app/routers/admin.py`**

```python
import time
import psutil
from app.utils.system_info import get_tool_versions
from app.schemas.admin import SystemInfo, StorageInfo

_BOOT_TIME = psutil.boot_time()


@router.get("/system", response_model=SystemInfo, dependencies=[Depends(require_superadmin)])
async def get_system_info():
    cpu = psutil.cpu_percent(interval=0.2)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    versions = get_tool_versions()
    return SystemInfo(
        cpu_percent=cpu,
        ram_used_mb=round(vm.used / (1024 * 1024), 1),
        ram_total_mb=round(vm.total / (1024 * 1024), 1),
        disk_used_gb=round(disk.used / (1024 ** 3), 2),
        disk_total_gb=round(disk.total / (1024 ** 3), 2),
        uptime_seconds=int(time.time() - _BOOT_TIME),
        python_version=versions.get("python_version", "недоступно"),
        ffmpeg_version=versions.get("ffmpeg_version", "недоступно"),
        yt_dlp_version=versions.get("yt_dlp_version", "недоступно"),
    )


def _count_files(path: str) -> int:
    if not os.path.isdir(path):
        return 0
    n = 0
    for _, _, files in os.walk(path):
        n += len(files)
    return n


@router.get("/storage", response_model=StorageInfo, dependencies=[Depends(require_superadmin)])
async def get_storage_info():
    data_dir = os.path.dirname(settings.UPLOAD_DIR.rstrip("/")) + "/data"
    return StorageInfo(
        data_size_mb=_dir_size_mb(data_dir),
        uploads_size_mb=_dir_size_mb(settings.UPLOAD_DIR),
        avatars_size_mb=_dir_size_mb(settings.AVATARS_DIR),
        total_files=_count_files(data_dir) + _count_files(settings.UPLOAD_DIR),
    )
```

- [ ] **Step 5: Прогнать тесты**

```bash
cd backend && pytest tests/test_admin_monitoring.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/routers/admin.py backend/app/schemas/admin.py backend/tests/test_admin_monitoring.py
git commit -m "feat(admin): system and storage info via psutil"
```

---

## Task 11: Admin — расширенный аудит-лог с фильтрами и CSV-экспортом

**Goal:** Заменить `/api/admin/audit-logs` на `/api/admin/audit-log` с фильтрами по user_id/action/from/to и добавить CSV-экспорт.

**Files:**
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/app/schemas/admin.py`
- Test: `backend/tests/test_audit_log.py`

**Acceptance Criteria:**
- [ ] `GET /api/admin/audit-log?user_id&action&from&to&offset&limit` возвращает `{items, total}` с фильтрацией.
- [ ] `GET /api/admin/audit-log/export.csv` возвращает `text/csv` с теми же фильтрами.
- [ ] Старый путь `/audit-logs` удалён (зачищаем плейсхолдер).

**Verify:** `cd backend && pytest tests/test_audit_log.py -v`

**Steps:**

- [ ] **Step 1: Схемы**

```python
class AuditLogItem(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    action: str
    details: dict | None
    ip_address: str
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
```

- [ ] **Step 2: Тесты `backend/tests/test_audit_log.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_audit_log_filter_by_action(client, admin_token):
    r = await client.get(
        "/api/admin/audit-log?action=login",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert all(item["action"] == "login" for item in body["items"])


@pytest.mark.asyncio
async def test_audit_log_export_csv(client, admin_token):
    r = await client.get(
        "/api/admin/audit-log/export.csv",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert b"action" in r.content[:200]
```

- [ ] **Step 3: Реализовать в `backend/app/routers/admin.py`**

Удалить существующий `get_audit_logs`. Добавить:

```python
import csv
import io
from datetime import datetime
from fastapi.responses import StreamingResponse
from app.schemas.admin import AuditLogItem, AuditLogListResponse


def _build_audit_filter(stmt, user_id: int | None, action: str | None,
                       date_from: datetime | None, date_to: datetime | None):
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return stmt


@router.get("/audit-log", response_model=AuditLogListResponse, dependencies=[Depends(require_admin)])
async def get_audit_log(
    user_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    offset: int = 0,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    base = select(AuditLog, User.username).outerjoin(User, User.id == AuditLog.user_id)
    base = _build_audit_filter(base, user_id, action, date_from, date_to)
    base = base.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(base)).all()

    cnt = select(func.count(AuditLog.id))
    cnt = _build_audit_filter(cnt, user_id, action, date_from, date_to)
    total = (await db.execute(cnt)).scalar() or 0

    items = [
        AuditLogItem(
            id=l.id, user_id=l.user_id, username=username,
            action=l.action, details=l.details,
            ip_address=l.ip_address, created_at=l.created_at,
        )
        for (l, username) in rows
    ]
    return AuditLogListResponse(items=items, total=total)


@router.get("/audit-log/export.csv", dependencies=[Depends(require_admin)])
async def export_audit_log(
    user_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
):
    base = select(AuditLog, User.username).outerjoin(User, User.id == AuditLog.user_id)
    base = _build_audit_filter(base, user_id, action, date_from, date_to)
    base = base.order_by(AuditLog.created_at.desc())
    rows = (await db.execute(base)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "user_id", "username", "action", "ip_address", "details"])
    for (l, username) in rows:
        writer.writerow([
            l.id, l.created_at.isoformat() if l.created_at else "",
            l.user_id or "", username or "",
            l.action, l.ip_address,
            (l.details or {}),
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )
```

- [ ] **Step 4: Прогнать тесты**

```bash
cd backend && pytest tests/test_audit_log.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/admin.py backend/app/schemas/admin.py backend/tests/test_audit_log.py
git commit -m "feat(admin): audit-log filters and CSV export"
```

---

## Task 12: Frontend — обновление типов

**Goal:** Расширить `types/index.ts` под новые поля User и admin/me-эндпоинты.

**Files:**
- Modify: `frontend/src/types/index.ts`

**Acceptance Criteria:**
- [ ] Тип `User` содержит `avatar_version`, `created_at`, `last_login`, `usage_reset_date`, `is_deleted`.
- [ ] Добавлены типы `AdminStats`, `TopUser`, `SystemInfo`, `StorageInfo`, `AdminSessionItem`, `MySessionItem`, `AuditLogItem`, `UserDetail`, `UpdateUserRequest`, `ResetPasswordResponse`.
- [ ] `bun run lint` и `tsc -b` проходят.

**Verify:** `cd frontend && bunx tsc -b --noEmit`

**Steps:**

- [ ] **Step 1: Заменить содержимое `frontend/src/types/index.ts`**

```typescript
export type Role = 'user' | 'admin' | 'superadmin'

export interface User {
  id: number
  username: string
  role: Role
  is_active: boolean
  is_deleted?: boolean
  must_change_password: boolean
  permissions: { youtube: boolean; converter: boolean; image: boolean }
  limits: { youtube_daily: number; convert_daily: number; image_daily: number }
  usage_today: { youtube: number; converter: number; image: number }
  usage_reset_date?: string
  avatar_version?: number
  created_at?: string
  last_login?: string | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  must_change_password: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

export interface UserListItem {
  id: number
  username: string
  role: Role
  is_active: boolean
  is_deleted: boolean
  avatar_version: number
  created_at: string
  last_login: string | null
  usage_today: Record<string, number>
  limits: Record<string, number>
}

export interface UserListResponse {
  items: UserListItem[]
  total: number
}

export interface UserDetail extends UserListItem {
  permissions: Record<string, boolean>
}

export interface CreateUserRequest {
  username: string
  role: Role
  permissions?: Record<string, boolean>
  limits?: Record<string, number>
}

export interface CreateUserResponse {
  id: number
  username: string
  password: string
  role: Role
}

export interface UpdateUserRequest {
  role?: Role
  permissions?: Record<string, boolean>
  limits?: Record<string, number>
  is_active?: boolean
}

export interface ResetPasswordResponse {
  user_id: number
  username: string
  password: string
}

export interface MySessionItem {
  id: number
  ip_address: string
  user_agent: string
  created_at: string
  expires_at: string
  is_current: boolean
}

export interface AdminSessionItem {
  id: number
  user_id: number
  username: string
  ip_address: string
  user_agent: string
  created_at: string
  expires_at: string
}

export interface AuditLogItem {
  id: number
  user_id: number | null
  username: string | null
  action: string
  details: Record<string, unknown> | null
  ip_address: string
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogItem[]
  total: number
}

export interface TopUser {
  user_id: number
  username: string
  avatar_version: number
  total_today: number
}

export interface AdminStats {
  total_users: number
  active_users: number
  deleted_users: number
  total_downloads_today: number
  total_conversions_today: number
  total_image_ops_today: number
  storage_used_mb: number
  active_sessions: number
  top_users: TopUser[]
  total_audit_logs: number
}

export interface SystemInfo {
  cpu_percent: number
  ram_used_mb: number
  ram_total_mb: number
  disk_used_gb: number
  disk_total_gb: number
  uptime_seconds: number
  python_version: string
  ffmpeg_version: string
  yt_dlp_version: string
}

export interface StorageInfo {
  data_size_mb: number
  uploads_size_mb: number
  avatars_size_mb: number
  total_files: number
}

export interface AvatarUploadResponse {
  avatar_path: string
  avatar_version: number
}
```

- [ ] **Step 2: Проверить компиляцию**

```bash
cd frontend && bunx tsc -b --noEmit
```

Ожидается: ошибки только в местах, которые ещё используют старые типы — будут исправляться в следующих task'ах.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): extend User and add admin/me types"
```

---

## Task 13: Frontend — `useAuthedImage` + `AvatarImage` + Topbar

**Goal:** Общие компоненты для отображения аватаров с авторизацией: хук и компонент. Заменить кружок-с-буквой в Topbar на `AvatarImage`.

**Files:**
- Create: `frontend/src/hooks/useAuthedImage.ts`
- Create: `frontend/src/components/AvatarImage.tsx`
- Create: `frontend/src/components/AvatarImage.module.css`
- Modify: `frontend/src/components/Layout/Topbar.tsx`

**Acceptance Criteria:**
- [ ] `useAuthedImage(url)` возвращает blob-URL и вызывает `URL.revokeObjectURL` при размонтировании / смене URL.
- [ ] `<AvatarImage userId={n} version={v} size={64} />` отображает аватар или иконку User из lucide.
- [ ] Topbar показывает реальный аватар пользователя; если его нет — иконку User.

**Verify:** Открыть приложение, авторизоваться, убедиться, что Topbar рендерит иконку User (аватар ещё не загружен).

```bash
playwright-cli open http://localhost:5173/
playwright-cli snapshot
```

Должно быть видно иконку человечка вместо буквы в Topbar.

**Steps:**

- [ ] **Step 1: `frontend/src/hooks/useAuthedImage.ts`**

```typescript
import { useEffect, useState } from 'react'
import api from '../api/client'

export function useAuthedImage(url: string | null): string | null {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    if (!url) {
      setSrc(null)
      return
    }
    let cancelled = false
    let objectUrl: string | null = null

    api
      .get<Blob>(url, { responseType: 'blob' })
      .then(({ data }) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(data)
        setSrc(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setSrc(null)
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url])

  return src
}
```

- [ ] **Step 2: `frontend/src/components/AvatarImage.tsx`**

```tsx
import { User as UserIcon } from 'lucide-react'
import { useAuthedImage } from '../hooks/useAuthedImage'
import styles from './AvatarImage.module.css'

interface Props {
  userId: number | undefined
  version?: number
  size?: number
  className?: string
}

export default function AvatarImage({ userId, version = 0, size = 32, className }: Props) {
  const url = userId ? `/users/${userId}/avatar?v=${version}` : null
  const src = useAuthedImage(url)

  const style: React.CSSProperties = {
    width: size,
    height: size,
    minWidth: size,
  }

  if (src) {
    return <img src={src} alt="" className={`${styles.avatar} ${className ?? ''}`} style={style} />
  }
  return (
    <div className={`${styles.fallback} ${className ?? ''}`} style={style}>
      <UserIcon size={Math.round(size * 0.55)} />
    </div>
  )
}
```

- [ ] **Step 3: `frontend/src/components/AvatarImage.module.css`**

```css
.avatar {
  border-radius: var(--radius-full);
  object-fit: cover;
  display: block;
}

.fallback {
  border-radius: var(--radius-full);
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
}
```

- [ ] **Step 4: Заменить аватарку в `frontend/src/components/Layout/Topbar.tsx`**

Удалить блок с `userAvatar` (буква), вставить:

```tsx
import AvatarImage from '../AvatarImage'

// ... внутри userInfo:
<AvatarImage userId={user?.id} version={user?.avatar_version ?? 0} size={36} />
```

Старые стили `.userAvatar` оставить — они переопределяются классом `.avatar` из AvatarImage.

- [ ] **Step 5: Проверка через playwright-cli**

```bash
cd backend && uvicorn app.main:app --port 8000 &
cd frontend && bun run dev &
sleep 5
playwright-cli open http://localhost:5173/login
playwright-cli snapshot
# залогиниться через UI или через curl + localStorage.setItem
playwright-cli close
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useAuthedImage.ts frontend/src/components/AvatarImage.tsx frontend/src/components/AvatarImage.module.css frontend/src/components/Layout/Topbar.tsx
git commit -m "feat(frontend): AvatarImage component with authed blob fetch"
```

---

## Task 14: Frontend — HomePage и редиректы

**Goal:** Создать главную страницу с логотипом и плитками; изменить редиректы на `/`.

**Files:**
- Create: `frontend/src/pages/Home/HomePage.tsx`
- Create: `frontend/src/pages/Home/Home.module.css`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Login/LoginPage.tsx` (редирект после логина)
- Modify: `frontend/src/pages/ChangePassword/ChangePasswordPage.tsx` (редирект после смены)

**Acceptance Criteria:**
- [ ] Маршрут `/` рендерит `HomePage` под `MainLayout`.
- [ ] Catch-all `*` ведёт на `/`.
- [ ] После логина — `/`. После смены пароля — `/`.
- [ ] Плитки появляются по permissions; для `user` есть «Личный кабинет», для admin/superadmin — «Admin Panel».

**Verify:**
```bash
playwright-cli open http://localhost:5173/login
# залогиниться обычным пользователем
playwright-cli snapshot
# Должна быть видна сетка плиток и логотип "NaturalskWeb"
```

**Steps:**

- [ ] **Step 1: `frontend/src/pages/Home/HomePage.tsx`**

```tsx
import { NavLink } from 'react-router-dom'
import { Youtube, FileBox, Image as ImageIcon, User as UserIcon, Shield } from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Home.module.css'

interface Tile {
  to: string
  icon: typeof Youtube
  title: string
  description: string
}

export default function HomePage() {
  const { user } = useAuth()
  if (!user) return null

  const isAdmin = user.role === 'admin' || user.role === 'superadmin'
  const tiles: Tile[] = []

  if (user.permissions.youtube) {
    tiles.push({ to: '/youtube', icon: Youtube, title: 'YouTube Downloader', description: 'Скачивание видео' })
  }
  if (user.permissions.converter) {
    tiles.push({ to: '/converter', icon: FileBox, title: 'File Converter', description: 'Конвертация файлов' })
  }
  if (user.permissions.image) {
    tiles.push({ to: '/image', icon: ImageIcon, title: 'Image Processor', description: 'Обработка изображений' })
  }
  if (isAdmin) {
    tiles.push({ to: '/admin', icon: Shield, title: 'Admin Panel', description: 'Управление и мониторинг' })
  } else {
    tiles.push({ to: '/me', icon: UserIcon, title: 'Личный кабинет', description: 'Профиль и статистика' })
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.logo}>
        <span className={styles.logoText}>
          Naturalsk<span className={styles.logoAccent}>Web</span>
        </span>
        <p className={styles.subtitle}>Закрытая рабочая среда</p>
      </div>

      <div className={styles.grid}>
        {tiles.map((t) => (
          <NavLink key={t.to} to={t.to} className={styles.tile}>
            <t.icon className={styles.tileIcon} />
            <div className={styles.tileTitle}>{t.title}</div>
            <div className={styles.tileDesc}>{t.description}</div>
          </NavLink>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: `frontend/src/pages/Home/Home.module.css`**

```css
.wrapper {
  min-height: calc(100vh - var(--topbar-height) - 4rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
  gap: var(--space-10);
}

.logo {
  text-align: center;
}

.logoText {
  font-family: var(--font-mono);
  font-size: clamp(2.5rem, 6vw, 4.5rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.logoAccent {
  color: var(--accent);
}

.subtitle {
  color: var(--text-muted);
  font-size: var(--fs-base);
  margin-top: var(--space-3);
  font-family: var(--font-mono);
}

.grid {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  width: min(100%, 1000px);
}

.tile {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  text-decoration: none;
  color: var(--text-primary);
  transition: all var(--transition-base);
}

.tile:hover {
  border-color: var(--accent);
  background: var(--accent-glow);
  transform: translateY(-2px);
}

.tileIcon {
  width: 40px;
  height: 40px;
  color: var(--accent);
  margin-bottom: var(--space-2);
}

.tileTitle {
  font-size: var(--fs-lg);
  font-weight: 600;
}

.tileDesc {
  font-size: var(--fs-sm);
  color: var(--text-muted);
}

@media (max-width: 768px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 3: Обновить `frontend/src/App.tsx`**

Добавить импорт `HomePage` и маршрут `/`. Изменить catch-all:

```tsx
import HomePage from './pages/Home/HomePage'

// внутри protected группы:
<Route index element={<HomePage />} />
<Route path="/" element={<HomePage />} />

// внизу
<Route path="*" element={<Navigate to="/" replace />} />
```

- [ ] **Step 4: Изменить редирект в `LoginPage.tsx` и `ChangePasswordPage.tsx`**

Везде где сейчас `navigate('/youtube'...)` — заменить на `navigate('/'...)`.

- [ ] **Step 5: Проверка через playwright-cli**

```bash
playwright-cli open http://localhost:5173/login
playwright-cli fill <ref-username> "user1"
playwright-cli fill <ref-password> "<password>"
playwright-cli click <ref-submit>
playwright-cli snapshot
# Должны быть видны логотип и плитки
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Home/ frontend/src/App.tsx frontend/src/pages/Login/LoginPage.tsx frontend/src/pages/ChangePassword/ChangePasswordPage.tsx
git commit -m "feat(frontend): HomePage with logo and module tiles"
```

---

## Task 15: Frontend — Sidebar обновление

**Goal:** Sidebar теперь показывает «Главная» вверху и нижний пункт по роли (Личный кабинет / Admin Panel).

**Files:**
- Modify: `frontend/src/components/Layout/Sidebar.tsx`

**Acceptance Criteria:**
- [ ] У всех есть пункт «Главная» (Home icon → `/`).
- [ ] Под модулями: для user — «Личный кабинет» (`/me`), для admin/superadmin — «Admin Panel» (`/admin`).
- [ ] Активный маршрут подсвечивается.

**Verify:** `playwright-cli snapshot` — оценить структуру меню.

**Steps:**

- [ ] **Step 1: Заменить `frontend/src/components/Layout/Sidebar.tsx`**

```tsx
import { NavLink } from 'react-router-dom'
import { Home, Youtube, FileBox, Image as ImageIcon, User as UserIcon, Shield } from 'lucide-react'
import { useAuth } from '../../stores/authStore'
import styles from './Layout.module.css'

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

  const moduleItems = [
    { to: '/youtube', icon: Youtube, label: 'YouTube Downloader', visible: user?.permissions.youtube },
    { to: '/converter', icon: FileBox, label: 'File Converter', visible: user?.permissions.converter },
    { to: '/image', icon: ImageIcon, label: 'Image Processor', visible: user?.permissions.image },
  ]

  return (
    <>
      {isOpen && <div className={styles.overlay} onClick={onClose} />}
      <aside className={`${styles.sidebar} ${isOpen ? styles.sidebarOpen : ''}`}>
        <div className={styles.sidebarLogo}>
          <span className={styles.sidebarLogoText}>
            Naturalsk<span className={styles.sidebarLogoAccent}>Web</span>
          </span>
        </div>

        <nav className={styles.sidebarNav}>
          <NavLink to="/" end onClick={onClose} className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ''}`}>
            <Home className={styles.navIcon} />
            Главная
          </NavLink>

          <div className={styles.navDivider} />

          {moduleItems.filter((i) => i.visible).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={onClose}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
            >
              <item.icon className={styles.navIcon} />
              {item.label}
            </NavLink>
          ))}

          <div className={styles.navDivider} />

          {isAdmin ? (
            <NavLink to="/admin" onClick={onClose} className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ''}`}>
              <Shield className={styles.navIcon} />
              Admin Panel
            </NavLink>
          ) : (
            <NavLink to="/me" onClick={onClose} className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ''}`}>
              <UserIcon className={styles.navIcon} />
              Личный кабинет
            </NavLink>
          )}
        </nav>
      </aside>
    </>
  )
}
```

- [ ] **Step 2: Проверка через playwright-cli**

```bash
playwright-cli snapshot
# В Sidebar должен быть пункт "Главная" сверху и "Личный кабинет"/"Admin Panel" снизу.
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Layout/Sidebar.tsx
git commit -m "feat(frontend): sidebar with Home and role-based bottom item"
```

---

## Task 16: Frontend — polling `/auth/me` + toast при отзыве доступа

**Goal:** Фоновый интервал в `useAuthProvider` для отлова смены permissions/role/деактивации. При 401 — toast «Сессия завершена» и редирект на login.

**Files:**
- Modify: `frontend/src/hooks/useAuthProvider.ts`
- Modify: `frontend/src/api/client.ts`

**Acceptance Criteria:**
- [ ] При смене permissions со стороны бэка фронт обновляет `user` в течение ≤ 16 секунд.
- [ ] При `is_deleted=true` / `is_active=false` / `kicked_at` — пользователь вылогинивается с toast'ом.
- [ ] Polling не работает, когда `document.visibilityState === 'hidden'`.

**Verify:**
```bash
# Стартуем оба сервиса, логинимся, через API меняем permission, ждём 16 секунд
playwright-cli open http://localhost:5173/image
# через bash в другом окне: PATCH /api/admin/users/{id} с permissions.image=false
# через 16 секунд должен случиться редирект на /
playwright-cli snapshot
```

**Steps:**

- [ ] **Step 1: Добавить polling в `frontend/src/hooks/useAuthProvider.ts`**

После существующего `useEffect` для начальной загрузки добавить:

```typescript
useEffect(() => {
  if (!user) return
  const POLL_MS = 15_000
  let stopped = false

  const tick = async () => {
    if (stopped) return
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
    try {
      const { data } = await api.get<User>('/auth/me')
      if (!stopped) setUser(data)
    } catch {
      // axios interceptor обработает 401
    }
  }

  const id = setInterval(tick, POLL_MS)
  return () => {
    stopped = true
    clearInterval(id)
  }
}, [user?.id])
```

- [ ] **Step 2: Обновить `frontend/src/api/client.ts` — toast при принудительном logout**

Найти interceptor 401 (там, где не получилось обновить токен). После очистки `localStorage` показать toast:

```typescript
import { toast } from 'react-toastify'

// В блоке, где refresh не удался / финальный 401:
toast.info('Сессия завершена. Войдите снова.')
window.location.href = '/login'
```

(Если в client.ts уже есть подобный код — добавить только `toast.info(...)` перед редиректом.)

- [ ] **Step 3: Проверка через playwright-cli**

```bash
cd backend && uvicorn app.main:app --port 8000 &
cd frontend && bun run dev &
sleep 5
playwright-cli open http://localhost:5173/login
# Залогиниться, открыть /image
# В отдельном терминале: получить admin token и сделать PATCH с permissions.image=false
# Подождать 16 секунд → должен произойти редирект на /
playwright-cli snapshot
playwright-cli close
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useAuthProvider.ts frontend/src/api/client.ts
git commit -m "feat(frontend): poll /auth/me and toast on forced logout"
```

---

## Task 17: Frontend — ProfilePage skeleton + ProfileTab + Header + UsageBars

**Goal:** Страница `/me` со скелетом ProfileTab, шапкой профиля (без аватара пока) и блоком прогресс-баров лимитов.

**Files:**
- Create: `frontend/src/pages/Profile/ProfilePage.tsx`
- Create: `frontend/src/pages/Profile/ProfileTab.tsx`
- Create: `frontend/src/pages/Profile/UsageBars.tsx`
- Create: `frontend/src/pages/Profile/Profile.module.css`
- Modify: `frontend/src/App.tsx` (роут `/me`)

**Acceptance Criteria:**
- [ ] `/me` рендерит `ProfilePage` под `MainLayout`.
- [ ] Шапка показывает аватар (через `AvatarImage`), username, роль, дату создания, последний вход.
- [ ] `UsageBars` рендерит 3 прогресс-бара (Y/C/I) с цветовой индикацией (<70%/<90%/более).
- [ ] Под барами — счётчик «Лимиты обнулятся через X ч Y мин».

**Verify:** `playwright-cli open http://localhost:5173/me` → snapshot должен содержать все блоки.

**Steps:**

- [ ] **Step 1: `frontend/src/pages/Profile/UsageBars.tsx`**

```tsx
import type { User } from '../../types'
import styles from './Profile.module.css'

interface Props {
  user: User
}

const MODULES: Array<{ key: 'youtube' | 'converter' | 'image'; label: string; limitKey: 'youtube_daily' | 'convert_daily' | 'image_daily' }> = [
  { key: 'youtube', label: 'YouTube', limitKey: 'youtube_daily' },
  { key: 'converter', label: 'Converter', limitKey: 'convert_daily' },
  { key: 'image', label: 'Image', limitKey: 'image_daily' },
]


function colorClass(used: number, limit: number): string {
  if (limit <= 0) return styles.barOk
  const pct = (used / limit) * 100
  if (pct >= 90) return styles.barDanger
  if (pct >= 70) return styles.barWarn
  return styles.barOk
}


function formatTimeUntilReset(resetDateIso: string | undefined): string {
  if (!resetDateIso) return ''
  const reset = new Date(resetDateIso + 'T00:00:00Z')
  const next = new Date(reset.getTime() + 24 * 60 * 60 * 1000)
  const diff = next.getTime() - Date.now()
  if (diff <= 0) return 'обновляются'
  const h = Math.floor(diff / (60 * 60 * 1000))
  const m = Math.floor((diff % (60 * 60 * 1000)) / (60 * 1000))
  return `${h} ч ${m} мин`
}


export default function UsageBars({ user }: Props) {
  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>Использование сегодня</h3>
      <div className={styles.bars}>
        {MODULES.map((m) => {
          const used = user.usage_today[m.key] ?? 0
          const limit = user.limits[m.limitKey] ?? 0
          const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
          return (
            <div key={m.key} className={styles.barRow}>
              <div className={styles.barLabel}>
                <span>{m.label}</span>
                <span className={styles.barCount}>{used} / {limit}</span>
              </div>
              <div className={styles.barTrack}>
                <div className={`${styles.barFill} ${colorClass(used, limit)}`} style={{ width: `${pct}%` }} />
              </div>
            </div>
          )
        })}
      </div>
      <div className={styles.resetHint}>Лимиты обнулятся через {formatTimeUntilReset(user.usage_reset_date)}</div>
    </section>
  )
}
```

- [ ] **Step 2: `frontend/src/pages/Profile/ProfileTab.tsx` (skeleton без аватара/сессий)**

```tsx
import { useEffect, useState } from 'react'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import type { User } from '../../types'
import { useAuth } from '../../stores/authStore'
import UsageBars from './UsageBars'
import styles from './Profile.module.css'


function formatDate(iso: string | undefined | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU')
}


export default function ProfileTab() {
  const { user: authUser, setUser } = useAuth()
  const [me, setMe] = useState<User | null>(authUser)

  useEffect(() => {
    api.get<User>('/me').then(({ data }) => {
      setMe(data)
      setUser(data)
    }).catch(() => {})
  }, [])

  if (!me) return null

  return (
    <div className={styles.tab}>
      <section className={styles.section}>
        <div className={styles.header}>
          <AvatarImage userId={me.id} version={me.avatar_version ?? 0} size={128} />
          <div className={styles.headerInfo}>
            <h2 className={styles.username}>{me.username}</h2>
            <div className={styles.role}>{me.role}</div>
            <div className={styles.headerMeta}>
              <div>Создан: {formatDate(me.created_at)}</div>
              <div>Последний вход: {formatDate(me.last_login)}</div>
            </div>
          </div>
        </div>
      </section>

      <UsageBars user={me} />
    </div>
  )
}
```

- [ ] **Step 3: `frontend/src/pages/Profile/ProfilePage.tsx`**

```tsx
import ProfileTab from './ProfileTab'
import styles from './Profile.module.css'


export default function ProfilePage() {
  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>Личный кабинет</h1>
      <ProfileTab />
    </div>
  )
}
```

- [ ] **Step 4: `frontend/src/pages/Profile/Profile.module.css`**

```css
.page {
  max-width: 900px;
  margin: 0 auto;
}

.pageTitle {
  font-size: var(--fs-2xl);
  margin-bottom: var(--space-6);
}

.tab {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
}

.sectionTitle {
  margin: 0 0 var(--space-4);
  font-size: var(--fs-lg);
  color: var(--text-primary);
}

.header {
  display: flex;
  gap: var(--space-6);
  align-items: center;
}

.headerInfo {
  flex: 1;
}

.username {
  margin: 0;
  font-size: var(--fs-xl);
}

.role {
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-muted);
  font-size: var(--fs-xs);
  margin-top: var(--space-1);
}

.headerMeta {
  margin-top: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  color: var(--text-secondary);
  font-size: var(--fs-sm);
}

.bars {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.barRow {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.barLabel {
  display: flex;
  justify-content: space-between;
  font-size: var(--fs-sm);
}

.barCount {
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.barTrack {
  height: 8px;
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.barFill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--transition-base);
}

.barOk { background: var(--accent); }
.barWarn { background: #d4a700; }
.barDanger { background: var(--danger, #d44); }

.resetHint {
  margin-top: var(--space-3);
  color: var(--text-muted);
  font-size: var(--fs-sm);
}

@media (max-width: 640px) {
  .header {
    flex-direction: column;
    align-items: flex-start;
  }
}
```

- [ ] **Step 5: Маршрут в `frontend/src/App.tsx`**

```tsx
import ProfilePage from './pages/Profile/ProfilePage'

// внутри protected группы:
<Route path="/me" element={<ProfilePage />} />
```

- [ ] **Step 6: Проверка через playwright-cli**

```bash
playwright-cli goto http://localhost:5173/me
playwright-cli snapshot
# Должны быть: шапка с аватаром-иконкой, прогресс-бары, "Лимиты обнулятся через..."
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Profile/ frontend/src/App.tsx
git commit -m "feat(profile): /me page with header and usage bars"
```

---

## Task 18: Frontend — SessionsList + ChangeUsernameForm + ChangePasswordForm

**Goal:** Добавить в ProfileTab блок активных сессий (с возможностью завершить) и формы изменения username и пароля.

**Files:**
- Create: `frontend/src/pages/Profile/SessionsList.tsx`
- Create: `frontend/src/pages/Profile/ChangeUsernameForm.tsx`
- Create: `frontend/src/pages/Profile/ChangePasswordForm.tsx`
- Modify: `frontend/src/pages/Profile/ProfileTab.tsx`
- Modify: `frontend/src/pages/Profile/Profile.module.css`

**Acceptance Criteria:**
- [ ] `SessionsList` грузит `/api/me/sessions`, рендерит карточки IP/UA/created/expires, кнопки «Завершить» и «Завершить все, кроме текущей».
- [ ] Текущая сессия помечена бейджем «Эта сессия».
- [ ] `ChangeUsernameForm` открывает модалку (или inline edit), при сохранении PATCH /api/me. 409 → toast.
- [ ] `ChangePasswordForm` открывает модалку, использует `/api/auth/change-password`.

**Verify:** `playwright-cli` interactive — заменить username, увидеть в snapshot новое имя.

**Steps:**

- [ ] **Step 1: `frontend/src/pages/Profile/SessionsList.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
import type { MySessionItem } from '../../types'
import styles from './Profile.module.css'


function shortUA(ua: string): string {
  // упрощённый парсер на стороне клиента
  if (!ua) return 'Неизвестно'
  let browser = ''
  if (/Firefox\/(\d+)/.test(ua)) browser = `Firefox ${ua.match(/Firefox\/(\d+)/)![1]}`
  else if (/Edg\/(\d+)/.test(ua)) browser = `Edge ${ua.match(/Edg\/(\d+)/)![1]}`
  else if (/Chrome\/(\d+)/.test(ua)) browser = `Chrome ${ua.match(/Chrome\/(\d+)/)![1]}`
  else if (/Safari\/(\d+)/.test(ua)) browser = `Safari ${ua.match(/Version\/(\d+)/)?.[1] ?? ''}`
  let os = ''
  if (/Windows/.test(ua)) os = 'Windows'
  else if (/Mac OS|Macintosh/.test(ua)) os = 'macOS'
  else if (/Android/.test(ua)) os = 'Android'
  else if (/iPhone|iPad/.test(ua)) os = 'iOS'
  else if (/Linux/.test(ua)) os = 'Linux'
  return [browser, os].filter(Boolean).join(' · ') || 'Иное'
}


export default function SessionsList() {
  const [sessions, setSessions] = useState<MySessionItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    api.get<MySessionItem[]>('/me/sessions')
      .then(({ data }) => setSessions(data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const killOne = async (id: number) => {
    await api.delete(`/me/sessions/${id}`)
    toast.success('Сессия завершена')
    load()
  }

  const killOthers = async () => {
    await api.delete('/me/sessions')
    toast.success('Остальные сессии завершены')
    load()
  }

  if (loading) return <div className={styles.section}>Загрузка сессий...</div>

  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>Активные сессии</h3>
        <button className={styles.btnSecondary} onClick={killOthers} disabled={sessions.length <= 1}>
          Завершить все, кроме текущей
        </button>
      </div>
      <div className={styles.sessionList}>
        {sessions.map((s) => (
          <div key={s.id} className={styles.sessionItem}>
            <div className={styles.sessionInfo}>
              <div className={styles.sessionLine}>
                <strong>{shortUA(s.user_agent)}</strong>
                {s.is_current && <span className={styles.badge}>Эта сессия</span>}
              </div>
              <div className={styles.sessionMeta}>IP: {s.ip_address || '—'}</div>
              <div className={styles.sessionMeta}>Создана: {new Date(s.created_at).toLocaleString('ru-RU')}</div>
            </div>
            {!s.is_current && (
              <button className={styles.btnDanger} onClick={() => killOne(s.id)}>Завершить</button>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
```

- [ ] **Step 2: `frontend/src/pages/Profile/ChangeUsernameForm.tsx`**

```tsx
import { useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import type { User } from '../../types'
import styles from './Profile.module.css'


export default function ChangeUsernameForm() {
  const { user, setUser } = useAuth()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(user?.username ?? '')
  const [busy, setBusy] = useState(false)

  if (!user) return null

  const submit = async () => {
    if (!/^[a-zA-Z0-9_]{2,50}$/.test(value)) {
      toast.error('Имя: 2–50 символов, латиница/цифры/_')
      return
    }
    setBusy(true)
    try {
      const { data } = await api.patch<User>('/me', { username: value })
      setUser(data)
      toast.success('Имя обновлено')
      setEditing(false)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  if (!editing) {
    return <button className={styles.btnSecondary} onClick={() => setEditing(true)}>Изменить имя</button>
  }

  return (
    <div className={styles.inlineForm}>
      <input className={styles.input} value={value} onChange={(e) => setValue(e.target.value)} disabled={busy} />
      <button className={styles.btnPrimary} onClick={submit} disabled={busy}>Сохранить</button>
      <button className={styles.btnSecondary} onClick={() => { setEditing(false); setValue(user.username) }} disabled={busy}>Отмена</button>
    </div>
  )
}
```

- [ ] **Step 3: `frontend/src/pages/Profile/ChangePasswordForm.tsx`**

```tsx
import { useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
import styles from './Profile.module.css'


export default function ChangePasswordForm() {
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (next.length < 8) { toast.error('Минимум 8 символов'); return }
    if (next !== confirm) { toast.error('Пароли не совпадают'); return }
    setBusy(true)
    try {
      await api.post('/auth/change-password', { current_password: current, new_password: next })
      toast.success('Пароль изменён')
      setOpen(false)
      setCurrent(''); setNext(''); setConfirm('')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return <button className={styles.btnSecondary} onClick={() => setOpen(true)}>Сменить пароль</button>

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && setOpen(false)}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>Смена пароля</h3>
        <input className={styles.input} type="password" placeholder="Текущий пароль" value={current} onChange={(e) => setCurrent(e.target.value)} />
        <input className={styles.input} type="password" placeholder="Новый пароль" value={next} onChange={(e) => setNext(e.target.value)} />
        <input className={styles.input} type="password" placeholder="Повторите новый" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <div className={styles.modalActions}>
          <button className={styles.btnSecondary} onClick={() => setOpen(false)} disabled={busy}>Отмена</button>
          <button className={styles.btnPrimary} onClick={submit} disabled={busy}>Сменить</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Подключить в `ProfileTab.tsx`**

В JSX внутри `<div className={styles.tab}>` (после `<UsageBars user={me} />`):

```tsx
import SessionsList from './SessionsList'
import ChangeUsernameForm from './ChangeUsernameForm'
import ChangePasswordForm from './ChangePasswordForm'

// после <UsageBars />:
<SessionsList />
<section className={styles.section}>
  <h3 className={styles.sectionTitle}>Безопасность</h3>
  <div className={styles.actionsRow}>
    <ChangeUsernameForm />
    <ChangePasswordForm />
  </div>
</section>
```

- [ ] **Step 5: Дополнить `Profile.module.css`**

```css
.sectionHeader { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4); }
.sessionList { display: flex; flex-direction: column; gap: var(--space-3); }
.sessionItem { display: flex; justify-content: space-between; padding: var(--space-3); background: var(--bg-secondary); border-radius: var(--radius-md); }
.sessionInfo { display: flex; flex-direction: column; gap: var(--space-1); }
.sessionLine { display: flex; gap: var(--space-2); align-items: center; }
.sessionMeta { font-size: var(--fs-xs); color: var(--text-muted); font-family: var(--font-mono); }
.badge { background: var(--accent-glow); color: var(--accent); font-size: var(--fs-xs); padding: 2px 8px; border-radius: var(--radius-full); }
.actionsRow { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.inlineForm { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.input { padding: var(--space-2) var(--space-3); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text-primary); font-family: var(--font-ui); }
.btnPrimary { padding: var(--space-2) var(--space-4); background: var(--accent); color: white; border: none; border-radius: var(--radius-md); cursor: pointer; }
.btnPrimary:disabled { opacity: 0.5; cursor: not-allowed; }
.btnSecondary { padding: var(--space-2) var(--space-4); background: transparent; color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-md); cursor: pointer; }
.btnSecondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btnDanger { padding: var(--space-2) var(--space-3); background: transparent; color: var(--danger); border: 1px solid var(--danger); border-radius: var(--radius-md); cursor: pointer; }
.modalOverlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.7); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-6); width: min(90vw, 420px); display: flex; flex-direction: column; gap: var(--space-3); }
.modalActions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-3); }
```

- [ ] **Step 6: Проверка через playwright-cli**

```bash
playwright-cli goto http://localhost:5173/me
playwright-cli snapshot
# должны быть: список сессий, кнопки "Изменить имя" и "Сменить пароль"
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Profile/
git commit -m "feat(profile): sessions list and username/password forms"
```

---

## Task 19: Frontend — AvatarUploader с react-easy-crop

**Goal:** Полноценная загрузка аватара с клиентским кропом до квадрата и сохранением через `/api/me/avatar`.

**Files:**
- Modify: `frontend/package.json` (добавить `react-easy-crop`)
- Create: `frontend/src/pages/Profile/AvatarUploader.tsx`
- Modify: `frontend/src/pages/Profile/ProfileTab.tsx`
- Modify: `frontend/src/pages/Profile/Profile.module.css`

**Acceptance Criteria:**
- [ ] Установлена зависимость `react-easy-crop`.
- [ ] При клике «Загрузить» открывается file-picker. После выбора — модалка с кропом, ползунком зума, кнопками «Сохранить»/«Отмена».
- [ ] После save: blob отправляется в `/api/me/avatar`, `auth.user.avatar_version` обновляется, аватар перерисовывается.
- [ ] При наличии аватара появляется кнопка «Удалить» — DELETE `/api/me/avatar`.

**Verify:** `playwright-cli` interactive — выбрать файл, обрезать, сохранить, увидеть аватар в Topbar.

**Steps:**

- [ ] **Step 1: Установить зависимость**

```bash
cd frontend && bun add react-easy-crop
```

- [ ] **Step 2: `frontend/src/pages/Profile/AvatarUploader.tsx`**

```tsx
import { useCallback, useRef, useState } from 'react'
import Cropper, { Area } from 'react-easy-crop'
import { toast } from 'react-toastify'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import { useAuth } from '../../stores/authStore'
import type { AvatarUploadResponse, User } from '../../types'
import styles from './Profile.module.css'


async function getCroppedBlob(imageSrc: string, area: Area): Promise<Blob> {
  const image = new Image()
  image.src = imageSrc
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve()
    image.onerror = () => reject(new Error('image load'))
  })
  const canvas = document.createElement('canvas')
  canvas.width = area.width
  canvas.height = area.height
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(image, area.x, area.y, area.width, area.height, 0, 0, area.width, area.height)
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('blob'))), 'image/jpeg', 0.92)
  })
}


export default function AvatarUploader() {
  const { user, setUser } = useAuth()
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [imageSrc, setImageSrc] = useState<string | null>(null)
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [areaPx, setAreaPx] = useState<Area | null>(null)
  const [busy, setBusy] = useState(false)

  if (!user) return null
  const hasAvatar = (user.avatar_version ?? 0) > 0

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setImageSrc(reader.result as string)
    reader.readAsDataURL(file)
    e.target.value = ''
  }

  const onCropComplete = useCallback((_: Area, pixels: Area) => setAreaPx(pixels), [])

  const save = async () => {
    if (!imageSrc || !areaPx) return
    setBusy(true)
    try {
      const blob = await getCroppedBlob(imageSrc, areaPx)
      const fd = new FormData()
      fd.append('file', blob, 'avatar.jpg')
      const { data } = await api.post<AvatarUploadResponse>('/me/avatar', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const fresh = await api.get<User>('/auth/me')
      setUser(fresh.data)
      setImageSrc(null)
      toast.success('Аватар обновлён')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Не удалось сохранить')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await api.delete('/me/avatar')
      const fresh = await api.get<User>('/auth/me')
      setUser(fresh.data)
      toast.success('Аватар удалён')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.avatarUploader}>
      <AvatarImage userId={user.id} version={user.avatar_version ?? 0} size={128} />
      <div className={styles.avatarActions}>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={onPick} />
        <button className={styles.btnSecondary} onClick={() => fileRef.current?.click()} disabled={busy}>Загрузить</button>
        {hasAvatar && <button className={styles.btnDanger} onClick={remove} disabled={busy}>Удалить</button>}
      </div>

      {imageSrc && (
        <div className={styles.modalOverlay} onClick={() => !busy && setImageSrc(null)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()} style={{ width: 'min(90vw, 480px)' }}>
            <h3>Обрезать аватар</h3>
            <div className={styles.cropArea}>
              <Cropper
                image={imageSrc}
                crop={crop}
                zoom={zoom}
                aspect={1}
                cropShape="round"
                showGrid={false}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={onCropComplete}
              />
            </div>
            <input type="range" min={1} max={3} step={0.05} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} />
            <div className={styles.modalActions}>
              <button className={styles.btnSecondary} onClick={() => setImageSrc(null)} disabled={busy}>Отмена</button>
              <button className={styles.btnPrimary} onClick={save} disabled={busy}>Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Подключить в `ProfileTab.tsx`**

Заменить блок шапки в `ProfileTab.tsx`:

```tsx
import AvatarUploader from './AvatarUploader'

// внутри section header — вместо <AvatarImage ... />:
<AvatarUploader />
```

- [ ] **Step 4: CSS для крoppера**

```css
.avatarUploader { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); }
.avatarActions { display: flex; gap: var(--space-2); }
.cropArea { position: relative; width: 100%; height: 320px; background: #000; border-radius: var(--radius-md); overflow: hidden; }
```

- [ ] **Step 5: Проверка через playwright-cli**

```bash
playwright-cli goto http://localhost:5173/me
# Найти кнопку "Загрузить", drop файл:
playwright-cli drop <ref-input> --path=./test.png
playwright-cli snapshot  # должна появиться модалка кропа
playwright-cli click <ref-save>
playwright-cli snapshot  # аватар должен обновиться
```

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/bun.lockb frontend/src/pages/Profile/
git commit -m "feat(profile): avatar uploader with react-easy-crop"
```

---

## Task 20: Frontend — AdminPage с табами + UsersTab (таблица + фильтры + пагинация)

**Goal:** Запустить структуру админки. AdminPage с табами через query-param. Внутри UsersTab — таблица пользователей с фильтрами и пагинацией.

**Files:**
- Modify: `frontend/src/pages/Admin/AdminPage.tsx` (заменить Placeholder)
- Create: `frontend/src/pages/Admin/UsersTab.tsx`
- Create: `frontend/src/pages/Admin/Admin.module.css`

**Acceptance Criteria:**
- [ ] AdminPage показывает табы: Пользователи / Аудит-лог / Мониторинг (только superadmin) / Мой профиль.
- [ ] Активный таб синхронизирован с `?tab=...`. F5 сохраняет состояние.
- [ ] UsersTab грузит `/api/admin/users` с пагинацией и фильтрами (поиск/роль/статус).
- [ ] В таблице отображаются аватарки через AvatarImage и компактное использование сегодня.
- [ ] Кнопки действий пока неактивны (или выкидывают TODO-toast) — модалки в Task 21.

**Verify:** `playwright-cli goto http://localhost:5173/admin` (под admin) → snapshot.

**Steps:**

- [ ] **Step 1: `frontend/src/pages/Admin/Admin.module.css`**

```css
.page { max-width: 1200px; margin: 0 auto; }
.tabs { display: flex; gap: var(--space-2); border-bottom: 1px solid var(--border); margin-bottom: var(--space-6); }
.tab { padding: var(--space-3) var(--space-5); background: none; border: none; color: var(--text-secondary); font-size: var(--fs-sm); cursor: pointer; border-bottom: 2px solid transparent; }
.tab:hover { color: var(--text-primary); }
.tabActive { color: var(--accent); border-bottom-color: var(--accent); }

.toolbar { display: flex; gap: var(--space-3); margin-bottom: var(--space-4); flex-wrap: wrap; align-items: center; }
.toolbar input, .toolbar select { padding: var(--space-2) var(--space-3); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text-primary); }
.toolbarSpacer { flex: 1; }

.table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.table th, .table td { padding: var(--space-3); text-align: left; border-bottom: 1px solid var(--border); }
.table th { color: var(--text-muted); font-weight: 500; font-family: var(--font-mono); text-transform: uppercase; font-size: var(--fs-xs); letter-spacing: 1px; }
.table tr:hover { background: var(--bg-hover); }

.roleBadge { display: inline-block; padding: 2px 8px; border-radius: var(--radius-full); font-family: var(--font-mono); font-size: var(--fs-xs); }
.roleSuperadmin { background: rgba(212, 167, 0, 0.15); color: #d4a700; }
.roleAdmin { background: var(--accent-glow); color: var(--accent); }
.roleUser { background: var(--bg-secondary); color: var(--text-secondary); }

.statusBadge { font-family: var(--font-mono); font-size: var(--fs-xs); padding: 2px 8px; border-radius: var(--radius-full); }
.statusActive { background: rgba(50, 200, 50, 0.15); color: #5c5; }
.statusInactive { background: var(--bg-secondary); color: var(--text-muted); }
.statusDeleted { background: rgba(220, 80, 80, 0.15); color: var(--danger); }

.usageCompact { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-muted); }

.actions { display: flex; gap: var(--space-1); }
.iconBtn { background: transparent; border: 1px solid var(--border); border-radius: var(--radius-md); padding: var(--space-1) var(--space-2); cursor: pointer; color: var(--text-secondary); }
.iconBtn:hover { color: var(--text-primary); border-color: var(--accent); }
.iconBtn:disabled { opacity: 0.3; cursor: not-allowed; }

.pagination { display: flex; gap: var(--space-2); align-items: center; justify-content: flex-end; margin-top: var(--space-4); }
.pageInfo { color: var(--text-muted); font-family: var(--font-mono); font-size: var(--fs-sm); }
```

- [ ] **Step 2: `frontend/src/pages/Admin/UsersTab.tsx`**

```tsx
import { useEffect, useState, useCallback } from 'react'
import { Plus, Eye, Pencil, Key, Power, Trash2 } from 'lucide-react'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import { useAuth } from '../../stores/authStore'
import type { Role, UserListItem, UserListResponse } from '../../types'
import styles from './Admin.module.css'

const PAGE_SIZE = 20


function statusOf(u: UserListItem): { label: string; cls: string } {
  if (u.is_deleted) return { label: 'удалён', cls: styles.statusDeleted }
  if (!u.is_active) return { label: 'отключён', cls: styles.statusInactive }
  return { label: 'активен', cls: styles.statusActive }
}


function roleClass(role: string): string {
  if (role === 'superadmin') return styles.roleSuperadmin
  if (role === 'admin') return styles.roleAdmin
  return styles.roleUser
}


function compactUsage(u: UserListItem): string {
  return `Y ${u.usage_today.youtube ?? 0}/${u.limits.youtube_daily ?? 0} · C ${u.usage_today.converter ?? 0}/${u.limits.convert_daily ?? 0} · I ${u.usage_today.image ?? 0}/${u.limits.image_daily ?? 0}`
}


interface Props {
  onCreate: () => void
  onEdit: (id: number) => void
  onResetPassword: (id: number) => void
  onToggle: (id: number) => void
  onDelete: (id: number) => void
}


export default function UsersTab({ onCreate, onEdit, onResetPassword, onToggle, onDelete }: Props) {
  const { user: actor } = useAuth()
  const isSuperadmin = actor?.role === 'superadmin'
  const [items, setItems] = useState<UserListItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [role, setRole] = useState<Role | ''>('')
  const [status, setStatus] = useState<'' | 'active' | 'inactive' | 'deleted'>('')

  const load = useCallback(() => {
    const params = new URLSearchParams()
    params.set('offset', String(offset))
    params.set('limit', String(PAGE_SIZE))
    if (search) params.set('search', search)
    if (role) params.set('role', role)
    if (status) params.set('status', status)
    if (status === 'deleted' && isSuperadmin) params.set('include_deleted', 'true')
    api.get<UserListResponse>(`/admin/users?${params}`).then(({ data }) => {
      setItems(data.items)
      setTotal(data.total)
    })
  }, [offset, search, role, status, isSuperadmin])

  useEffect(() => {
    const t = setTimeout(load, search ? 250 : 0)
    return () => clearTimeout(t)
  }, [load])

  const canDelete = (u: UserListItem) => isSuperadmin && u.id !== actor?.id && !u.is_deleted
  const canEdit = (u: UserListItem) => {
    if (u.is_deleted) return false
    if (actor?.role === 'admin' && u.role === 'superadmin') return false
    if (actor?.id === u.id) return false
    return true
  }
  const canResetPassword = canEdit
  const canToggle = canEdit

  return (
    <div>
      <div className={styles.toolbar}>
        <input placeholder="Поиск по имени" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0) }} />
        <select value={role} onChange={(e) => { setRole(e.target.value as Role | ''); setOffset(0) }}>
          <option value="">Все роли</option>
          <option value="user">user</option>
          <option value="admin">admin</option>
          <option value="superadmin">superadmin</option>
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value as any); setOffset(0) }}>
          <option value="">Все статусы</option>
          <option value="active">Активные</option>
          <option value="inactive">Отключённые</option>
          {isSuperadmin && <option value="deleted">Удалённые</option>}
        </select>
        <div className={styles.toolbarSpacer} />
        <button className={styles.iconBtn} onClick={onCreate}><Plus size={16} /> Создать</button>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th></th>
            <th>Username</th>
            <th>Роль</th>
            <th>Статус</th>
            <th>Создан</th>
            <th>Последний вход</th>
            <th>Использование</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((u) => {
            const st = statusOf(u)
            return (
              <tr key={u.id}>
                <td><AvatarImage userId={u.id} version={u.avatar_version} size={28} /></td>
                <td>{u.username}</td>
                <td><span className={`${styles.roleBadge} ${roleClass(u.role)}`}>{u.role}</span></td>
                <td><span className={`${styles.statusBadge} ${st.cls}`}>{st.label}</span></td>
                <td>{new Date(u.created_at).toLocaleDateString('ru-RU')}</td>
                <td>{u.last_login ? new Date(u.last_login).toLocaleDateString('ru-RU') : '—'}</td>
                <td className={styles.usageCompact}>{compactUsage(u)}</td>
                <td>
                  <div className={styles.actions}>
                    {!canEdit(u) ? (
                      <button className={styles.iconBtn} onClick={() => onEdit(u.id)} title="Подробно"><Eye size={14} /></button>
                    ) : (
                      <>
                        <button className={styles.iconBtn} onClick={() => onEdit(u.id)} title="Редактировать"><Pencil size={14} /></button>
                        <button className={styles.iconBtn} onClick={() => onResetPassword(u.id)} disabled={!canResetPassword(u)} title="Сбросить пароль"><Key size={14} /></button>
                        <button className={styles.iconBtn} onClick={() => onToggle(u.id)} disabled={!canToggle(u)} title="Включить/Выключить"><Power size={14} /></button>
                      </>
                    )}
                    {canDelete(u) && (
                      <button className={styles.iconBtn} onClick={() => onDelete(u.id)} title="Удалить"><Trash2 size={14} /></button>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className={styles.pagination}>
        <span className={styles.pageInfo}>{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} из {total}</span>
        <button className={styles.iconBtn} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Назад</button>
        <button className={styles.iconBtn} disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Вперёд</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: `frontend/src/pages/Admin/AdminPage.tsx`** (заменить Placeholder)

```tsx
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../../stores/authStore'
import ProfileTab from '../Profile/ProfileTab'
import UsersTab from './UsersTab'
import styles from './Admin.module.css'

type Tab = 'users' | 'audit' | 'monitoring' | 'profile'


export default function AdminPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const isSuperadmin = user?.role === 'superadmin'
  const tab: Tab = (params.get('tab') as Tab) || 'users'

  const setTab = (t: Tab) => { setParams({ tab: t }) }

  // Заглушки — модалки появятся в Task 21
  const noop = () => alert('TODO Task 21')

  return (
    <div className={styles.page}>
      <h1>Admin Panel</h1>
      <div className={styles.tabs}>
        <button className={`${styles.tab} ${tab === 'users' ? styles.tabActive : ''}`} onClick={() => setTab('users')}>Пользователи</button>
        <button className={`${styles.tab} ${tab === 'audit' ? styles.tabActive : ''}`} onClick={() => setTab('audit')}>Аудит-лог</button>
        {isSuperadmin && (
          <button className={`${styles.tab} ${tab === 'monitoring' ? styles.tabActive : ''}`} onClick={() => setTab('monitoring')}>Мониторинг</button>
        )}
        <button className={`${styles.tab} ${tab === 'profile' ? styles.tabActive : ''}`} onClick={() => setTab('profile')}>Мой профиль</button>
      </div>

      {tab === 'users' && <UsersTab onCreate={noop} onEdit={noop} onResetPassword={noop} onToggle={noop} onDelete={noop} />}
      {tab === 'audit' && <div>Аудит-лог (Task 22)</div>}
      {tab === 'monitoring' && isSuperadmin && <div>Мониторинг (Task 23)</div>}
      {tab === 'profile' && <ProfileTab />}
    </div>
  )
}
```

- [ ] **Step 4: Проверка через playwright-cli**

```bash
playwright-cli goto http://localhost:5173/admin
playwright-cli snapshot
# должны быть табы и таблица пользователей
playwright-cli goto "http://localhost:5173/admin?tab=profile"
playwright-cli snapshot
# должен быть ProfileTab
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Admin/
git commit -m "feat(admin): page with tabs and UsersTab"
```

---

## Task 21: Frontend — модалки управления пользователями

**Goal:** Реализовать `CreateUserModal`, `EditUserModal`, `ResetPasswordModal`, `ConfirmDeleteModal`. Подключить их к UsersTab через AdminPage.

**Files:**
- Create: `frontend/src/pages/Admin/CreateUserModal.tsx`
- Create: `frontend/src/pages/Admin/EditUserModal.tsx`
- Create: `frontend/src/pages/Admin/ResetPasswordModal.tsx`
- Create: `frontend/src/pages/Admin/ConfirmDeleteModal.tsx`
- Modify: `frontend/src/pages/Admin/AdminPage.tsx`

**Acceptance Criteria:**
- [ ] `CreateUserModal`: поле username, селект роли (admin → только user; superadmin → все), чекбоксы permissions, поля limits. После создания показывается одноразовый пароль.
- [ ] `EditUserModal`: подгружает `/api/admin/users/{id}`, позволяет менять role/permissions/limits/is_active. Read-only режим, если текущий actor не может править цель.
- [ ] `ResetPasswordModal`: подтверждение → POST → показывает новый пароль один раз с кнопкой «Скопировать».
- [ ] `ConfirmDeleteModal`: «Введите username для подтверждения» → DELETE.

**Verify:** Создать пользователя, увидеть пароль. Отредактировать его, увидеть изменения в таблице.

**Steps:**

- [ ] **Step 1: `CreateUserModal.tsx`**

```tsx
import { useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import type { CreateUserResponse, Role } from '../../types'
import styles from '../Profile/Profile.module.css'

interface Props {
  onClose: () => void
  onCreated: () => void
}

const DEFAULT_PERMS = { youtube: true, converter: true, image: true }
const DEFAULT_LIMITS = { youtube_daily: 50, convert_daily: 100, image_daily: 50 }


export default function CreateUserModal({ onClose, onCreated }: Props) {
  const { user: actor } = useAuth()
  const isSuperadmin = actor?.role === 'superadmin'
  const [username, setUsername] = useState('')
  const [role, setRole] = useState<Role>('user')
  const [perms, setPerms] = useState({ ...DEFAULT_PERMS })
  const [limits, setLimits] = useState({ ...DEFAULT_LIMITS })
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState<CreateUserResponse | null>(null)

  const submit = async () => {
    if (!/^[a-zA-Z0-9_]{2,50}$/.test(username)) { toast.error('Имя: 2–50 символов'); return }
    setBusy(true)
    try {
      const { data } = await api.post<CreateUserResponse>('/admin/users', {
        username, role, permissions: perms, limits,
      })
      setCreated(data)
      onCreated()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Ошибка')
    } finally { setBusy(false) }
  }

  if (created) {
    return (
      <div className={styles.modalOverlay} onClick={onClose}>
        <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
          <h3>Пользователь создан</h3>
          <p>Имя: <strong>{created.username}</strong></p>
          <p>Пароль (показывается один раз):</p>
          <code style={{ padding: '0.5rem', background: 'var(--bg-secondary)', borderRadius: 4, display: 'block', wordBreak: 'break-all' }}>{created.password}</code>
          <button className={styles.btnSecondary} onClick={() => { navigator.clipboard.writeText(created.password); toast.success('Скопировано') }}>Скопировать</button>
          <div className={styles.modalActions}>
            <button className={styles.btnPrimary} onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()} style={{ width: 'min(92vw, 520px)' }}>
        <h3>Создание пользователя</h3>
        <input className={styles.input} placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        <label>Роль:
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="user">user</option>
            {isSuperadmin && <option value="admin">admin</option>}
            {isSuperadmin && <option value="superadmin">superadmin</option>}
          </select>
        </label>
        <fieldset>
          <legend>Права</legend>
          {(['youtube', 'converter', 'image'] as const).map((k) => (
            <label key={k}>
              <input type="checkbox" checked={perms[k]} onChange={(e) => setPerms({ ...perms, [k]: e.target.checked })} /> {k}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Лимиты</legend>
          {([['youtube_daily', 'YouTube'], ['convert_daily', 'Convert'], ['image_daily', 'Image']] as const).map(([k, l]) => (
            <label key={k}>{l}: <input type="number" min={0} value={limits[k]} onChange={(e) => setLimits({ ...limits, [k]: Number(e.target.value) })} /></label>
          ))}
        </fieldset>
        <div className={styles.modalActions}>
          <button className={styles.btnSecondary} onClick={onClose} disabled={busy}>Отмена</button>
          <button className={styles.btnPrimary} onClick={submit} disabled={busy}>Создать</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: `EditUserModal.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
import { useAuth } from '../../stores/authStore'
import type { UserDetail, UpdateUserRequest, Role } from '../../types'
import styles from '../Profile/Profile.module.css'

interface Props { userId: number; onClose: () => void; onSaved: () => void }


function canModify(actorRole: string, actorId: number, target: UserDetail): boolean {
  if (actorRole === 'superadmin') return true
  if (actorRole !== 'admin') return false
  if (target.role === 'superadmin') return false
  if (target.id === actorId) return false
  return true
}


export default function EditUserModal({ userId, onClose, onSaved }: Props) {
  const { user: actor } = useAuth()
  const [user, setUser] = useState<UserDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<UpdateUserRequest>({})

  useEffect(() => {
    api.get<UserDetail>(`/admin/users/${userId}`).then(({ data }) => {
      setUser(data)
      setDraft({ role: data.role as Role, permissions: { ...data.permissions }, limits: { ...data.limits }, is_active: data.is_active })
    })
  }, [userId])

  if (!user || !actor) return null
  const editable = canModify(actor.role, actor.id, user)

  const save = async () => {
    setBusy(true)
    try {
      await api.patch(`/admin/users/${userId}`, draft)
      toast.success('Сохранено')
      onSaved()
      onClose()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Ошибка')
    } finally { setBusy(false) }
  }

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()} style={{ width: 'min(92vw, 520px)' }}>
        <h3>{editable ? 'Редактирование' : 'Подробно'}: {user.username}</h3>

        {editable && actor.role === 'superadmin' && (
          <label>Роль:
            <select value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}>
              <option value="user">user</option>
              <option value="admin">admin</option>
              <option value="superadmin">superadmin</option>
            </select>
          </label>
        )}
        <fieldset>
          <legend>Права</legend>
          {(['youtube', 'converter', 'image'] as const).map((k) => (
            <label key={k}>
              <input type="checkbox" disabled={!editable} checked={!!draft.permissions?.[k]}
                onChange={(e) => setDraft({ ...draft, permissions: { ...draft.permissions, [k]: e.target.checked } })} /> {k}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Лимиты</legend>
          {([['youtube_daily', 'YouTube'], ['convert_daily', 'Convert'], ['image_daily', 'Image']] as const).map(([k, l]) => (
            <label key={k}>{l}: <input type="number" min={0} disabled={!editable} value={draft.limits?.[k] ?? 0}
              onChange={(e) => setDraft({ ...draft, limits: { ...draft.limits, [k]: Number(e.target.value) } })} /></label>
          ))}
        </fieldset>
        {editable && (
          <label>
            <input type="checkbox" checked={!!draft.is_active}
              onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} /> Активен
          </label>
        )}
        <div className={styles.modalActions}>
          <button className={styles.btnSecondary} onClick={onClose}>Закрыть</button>
          {editable && <button className={styles.btnPrimary} onClick={save} disabled={busy}>Сохранить</button>}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: `ResetPasswordModal.tsx`**

```tsx
import { useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
import type { ResetPasswordResponse } from '../../types'
import styles from '../Profile/Profile.module.css'

interface Props { userId: number; onClose: () => void }


export default function ResetPasswordModal({ userId, onClose }: Props) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ResetPasswordResponse | null>(null)

  const reset = async () => {
    setBusy(true)
    try {
      const { data } = await api.post<ResetPasswordResponse>(`/admin/users/${userId}/reset-password`)
      setResult(data)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Ошибка')
    } finally { setBusy(false) }
  }

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {!result ? (
          <>
            <h3>Сбросить пароль?</h3>
            <p>Текущие сессии пользователя будут завершены, ему придётся сменить пароль при следующем входе.</p>
            <div className={styles.modalActions}>
              <button className={styles.btnSecondary} onClick={onClose} disabled={busy}>Отмена</button>
              <button className={styles.btnPrimary} onClick={reset} disabled={busy}>Сбросить</button>
            </div>
          </>
        ) : (
          <>
            <h3>Новый пароль для {result.username}</h3>
            <code style={{ padding: '0.5rem', background: 'var(--bg-secondary)', borderRadius: 4, display: 'block', wordBreak: 'break-all' }}>{result.password}</code>
            <button className={styles.btnSecondary} onClick={() => { navigator.clipboard.writeText(result.password); toast.success('Скопировано') }}>Скопировать</button>
            <div className={styles.modalActions}>
              <button className={styles.btnPrimary} onClick={onClose}>Закрыть</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: `ConfirmDeleteModal.tsx`**

```tsx
import { useState } from 'react'
import { toast } from 'react-toastify'
import api from '../../api/client'
import styles from '../Profile/Profile.module.css'

interface Props { userId: number; username: string; onClose: () => void; onDeleted: () => void }


export default function ConfirmDeleteModal({ userId, username, onClose, onDeleted }: Props) {
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  const remove = async () => {
    if (confirm !== username) { toast.error('Имя не совпадает'); return }
    setBusy(true)
    try {
      await api.delete(`/admin/users/${userId}`)
      toast.success('Пользователь удалён')
      onDeleted()
      onClose()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Ошибка')
    } finally { setBusy(false) }
  }

  return (
    <div className={styles.modalOverlay} onClick={() => !busy && onClose()}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h3>Удалить пользователя {username}?</h3>
        <p>Введите username для подтверждения:</p>
        <input className={styles.input} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <div className={styles.modalActions}>
          <button className={styles.btnSecondary} onClick={onClose} disabled={busy}>Отмена</button>
          <button className={styles.btnDanger} onClick={remove} disabled={busy || confirm !== username}>Удалить</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Подключить в `AdminPage.tsx`**

Заменить `noop` на реальные state-флаги модалок:

```tsx
import CreateUserModal from './CreateUserModal'
import EditUserModal from './EditUserModal'
import ResetPasswordModal from './ResetPasswordModal'
import ConfirmDeleteModal from './ConfirmDeleteModal'
import api from '../../api/client'

// внутри AdminPage:
const [showCreate, setShowCreate] = useState(false)
const [editId, setEditId] = useState<number | null>(null)
const [resetId, setResetId] = useState<number | null>(null)
const [deleteCtx, setDeleteCtx] = useState<{ id: number; username: string } | null>(null)
const [usersRefresh, setUsersRefresh] = useState(0)
const triggerRefresh = () => setUsersRefresh((v) => v + 1)

const onToggle = async (id: number) => {
  await api.post(`/admin/users/${id}/toggle-active`)
  triggerRefresh()
}

const onDeleteAsk = async (id: number) => {
  // подтянуть имя
  const { data } = await api.get<{ username: string }>(`/admin/users/${id}`)
  setDeleteCtx({ id, username: data.username })
}

// ...в JSX:
{tab === 'users' && (
  <UsersTab
    key={usersRefresh}
    onCreate={() => setShowCreate(true)}
    onEdit={(id) => setEditId(id)}
    onResetPassword={(id) => setResetId(id)}
    onToggle={onToggle}
    onDelete={onDeleteAsk}
  />
)}
{showCreate && <CreateUserModal onClose={() => setShowCreate(false)} onCreated={triggerRefresh} />}
{editId !== null && <EditUserModal userId={editId} onClose={() => setEditId(null)} onSaved={triggerRefresh} />}
{resetId !== null && <ResetPasswordModal userId={resetId} onClose={() => setResetId(null)} />}
{deleteCtx && <ConfirmDeleteModal userId={deleteCtx.id} username={deleteCtx.username} onClose={() => setDeleteCtx(null)} onDeleted={triggerRefresh} />}
```

- [ ] **Step 6: Проверка через playwright-cli**

```bash
playwright-cli goto http://localhost:5173/admin
playwright-cli click <ref-create>
playwright-cli fill <ref-username> "test_e2e"
playwright-cli click <ref-submit>
playwright-cli snapshot   # должен появиться экран с одноразовым паролем
playwright-cli close
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Admin/
git commit -m "feat(admin): user management modals (create/edit/reset/delete)"
```

---

## Task 22: Frontend — AuditLogTab

**Goal:** Таб «Аудит-лог» с таблицей, фильтрами и кнопкой экспорта в CSV.

**Files:**
- Create: `frontend/src/pages/Admin/AuditLogTab.tsx`
- Modify: `frontend/src/pages/Admin/AdminPage.tsx`

**Acceptance Criteria:**
- [ ] Таблица: дата, пользователь (username), action (badge), детали (раскрываемый JSON), IP.
- [ ] Фильтры: поиск по username (-> user_id), action (фиксированный select), date from/to, пагинация offset/limit=50.
- [ ] Кнопка «Экспорт CSV» скачивает файл.

**Verify:** snapshot вкладки должен показывать таблицу и контролы фильтра.

**Steps:**

- [ ] **Step 1: `frontend/src/pages/Admin/AuditLogTab.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import api from '../../api/client'
import type { AuditLogItem, AuditLogListResponse } from '../../types'
import styles from './Admin.module.css'

const PAGE = 50
const ACTIONS = [
  '', 'login', 'logout', 'login_failed', 'change_password',
  'user_created', 'user_updated', 'user_deleted', 'user_password_reset',
  'user_toggled_active', 'session_killed_by_admin', 'username_changed',
  'avatar_updated', 'avatar_removed',
]


export default function AuditLogTab() {
  const [items, setItems] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [action, setAction] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  const buildQuery = () => {
    const p = new URLSearchParams()
    p.set('offset', String(offset))
    p.set('limit', String(PAGE))
    if (action) p.set('action', action)
    if (from) p.set('from', from)
    if (to) p.set('to', to)
    return p.toString()
  }

  useEffect(() => {
    api.get<AuditLogListResponse>(`/admin/audit-log?${buildQuery()}`).then(({ data }) => {
      setItems(data.items)
      setTotal(data.total)
    })
  }, [offset, action, from, to])

  const downloadCsv = async () => {
    const r = await api.get(`/admin/audit-log/export.csv?${buildQuery()}`, { responseType: 'blob' })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'audit-log.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <select value={action} onChange={(e) => { setAction(e.target.value); setOffset(0) }}>
          {ACTIONS.map((a) => <option key={a} value={a}>{a || 'Все действия'}</option>)}
        </select>
        <input type="datetime-local" value={from} onChange={(e) => { setFrom(e.target.value); setOffset(0) }} />
        <input type="datetime-local" value={to} onChange={(e) => { setTo(e.target.value); setOffset(0) }} />
        <div className={styles.toolbarSpacer} />
        <button className={styles.iconBtn} onClick={downloadCsv}><Download size={14} /> CSV</button>
      </div>

      <table className={styles.table}>
        <thead>
          <tr><th>Дата</th><th>Пользователь</th><th>Действие</th><th>IP</th><th>Детали</th></tr>
        </thead>
        <tbody>
          {items.map((l) => (
            <tr key={l.id}>
              <td>{new Date(l.created_at).toLocaleString('ru-RU')}</td>
              <td>{l.username ?? '—'}</td>
              <td><code>{l.action}</code></td>
              <td className={styles.usageCompact}>{l.ip_address || '—'}</td>
              <td>
                {l.details ? (
                  <button className={styles.iconBtn} onClick={() => setExpanded(expanded === l.id ? null : l.id)}>
                    {expanded === l.id ? '▼' : '▶'}
                  </button>
                ) : '—'}
                {expanded === l.id && (
                  <pre style={{ background: 'var(--bg-secondary)', padding: 8, borderRadius: 4, fontSize: 12, marginTop: 4, overflow: 'auto' }}>{JSON.stringify(l.details, null, 2)}</pre>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.pagination}>
        <span className={styles.pageInfo}>{offset + 1}–{Math.min(offset + PAGE, total)} из {total}</span>
        <button className={styles.iconBtn} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Назад</button>
        <button className={styles.iconBtn} disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Вперёд</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Подключить в `AdminPage.tsx`**

```tsx
import AuditLogTab from './AuditLogTab'
// ...
{tab === 'audit' && <AuditLogTab />}
```

- [ ] **Step 3: Проверка**

```bash
playwright-cli goto "http://localhost:5173/admin?tab=audit"
playwright-cli snapshot
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Admin/AuditLogTab.tsx frontend/src/pages/Admin/AdminPage.tsx
git commit -m "feat(admin): audit log tab with filters and CSV export"
```

---

## Task 23: Frontend — MonitoringTab (только superadmin)

**Goal:** Таб «Мониторинг» с карточками CPU/RAM/Disk/Uptime, счётчиками операций, top-5 пользователей и версиями. Автообновление каждые 30 секунд.

**Files:**
- Create: `frontend/src/pages/Admin/MonitoringTab.tsx`
- Modify: `frontend/src/pages/Admin/Admin.module.css`
- Modify: `frontend/src/pages/Admin/AdminPage.tsx`

**Acceptance Criteria:**
- [ ] Карточки CPU/RAM/Disk/Uptime, второй ряд с операциями, третий с top-5.
- [ ] Версии в подвале.
- [ ] Polling раз в 30с, останавливается при `visibilityState !== 'visible'`.

**Verify:** snapshot должен содержать карточки с непустыми числами.

**Steps:**

- [ ] **Step 1: CSS**

```css
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-3); margin-bottom: var(--space-4); }
.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-4); }
.cardLabel { color: var(--text-muted); font-size: var(--fs-xs); font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 1px; }
.cardValue { font-size: var(--fs-2xl); font-weight: 600; margin-top: var(--space-2); }
.cardBar { height: 6px; background: var(--bg-secondary); border-radius: var(--radius-full); margin-top: var(--space-3); overflow: hidden; }
.cardBarFill { height: 100%; background: var(--accent); transition: width var(--transition-base); }
.versions { color: var(--text-muted); font-family: var(--font-mono); font-size: var(--fs-xs); margin-top: var(--space-6); padding-top: var(--space-4); border-top: 1px solid var(--border); }
```

- [ ] **Step 2: `MonitoringTab.tsx`**

```tsx
import { useEffect, useState } from 'react'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import type { AdminStats, SystemInfo } from '../../types'
import styles from './Admin.module.css'


function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${d}д ${h}ч ${m}м`
}


export default function MonitoringTab() {
  const [sys, setSys] = useState<SystemInfo | null>(null)
  const [stats, setStats] = useState<AdminStats | null>(null)

  const load = async () => {
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
    try {
      const [s, st] = await Promise.all([
        api.get<SystemInfo>('/admin/system'),
        api.get<AdminStats>('/admin/stats'),
      ])
      setSys(s.data)
      setStats(st.data)
    } catch {}
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  if (!sys || !stats) return <div>Загрузка...</div>

  const ramPct = sys.ram_total_mb > 0 ? Math.round((sys.ram_used_mb / sys.ram_total_mb) * 100) : 0
  const diskPct = sys.disk_total_gb > 0 ? Math.round((sys.disk_used_gb / sys.disk_total_gb) * 100) : 0

  return (
    <div>
      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardLabel}>CPU</div>
          <div className={styles.cardValue}>{sys.cpu_percent.toFixed(1)}%</div>
          <div className={styles.cardBar}><div className={styles.cardBarFill} style={{ width: `${sys.cpu_percent}%` }} /></div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>RAM</div>
          <div className={styles.cardValue}>{Math.round(sys.ram_used_mb)} / {Math.round(sys.ram_total_mb)} МБ</div>
          <div className={styles.cardBar}><div className={styles.cardBarFill} style={{ width: `${ramPct}%` }} /></div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Disk</div>
          <div className={styles.cardValue}>{sys.disk_used_gb.toFixed(1)} / {sys.disk_total_gb.toFixed(1)} ГБ</div>
          <div className={styles.cardBar}><div className={styles.cardBarFill} style={{ width: `${diskPct}%` }} /></div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Uptime</div>
          <div className={styles.cardValue}>{formatUptime(sys.uptime_seconds)}</div>
        </div>
      </div>

      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Downloads сегодня</div>
          <div className={styles.cardValue}>{stats.total_downloads_today}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Conversions сегодня</div>
          <div className={styles.cardValue}>{stats.total_conversions_today}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Image ops сегодня</div>
          <div className={styles.cardValue}>{stats.total_image_ops_today}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Storage</div>
          <div className={styles.cardValue}>{stats.storage_used_mb.toFixed(0)} МБ</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>Активные сессии</div>
          <div className={styles.cardValue}>{stats.active_sessions}</div>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.cardLabel}>Топ-5 пользователей сегодня</div>
        <table className={styles.table} style={{ marginTop: 12 }}>
          <thead><tr><th></th><th>Имя</th><th>Всего операций</th></tr></thead>
          <tbody>
            {stats.top_users.map((u) => (
              <tr key={u.user_id}>
                <td><AvatarImage userId={u.user_id} version={u.avatar_version} size={24} /></td>
                <td>{u.username}</td>
                <td>{u.total_today}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={styles.versions}>
        Python {sys.python_version} · ffmpeg {sys.ffmpeg_version} · yt-dlp {sys.yt_dlp_version}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Подключить в `AdminPage.tsx`**

```tsx
import MonitoringTab from './MonitoringTab'
// ...
{tab === 'monitoring' && isSuperadmin && <MonitoringTab />}
```

- [ ] **Step 4: Проверка**

```bash
playwright-cli goto "http://localhost:5173/admin?tab=monitoring"
playwright-cli snapshot
# Должны быть видны карточки CPU/RAM/Disk/Uptime, top-5, версии
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Admin/MonitoringTab.tsx frontend/src/pages/Admin/Admin.module.css frontend/src/pages/Admin/AdminPage.tsx
git commit -m "feat(admin): monitoring tab with cards and top-5 polling"
```

---

## Task 24: Финальная UI-верификация через playwright-cli

**Goal:** Прогнать сквозные сценарии в живом браузере, чтобы убедиться, что фаза 5 работает целиком. Backend-тесты на этом этапе уже зелёные (см. Task 0-11).

**Files:** Не создаются.

**Acceptance Criteria:**
- [ ] Login → редирект на `/`. Видны логотип и плитки.
- [ ] User видит только разрешённые модули + плитку «Личный кабинет».
- [ ] `/me` рендерит профиль с аватаром (загрузка/удаление работают).
- [ ] Admin видит полную админку с табами; Пользователи / Аудит-лог / Мой профиль доступны.
- [ ] Superadmin дополнительно видит «Мониторинг».
- [ ] Создание пользователя через UI — пароль показывается один раз.
- [ ] Polling: после смены permissions через API в течение ≤ 16с пользователь редиректится с защищённой страницы.
- [ ] Kill-session делает logout у жертвы с toast'ом.

**Verify:** ручной прогон сценариев через `playwright-cli`. Никакие изменения в код не вносятся; если что-то ломается — открывается отдельная задача.

**Steps:**

- [ ] **Step 1: Запустить оба сервиса**

```bash
cd backend && uvicorn app.main:app --port 8000 &
cd frontend && bun run dev &
sleep 5
```

- [ ] **Step 2: Сценарий 1 — User-пользователь**

```bash
playwright-cli open http://localhost:5173/login
# Создать тестового user через admin (см. ниже сценарий 2) или использовать существующего.
playwright-cli fill <username-ref> "user1"
playwright-cli fill <password-ref> "<password>"
playwright-cli click <submit-ref>
playwright-cli snapshot
# Проверить: URL = /, видны плитки и плитка "Личный кабинет"

playwright-cli click <tile-me-ref>
playwright-cli snapshot
# Проверить: шапка профиля, прогресс-бары, список сессий
```

- [ ] **Step 3: Сценарий 2 — Загрузка аватара**

```bash
playwright-cli click <upload-button-ref>
playwright-cli drop <input-ref> --path=./test-avatar.png
playwright-cli snapshot
# Видна модалка кропа
playwright-cli click <save-ref>
playwright-cli snapshot
# Аватар отображается в шапке профиля и в Topbar
```

- [ ] **Step 4: Сценарий 3 — Admin Panel**

```bash
# Перелогиниться в admin
playwright-cli goto http://localhost:5173/login
playwright-cli fill <user-ref> "admin"
playwright-cli fill <pass-ref> "<admin-password>"
playwright-cli click <submit>
playwright-cli goto http://localhost:5173/admin
playwright-cli snapshot
# Создать пользователя
playwright-cli click <create-button>
playwright-cli fill <new-username-ref> "test_e2e"
playwright-cli click <submit-create>
playwright-cli snapshot
# Должен быть показан одноразовый пароль
```

- [ ] **Step 5: Сценарий 4 — Мониторинг (superadmin)**

```bash
playwright-cli goto "http://localhost:5173/admin?tab=monitoring"
playwright-cli snapshot
# Карточки CPU/RAM/Disk/Uptime, top-5 пользователей, версии в подвале
```

- [ ] **Step 6: Сценарий 5 — Polling permissions**

```bash
# Войти как user в одной вкладке, открыть /image
# В другом терминале:
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<password>"}' | jq -r .access_token)
USER_ID=...
curl -X PATCH "http://localhost:8000/api/admin/users/$USER_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"permissions":{"youtube":true,"converter":true,"image":false}}'
# Через 16 секунд:
playwright-cli snapshot
# user должен оказаться на /
```

- [ ] **Step 7: Зафиксировать результаты**

Если все 5 сценариев прошли:

```bash
playwright-cli close
git status
# Должен быть чистый рабочий каталог
```

Если что-то сломалось — открыть GitHub-issue или TODO с воспроизведением. Не пытаться исправить в этом таске.

---

## Self-review

Все секции спецификации покрыты задачами:
- §1 Маршрутизация — Task 14, 15
- §2 Главная — Task 14
- §3 Личный кабинет — Tasks 4, 5, 17, 18, 19
- §4 Admin Panel — Tasks 6-11, 20, 21, 22, 23
- §5 Аватары — Tasks 3, 5, 13, 19
- §6 Backend — Tasks 0-11
- §7 Polling/безопасность — Task 16, ролевые правила в Tasks 6-8
- §8 Тестирование — backend pytest в каждой backend-задаче, UI через playwright-cli в Task 24

Без placeholders. Все типы согласованы (User содержит avatar_version, AvatarImage принимает userId/version, AvatarUploader использует AvatarImage).
