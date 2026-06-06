# Multi downloader — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 4th module "Multi downloader" that downloads video (mp4) or audio (mp3) from any yt-dlp-supported site (examples shown: Pinterest, Twitter/X, TikTok no-watermark, VK), fully integrated into the standard module system.

**Architecture:** Approach A — own `multi_download_tasks` table, lean `multidl_service`, own `/api/multidl` router. Reuses existing `SharedFile` for storage/TTL/cleanup (`video_id` prefixed `multidl:` to avoid YouTube cache collisions) and extracts a shared `find_ffmpeg()` util. YouTube module is **not modified**.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + aiosqlite + Alembic + yt-dlp + FFmpeg (backend); React 18 + TypeScript + Vite + Axios (frontend). Backend tests use the direct-call pattern (no HTTP layer).

**Spec:** `docs/superpowers/specs/2026-06-05-multi-downloader-design.md`

---

## File Structure

**Backend — new files:**
- `backend/app/models/multi_download_task.py` — `MultiDownloadTask` ORM model
- `backend/app/schemas/multidl.py` — request/response Pydantic schemas
- `backend/app/utils/ffmpeg.py` — `find_ffmpeg()` shared helper
- `backend/app/services/multidl_service.py` — info + download pipeline + task helpers
- `backend/app/routers/multidl.py` — `/api/multidl` endpoints
- `backend/alembic/versions/0002_multi_download_tasks.py` — table migration
- `backend/tests/test_multidl.py` — backend tests

**Backend — modified files:**
- `backend/app/models/__init__.py` — register new model
- `backend/app/main.py` — register router, superadmin defaults, `reset_daily_usage`, `cleanup_stale_pending_tasks`
- `backend/app/models/user.py` — default dicts (+`multidl`)
- `backend/app/routers/admin/users.py` — create defaults
- `backend/app/routers/{youtube,convert,image}.py` — `_increment_usage` reset dict (+`multidl`)
- `backend/app/routers/admin/monitoring.py` — usage counter + stat
- `backend/app/schemas/admin.py` — `AdminStats.total_multidl_ops_today`

**Frontend — new files:**
- `frontend/src/pages/MultiDownloader/MultiDownloaderPage.tsx`
- `frontend/src/pages/MultiDownloader/DownloadCard.tsx`
- `frontend/src/pages/MultiDownloader/multidlApi.ts`
- `frontend/src/pages/MultiDownloader/types.ts`
- `frontend/src/pages/MultiDownloader/MultiDownloader.module.css`
- `frontend/src/hooks/useAuthedMedia.ts`

**Frontend — modified files:**
- `frontend/src/App.tsx`, `frontend/src/components/ProtectedRoute.tsx`
- `frontend/src/pages/Home/HomePage.tsx`
- `frontend/src/components/Layout/Sidebar.tsx`, `frontend/src/components/Layout/BottomNav.tsx`
- `frontend/src/pages/Admin/CreateUserModal.tsx`, `frontend/src/pages/Admin/EditUserModal.tsx`
- `frontend/src/pages/Profile/UsageBars.tsx`, `frontend/src/pages/Admin/MonitoringTab.tsx`
- `frontend/src/types/index.ts`

---

## Task 0: MultiDownloadTask model + migration

**Goal:** Persisted task table for Multi downloader, created via Alembic.

**Files:**
- Create: `backend/app/models/multi_download_task.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0002_multi_download_tasks.py`

**Acceptance Criteria:**
- [ ] `MultiDownloadTask` importable from `app.models`
- [ ] `alembic upgrade head` creates `multi_download_tasks` with index on `user_id`
- [ ] `alembic downgrade -1` drops it cleanly

**Verify:** `cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -c "from app.models import MultiDownloadTask; print(MultiDownloadTask.__tablename__)"` → prints `multi_download_tasks`

**Steps:**

- [ ] **Step 1: Create the model** (`backend/app/models/multi_download_task.py`)

```python
from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MultiDownloadTask(Base):
    """Persisted record of a Multi downloader task (single video/audio, any yt-dlp site)."""

    __tablename__ = "multi_download_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    audio_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    shared_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Register in `backend/app/models/__init__.py`**

Add import and `__all__` entry:

```python
from app.models.user import User
from app.models.audit import AuditLog, ActiveSession
from app.models.download_task import DownloadTask
from app.models.shared_file import SharedFile
from app.models.convert_task import ConvertTask
from app.models.image_task import ImageTask
from app.models.multi_download_task import MultiDownloadTask

__all__ = ["User", "AuditLog", "ActiveSession", "DownloadTask", "SharedFile", "ConvertTask", "ImageTask", "MultiDownloadTask"]
```

- [ ] **Step 3: Create migration** (`backend/alembic/versions/0002_multi_download_tasks.py`)

```python
"""multi_download_tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'multi_download_tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(length=1024), nullable=True),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('thumbnail', sa.String(length=2048), nullable=True),
        sa.Column('platform', sa.String(length=40), nullable=True),
        sa.Column('audio_only', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('shared_file_id', sa.String(length=36), nullable=True),
        sa.Column('hidden', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_multi_download_tasks_user_id'), 'multi_download_tasks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_multi_download_tasks_user_id'), table_name='multi_download_tasks')
    op.drop_table('multi_download_tasks')
```

- [ ] **Step 4: Run migration & verify**

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -c "from app.models import MultiDownloadTask; print(MultiDownloadTask.__tablename__)"`
Expected: `multi_download_tasks`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/multi_download_task.py backend/app/models/__init__.py backend/alembic/versions/0002_multi_download_tasks.py
git commit -m "feat(multidl): add MultiDownloadTask model and migration"
```

---

## Task 1: Pydantic schemas

**Goal:** Request/response schemas for the multidl router with URL validation.

**Files:**
- Create: `backend/app/schemas/multidl.py`
- Test: `backend/tests/test_multidl.py` (schema-validation tests only in this task)

**Acceptance Criteria:**
- [ ] `DownloadRequest` accepts `{url, audio_only}` and rejects empty/oversized URLs
- [ ] `DownloadStatus`, `InfoResponse`, `QuotaResponse` defined with correct field types
- [ ] Status literal includes `pending/downloading/converting/ready/error/cancelled`

**Verify:** `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k schema -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests** (`backend/tests/test_multidl.py`)

```python
import pytest
from pydantic import ValidationError

from app.schemas.multidl import DownloadRequest, InfoRequest, DownloadStatus


def test_schema_download_request_valid():
    req = DownloadRequest(url="https://www.tiktok.com/@user/video/123", audio_only=True)
    assert req.audio_only is True
    assert req.url.startswith("https://")


def test_schema_download_request_defaults_video():
    req = DownloadRequest(url="https://vk.com/video-1_1")
    assert req.audio_only is False


def test_schema_download_request_rejects_blank():
    with pytest.raises(ValidationError):
        DownloadRequest(url="   ")


def test_schema_status_literal_accepts_converting():
    s = DownloadStatus(task_id="t1", status="converting", progress=10.0)
    assert s.status == "converting"
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k schema -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.multidl'`

- [ ] **Step 3: Create schemas** (`backend/app/schemas/multidl.py`)

```python
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas._types import UtcDatetime


class InfoRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2048)

    @field_validator("url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("URL не должен быть пустым")
        return s


class InfoResponse(BaseModel):
    title: str
    thumbnail: str | None = None
    duration: int = 0  # seconds
    platform: str | None = None  # detected extractor key, e.g. "TikTok"


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2048)
    title: str | None = Field(default=None, max_length=512)
    audio_only: bool = Field(default=False, description="Download audio only and convert to mp3")

    @field_validator("url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("URL не должен быть пустым")
        return s


class DownloadStatus(BaseModel):
    task_id: str
    status: Literal["pending", "downloading", "converting", "ready", "error", "cancelled"]
    progress: float = Field(ge=0.0, le=100.0)
    filename: str | None = None
    error: str | None = None
    download_url: str | None = None
    file_size: int | None = None
    url: str | None = None
    title: str | None = None
    thumbnail: str | None = None
    platform: str | None = None
    audio_only: bool = False
    speed: float | None = None
    eta: int | None = None
    created_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    file_exists: bool = False


class QuotaResponse(BaseModel):
    used: int
    limit: int
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k schema -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/multidl.py backend/tests/test_multidl.py
git commit -m "feat(multidl): add request/response schemas"
```

---

## Task 2: find_ffmpeg() util

**Goal:** Shared ffmpeg-path helper for the multidl service.

**Files:**
- Create: `backend/app/utils/ffmpeg.py`
- Test: `backend/tests/test_multidl.py` (one test)

**Acceptance Criteria:**
- [ ] `find_ffmpeg()` returns a non-empty string (path or bare `ffmpeg`)

**Verify:** `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k ffmpeg -v` → pass

**Steps:**

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_multidl.py`)

```python
def test_ffmpeg_returns_path():
    from app.utils.ffmpeg import find_ffmpeg
    p = find_ffmpeg()
    assert isinstance(p, str) and len(p) > 0
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k ffmpeg -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.ffmpeg'`

- [ ] **Step 3: Create util** (`backend/app/utils/ffmpeg.py`)

```python
"""Shared FFmpeg locator."""
import os
import shutil


def find_ffmpeg() -> str:
    """Return the path to ffmpeg, preferring known install locations over PATH."""
    candidates = [
        os.path.join(os.path.expanduser("~"), r"AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"
```

- [ ] **Step 4: Run test to confirm pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k ffmpeg -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/ffmpeg.py backend/tests/test_multidl.py
git commit -m "feat(multidl): add shared find_ffmpeg util"
```

---

## Task 3: multidl_service (info + download + task helpers)

**Goal:** Lean download service — metadata fetch, video/audio download pipeline, in-memory progress, task CRUD helpers. No playlist/quality-ladder/cache/dedup.

**Files:**
- Create: `backend/app/services/multidl_service.py`
- Test: `backend/tests/test_multidl.py`

**Acceptance Criteria:**
- [ ] `create_task` persists a pending row and registers it in-memory
- [ ] `get_download_progress` returns in-memory status, falls back to DB
- [ ] `cancel_task` / `dismiss_task` mutate state correctly
- [ ] `get_user_tasks` excludes hidden rows
- [ ] `get_info` parses mocked yt-dlp output into `InfoResponse`
- [ ] Completed download writes a `SharedFile` with `video_id` prefixed `multidl:`

**Verify:** `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k service -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests** (append to `backend/tests/test_multidl.py`)

```python
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.multi_download_task import MultiDownloadTask


async def _make_user(db, username="u", role="user", perms=None):
    user = User(
        username=username,
        password_hash="x",
        role=role,
        permissions=perms if perms is not None else {"multidl": True},
        limits={"multidl_daily": 50},
        usage_today={"multidl": 0},
        usage_reset_date=date.today(),
        must_change_password=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_service_create_and_get_task(db_session):
    from app.services import multidl_service
    user = await _make_user(db_session)
    tid = str(uuid.uuid4())
    from app.schemas.multidl import DownloadRequest
    req = DownloadRequest(url="https://vk.com/video-1_1", audio_only=False)
    status = await multidl_service.create_task(tid, user.id, req, db_session)
    assert status.status == "pending"
    got = await multidl_service.get_download_progress(tid)
    assert got is not None and got.task_id == tid


@pytest.mark.asyncio
async def test_service_dismiss_hides_task(db_session):
    from app.services import multidl_service
    from app.schemas.multidl import DownloadRequest
    user = await _make_user(db_session, username="u2")
    tid = str(uuid.uuid4())
    await multidl_service.create_task(tid, user.id, DownloadRequest(url="https://vk.com/video-1_1"), db_session)
    # Persist a terminal state so it is listable
    await multidl_service._persist_task(tid, status="ready", filename="v.mp4")
    ok = await multidl_service.dismiss_task(tid, user.id)
    assert ok is True
    tasks = await multidl_service.get_user_tasks(user.id)
    assert all(t.task_id != tid for t in tasks)


@pytest.mark.asyncio
async def test_service_get_info_parses_mock(db_session, monkeypatch):
    from app.services import multidl_service

    def fake_extract(url):
        return {
            "title": "Cool clip",
            "thumbnail": "https://cdn/t.jpg",
            "duration": 12,
            "extractor_key": "TikTok",
        }

    monkeypatch.setattr(multidl_service, "_extract_info_sync", fake_extract)
    info = await multidl_service.get_info("https://www.tiktok.com/@u/video/1")
    assert info.title == "Cool clip"
    assert info.platform == "TikTok"
    assert info.duration == 12
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k service -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.multidl_service'`

- [ ] **Step 3: Create the service** (`backend/app/services/multidl_service.py`)

```python
"""Multi downloader service — single video/audio downloads from any yt-dlp site.

Lean by design: no playlist, no quality ladder, no cache-hit, no dedup. Reuses
SharedFile for storage/TTL/cleanup (video_id prefixed "multidl:" to avoid any
collision with YouTube cache lookups).
"""

import asyncio
import logging
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timedelta, timezone

import yt_dlp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.multi_download_task import MultiDownloadTask
from app.models.shared_file import SharedFile
from app.schemas.multidl import DownloadRequest, DownloadStatus, InfoResponse
from app.utils.ffmpeg import find_ffmpeg

logger = logging.getLogger("naturalsk.multidl")
FFMPEG_PATH = find_ffmpeg()

_TERMINAL = ("ready", "error", "cancelled")
_ACTIVE = ("pending", "downloading", "converting")

_active_tasks: dict[str, DownloadStatus] = {}
_tasks_lock = threading.Lock()
_active_ytdlp: dict[str, yt_dlp.YoutubeDL] = {}


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:200]


def _row_to_status(row: MultiDownloadTask, *, check_file: bool = False) -> DownloadStatus:
    download_url = f"/api/multidl/file/{row.id}" if row.status == "ready" else None
    file_exists = False
    if check_file and row.filename and row.shared_file_id:
        shared_dir = os.path.join(settings.UPLOAD_DIR, row.shared_file_id)
        file_exists = os.path.isfile(os.path.join(shared_dir, row.filename))
    return DownloadStatus(
        task_id=row.id,
        status=row.status,  # type: ignore[arg-type]
        progress=row.progress,
        filename=row.filename,
        error=row.error,
        download_url=download_url,
        file_size=row.file_size,
        url=row.url,
        title=row.title,
        thumbnail=row.thumbnail,
        platform=row.platform,
        audio_only=row.audio_only,
        created_at=_ensure_utc(row.created_at),
        completed_at=_ensure_utc(row.completed_at),
        file_exists=file_exists,
    )


async def _persist_task(task_id: str, **updates) -> None:
    updates.setdefault("updated_at", datetime.now(timezone.utc))
    async with async_session() as db:
        row = (await db.execute(select(MultiDownloadTask).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
        if row is None:
            logger.warning("_persist_task: task %s not found", task_id)
            return
        for k, v in updates.items():
            setattr(row, k, v)
        await db.commit()


def _update_active(task_id: str, **updates) -> None:
    with _tasks_lock:
        if task_id in _active_tasks:
            _active_tasks[task_id] = _active_tasks[task_id].model_copy(update=updates)


def _is_cancelled(task_id: str) -> bool:
    with _tasks_lock:
        t = _active_tasks.get(task_id)
        return t is not None and t.status == "cancelled"


# --- info ------------------------------------------------------------------

def _extract_info_sync(url: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "socket_timeout": 30, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


async def get_info(url: str) -> InfoResponse:
    """Fetch lightweight metadata for the preview card."""
    try:
        info = await asyncio.wait_for(asyncio.to_thread(_extract_info_sync, url), timeout=30.0)
    except asyncio.TimeoutError:
        raise TimeoutError("Timed out while fetching info")
    if not info:
        raise ValueError("yt-dlp returned no info for the given URL")
    return InfoResponse(
        title=info.get("title") or info.get("id") or "",
        thumbnail=info.get("thumbnail"),
        duration=int(info.get("duration") or 0),
        platform=info.get("extractor_key") or info.get("extractor"),
    )


# --- task CRUD -------------------------------------------------------------

async def create_task(task_id: str, user_id: int, request: DownloadRequest, db: AsyncSession) -> DownloadStatus:
    row = MultiDownloadTask(
        id=task_id,
        user_id=user_id,
        status="pending",
        progress=0.0,
        url=request.url,
        title=request.title,
        audio_only=request.audio_only,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    initial = _row_to_status(row)
    with _tasks_lock:
        _active_tasks[task_id] = initial
    return initial


async def get_task_for_user(task_id: str, user_id: int, db: AsyncSession) -> MultiDownloadTask | None:
    row = (await db.execute(select(MultiDownloadTask).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None
    return row


async def resolve_shared_file_dir(task_id: str, user_id: int, db: AsyncSession) -> str | None:
    row = await get_task_for_user(task_id, user_id, db)
    if row is None or row.shared_file_id is None:
        return None
    return os.path.join(settings.UPLOAD_DIR, row.shared_file_id)


async def get_download_progress(task_id: str) -> DownloadStatus | None:
    with _tasks_lock:
        cached = _active_tasks.get(task_id)
    if cached is not None:
        return cached
    async with async_session() as db:
        row = (await db.execute(select(MultiDownloadTask).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
    return _row_to_status(row) if row else None


async def get_user_tasks(user_id: int, limit: int = 50) -> list[DownloadStatus]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)).replace(tzinfo=None)
    async with async_session() as db:
        rows = (await db.execute(
            select(MultiDownloadTask)
            .where(
                MultiDownloadTask.user_id == user_id,
                MultiDownloadTask.created_at >= cutoff,
                MultiDownloadTask.hidden == False,  # noqa: E712
            )
            .order_by(MultiDownloadTask.created_at.desc())
            .limit(limit)
        )).scalars().all()
    out: list[DownloadStatus] = []
    for row in rows:
        with _tasks_lock:
            cached = _active_tasks.get(row.id)
        out.append(cached if cached is not None else _row_to_status(row, check_file=True))
    return out


async def cancel_task(task_id: str) -> bool:
    with _tasks_lock:
        t = _active_tasks.get(task_id)
        if t is not None:
            if t.status in _TERMINAL:
                return True
            _active_tasks[task_id] = t.model_copy(update={"status": "cancelled", "error": "Cancelled by user"})
    ydl = _active_ytdlp.pop(task_id, None)
    if ydl:
        try:
            ydl.params["abort_on_error"] = True
        except Exception:
            pass
    async with async_session() as db:
        result = await db.execute(
            update(MultiDownloadTask)
            .where(MultiDownloadTask.id == task_id, MultiDownloadTask.status.not_in(_TERMINAL))
            .values(status="cancelled", error="Cancelled by user", updated_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            exists = (await db.execute(select(MultiDownloadTask.id).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
            await db.commit()
            return exists is not None
        await db.commit()
    return True


async def dismiss_task(task_id: str, user_id: int) -> bool:
    async with async_session() as db:
        row = (await db.execute(
            select(MultiDownloadTask).where(MultiDownloadTask.id == task_id, MultiDownloadTask.user_id == user_id)
        )).scalar_one_or_none()
        if row is None:
            return False
        row.hidden = True
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()
    return True


# --- download pipeline -----------------------------------------------------

def _build_progress_hook(task_id: str):
    def hook(d: dict) -> None:
        with _tasks_lock:
            if task_id not in _active_tasks:
                return
            if _active_tasks[task_id].status == "cancelled":
                raise Exception("Download cancelled by user")
            if d.get("status") == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                pct = min(downloaded / total * 100, 99.0) if total > 0 else _active_tasks[task_id].progress
                raw_speed, raw_eta = d.get("speed"), d.get("eta")
                _active_tasks[task_id] = _active_tasks[task_id].model_copy(update={
                    "status": "downloading",
                    "progress": round(pct, 1),
                    "speed": float(raw_speed) if raw_speed is not None else None,
                    "eta": int(raw_eta) if raw_eta is not None else None,
                })
            elif d.get("status") == "finished":
                _active_tasks[task_id] = _active_tasks[task_id].model_copy(update={"progress": 99.0, "speed": None, "eta": None})
    return hook


def _run_ytdlp(ydl_opts: dict, url: str, task_id: str) -> None:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        _active_ytdlp[task_id] = ydl
        try:
            ydl.download([url])
        finally:
            _active_ytdlp.pop(task_id, None)


def _find_output(directory: str, extensions: tuple[str, ...]) -> str | None:
    temp = (".part", ".ytdl", ".tmp")
    fallback: str | None = None
    for fname in os.listdir(directory):
        fpath = os.path.join(directory, fname)
        if not os.path.isfile(fpath):
            continue
        low = fname.lower()
        if low.endswith(temp):
            continue
        if low.endswith(extensions):
            return fpath
        if fallback is None:
            fallback = fpath
    return fallback


async def _run_ffmpeg(args: list[str], task_id: str) -> None:
    _update_active(task_id, status="converting")
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("FFmpeg conversion timed out")
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed (rc={proc.returncode}): {stderr.decode(errors='replace')[-500:]}")


async def download(request: DownloadRequest, task_id: str, user_id: int, shared_file_id: str) -> None:
    """Background coroutine: download mp4 or extract mp3, then register a SharedFile."""
    url = request.url
    out_dir = os.path.join(settings.UPLOAD_DIR, shared_file_id)
    os.makedirs(out_dir, exist_ok=True)
    try:
        if request.audio_only:
            audio_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                "quiet": True, "no_warnings": True, "socket_timeout": 30, "noplaylist": True,
                "progress_hooks": [_build_progress_hook(task_id)],
                "ffmpeg_location": os.path.dirname(FFMPEG_PATH),
            }
            await asyncio.to_thread(_run_ytdlp, audio_opts, url, task_id)
            src = _find_output(out_dir, (".m4a", ".webm", ".ogg", ".opus", ".mp3", ".mp4", ".mkv"))
            if not src:
                raise RuntimeError("Downloaded audio file not found")
            base = os.path.splitext(os.path.basename(src))[0]
            output_file = os.path.join(out_dir, f"{base}.mp3")
            await _run_ffmpeg([FFMPEG_PATH, "-y", "-i", src, "-vn", "-acodec", "libmp3lame", output_file], task_id)
            if os.path.abspath(src) != os.path.abspath(output_file):
                try:
                    os.remove(src)
                except OSError:
                    pass
        else:
            video_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                "quiet": True, "no_warnings": True, "socket_timeout": 30, "noplaylist": True,
                "progress_hooks": [_build_progress_hook(task_id)],
                "ffmpeg_location": os.path.dirname(FFMPEG_PATH),
            }
            await asyncio.to_thread(_run_ytdlp, video_opts, url, task_id)
            output_file = _find_output(out_dir, (".mp4", ".mkv", ".webm"))
            if not output_file:
                raise RuntimeError("Downloaded video file not found")

        if _is_cancelled(task_id):
            return

        final_filename = os.path.basename(output_file)
        try:
            final_size: int | None = os.path.getsize(output_file)
        except OSError:
            final_size = None
        completed_now = datetime.now(timezone.utc)

        async with async_session() as db_sf:
            db_sf.add(SharedFile(
                id=shared_file_id,
                video_id=f"multidl:{shared_file_id}",
                format="mp3" if request.audio_only else "mp4",
                quality="audio" if request.audio_only else "best",
                filename=final_filename,
                title=request.title,
                file_size=final_size,
                expires_at=completed_now + timedelta(hours=settings.FILE_TTL_HOURS),
                created_at=completed_now,
            ))
            await db_sf.commit()

        _update_active(task_id, status="ready", progress=100.0, filename=final_filename,
                       download_url=f"/api/multidl/file/{task_id}", file_size=final_size,
                       completed_at=completed_now, file_exists=True)
        await _persist_task(task_id, status="ready", progress=100.0, filename=final_filename,
                            file_size=final_size, shared_file_id=shared_file_id, completed_at=completed_now)
        logger.info("Multidl task %s ready: %s", task_id, final_filename)

    except Exception as exc:
        if _is_cancelled(task_id):
            shutil.rmtree(out_dir, ignore_errors=True)
            return
        msg = str(exc)
        logger.error("Multidl task %s failed: %s", task_id, msg, exc_info=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        _update_active(task_id, status="error", error=msg[:500])
        await _persist_task(task_id, status="error", error=msg[:500])
    finally:
        async def _evict() -> None:
            await asyncio.sleep(30)
            with _tasks_lock:
                _active_tasks.pop(task_id, None)
        asyncio.create_task(_evict())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k service -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/multidl_service.py backend/tests/test_multidl.py
git commit -m "feat(multidl): add download service (info, pipeline, task helpers)"
```

---

## Task 4: Router + registration

**Goal:** `/api/multidl` endpoints with permission gate, quota, and task lifecycle; registered in `main.py`.

**Files:**
- Create: `backend/app/routers/multidl.py`
- Modify: `backend/app/main.py` (router import + include)
- Test: `backend/tests/test_multidl.py`

**Acceptance Criteria:**
- [ ] No `multidl` permission → `start_download` raises HTTPException 403
- [ ] Quota exhausted → 429; successful start increments `usage_today["multidl"]`
- [ ] `get_status`/`cancel_download` enforce ownership (404 for other users)
- [ ] `retry_download` rejects non-terminal tasks (409)
- [ ] Regression: a `multidl:`-prefixed SharedFile is NOT returned by `youtube_service.find_cached_shared_file`

**Verify:** `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k router -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests** (append to `backend/tests/test_multidl.py`)

Reuse `_make_user` and the `_make_request` helper pattern from the existing admin tests. Add a local `_make_request`:

```python
from starlette.requests import Request


def _make_request() -> Request:
    scope = {"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)}
    return Request(scope)


@pytest.mark.asyncio
async def test_router_permission_gate(db_session):
    from app.routers.multidl import start_download
    from app.schemas.multidl import DownloadRequest
    from fastapi import HTTPException
    user = await _make_user(db_session, username="noperm", perms={"multidl": False})

    class _BG:
        def add_task(self, *a, **k):
            pass

    with pytest.raises(HTTPException) as exc:
        await start_download(body=DownloadRequest(url="https://vk.com/video-1_1"),
                             background_tasks=_BG(), user=user, db=db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_router_start_increments_usage(db_session):
    from app.routers.multidl import start_download
    from app.schemas.multidl import DownloadRequest
    user = await _make_user(db_session, username="ok")

    class _BG:
        def add_task(self, *a, **k):
            pass

    res = await start_download(body=DownloadRequest(url="https://vk.com/video-1_1"),
                               background_tasks=_BG(), user=user, db=db_session)
    assert res.status == "pending"
    await db_session.refresh(user)
    assert user.usage_today.get("multidl") == 1


@pytest.mark.asyncio
async def test_router_quota_exhausted(db_session):
    from app.routers.multidl import start_download
    from app.schemas.multidl import DownloadRequest
    from fastapi import HTTPException
    user = await _make_user(db_session, username="full")
    user.limits = {"multidl_daily": 1}
    user.usage_today = {"multidl": 1}
    await db_session.commit()

    class _BG:
        def add_task(self, *a, **k):
            pass

    with pytest.raises(HTTPException) as exc:
        await start_download(body=DownloadRequest(url="https://vk.com/video-1_1"),
                             background_tasks=_BG(), user=user, db=db_session)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_router_no_youtube_cache_collision(db_session):
    """A multidl SharedFile must never satisfy a YouTube cache lookup."""
    from datetime import datetime, timedelta, timezone
    from app.models.shared_file import SharedFile
    from app.services import youtube_service
    sf = SharedFile(
        id="abc", video_id="multidl:abc", format="mp4", quality="best",
        filename="x.mp4", file_size=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(sf)
    await db_session.commit()
    hit = await youtube_service.find_cached_shared_file(video_id="abc", fmt="mp4", quality="best", db=db_session)
    assert hit is None
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k router -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.multidl'`

- [ ] **Step 3: Create router** (`backend/app/routers/multidl.py`)

```python
"""Multi downloader API router.

POST   /api/multidl/info            — preview metadata
POST   /api/multidl/download        — start a background download
GET    /api/multidl/status/{id}     — poll progress
GET    /api/multidl/file/{id}       — stream finished file
DELETE /api/multidl/cancel/{id}     — cancel active download
GET    /api/multidl/tasks           — user's recent tasks
POST   /api/multidl/retry/{id}      — re-run a failed/cancelled task
DELETE /api/multidl/task/{id}       — dismiss (hide) a task
GET    /api/multidl/quota           — daily quota usage
"""

import logging
import os
import uuid
from datetime import date

import yt_dlp
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.limits import UNLIMITED, has_unlimited_quota
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.multidl import DownloadRequest, DownloadStatus, InfoRequest, InfoResponse, QuotaResponse
from app.services import multidl_service

logger = logging.getLogger("naturalsk.multidl")
router = APIRouter(prefix="/api/multidl", tags=["multidl"])


def _require_permission(user: User) -> None:
    if not user.permissions.get("multidl", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="У вас нет доступа к Multi downloader")


def _get_quota(user: User) -> tuple[int, int]:
    used = user.usage_today.get("multidl", 0) if user.usage_reset_date == date.today() else 0
    limit = UNLIMITED if has_unlimited_quota(user) else user.limits.get("multidl_daily", 50)
    return used, limit


def _check_daily_limit(user: User) -> None:
    if has_unlimited_quota(user):
        return
    used, limit = _get_quota(user)
    if used >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Достигнут дневной лимит загрузок ({limit} загрузок/день)")


async def _increment_usage(user: User, db: AsyncSession) -> None:
    today = date.today()
    if user.usage_reset_date != today:
        user.usage_today = {"youtube": 0, "converter": 0, "image": 0, "multidl": 0}
        user.usage_reset_date = today
    today_usage = dict(user.usage_today)
    today_usage["multidl"] = today_usage.get("multidl", 0) + 1
    user.usage_today = today_usage
    await db.commit()


@router.post("/info", response_model=InfoResponse)
async def get_info(body: InfoRequest, user: User = Depends(get_current_user)) -> InfoResponse:
    _require_permission(user)
    try:
        return await multidl_service.get_info(body.url)
    except TimeoutError:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT,
                            detail="Превышено время ожидания. Попробуйте снова.")
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ("private", "unavailable", "not available", "removed", "deleted")):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Видео недоступно (приватное, удалено или заблокировано)")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Не удалось обработать ссылку. Проверьте, что она ведёт на видео.")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("multidl info error for %s: %s", body.url, exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Непредвиденная ошибка при получении информации")


@router.post("/download", response_model=DownloadStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_download(body: DownloadRequest, background_tasks: BackgroundTasks,
                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> DownloadStatus:
    _require_permission(user)
    _check_daily_limit(user)
    task_id = str(uuid.uuid4())
    shared_file_id = str(uuid.uuid4())
    initial = await multidl_service.create_task(task_id, user.id, body, db)
    await _increment_usage(user, db)
    background_tasks.add_task(multidl_service.download, request=body, task_id=task_id,
                             user_id=user.id, shared_file_id=shared_file_id)
    logger.info("Multidl task %s enqueued by user %d (audio_only=%s)", task_id, user.id, body.audio_only)
    return initial


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(user: User = Depends(get_current_user)) -> QuotaResponse:
    _require_permission(user)
    used, limit = _get_quota(user)
    return QuotaResponse(used=used, limit=limit)


@router.get("/tasks", response_model=list[DownloadStatus])
async def list_tasks(user: User = Depends(get_current_user)) -> list[DownloadStatus]:
    _require_permission(user)
    return await multidl_service.get_user_tasks(user_id=user.id)


@router.get("/status/{task_id}", response_model=DownloadStatus)
async def get_status(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> DownloadStatus:
    _require_permission(user)
    if await multidl_service.get_task_for_user(task_id, user.id, db) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или истекла")
    task = await multidl_service.get_download_progress(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или истекла")
    return task


@router.get("/file/{task_id}")
async def download_file(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> FileResponse:
    _require_permission(user)
    task = await multidl_service.get_download_progress(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или истекла")
    if task.status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Файл ещё не готов (статус: {task.status})")
    if not task.filename:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Имя файла отсутствует")
    shared_dir = await multidl_service.resolve_shared_file_dir(task_id, user.id, db)
    if shared_dir is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или файл не готов")
    file_path = os.path.join(shared_dir, task.filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Файл не найден. Возможно, он был удалён по истечении срока хранения.")
    return FileResponse(path=file_path, filename=task.filename, media_type="application/octet-stream")


@router.delete("/cancel/{task_id}", response_model=dict)
async def cancel_download(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    _require_permission(user)
    if await multidl_service.get_task_for_user(task_id, user.id, db) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    if not await multidl_service.cancel_task(task_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return {"task_id": task_id, "cancelled": True}


@router.delete("/task/{task_id}", response_model=dict)
async def dismiss_task(task_id: str, user: User = Depends(get_current_user)) -> dict:
    _require_permission(user)
    if not await multidl_service.dismiss_task(task_id=task_id, user_id=user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return {"task_id": task_id, "dismissed": True}


@router.post("/retry/{task_id}", response_model=DownloadStatus, status_code=status.HTTP_202_ACCEPTED)
async def retry_download(task_id: str, background_tasks: BackgroundTasks,
                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> DownloadStatus:
    _require_permission(user)
    _check_daily_limit(user)
    orig = await multidl_service.get_task_for_user(task_id, user.id, db)
    if orig is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Исходная задача не найдена")
    current = await multidl_service.get_download_progress(task_id)
    if current is None or current.status not in ("error", "cancelled"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Повторить можно только неудачные или отменённые задачи")
    retry_req = DownloadRequest(url=orig.url, title=orig.title, audio_only=orig.audio_only)
    new_id = str(uuid.uuid4())
    shared_file_id = str(uuid.uuid4())
    new_status = await multidl_service.create_task(new_id, user.id, retry_req, db)
    await _increment_usage(user, db)
    background_tasks.add_task(multidl_service.download, request=retry_req, task_id=new_id,
                             user_id=user.id, shared_file_id=shared_file_id)
    return new_status
```

- [ ] **Step 4: Register router in `backend/app/main.py`**

Change the import line (currently `from app.routers import auth, admin, youtube, convert, image, users, me`) to add `multidl`:

```python
from app.routers import auth, admin, youtube, convert, image, users, me, multidl
```

Add the include after the existing `app.include_router(youtube.router)` block:

```python
app.include_router(multidl.router)
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k router -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/multidl.py backend/app/main.py backend/tests/test_multidl.py
git commit -m "feat(multidl): add API router and register it"
```

---

## Task 5: Register multidl as a first-class usage key

**Goal:** Add `multidl` permission, `multidl_daily` limit, and `multidl` usage keys to every place modules are enumerated — critically including the `usage_today`-reset dicts in all four module routers (which currently drop unknown keys on a date change).

**Files:**
- Modify: `backend/app/models/user.py:18-26`
- Modify: `backend/app/routers/admin/users.py:122,125`
- Modify: `backend/app/main.py` (`_create_superadmin` ~line 40, `reset_daily_usage` ~line 146, `cleanup_stale_pending_tasks` ~line 150)
- Modify: `backend/app/routers/youtube.py:86`, `backend/app/routers/convert.py:100`, `backend/app/routers/image.py:97`
- Test: `backend/tests/test_multidl.py`

**Acceptance Criteria:**
- [ ] New `User` defaults include `multidl`/`multidl_daily`
- [ ] Calling another module's `_increment_usage` after a date rollover preserves `multidl` (= 0, not dropped)
- [ ] `cleanup_stale_pending_tasks` deletes stale pending `multi_download_tasks`

**Verify:** `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k integration -v` → pass

**Steps:**

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_multidl.py`)

```python
@pytest.mark.asyncio
async def test_integration_youtube_increment_keeps_multidl(db_session):
    """A date rollover in youtube's _increment_usage must not wipe multidl usage."""
    from datetime import date, timedelta
    from app.routers.youtube import _increment_usage as yt_increment
    user = await _make_user(db_session, username="roll")
    user.usage_today = {"youtube": 3, "converter": 0, "image": 0, "multidl": 7}
    user.usage_reset_date = date.today() - timedelta(days=1)  # force rollover
    await db_session.commit()
    await yt_increment(user, db_session)
    await db_session.refresh(user)
    # After rollover youtube resets to 1; multidl must be present and 0, not missing
    assert user.usage_today.get("youtube") == 1
    assert user.usage_today.get("multidl") == 0


def test_integration_user_defaults_include_multidl():
    from app.models.user import User
    u = User.__table__.columns  # smoke: model import works
    from sqlalchemy import inspect  # noqa: F401
    # Construct with defaults via the column default callables
    perms = User.permissions.default.arg(None)
    limits = User.limits.default.arg(None)
    assert perms.get("multidl") is True
    assert limits.get("multidl_daily") == 50
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k integration -v`
Expected: FAIL — `multidl` missing from defaults / wiped on rollover

- [ ] **Step 3: Update `backend/app/models/user.py`** (lines 18-26)

```python
    permissions: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"youtube": True, "converter": True, "image": True, "multidl": True}, nullable=False
    )
    limits: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50, "multidl_daily": 50}, nullable=False
    )
    usage_today: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"youtube": 0, "converter": 0, "image": 0, "multidl": 0}, nullable=False
    )
```

- [ ] **Step 4: Update `backend/app/routers/admin/users.py`** (lines 122, 125)

```python
        permissions=body.permissions or {"youtube": True, "converter": True, "image": True, "multidl": True},
```
```python
        limits=body.limits or {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50, "multidl_daily": 50},
```

- [ ] **Step 5: Update `backend/app/main.py`**

`_create_superadmin` (~line 40):
```python
            permissions={"youtube": True, "converter": True, "image": True, "multidl": True},
```

`reset_daily_usage` (~line 146):
```python
                    user.usage_today = {"youtube": 0, "converter": 0, "image": 0, "multidl": 0}
```

`cleanup_stale_pending_tasks` — add the model import and a third scan block. After the import lines (~154) add:
```python
        from app.models.multi_download_task import MultiDownloadTask
```
After the stale image-tasks block (before `total = ...`), add:
```python
                # Clean stale multidl tasks
                result_md = await db.execute(
                    select(MultiDownloadTask).where(
                        MultiDownloadTask.status == "pending",
                        MultiDownloadTask.created_at < cutoff_naive,
                    )
                )
                stale_md_tasks = result_md.scalars().all()
                for task in stale_md_tasks:
                    task_dir = os.path.join(settings.UPLOAD_DIR, task.id)
                    if os.path.isdir(task_dir):
                        shutil.rmtree(task_dir, ignore_errors=True)
                    await db.delete(task)
```
Then update the `total` line to include them:
```python
                total = len(stale_tasks) + len(stale_image_tasks) + len(stale_md_tasks)
```

- [ ] **Step 6: Update the three module routers' reset dicts**

`backend/app/routers/youtube.py:86`, `backend/app/routers/convert.py:100`, `backend/app/routers/image.py:97` — each currently:
```python
        user.usage_today = {"youtube": 0, "converter": 0, "image": 0}
```
Change all three to:
```python
        user.usage_today = {"youtube": 0, "converter": 0, "image": 0, "multidl": 0}
```

- [ ] **Step 7: Run tests to confirm pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k integration -v`
Expected: 2 passed

- [ ] **Step 8: Run the full backend suite (regression check)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass (no regressions in youtube/convert/image)

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/user.py backend/app/routers/admin/users.py backend/app/main.py backend/app/routers/youtube.py backend/app/routers/convert.py backend/app/routers/image.py backend/tests/test_multidl.py
git commit -m "feat(multidl): register multidl as first-class permission/limit/usage key"
```

---

## Task 6: Admin monitoring stat

**Goal:** Surface daily multidl downloads in admin stats and include them in per-user totals.

**Files:**
- Modify: `backend/app/schemas/admin.py` (`AdminStats`)
- Modify: `backend/app/routers/admin/monitoring.py:56-107`
- Test: `backend/tests/test_multidl.py`

**Acceptance Criteria:**
- [ ] `AdminStats` has `total_multidl_ops_today: int`
- [ ] `get_stats` sums `usage_today["multidl"]` across users and includes it in `top_users` totals

**Verify:** `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k monitoring -v` → pass

**Steps:**

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_multidl.py`)

```python
@pytest.mark.asyncio
async def test_monitoring_counts_multidl(db_session):
    from app.routers.admin.monitoring import get_stats
    admin = await _make_user(db_session, username="adm", role="superadmin")
    admin.usage_today = {"youtube": 0, "converter": 0, "image": 0, "multidl": 4}
    await db_session.commit()
    stats = await get_stats(db=db_session, actor=admin)
    assert stats.total_multidl_ops_today == 4
```

> Note: match `get_stats`'s real parameter names/dependencies when calling directly — inspect the function signature in `monitoring.py` and pass `db=db_session` plus whatever `actor`/auth dependency it declares (mirror the existing monitoring tests if present).

- [ ] **Step 2: Run to confirm failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k monitoring -v`
Expected: FAIL — `AdminStats` has no `total_multidl_ops_today`

- [ ] **Step 3: Add field to `backend/app/schemas/admin.py`** (`AdminStats`, after `total_image_ops_today`)

```python
    total_multidl_ops_today: int
```

- [ ] **Step 4: Update `backend/app/routers/admin/monitoring.py`**

Add a helper next to `_im` (~line 63):
```python
    def _md(u: User) -> int:
        return int(u.usage_today.get("multidl", 0)) if u.usage_today else 0
```
Add the sum next to `im = ...` (~line 67):
```python
    md = sum(_md(u) for u in users)
```
Update `_total` (~line 80) to include multidl:
```python
    def _total(u: User) -> int:
        return _yt(u) + _cv(u) + _im(u) + _md(u)
```
Add the field to the `AdminStats(...)` return (after `total_image_ops_today=im,`):
```python
        total_multidl_ops_today=md,
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_multidl.py -k monitoring -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/routers/admin/monitoring.py backend/tests/test_multidl.py
git commit -m "feat(multidl): add multidl downloads to admin stats"
```

---

## Task 7: Frontend types, API client, useAuthedMedia hook

**Goal:** TypeScript types, axios API wrapper, and an authed-blob hook for video/audio preview.

**Files:**
- Create: `frontend/src/pages/MultiDownloader/types.ts`
- Create: `frontend/src/pages/MultiDownloader/multidlApi.ts`
- Create: `frontend/src/hooks/useAuthedMedia.ts`
- Modify: `frontend/src/types/index.ts` (User perms/limits/usage + AdminStats)

**Acceptance Criteria:**
- [ ] `User.permissions`/`limits`/`usage_today` include `multidl` keys
- [ ] `AdminStats` includes `total_multidl_ops_today`
- [ ] `multidlApi` exposes `getInfo/startDownload/getStatus/getTasks/cancelDownload/retryDownload/dismissTask/getQuota/downloadFile`
- [ ] `tsc` build passes

**Verify:** `cd frontend && bun run build` → succeeds (tsc + vite)

**Steps:**

- [ ] **Step 1: Update `frontend/src/types/index.ts`**

Extend the `User` interface blocks:
```typescript
  permissions: {
    youtube: boolean
    converter: boolean
    image: boolean
    multidl: boolean
  }
  limits: {
    youtube_daily: number
    convert_daily: number
    image_daily: number
    multidl_daily: number
  }
  usage_today: {
    youtube: number
    converter: number
    image: number
    multidl: number
  }
```
Add to `AdminStats` (after `total_image_ops_today`):
```typescript
  total_multidl_ops_today: number
```

- [ ] **Step 2: Create `frontend/src/pages/MultiDownloader/types.ts`**

```typescript
export interface InfoResponse {
  title: string
  thumbnail?: string | null
  duration: number
  platform?: string | null
}

export type TaskStatus = 'pending' | 'downloading' | 'converting' | 'ready' | 'error' | 'cancelled'

export interface DownloadStatus {
  task_id: string
  status: TaskStatus
  progress: number
  filename?: string | null
  error?: string | null
  download_url?: string | null
  file_size?: number | null
  url?: string | null
  title?: string | null
  thumbnail?: string | null
  platform?: string | null
  audio_only: boolean
  speed?: number | null
  eta?: number | null
  created_at?: string | null
  completed_at?: string | null
  file_exists: boolean
}

export interface QuotaResponse {
  used: number
  limit: number
}
```

- [ ] **Step 3: Create `frontend/src/pages/MultiDownloader/multidlApi.ts`**

```typescript
import api from '../../api/client'
import type { InfoResponse, DownloadStatus, QuotaResponse } from './types'

export const multidlApi = {
  getInfo(url: string): Promise<InfoResponse> {
    return api.post<InfoResponse>('/multidl/info', { url }).then((r) => r.data)
  },
  startDownload(url: string, audioOnly: boolean, title?: string | null): Promise<DownloadStatus> {
    return api
      .post<DownloadStatus>('/multidl/download', { url, audio_only: audioOnly, title: title ?? null })
      .then((r) => r.data)
  },
  getStatus(taskId: string): Promise<DownloadStatus> {
    return api.get<DownloadStatus>(`/multidl/status/${taskId}`).then((r) => r.data)
  },
  getTasks(): Promise<DownloadStatus[]> {
    return api.get<DownloadStatus[]>('/multidl/tasks').then((r) => r.data)
  },
  cancelDownload(taskId: string): Promise<void> {
    return api.delete(`/multidl/cancel/${taskId}`).then(() => undefined)
  },
  retryDownload(taskId: string): Promise<DownloadStatus> {
    return api.post<DownloadStatus>(`/multidl/retry/${taskId}`).then((r) => r.data)
  },
  dismissTask(taskId: string): Promise<void> {
    return api.delete(`/multidl/task/${taskId}`).then(() => undefined)
  },
  getQuota(): Promise<QuotaResponse> {
    return api.get<QuotaResponse>('/multidl/quota').then((r) => r.data)
  },
  downloadFile(taskId: string): Promise<{ blob: Blob; filename: string }> {
    return api.get(`/multidl/file/${taskId}`, { responseType: 'blob' }).then((r) => {
      const disposition: string = r.headers['content-disposition'] ?? ''
      const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i)
      const filename = match ? decodeURIComponent(match[1]) : 'download'
      return { blob: r.data as Blob, filename }
    })
  },
}
```

- [ ] **Step 4: Create `frontend/src/hooks/useAuthedMedia.ts`**

```typescript
import { useEffect, useState } from 'react'
import api from '../api/client'

/** Fetch an authed binary resource (video/audio/image) as an object URL. */
export function useAuthedMedia(url: string | null): string | null {
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

- [ ] **Step 5: Build to verify**

Run: `cd frontend && bun run build`
Expected: build succeeds (no tsc errors). The new files are not yet imported anywhere — that's fine; they compile standalone.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/MultiDownloader/types.ts frontend/src/pages/MultiDownloader/multidlApi.ts frontend/src/hooks/useAuthedMedia.ts frontend/src/types/index.ts
git commit -m "feat(multidl): frontend types, api client, useAuthedMedia hook"
```

---

## Task 8: MultiDownloaderPage + DownloadCard

**Goal:** The page UI — URL input → info preview → mp4/mp3 toggle → download; task cards with progress and an inline authed preview of the finished file.

**Files:**
- Create: `frontend/src/pages/MultiDownloader/MultiDownloaderPage.tsx`
- Create: `frontend/src/pages/MultiDownloader/DownloadCard.tsx`
- Create: `frontend/src/pages/MultiDownloader/MultiDownloader.module.css`

**Acceptance Criteria:**
- [ ] URL field + "только mp3" toggle + "Скачать" button; placeholder lists Pinterest / Twitter·X / TikTok / VK
- [ ] After submit, polls `/status/{id}` until terminal; shows progress
- [ ] Ready video card shows inline `<video controls>` (mp4) or `<audio controls>` (mp3) via `useAuthedMedia` + a "Скачать файл" button
- [ ] Cancel / retry / dismiss wired to the API
- [ ] `tsc` build passes

**Verify:** `cd frontend && bun run build` → succeeds

**Steps:**

- [ ] **Step 1: Create `frontend/src/pages/MultiDownloader/DownloadCard.tsx`**

```tsx
import { Download, X, RotateCcw, Trash2, Film, Music } from 'lucide-react'
import { Button, Card } from '../../components/ui'
import { useAuthedMedia } from '../../hooks/useAuthedMedia'
import { multidlApi } from './multidlApi'
import type { DownloadStatus } from './types'
import styles from './MultiDownloader.module.css'

interface Props {
  task: DownloadStatus
  onCancel: (id: string) => void
  onRetry: (id: string) => void
  onDismiss: (id: string) => void
}

const ACTIVE = new Set(['pending', 'downloading', 'converting'])

export default function DownloadCard({ task, onCancel, onRetry, onDismiss }: Props) {
  // Inline preview of the finished file (authed blob). Only fetch when ready.
  const mediaUrl = task.status === 'ready' && task.file_exists ? `/multidl/file/${task.task_id}` : null
  const src = useAuthedMedia(mediaUrl)

  async function handleSave() {
    const { blob, filename } = await multidlApi.downloadFile(task.task_id)
    const a = document.createElement('a')
    const objectUrl = URL.createObjectURL(blob)
    a.href = objectUrl
    a.download = filename
    a.click()
    URL.revokeObjectURL(objectUrl)
  }

  return (
    <Card variant="glass" className={styles.card}>
      <div className={styles.cardHead}>
        {task.audio_only ? <Music size={18} /> : <Film size={18} />}
        <span className={styles.cardTitle}>{task.title || task.url}</span>
        {task.platform && <span className={styles.platformChip}>{task.platform}</span>}
      </div>

      {ACTIVE.has(task.status) && (
        <div className={styles.progressTrack}>
          <div className={styles.progressFill} style={{ width: `${task.progress}%` }} />
        </div>
      )}

      {task.status === 'ready' && (
        <div className={styles.preview}>
          {src ? (
            task.audio_only ? (
              <audio controls src={src} className={styles.player} />
            ) : (
              <video controls src={src} poster={task.thumbnail ?? undefined} className={styles.player} />
            )
          ) : (
            task.thumbnail && <img src={task.thumbnail} alt="" className={styles.posterFallback} />
          )}
        </div>
      )}

      {task.status === 'error' && <div className={styles.errorText}>{task.error}</div>}

      <div className={styles.cardActions}>
        {ACTIVE.has(task.status) && (
          <Button variant="ghost" size="sm" leftIcon={<X size={14} />} onClick={() => onCancel(task.task_id)}>
            Отмена
          </Button>
        )}
        {task.status === 'ready' && (
          <Button variant="primary" size="sm" leftIcon={<Download size={14} />} onClick={handleSave}>
            Скачать файл
          </Button>
        )}
        {(task.status === 'error' || task.status === 'cancelled') && (
          <Button variant="secondary" size="sm" leftIcon={<RotateCcw size={14} />} onClick={() => onRetry(task.task_id)}>
            Повторить
          </Button>
        )}
        {!ACTIVE.has(task.status) && (
          <Button variant="ghost" size="sm" leftIcon={<Trash2 size={14} />} onClick={() => onDismiss(task.task_id)}>
            Убрать
          </Button>
        )}
      </div>
    </Card>
  )
}
```

- [ ] **Step 2: Create `frontend/src/pages/MultiDownloader/MultiDownloaderPage.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react'
import { toast } from 'react-toastify'
import axios from 'axios'
import { Download } from 'lucide-react'
import { Button, Card, Input } from '../../components/ui'
import { multidlApi } from './multidlApi'
import type { DownloadStatus } from './types'
import DownloadCard from './DownloadCard'
import styles from './MultiDownloader.module.css'

const ACTIVE = new Set(['pending', 'downloading', 'converting'])
const PLACEHOLDER = 'Ссылка с Pinterest, Twitter/X, TikTok или VK'

export default function MultiDownloaderPage() {
  const [url, setUrl] = useState('')
  const [audioOnly, setAudioOnly] = useState(false)
  const [previewTitle, setPreviewTitle] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [tasks, setTasks] = useState<DownloadStatus[]>([])
  const pollRef = useRef<number | null>(null)

  // Restore tasks on mount
  useEffect(() => {
    multidlApi.getTasks().then(setTasks).catch(() => undefined)
  }, [])

  // Poll active tasks
  useEffect(() => {
    const hasActive = tasks.some((t) => ACTIVE.has(t.status))
    if (!hasActive) {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      return
    }
    if (pollRef.current) return
    pollRef.current = window.setInterval(async () => {
      const active = tasks.filter((t) => ACTIVE.has(t.status))
      for (const t of active) {
        try {
          const s = await multidlApi.getStatus(t.task_id)
          setTasks((prev) => prev.map((p) => (p.task_id === s.task_id ? s : p)))
        } catch {
          /* ignore transient errors */
        }
      }
    }, 1500)
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [tasks])

  async function handleSubmit() {
    if (!url.trim()) return
    setSubmitting(true)
    try {
      let title: string | null = previewTitle
      if (!title) {
        try {
          const info = await multidlApi.getInfo(url.trim())
          title = info.title
          setPreviewTitle(info.title)
        } catch {
          title = null // info is best-effort; download can still proceed
        }
      }
      const task = await multidlApi.startDownload(url.trim(), audioOnly, title)
      setTasks((prev) => [task, ...prev])
      setUrl('')
      setPreviewTitle(null)
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 429) {
        toast.error('Достигнут дневной лимит загрузок')
      } else if (axios.isAxiosError(err) && err.response?.data?.detail) {
        toast.error(String(err.response.data.detail))
      } else {
        toast.error('Не удалось начать загрузку')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCancel(id: string) {
    await multidlApi.cancelDownload(id).catch(() => undefined)
    setTasks((prev) => prev.map((t) => (t.task_id === id ? { ...t, status: 'cancelled' } : t)))
  }

  async function handleRetry(id: string) {
    try {
      const task = await multidlApi.retryDownload(id)
      setTasks((prev) => [task, ...prev.filter((t) => t.task_id !== id)])
    } catch {
      toast.error('Не удалось повторить загрузку')
    }
  }

  async function handleDismiss(id: string) {
    await multidlApi.dismissTask(id).catch(() => undefined)
    setTasks((prev) => prev.filter((t) => t.task_id !== id))
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Multi downloader</h1>
      <p className={styles.subheading}>Скачивание видео с Pinterest, Twitter/X, TikTok (без водяного знака) и VK</p>

      <Card variant="elevated" className={styles.inputCard}>
        <Input
          label="Ссылка на видео"
          placeholder={PLACEHOLDER}
          value={url}
          onChange={(e) => {
            setUrl(e.target.value)
            setPreviewTitle(null)
          }}
        />
        <label className={styles.toggleRow}>
          <input type="checkbox" checked={audioOnly} onChange={(e) => setAudioOnly(e.target.checked)} />
          Только аудио (mp3)
        </label>
        <Button
          variant="primary"
          leftIcon={<Download size={16} />}
          loading={submitting}
          onClick={handleSubmit}
        >
          Скачать
        </Button>
      </Card>

      <div className={styles.tasks}>
        {tasks.map((t) => (
          <DownloadCard
            key={t.task_id}
            task={t}
            onCancel={handleCancel}
            onRetry={handleRetry}
            onDismiss={handleDismiss}
          />
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create `frontend/src/pages/MultiDownloader/MultiDownloader.module.css`**

Use cosmic (Indigo Nebula) tokens — do NOT use removed legacy tokens.

```css
.wrapper {
  max-width: 760px;
  margin: 0 auto;
  padding: 24px 16px 96px;
}
.heading {
  font-family: var(--font-display);
  font-size: 1.75rem;
  margin: 0 0 4px;
}
.subheading {
  font-family: var(--font-ui);
  color: var(--text-secondary);
  margin: 0 0 24px;
}
.inputCard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
}
.toggleRow {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-ui);
  color: var(--text-secondary);
  cursor: pointer;
}
.tasks {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 24px;
}
.card {
  padding: 16px;
}
.cardHead {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.cardTitle {
  font-family: var(--font-ui);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.platformChip {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: var(--bg-hover);
  color: var(--text-secondary);
}
.progressTrack {
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--bg-input);
  overflow: hidden;
  margin-bottom: 12px;
}
.progressFill {
  height: 100%;
  background: var(--accent-gradient);
  transition: width 0.3s ease;
}
.preview {
  margin: 12px 0;
}
.player {
  width: 100%;
  border-radius: 12px;
  background: #000;
}
.posterFallback {
  width: 100%;
  border-radius: 12px;
}
.errorText {
  color: var(--accent-3);
  font-family: var(--font-ui);
  font-size: 0.85rem;
  margin: 8px 0;
}
.cardActions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
```

> If `Input` does not forward `onChange`/`value`/`placeholder` exactly as assumed, open `frontend/src/components/ui/Input.tsx` and adapt the props (mirror how `YouTubePage` uses the UI kit). Verify `Button` supports `loading` and `leftIcon` (per CLAUDE.md it does).

- [ ] **Step 4: Build to verify**

Run: `cd frontend && bun run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/MultiDownloader/
git commit -m "feat(multidl): add MultiDownloader page and download card with inline preview"
```

---

## Task 9: Frontend integration wiring

**Goal:** Wire the module into routing, navigation, home tile, admin user forms, profile usage bars, and the monitoring tab.

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/components/ProtectedRoute.tsx`
- Modify: `frontend/src/pages/Home/HomePage.tsx`
- Modify: `frontend/src/components/Layout/Sidebar.tsx`, `frontend/src/components/Layout/BottomNav.tsx`
- Modify: `frontend/src/pages/Admin/CreateUserModal.tsx`, `frontend/src/pages/Admin/EditUserModal.tsx`
- Modify: `frontend/src/pages/Profile/UsageBars.tsx`, `frontend/src/pages/Admin/MonitoringTab.tsx`

**Acceptance Criteria:**
- [ ] `/multidl` route guarded by `requiredPermission="multidl"` renders the page
- [ ] HomePage shows a Multi downloader tile (gated by `permissions.multidl`); module counter says "из 4"
- [ ] Sidebar + BottomNav show the nav entry when permitted
- [ ] Create/Edit user modals expose the `multidl` permission checkbox + `multidl_daily` limit
- [ ] UsageBars shows a Multi downloader row; MonitoringTab shows the multidl stat
- [ ] `tsc` build passes

**Verify:** `cd frontend && bun run build` → succeeds

**Steps:**

- [ ] **Step 1: `ProtectedRoute.tsx`** — extend the union type (line 6):

```typescript
  requiredPermission?: 'youtube' | 'converter' | 'image' | 'multidl'
```

- [ ] **Step 2: `App.tsx`** — add the route alongside the others (mirror the `/image` block):

```tsx
          <Route
            path="/multidl"
            element={
              <ProtectedRoute requiredPermission="multidl">
                <MultiDownloaderPage />
              </ProtectedRoute>
            }
          />
```
And add the import near the other page imports:
```tsx
import MultiDownloaderPage from './pages/MultiDownloader/MultiDownloaderPage'
```

- [ ] **Step 3: `HomePage.tsx`** — import the icon, add a tile, fix the counter.

Add `Download` to the lucide import. After the `image` tile block (line ~28) add:
```tsx
  if (user.permissions.multidl) {
    tiles.push({ to: '/multidl', icon: Download, title: 'Multi downloader', description: 'Видео с Pinterest, Twitter/X, TikTok, VK' })
  }
```
Update the counter (lines 35-36):
```tsx
  const totalAvailable = [user.permissions.youtube, user.permissions.converter, user.permissions.image, user.permissions.multidl].filter(Boolean).length
  const status = totalAvailable === 4 ? 'Все модули доступны' : `${totalAvailable} из 4 модулей`
```

- [ ] **Step 4: `Sidebar.tsx`** — add `Download` to the lucide import and a `moduleItems` entry (after the image line, ~25):

```tsx
    { to: '/multidl', icon: Download, label: 'Multi downloader', visible: user?.permissions.multidl },
```

- [ ] **Step 5: `BottomNav.tsx`** — add `Download` to the lucide import and a nav push mirroring the existing pattern:

```tsx
  if (user.permissions.multidl) {
    items.push({ to: '/multidl', icon: Download, label: 'Multi' })
  }
```

> Open `BottomNav.tsx` first to match its exact `items.push({...})` shape (label/icon keys) used by the existing youtube/converter/image entries.

- [ ] **Step 6: `CreateUserModal.tsx`** — extend defaults and the rendered checkbox/limit arrays:

```typescript
const DEFAULT_PERMS = { youtube: true, converter: true, image: true, multidl: true }
const DEFAULT_LIMITS = { youtube_daily: 50, convert_daily: 100, image_daily: 50, multidl_daily: 50 }
```
Permission checkbox map (line ~155):
```tsx
{(['youtube', 'converter', 'image', 'multidl'] as const).map((k) => (
```
Limit rows array (line ~176) — add the multidl row:
```tsx
                    ['multidl_daily', 'Multi downloader'],
```

- [ ] **Step 7: `EditUserModal.tsx`** — same two edits as Create:

Permission checkbox map (line ~118):
```tsx
{(['youtube', 'converter', 'image', 'multidl'] as const).map((k) => (
```
Limit rows (line ~145) — add:
```tsx
                    ['multidl_daily', 'Multi downloader'],
```

> Open both modals to confirm the surrounding array literal shape before editing; match it exactly.

- [ ] **Step 8: `UsageBars.tsx`** — extend the `MODULES` type union and array (lines 8-16):

```typescript
const MODULES: Array<{
  key: 'youtube' | 'converter' | 'image' | 'multidl'
  label: string
  limitKey: 'youtube_daily' | 'convert_daily' | 'image_daily' | 'multidl_daily'
}> = [
  { key: 'youtube', label: 'YouTube', limitKey: 'youtube_daily' },
  { key: 'converter', label: 'Converter', limitKey: 'convert_daily' },
  { key: 'image', label: 'Image', limitKey: 'image_daily' },
  { key: 'multidl', label: 'Multi downloader', limitKey: 'multidl_daily' },
]
```

- [ ] **Step 9: `MonitoringTab.tsx`** — add a stat card for `total_multidl_ops_today`.

Open the file, find the card that renders `stats.total_image_ops_today`, and add an adjacent card mirroring it:
```tsx
        <div className={styles.card}>
          <div className={styles.cardLabel}>Multi downloads сегодня</div>
          <div className={styles.cardValue}>{stats.total_multidl_ops_today}</div>
        </div>
```
> Match the exact class names and card markup used by the surrounding cards in this file.

- [ ] **Step 10: Build to verify**

Run: `cd frontend && bun run build`
Expected: build succeeds (tsc has no errors; all `multidl` keys resolve).

- [ ] **Step 11: Run frontend unit tests (regression)**

Run: `cd frontend && bun run test:run`
Expected: existing tests pass.

- [ ] **Step 12: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/ProtectedRoute.tsx frontend/src/pages/Home/HomePage.tsx frontend/src/components/Layout/Sidebar.tsx frontend/src/components/Layout/BottomNav.tsx frontend/src/pages/Admin/CreateUserModal.tsx frontend/src/pages/Admin/EditUserModal.tsx frontend/src/pages/Profile/UsageBars.tsx frontend/src/pages/Admin/MonitoringTab.tsx
git commit -m "feat(multidl): wire module into routing, nav, home, admin, profile"
```

---

## Task 10: End-to-end smoke verification

**Goal:** Confirm the module works against a real backend with a real download.

**Files:** none (manual/verification task)

**Acceptance Criteria:**
- [ ] Backend boots, `alembic upgrade head` applied, `/api/multidl/quota` returns 200 for a permitted user
- [ ] A real public URL (e.g. a TikTok/VK video) downloads to `ready` and the file streams from `/api/multidl/file/{id}`
- [ ] mp3 toggle produces a playable `.mp3`

**Verify:** Manual — see steps.

**Steps:**

- [ ] **Step 1: Boot backend**

```bash
cd backend && .venv/bin/alembic upgrade head && .venv/bin/uvicorn app.main:app --reload
```

- [ ] **Step 2: Boot frontend** (separate shell)

```bash
cd frontend && bun run dev
```

- [ ] **Step 3: Drive the UI with camoufox-cli**

Use the `camoufox-cli` skill: open `http://localhost:5173`, log in, grant the test user the `multidl` permission (via admin if needed), open `/multidl`, paste a public TikTok or VK video URL, click Скачать, snapshot until the card reaches "ready", verify the inline player renders, click "Скачать файл". Repeat with the mp3 toggle on.

- [ ] **Step 4: Confirm cleanup is unaffected**

Verify a downloaded file lands under `backend/uploads/<shared_file_id>/` and a matching `SharedFile` row exists with `video_id` like `multidl:...`.

- [ ] **Step 5: Final full-suite check**

```bash
cd backend && .venv/bin/python -m pytest -q
```
Expected: all pass.

---

## Self-Review

**Spec coverage:**
- §1 Goal/scope → Tasks 0–9 (module end-to-end). ✓
- §2.1 model → Task 0. ✓
- §2.2 service (info, download, helpers, SharedFile reuse, multidl: prefix) → Task 3. ✓
- §2.3 ffmpeg util → Task 2. ✓
- §2.4 router + schemas + registration → Tasks 1, 4. ✓
- §2.5 migration → Task 0. ✓
- §3 integration points (keys in all 4 reset dicts, model/admin/superadmin/reset/monitoring/cleanup) → Tasks 5, 6. ✓
- §4 frontend (page, preview via authed media, all wiring points) → Tasks 7, 8, 9. ✓
- §5 error handling → Task 4 router (403/429/408/404/400/500). ✓
- §6 tests → Tasks 1–6 (backend), Task 9 (frontend build/test), Task 10 (e2e). ✓

**Placeholder scan:** No TBD/TODO. Each code step contains real code. Where exact upstream markup is uncertain (UI-kit props, modal array shape, MonitoringTab card classes), the step includes an inline "open the file and match" directive rather than a vague placeholder — acceptable because the change is mechanical and the surrounding pattern is shown.

**Type consistency:** `DownloadStatus` fields identical across backend schema (Task 1) and frontend type (Task 7). API method names in `multidlApi` (Task 7) match the calls in `MultiDownloaderPage`/`DownloadCard` (Task 8). Permission key `multidl`, limit key `multidl_daily`, usage key `multidl`, route `/multidl`, endpoint prefix `/api/multidl`, SharedFile `video_id` prefix `multidl:` — consistent throughout.

No user-gate tasks tagged.
