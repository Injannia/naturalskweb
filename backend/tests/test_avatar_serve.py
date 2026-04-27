"""Tests for GET /api/users/{id}/avatar (Phase 5, Task 3).

The repo's test infrastructure exposes only a `db_session` fixture and runs
in-memory SQLite. There is no TestClient/httpx setup, so these tests call the
router endpoint function directly and bypass the auth dependency.
"""
import io
import os

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User
from app.routers.users import get_user_avatar


async def _make_user(
    db,
    *,
    username: str,
    avatar_path: str | None = None,
    avatar_version: int = 0,
    is_deleted: bool = False,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password("Password1"),
        role="user",
        is_active=True,
        is_deleted=is_deleted,
        must_change_password=False,
        avatar_path=avatar_path,
        avatar_version=avatar_version,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _write_webp(user_id: int) -> str:
    """Create a tiny real WebP file at AVATARS_DIR/{user_id}.webp and return path."""
    os.makedirs(settings.AVATARS_DIR, exist_ok=True)
    path = os.path.join(settings.AVATARS_DIR, f"{user_id}.webp")
    img = Image.new("RGB", (4, 4), color=(0, 128, 200))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


@pytest.mark.asyncio
async def test_avatar_404_when_user_has_no_avatar_path(db_session):
    user = await _make_user(db_session, username="noavatar", avatar_path=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_user_avatar(user.id, db_session, _=user)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_avatar_404_when_file_missing(db_session):
    user = await _make_user(db_session, username="missfile", avatar_path="placeholder")
    # Make sure no file is on disk for this user.
    abs_path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    if os.path.exists(abs_path):
        os.remove(abs_path)

    # avatar_path on the model is set, but file does not exist on disk.
    user.avatar_path = f"avatars/{user.id}.webp"
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_user_avatar(user.id, db_session, _=user)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_avatar_200_when_file_exists(db_session):
    user = await _make_user(db_session, username="hasavatar")
    user.avatar_path = f"avatars/{user.id}.webp"
    user.avatar_version = 1
    await db_session.commit()

    file_path = _write_webp(user.id)
    try:
        response = await get_user_avatar(user.id, db_session, _=user)
        assert isinstance(response, FileResponse)
        assert response.media_type == "image/webp"
        assert response.path == file_path
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@pytest.mark.asyncio
async def test_avatar_404_for_deleted_user(db_session):
    """A soft-deleted user's avatar must NOT be served, even if the file exists."""
    target = await _make_user(db_session, username="deleted_target")
    target.avatar_path = f"avatars/{target.id}.webp"
    target.avatar_version = 1
    target.is_deleted = True
    await db_session.commit()

    file_path = _write_webp(target.id)

    # The caller is a different, non-deleted user.
    caller = await _make_user(db_session, username="caller")

    try:
        with pytest.raises(HTTPException) as exc_info:
            await get_user_avatar(target.id, db_session, _=caller)
        assert exc_info.value.status_code == 404
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
