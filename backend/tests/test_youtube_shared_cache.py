import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.models.download_task import DownloadTask
from app.models.shared_file import SharedFile
from app.schemas.youtube import DownloadRequest
from app.services import youtube_service


def _make_request(**kwargs) -> DownloadRequest:
    defaults = {
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "format": "mp4",
        "quality": "720p",
        "title": "Test Video",
    }
    defaults.update(kwargs)
    return DownloadRequest(**defaults)


async def _insert_shared_file(db_session, *, expires_offset_hours: float = 5.0) -> SharedFile:
    sf = SharedFile(
        id=str(uuid.uuid4()),
        video_id="dQw4w9WgXcQ",
        format="mp4",
        quality="720p",
        filename="rickroll.mp4",
        title="Never Gonna Give You Up",
        file_size=1024,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_offset_hours),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(sf)
    await db_session.commit()
    await db_session.refresh(sf)
    return sf


@pytest.mark.asyncio
async def test_cache_hit_creates_task_with_shared_file_id(db_session):
    """create_cached_task должна создать таск с shared_file_id и is_cache_hit=True."""
    sf = await _insert_shared_file(db_session)

    task_id = str(uuid.uuid4())
    status = await youtube_service.create_cached_task(
        task_id=task_id,
        user_id=42,
        request=_make_request(),
        shared_file=sf,
        video_id="dQw4w9WgXcQ",
        db=db_session,
    )

    result = await db_session.execute(
        select(DownloadTask).where(DownloadTask.id == task_id)
    )
    row = result.scalar_one()

    assert row.shared_file_id == sf.id
    assert row.is_cache_hit is True
    assert row.status == "ready"
    assert status.cached is True


@pytest.mark.asyncio
async def test_permanent_delete_keeps_shared_file(db_session):
    """Удаление таска не должно трогать SharedFile."""
    sf = await _insert_shared_file(db_session)

    task_id = str(uuid.uuid4())
    row = DownloadTask(
        id=task_id,
        user_id=1,
        status="ready",
        progress=100.0,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        format="mp4",
        quality="720p",
        shared_file_id=sf.id,
        filename="rickroll.mp4",
    )
    db_session.add(row)
    await db_session.commit()

    # Удаляем таск напрямую (тестируем логику удаления без внешней сессии)
    await db_session.delete(row)
    await db_session.commit()

    # SharedFile должен остаться
    sf_result = await db_session.execute(
        select(SharedFile).where(SharedFile.id == sf.id)
    )
    assert sf_result.scalar_one_or_none() is not None

    # Таск должен быть удалён
    task_result = await db_session.execute(
        select(DownloadTask).where(DownloadTask.id == task_id)
    )
    assert task_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_find_cached_shared_file_returns_none_when_expired(db_session):
    """find_cached_shared_file не должна возвращать истёкший SharedFile."""
    sf = SharedFile(
        id=str(uuid.uuid4()),
        video_id="dQw4w9WgXcQ",
        format="mp4",
        quality="720p",
        filename="rickroll.mp4",
        file_size=1024,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        created_at=datetime.now(timezone.utc) - timedelta(hours=7),
    )
    db_session.add(sf)
    await db_session.commit()

    result = await youtube_service.find_cached_shared_file(
        video_id="dQw4w9WgXcQ",
        fmt="mp4",
        quality="720p",
        db=db_session,
    )
    assert result is None


@pytest.mark.asyncio
async def test_find_cached_shared_file_returns_none_when_file_missing(db_session):
    """find_cached_shared_file не должна возвращать SharedFile если файла нет на диске."""
    sf = await _insert_shared_file(db_session, expires_offset_hours=5.0)
    # Файла на диске нет — должна вернуть None

    result = await youtube_service.find_cached_shared_file(
        video_id="dQw4w9WgXcQ",
        fmt="mp4",
        quality="720p",
        db=db_session,
    )
    assert result is None
