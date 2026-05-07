from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import require_admin
from app.models.audit import ActiveSession
from app.models.user import User
from app.schemas.admin import AdminSessionItem
from app.schemas.auth import MessageResponse
from app.utils import audit_actions
from app.utils.audit import log_audit

router = APIRouter()


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
