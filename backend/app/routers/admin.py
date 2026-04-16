from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, generate_random_password
from app.dependencies import require_admin
from app.models.user import User
from app.models.audit import AuditLog

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    role: str = Field(default="user", pattern=r"^(user|admin)$")
    permissions: dict | None = None
    limits: dict | None = None


class CreateUserResponse(BaseModel):
    id: int
    username: str
    password: str
    role: str


class UserListItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    last_login: datetime | None
    usage_today: dict

    model_config = {"from_attributes": True}


@router.get("/users", response_model=list[UserListItem])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(body: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с таким именем уже существует")

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

    return CreateUserResponse(id=user.id, username=user.username, password=password, role=user.role)


@router.patch("/users/{user_id}/toggle")
async def toggle_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Нельзя отключить суперадмина")
    user.is_active = not user.is_active
    return {"id": user.id, "is_active": user.is_active}


@router.get("/audit-logs")
async def get_audit_logs(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "user_id": l.user_id,
            "action": l.action,
            "details": l.details,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_users = await db.execute(select(func.count(User.id)))
    active_users = await db.execute(select(func.count(User.id)).where(User.is_active == True))
    total_logs = await db.execute(select(func.count(AuditLog.id)))

    return {
        "total_users": total_users.scalar(),
        "active_users": active_users.scalar(),
        "total_audit_logs": total_logs.scalar(),
    }
