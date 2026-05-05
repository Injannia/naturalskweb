"""Tests for /api/admin/system and /api/admin/storage endpoints (Phase 5, Task 10).

Follows the project's pattern: only `db_session` fixture, router function
called directly. Role-gating is verified by calling `require_superadmin`
dependency directly.
"""
import os

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import hash_password
from app.dependencies import require_superadmin
from app.models.user import User
from app.routers.admin import get_storage_info, get_system_info
from app.schemas.admin import StorageInfo, SystemInfo


async def _make_user(
    db,
    *,
    username: str,
    role: str = "user",
) -> User:
    user = User(
        username=username,
        password_hash=hash_password("Password1"),
        role=role,
        is_active=True,
        must_change_password=False,
        is_deleted=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# /system role-gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_admin_forbidden(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    with pytest.raises(HTTPException) as exc:
        await require_superadmin(user=admin)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_system_user_forbidden(db_session):
    user = await _make_user(db_session, username="bob", role="user")
    with pytest.raises(HTTPException) as exc:
        await require_superadmin(user=user)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# /system positive: superadmin gets metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_superadmin_returns_metrics(db_session):
    await _make_user(db_session, username="root", role="superadmin")

    result = await get_system_info()

    assert isinstance(result, SystemInfo)
    assert result.ram_total_mb > 0
    assert result.ram_used_mb >= 0
    assert result.disk_total_gb > 0
    assert result.disk_used_gb >= 0
    assert result.uptime_seconds >= 0
    assert result.cpu_percent >= 0.0
    assert result.python_version  # non-empty
    assert isinstance(result.ffmpeg_version, str)
    assert isinstance(result.yt_dlp_version, str)


# ---------------------------------------------------------------------------
# /storage role-gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_admin_forbidden(db_session):
    admin = await _make_user(db_session, username="adm2", role="admin")
    with pytest.raises(HTTPException) as exc:
        await require_superadmin(user=admin)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# /storage positive: superadmin gets sizes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_superadmin_returns_sizes(db_session):
    await _make_user(db_session, username="root2", role="superadmin")

    result = await get_storage_info()

    assert isinstance(result, StorageInfo)
    assert isinstance(result.data_size_mb, float)
    assert isinstance(result.uploads_size_mb, float)
    assert isinstance(result.avatars_size_mb, float)
    assert isinstance(result.total_files, int)
    assert result.data_size_mb >= 0.0
    assert result.uploads_size_mb >= 0.0
    assert result.avatars_size_mb >= 0.0
    assert result.total_files >= 0


# ---------------------------------------------------------------------------
# total_files = files in DATA_DIR + UPLOAD_DIR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_total_files_counts_data_and_uploads(
    db_session, tmp_path, monkeypatch
):
    data_dir = tmp_path / "data"
    uploads_dir = tmp_path / "uploads"
    avatars_dir = tmp_path / "avatars"
    data_dir.mkdir()
    uploads_dir.mkdir()
    avatars_dir.mkdir()

    # 2 files in data
    (data_dir / "a.txt").write_text("a")
    (data_dir / "b.txt").write_text("b")
    # 3 files in uploads (one nested)
    (uploads_dir / "x.bin").write_bytes(b"x")
    (uploads_dir / "y.bin").write_bytes(b"y")
    nested = uploads_dir / "sub"
    nested.mkdir()
    (nested / "z.bin").write_bytes(b"z")
    # avatars must NOT count toward total_files
    (avatars_dir / "ava.png").write_bytes(b"ava")

    monkeypatch.setattr(settings, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(uploads_dir))
    monkeypatch.setattr(settings, "AVATARS_DIR", str(avatars_dir))

    result = await get_storage_info()

    assert result.total_files == 5
