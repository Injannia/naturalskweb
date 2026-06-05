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


def test_ffmpeg_returns_path():
    from app.utils.ffmpeg import find_ffmpeg
    p = find_ffmpeg()
    assert isinstance(p, str) and len(p) > 0


import uuid
from datetime import date

import pytest

from app.models.user import User


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
    from app.schemas.multidl import DownloadRequest
    user = await _make_user(db_session)
    tid = str(uuid.uuid4())
    status = await multidl_service.create_task(tid, user.id, DownloadRequest(url="https://vk.com/video-1_1", audio_only=False), db_session)
    assert status.status == "pending"
    got = await multidl_service.get_download_progress(tid, db_session)
    assert got is not None and got.task_id == tid


@pytest.mark.asyncio
async def test_service_dismiss_hides_task(db_session):
    from app.services import multidl_service
    from app.schemas.multidl import DownloadRequest
    user = await _make_user(db_session, username="u2")
    tid = str(uuid.uuid4())
    await multidl_service.create_task(tid, user.id, DownloadRequest(url="https://vk.com/video-1_1"), db_session)
    # mark terminal directly on the row so it is listable
    row = await multidl_service.get_task_for_user(tid, user.id, db_session)
    row.status = "ready"
    row.filename = "v.mp4"
    await db_session.commit()
    ok = await multidl_service.dismiss_task(tid, user.id, db_session)
    assert ok is True
    tasks = await multidl_service.get_user_tasks(user.id, db_session)
    assert all(t.task_id != tid for t in tasks)


@pytest.mark.asyncio
async def test_service_get_info_parses_mock(db_session, monkeypatch):
    from app.services import multidl_service
    def fake_extract(url):
        return {"title": "Cool clip", "thumbnail": "https://cdn/t.jpg", "duration": 12, "extractor_key": "TikTok"}
    monkeypatch.setattr(multidl_service, "_extract_info_sync", fake_extract)
    info = await multidl_service.get_info("https://www.tiktok.com/@u/video/1")
    assert info.title == "Cool clip"
    assert info.platform == "TikTok"
    assert info.duration == 12
