import csv
import io
import json
import os
import time
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import generate_random_password, hash_password
from app.dependencies import get_current_user, require_admin, require_superadmin
from app.models.audit import ActiveSession, AuditLog
from app.models.user import User
from app.schemas.admin import (
    AdminSessionItem,
    AdminStats,
    AuditLogItem,
    AuditLogListResponse,
    CreateUserRequest,
    CreateUserResponse,
    ResetPasswordResponse,
    StorageInfo,
    SystemInfo,
    ToggleActiveResponse,
    TopUser,
    UpdateUserRequest,
    UserDetailResponse,
    UserListItemAdmin,
    UserListResponse,
)
from app.schemas.auth import MessageResponse
from app.utils import audit_actions
from app.utils.audit import log_audit
from app.utils.system_info import get_tool_versions

_BOOT_TIME = psutil.boot_time()


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


def _prune_excluded(root: str, dirs: list[str], exclude_abs: str | None) -> None:
    """Drop subdirectories that match the excluded absolute path so os.walk skips them."""
    if not exclude_abs:
        return
    dirs[:] = [d for d in dirs if os.path.abspath(os.path.join(root, d)) != exclude_abs]


def _count_files(path: str, exclude: str | None = None) -> int:
    if not os.path.isdir(path):
        return 0
    exclude_abs = os.path.abspath(exclude) if exclude else None
    path_abs = os.path.abspath(path)
    n = 0
    for root, dirs, files in os.walk(path_abs):
        _prune_excluded(root, dirs, exclude_abs)
        n += len(files)
    return n


def _dir_size_mb_excluding(path: str, exclude: str | None) -> float:
    """Like _dir_size_mb but skips the `exclude` subtree (resolved absolute)."""
    if not os.path.isdir(path):
        return 0.0
    exclude_abs = os.path.abspath(exclude) if exclude else None
    path_abs = os.path.abspath(path)
    total = 0
    for root, dirs, files in os.walk(path_abs):
        _prune_excluded(root, dirs, exclude_abs)
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _is_visible(actor: User, target: User) -> bool:
    """Soft-deleted users are visible only to superadmin."""
    if not target.is_deleted:
        return True
    return actor.role == "superadmin"


def _can_admin_modify(actor: User, target: User) -> bool:
    """Return True iff `actor` is allowed to PATCH/operate on `target`.

    Rules:
      - superadmin: can modify anyone (including themselves elsewhere is checked separately).
      - admin: cannot modify superadmin, cannot modify themselves.
      - any other role: cannot modify anyone.
    """
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
        changes["permissions"] = [dict(target.permissions), dict(body.permissions)]
    if body.limits is not None and body.limits != target.limits:
        changes["limits"] = [dict(target.limits), dict(body.limits)]
    if body.is_active is not None and body.is_active != target.is_active:
        changes["is_active"] = [target.is_active, body.is_active]
    return changes


@router.get("/users", response_model=UserListResponse)
async def list_users(
    offset: int = 0,
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    role: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    include_deleted: bool = False,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    show_deleted = include_deleted or status_filter == "deleted"
    if show_deleted and actor.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только superadmin")

    stmt = select(User)
    count_stmt = select(func.count(User.id))

    if search:
        like = f"%{search}%"
        stmt = stmt.where(User.username.ilike(like))
        count_stmt = count_stmt.where(User.username.ilike(like))

    if role:
        stmt = stmt.where(User.role == role)
        count_stmt = count_stmt.where(User.role == role)

    if status_filter == "active":
        stmt = stmt.where(User.is_active.is_(True), User.is_deleted.is_(False))
        count_stmt = count_stmt.where(User.is_active.is_(True), User.is_deleted.is_(False))
    elif status_filter == "inactive":
        stmt = stmt.where(User.is_active.is_(False), User.is_deleted.is_(False))
        count_stmt = count_stmt.where(User.is_active.is_(False), User.is_deleted.is_(False))
    elif status_filter == "deleted":
        stmt = stmt.where(User.is_deleted.is_(True))
        count_stmt = count_stmt.where(User.is_deleted.is_(True))
    elif not include_deleted:
        stmt = stmt.where(User.is_deleted.is_(False))
        count_stmt = count_stmt.where(User.is_deleted.is_(False))

    stmt = stmt.order_by(User.id).offset(offset).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar() or 0

    return UserListResponse(
        items=[UserListItemAdmin.model_validate(u) for u in items],
        total=total,
    )


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: int,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not _is_visible(actor, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return user


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if actor.role == "admin" and body.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin может создавать только пользователей с ролью user",
        )

    existing = (
        await db.execute(select(User).where(User.username == body.username))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким именем уже существует",
        )

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
        db,
        actor.id,
        audit_actions.USER_CREATED,
        request,
        {
            "target_user_id": user.id,
            "target_username": user.username,
            "role": user.role,
            "permissions": user.permissions,
            "limits": user.limits,
        },
    )

    await db.commit()
    await db.refresh(user)

    return CreateUserResponse(
        id=user.id,
        username=user.username,
        password=password,
        role=user.role,
    )


@router.patch("/users/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target or not _is_visible(actor, target):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    if not _can_admin_modify(actor, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    if actor.role == "admin" and body.role is not None and body.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin может назначать только роль user",
        )

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
            db,
            actor.id,
            audit_actions.USER_UPDATED,
            request,
            {
                "target_user_id": target.id,
                "target_username": target.username,
                "changes": changes,
            },
        )

    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    request: Request,
    actor: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя удалить себя")

    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if target.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь уже удалён",
        )

    target.is_deleted = True
    target.kicked_at = datetime.now(timezone.utc)

    sessions = (
        await db.execute(select(ActiveSession).where(ActiveSession.user_id == target.id))
    ).scalars().all()
    for s in sessions:
        await db.delete(s)

    await log_audit(
        db,
        actor.id,
        audit_actions.USER_DELETED,
        request,
        {"target_user_id": target.id, "target_username": target.username},
    )

    await db.commit()
    return MessageResponse(message="Пользователь удалён")


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    user_id: int,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target or not _is_visible(actor, target):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    if not _can_admin_modify(actor, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    new_password = generate_random_password()
    target.password_hash = hash_password(new_password)
    target.must_change_password = True
    target.kicked_at = datetime.now(timezone.utc)

    sessions = (
        await db.execute(select(ActiveSession).where(ActiveSession.user_id == target.id))
    ).scalars().all()
    for s in sessions:
        await db.delete(s)

    await log_audit(
        db,
        actor.id,
        audit_actions.USER_PASSWORD_RESET,
        request,
        {"target_user_id": target.id, "target_username": target.username},
    )

    await db.commit()

    return ResetPasswordResponse(
        id=target.id,
        username=target.username,
        password=new_password,
    )


@router.post("/users/{user_id}/toggle-active", response_model=ToggleActiveResponse)
async def toggle_active(
    user_id: int,
    request: Request,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target or not _is_visible(actor, target):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    # Self-deactivation is forbidden for everyone, including superadmin (lock-out risk).
    if target.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя деактивировать самого себя",
        )

    if actor.role == "admin" and target.role == "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin не может менять активность superadmin",
        )

    target.is_active = not target.is_active

    await log_audit(
        db,
        actor.id,
        audit_actions.USER_TOGGLED_ACTIVE,
        request,
        {
            "target_user_id": target.id,
            "target_username": target.username,
            "new_state": target.is_active,
        },
    )

    await db.commit()
    await db.refresh(target)

    return ToggleActiveResponse(id=target.id, is_active=target.is_active)


@router.get("/sessions", response_model=list[AdminSessionItem])
async def list_all_sessions(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(ActiveSession, User.username)
            .join(User, User.id == ActiveSession.user_id)
            .order_by(ActiveSession.created_at.desc())
        )
    ).all()
    return [
        AdminSessionItem(
            id=s.id,
            user_id=s.user_id,
            username=username,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            created_at=s.created_at,
            expires_at=s.expires_at,
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
    session = (
        await db.execute(select(ActiveSession).where(ActiveSession.id == session_id))
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сессия не найдена")

    # ON DELETE CASCADE on ActiveSession.user_id guarantees a session always
    # has a live owner — orphans are impossible at the schema level.
    target = (
        await db.execute(select(User).where(User.id == session.user_id))
    ).scalar_one()

    if actor.role == "admin" and target.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    target_user_id = target.id
    target_username = target.username

    await db.delete(session)
    target.kicked_at = datetime.now(timezone.utc)

    await log_audit(
        db,
        actor.id,
        audit_actions.SESSION_KILLED_BY_ADMIN,
        request,
        {
            "target_user_id": target_user_id,
            "target_username": target_username,
            "session_id": session_id,
        },
    )

    await db.commit()
    return MessageResponse(message="Сессия завершена")


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
        uptime_seconds=int(time.time() - _BOOT_TIME),
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


def _apply_audit_filter(stmt, *, user_id, action, date_from, date_to):
    """Apply audit-log filters to a select() statement (used by both endpoints)."""
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return stmt


@router.get(
    "/audit-log",
    response_model=AuditLogListResponse,
    dependencies=[Depends(require_admin)],
)
async def get_audit_log(
    user_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    offset: int = 0,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    base = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.user_id)
    )
    base = _apply_audit_filter(
        base, user_id=user_id, action=action, date_from=date_from, date_to=date_to
    )
    base = (
        base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(base)).all()

    cnt = select(func.count(AuditLog.id))
    cnt = _apply_audit_filter(
        cnt, user_id=user_id, action=action, date_from=date_from, date_to=date_to
    )
    total = (await db.execute(cnt)).scalar() or 0

    items = [
        AuditLogItem(
            id=log.id,
            user_id=log.user_id,
            username=username,
            action=log.action,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for (log, username) in rows
    ]
    return AuditLogListResponse(items=items, total=total)


@router.get(
    "/audit-log/export.csv",
    dependencies=[Depends(require_admin)],
)
async def export_audit_log(
    user_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
):
    base = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.user_id)
    )
    base = _apply_audit_filter(
        base, user_id=user_id, action=action, date_from=date_from, date_to=date_to
    )
    base = base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    rows = (await db.execute(base)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "created_at", "user_id", "username", "action", "ip_address", "details"]
    )
    for (log, username) in rows:
        details_cell = (
            json.dumps(log.details, ensure_ascii=False)
            if log.details is not None
            else ""
        )
        writer.writerow(
            [
                log.id,
                log.created_at.isoformat() if log.created_at else "",
                log.user_id if log.user_id is not None else "",
                username or "",
                log.action,
                log.ip_address or "",
                details_cell,
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )
