from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import generate_random_password, hash_password
from app.dependencies import require_admin, require_superadmin
from app.models.audit import ActiveSession
from app.models.user import User
from app.routers.admin._shared import _can_admin_modify, _diff_changes, _is_visible
from app.schemas.admin import (
    CreateUserRequest,
    CreateUserResponse,
    ResetPasswordResponse,
    ToggleActiveResponse,
    UpdateUserRequest,
    UserDetailResponse,
    UserListItemAdmin,
    UserListResponse,
)
from app.schemas.auth import MessageResponse
from app.utils import audit_actions
from app.utils.audit import log_audit

router = APIRouter()


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
    actor: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    # Defense-in-depth alongside the require_superadmin dependency: only a
    # superadmin may create accounts.
    if actor.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только суперадмин может создавать пользователей",
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
        permissions=body.permissions or {"youtube": True, "converter": True, "image": True, "multidl": True},
        # Only superadmin reaches this endpoint; they may set limits for the new
        # account (relevant for regular users — admins/superadmins are unlimited).
        limits=body.limits or {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50, "multidl_daily": 50},
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

    # Limits are editable only by a superadmin, and only for regular users.
    # (Admins/superadmins are unlimited, so their limits are meaningless.)
    can_edit_limits = actor.role == "superadmin" and target.role == "user"
    changes = _diff_changes(target, body, include_limits=can_edit_limits)

    if body.role is not None:
        target.role = body.role
    if body.permissions is not None:
        target.permissions = body.permissions
    if can_edit_limits and body.limits is not None:
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
