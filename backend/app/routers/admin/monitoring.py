import os
import time
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import require_admin, require_superadmin
from app.models.audit import ActiveSession, AuditLog
from app.models.user import User
from app.routers.admin._filesystem import (
    _count_files,
    _dir_size_mb,
    _dir_size_mb_excluding,
)
from app.schemas.admin import AdminStats, StorageInfo, SystemInfo, TopUser
from app.utils.system_info import get_tool_versions

# Application start time, captured when this module is imported during app
# startup. Uptime reported in /admin/system is the *service* uptime (since the
# backend process started), NOT the OS boot time — psutil.boot_time() showed
# machine uptime, which is wrong/misleading after an app restart.
_APP_START = time.time()

router = APIRouter()


@router.get("/stats", response_model=AdminStats)
async def get_stats(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = (
        await db.execute(select(func.count(User.id)).where(User.is_deleted.is_(False)))
    ).scalar() or 0
    active_users = (
        await db.execute(
            select(func.count(User.id)).where(
                User.is_active.is_(True), User.is_deleted.is_(False)
            )
        )
    ).scalar() or 0
    deleted_users = (
        await db.execute(select(func.count(User.id)).where(User.is_deleted.is_(True)))
    ).scalar() or 0

    users = (
        await db.execute(select(User).where(User.is_deleted.is_(False)))
    ).scalars().all()

    def _yt(u: User) -> int:
        return int(u.usage_today.get("youtube", 0)) if u.usage_today else 0

    def _cv(u: User) -> int:
        return int(u.usage_today.get("converter", 0)) if u.usage_today else 0

    def _im(u: User) -> int:
        return int(u.usage_today.get("image", 0)) if u.usage_today else 0

    dl = sum(_yt(u) for u in users)
    cv = sum(_cv(u) for u in users)
    im = sum(_im(u) for u in users)

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    active_sess = (
        await db.execute(
            select(func.count(ActiveSession.id)).where(
                ActiveSession.expires_at > now_naive
            )
        )
    ).scalar() or 0

    storage_mb = _dir_size_mb(settings.UPLOAD_DIR) + _dir_size_mb(settings.DATA_DIR)

    def _total(u: User) -> int:
        return _yt(u) + _cv(u) + _im(u)

    top_sorted = sorted(users, key=_total, reverse=True)[:5]
    top_users = [
        TopUser(
            user_id=u.id,
            username=u.username,
            avatar_version=u.avatar_version,
            total_today=_total(u),
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


@router.get(
    "/system",
    response_model=SystemInfo,
    dependencies=[Depends(require_superadmin)],
)
async def get_system_info():
    cpu = await run_in_threadpool(psutil.cpu_percent, 0.2)
    vm = psutil.virtual_memory()
    # Report disk usage for the data partition; fall back to root if DATA_DIR
    # doesn't exist yet (e.g. on first boot before lifespan creates it).
    disk_path = settings.DATA_DIR if os.path.isdir(settings.DATA_DIR) else "/"
    disk = psutil.disk_usage(disk_path)
    versions = get_tool_versions()
    return SystemInfo(
        cpu_percent=cpu,
        ram_used_mb=round(vm.used / (1024 * 1024), 1),
        ram_total_mb=round(vm.total / (1024 * 1024), 1),
        disk_used_gb=round(disk.used / (1024 ** 3), 2),
        disk_total_gb=round(disk.total / (1024 ** 3), 2),
        uptime_seconds=int(time.time() - _APP_START),
        python_version=versions.get("python_version", "недоступно"),
        ffmpeg_version=versions.get("ffmpeg_version", "недоступно"),
        yt_dlp_version=versions.get("yt_dlp_version", "недоступно"),
    )


@router.get(
    "/storage",
    response_model=StorageInfo,
    dependencies=[Depends(require_superadmin)],
)
async def get_storage_info():
    # AVATARS_DIR may be nested inside DATA_DIR (default layout) — report
    # disjoint sizes/counts so a UI summing them doesn't double-count avatars.
    return StorageInfo(
        data_size_mb=_dir_size_mb_excluding(settings.DATA_DIR, settings.AVATARS_DIR),
        uploads_size_mb=_dir_size_mb(settings.UPLOAD_DIR),
        avatars_size_mb=_dir_size_mb(settings.AVATARS_DIR),
        total_files=(
            _count_files(settings.DATA_DIR, exclude=settings.AVATARS_DIR)
            + _count_files(settings.UPLOAD_DIR)
        ),
    )
