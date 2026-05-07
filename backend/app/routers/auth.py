import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core import token_blacklist
from app.dependencies import get_current_user
from app.models.user import User
from app.models.audit import ActiveSession
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    ChangePasswordRequest,
    UserResponse,
    MessageResponse,
)
from app.utils.audit import log_audit
from app.utils import audit_actions

router = APIRouter(prefix="/api/auth", tags=["auth"])

security_scheme = HTTPBearer()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user:
        await log_audit(db, None, audit_actions.LOGIN_FAILED, request, {"reason": "user_not_found", "username": body.username})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")

    if user.is_deleted:
        await log_audit(db, user.id, audit_actions.LOGIN_FAILED, request, {"reason": "deleted"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")

    if not user.is_active:
        await log_audit(db, user.id, audit_actions.LOGIN_FAILED, request, {"reason": "inactive"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Аккаунт отключён")

    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds())
        await log_audit(db, user.id, audit_actions.LOGIN_FAILED, request, {"reason": "locked"})
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Аккаунт заблокирован. Попробуйте через {remaining} секунд.",
        )

    if not verify_password(body.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            await log_audit(db, user.id, audit_actions.ACCOUNT_LOCKED, request)
        else:
            await log_audit(db, user.id, audit_actions.LOGIN_FAILED, request, {"reason": "wrong_password"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = now

    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    refresh_token = create_refresh_token({"sub": str(user.id), "role": user.role})

    refresh_payload = decode_token(refresh_token)
    ip_address = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")[:256]

    # Deduplicate: a user logging in repeatedly from the same browser would
    # otherwise pile up identical-looking session rows. Drop any existing
    # session with the same (user_id, ip, user_agent) before creating a new one.
    existing_dupes = (
        await db.execute(
            select(ActiveSession).where(
                ActiveSession.user_id == user.id,
                ActiveSession.ip_address == ip_address,
                ActiveSession.user_agent == user_agent,
            )
        )
    ).scalars().all()
    for dup in existing_dupes:
        await db.delete(dup)

    session = ActiveSession(
        user_id=user.id,
        token_jti=refresh_payload["jti"],
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc),
    )
    db.add(session)

    await log_audit(db, user.id, audit_actions.LOGIN, request)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен обновления")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный тип токена")

    jti = payload.get("jti")
    result = await db.execute(select(ActiveSession).where(ActiveSession.token_jti == jti))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия не найдена или отозвана")

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or user.is_deleted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден или отключён")

    if user.kicked_at:
        iat = payload.get("iat", 0)
        kicked_at = user.kicked_at
        if kicked_at.tzinfo is None:
            kicked_at = kicked_at.replace(tzinfo=timezone.utc)
        token_iat = datetime.fromtimestamp(iat, tz=timezone.utc)
        if token_iat < kicked_at:
            await db.delete(session)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия завершена администратором")

    await db.delete(session)

    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    new_refresh_token = create_refresh_token({"sub": str(user.id), "role": user.role})

    new_payload = decode_token(new_refresh_token)
    new_session = ActiveSession(
        user_id=user.id,
        token_jti=new_payload["jti"],
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")[:256],
        expires_at=datetime.fromtimestamp(new_payload["exp"], tz=timezone.utc),
    )
    db.add(new_session)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        must_change_password=user.must_change_password,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    body: RefreshRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Blacklist the current access token so it cannot be reused after logout
    try:
        access_payload = decode_token(credentials.credentials)
        access_jti = access_payload.get("jti")
        access_exp = access_payload.get("exp", 0)
        if access_jti:
            token_blacklist.add(access_jti, float(access_exp))
    except Exception:
        pass

    # Revoke the refresh token session
    try:
        payload = decode_token(body.refresh_token)
        jti = payload.get("jti")
        if jti:
            result = await db.execute(select(ActiveSession).where(ActiveSession.token_jti == jti))
            session = result.scalar_one_or_none()
            if session:
                await db.delete(session)
    except Exception:
        pass

    await log_audit(db, user.id, audit_actions.LOGOUT, request)
    return MessageResponse(message="Вы вышли из системы")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текущий пароль неверен")

    if not re.search(r"[a-zA-Z]", body.new_password) or not re.search(r"\d", body.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пароль должен содержать хотя бы одну букву и одну цифру",
        )

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False

    await log_audit(db, user.id, audit_actions.CHANGE_PASSWORD, request)
    return MessageResponse(message="Пароль успешно изменён")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user
