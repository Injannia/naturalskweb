from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.audit import ActiveSession
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.me import (
    MySessionItem,
    UpdateMeRequest,
    UserMeResponse,
)
from app.utils import audit_actions
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=UserMeResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("", response_model=UserMeResponse)
async def update_me(
    body: UpdateMeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.username == user.username:
        return user

    result = await db.execute(
        select(User).where(User.username == body.username, User.id != user.id)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Имя занято")

    old_username = user.username
    user.username = body.username

    await log_audit(
        db,
        user.id,
        audit_actions.USERNAME_CHANGED,
        request,
        {"old_username": old_username, "new_username": body.username},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/sessions", response_model=list[MySessionItem])
async def list_my_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's own active sessions.

    The most recent session by `created_at` is marked `is_current=True`.
    The remaining are `is_current=False`.
    """
    result = await db.execute(
        select(ActiveSession)
        .where(ActiveSession.user_id == user.id)
        .order_by(ActiveSession.created_at.desc())
    )
    sessions = list(result.scalars().all())

    items: list[MySessionItem] = []
    for index, session in enumerate(sessions):
        items.append(
            MySessionItem(
                id=session.id,
                ip_address=session.ip_address,
                user_agent=session.user_agent,
                created_at=session.created_at,
                expires_at=session.expires_at,
                is_current=(index == 0),
            )
        )
    return items


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def delete_my_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActiveSession).where(
            ActiveSession.id == session_id,
            ActiveSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    await db.delete(session)
    await db.commit()
    return MessageResponse(message="Сессия завершена")


@router.delete("/sessions", response_model=MessageResponse)
async def delete_all_my_sessions_except_current(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all of the user's sessions except the most recent one (current)."""
    result = await db.execute(
        select(ActiveSession)
        .where(ActiveSession.user_id == user.id)
        .order_by(ActiveSession.created_at.desc())
    )
    sessions = list(result.scalars().all())
    if len(sessions) <= 1:
        return MessageResponse(message="Других сессий нет")

    for session in sessions[1:]:
        await db.delete(session)
    await db.commit()
    return MessageResponse(message="Остальные сессии завершены")
