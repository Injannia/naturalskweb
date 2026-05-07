"""Tests for POST/DELETE /api/me/avatar (Phase 5, Task 5).

The repo's test infrastructure (see tests/conftest.py) only exposes a
`db_session` fixture and uses an in-memory SQLite DB. There is no
TestClient/httpx setup, so these tests call the router functions directly.
"""
import io
import os

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import select
from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.config import settings
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.user import User
from app.routers import me as me_router
from app.routers.me import delete_avatar, upload_avatar
from app.utils import audit_actions


def _make_request() -> Request:
    """Minimal ASGI Request acceptable to log_audit."""
    scope = {
        "type": "http",
        "headers": [(b"user-agent", b"pytest")],
        "client": ("127.0.0.1", 0),
    }
    return Request(scope)


async def _make_user(
    db,
    *,
    username: str = "user1",
    avatar_version: int = 0,
    avatar_path: str | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password("Password1"),
        role="user",
        is_active=True,
        must_change_password=False,
        avatar_version=avatar_version,
        avatar_path=avatar_path,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _png_bytes(size: tuple[int, int] = (300, 200), color=(10, 20, 30)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(size: tuple[int, int] = (100, 100)) -> bytes:
    img = Image.new("RGB", size, color=(255, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _webp_bytes(size: tuple[int, int] = (100, 100)) -> bytes:
    img = Image.new("RGB", size, color=(0, 200, 100))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


def _make_upload(
    data: bytes, *, filename: str = "avatar.png", content_type: str = "image/png"
) -> UploadFile:
    headers = Headers({"content-type": content_type})
    return UploadFile(filename=filename, file=io.BytesIO(data), headers=headers)


def _avatar_path_for(user_id: int) -> str:
    return os.path.join(settings.AVATARS_DIR, f"{user_id}.webp")


def _cleanup(user_id: int) -> None:
    p = _avatar_path_for(user_id)
    if os.path.exists(p):
        os.remove(p)


# ---------------------------------------------------------------------------
# POST /api/me/avatar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_avatar_png_success(db_session):
    user = await _make_user(db_session, username="png_uploader")
    request = _make_request()
    upload = _make_upload(_png_bytes((300, 200)), filename="a.png", content_type="image/png")

    try:
        result = await upload_avatar(
            file=upload, request=request, user=user, db=db_session
        )
        assert result.avatar_path == f"avatars/{user.id}.webp"
        assert result.avatar_version == 1

        # File exists, is a valid WebP, and is downsized to <= 256x256.
        path = _avatar_path_for(user.id)
        assert os.path.exists(path)
        with Image.open(path) as img:
            assert img.format == "WEBP"
            assert img.size[0] <= 256
            assert img.size[1] <= 256
            # Aspect ratio preserved (300x200 -> 256x171 approximately).
            assert img.size == (256, 170) or img.size == (256, 171)

        # User row was updated.
        fresh = (
            await db_session.execute(select(User).where(User.id == user.id))
        ).scalar_one()
        assert fresh.avatar_path == f"avatars/{user.id}.webp"
        assert fresh.avatar_version == 1
    finally:
        _cleanup(user.id)


@pytest.mark.asyncio
async def test_upload_avatar_jpeg_success(db_session):
    user = await _make_user(db_session, username="jpeg_uploader")
    request = _make_request()
    upload = _make_upload(
        _jpeg_bytes((50, 50)), filename="a.jpg", content_type="image/jpeg"
    )

    try:
        result = await upload_avatar(
            file=upload, request=request, user=user, db=db_session
        )
        assert result.avatar_path == f"avatars/{user.id}.webp"
        assert result.avatar_version == 1

        path = _avatar_path_for(user.id)
        with Image.open(path) as img:
            assert img.format == "WEBP"
    finally:
        _cleanup(user.id)


@pytest.mark.asyncio
async def test_upload_avatar_webp_success(db_session):
    user = await _make_user(db_session, username="webp_uploader")
    request = _make_request()
    upload = _make_upload(
        _webp_bytes((100, 100)), filename="a.webp", content_type="image/webp"
    )

    try:
        result = await upload_avatar(
            file=upload, request=request, user=user, db=db_session
        )
        assert result.avatar_path == f"avatars/{user.id}.webp"
        path = _avatar_path_for(user.id)
        assert os.path.exists(path)
    finally:
        _cleanup(user.id)


def _transparent_png_bytes() -> bytes:
    """Fully transparent RGBA PNG with default (0, 0, 0, 0) pixels."""
    img = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_avatar_transparent_png_renders_on_white(db_session):
    """A transparent PNG must be composited onto white, not flattened to black."""
    user = await _make_user(db_session, username="transparent_png")
    request = _make_request()
    upload = _make_upload(
        _transparent_png_bytes(), filename="t.png", content_type="image/png"
    )

    try:
        await upload_avatar(file=upload, request=request, user=user, db=db_session)

        path = _avatar_path_for(user.id)
        with Image.open(path) as img:
            sample = img.convert("RGB").getpixel((0, 0))
        assert sample == (255, 255, 255), f"expected white background, got {sample}"
    finally:
        _cleanup(user.id)


@pytest.mark.asyncio
async def test_upload_avatar_increments_version(db_session):
    user = await _make_user(db_session, username="version_bump", avatar_version=4)
    request = _make_request()
    upload = _make_upload(_png_bytes(), filename="a.png", content_type="image/png")

    try:
        result = await upload_avatar(
            file=upload, request=request, user=user, db=db_session
        )
        assert result.avatar_version == 5
    finally:
        _cleanup(user.id)


@pytest.mark.asyncio
async def test_upload_avatar_writes_audit_log(db_session):
    user = await _make_user(db_session, username="audit_up")
    request = _make_request()
    upload = _make_upload(_png_bytes(), filename="a.png", content_type="image/png")

    try:
        await upload_avatar(file=upload, request=request, user=user, db=db_session)

        log = (
            await db_session.execute(
                select(AuditLog)
                .where(
                    AuditLog.user_id == user.id,
                    AuditLog.action == audit_actions.AVATAR_UPDATED,
                )
                .order_by(AuditLog.id.desc())
            )
        ).scalars().first()
        assert log is not None
        assert log.action == "avatar_updated"
    finally:
        _cleanup(user.id)


@pytest.mark.asyncio
async def test_upload_avatar_text_plain_returns_400(db_session):
    user = await _make_user(db_session, username="text_plain")
    request = _make_request()
    upload = _make_upload(
        b"hello world", filename="note.txt", content_type="text/plain"
    )

    with pytest.raises(HTTPException) as exc_info:
        await upload_avatar(file=upload, request=request, user=user, db=db_session)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_avatar_invalid_image_bytes_returns_400(db_session):
    """Bytes that look like an image (by content-type) but aren't valid → 400."""
    user = await _make_user(db_session, username="fake_image")
    request = _make_request()
    upload = _make_upload(
        b"not an image at all, just some bytes",
        filename="evil.png",
        content_type="image/png",
    )

    with pytest.raises(HTTPException) as exc_info:
        await upload_avatar(file=upload, request=request, user=user, db=db_session)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_avatar_too_large_returns_413(db_session, monkeypatch):
    user = await _make_user(db_session, username="big_file")
    request = _make_request()

    # Lower the limit to make the test fast and deterministic.
    monkeypatch.setattr(me_router, "MAX_AVATAR_BYTES", 100)

    big = _png_bytes((50, 50))  # Tiny PNG, but still over 100 bytes.
    assert len(big) > 100
    upload = _make_upload(big, filename="big.png", content_type="image/png")

    with pytest.raises(HTTPException) as exc_info:
        await upload_avatar(file=upload, request=request, user=user, db=db_session)
    assert exc_info.value.status_code == 413


# ---------------------------------------------------------------------------
# DELETE /api/me/avatar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_avatar_removes_file_and_clears_path(db_session):
    user = await _make_user(
        db_session,
        username="delete_me",
        avatar_version=2,
        avatar_path=None,
    )
    # Pre-create avatar via upload, so file definitely exists.
    request = _make_request()
    upload = _make_upload(_png_bytes(), filename="a.png", content_type="image/png")
    await upload_avatar(file=upload, request=request, user=user, db=db_session)

    path = _avatar_path_for(user.id)
    assert os.path.exists(path)

    try:
        msg = await delete_avatar(request=request, user=user, db=db_session)
        assert msg.message

        # File gone, model fields cleared, version bumped again.
        assert not os.path.exists(path)
        fresh = (
            await db_session.execute(select(User).where(User.id == user.id))
        ).scalar_one()
        assert fresh.avatar_path is None
        # 2 (start) -> upload (3) -> delete (4)
        assert fresh.avatar_version == 4
    finally:
        _cleanup(user.id)


@pytest.mark.asyncio
async def test_delete_avatar_when_no_file_on_disk(db_session):
    """DELETE must succeed even when the avatar file is missing on disk."""
    user = await _make_user(
        db_session,
        username="no_file_delete",
        avatar_version=7,
        avatar_path=f"avatars/999.webp",
    )
    request = _make_request()
    # Make sure no file is on disk for this user.
    _cleanup(user.id)

    msg = await delete_avatar(request=request, user=user, db=db_session)
    assert msg.message

    fresh = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one()
    assert fresh.avatar_path is None
    assert fresh.avatar_version == 8


@pytest.mark.asyncio
async def test_delete_avatar_writes_audit_log(db_session):
    user = await _make_user(db_session, username="audit_del")
    request = _make_request()

    await delete_avatar(request=request, user=user, db=db_session)

    log = (
        await db_session.execute(
            select(AuditLog)
            .where(
                AuditLog.user_id == user.id,
                AuditLog.action == audit_actions.AVATAR_REMOVED,
            )
            .order_by(AuditLog.id.desc())
        )
    ).scalars().first()
    assert log is not None
    assert log.action == "avatar_removed"
