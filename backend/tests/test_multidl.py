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


from starlette.requests import Request


def _make_request() -> Request:
    scope = {"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)}
    return Request(scope)


class _BG:
    def add_task(self, *a, **k):
        pass


@pytest.mark.asyncio
async def test_router_permission_gate(db_session):
    from app.routers.multidl import start_download
    from app.schemas.multidl import DownloadRequest
    from fastapi import HTTPException
    user = await _make_user(db_session, username="noperm", perms={"multidl": False})
    with pytest.raises(HTTPException) as exc:
        await start_download(body=DownloadRequest(url="https://vk.com/video-1_1"),
                             background_tasks=_BG(), user=user, db=db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_router_start_increments_usage(db_session):
    from app.routers.multidl import start_download
    from app.schemas.multidl import DownloadRequest
    user = await _make_user(db_session, username="ok")
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
    with pytest.raises(HTTPException) as exc:
        await start_download(body=DownloadRequest(url="https://vk.com/video-1_1"),
                             background_tasks=_BG(), user=user, db=db_session)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_router_no_youtube_cache_collision(db_session):
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
    assert user.usage_today.get("youtube") == 1
    assert user.usage_today.get("multidl") == 0


def test_integration_user_defaults_include_multidl():
    from app.models.user import User
    perms = User.permissions.default.arg(None)
    limits = User.limits.default.arg(None)
    usage = User.usage_today.default.arg(None)
    assert perms.get("multidl") is True
    assert limits.get("multidl_daily") == 50
    assert "multidl" in usage


@pytest.mark.asyncio
async def test_monitoring_counts_multidl(db_session):
    from app.routers.admin.monitoring import get_stats
    admin = await _make_user(db_session, username="adm_md", role="superadmin")
    admin.usage_today = {"youtube": 0, "converter": 0, "image": 0, "multidl": 4}
    await db_session.commit()
    stats = await get_stats(actor=admin, db=db_session)
    assert stats.total_multidl_ops_today == 4
