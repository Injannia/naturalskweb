from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt

from app.core.database import get_db
from app.core.security import decode_token
from app.core import token_blacklist
from app.models.user import User

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен истёк")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный тип токена")

    jti = payload.get("jti")
    if jti and token_blacklist.contains(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен отозван")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

    result = await db.execute(select(User).where(User.id == int(user_id)))
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
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия завершена администратором")

    return user


async def get_current_session_jti(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str | None:
    """Return the `sid` claim of the access token = the ActiveSession.token_jti
    of the session that issued this request. Lets endpoints identify *which*
    of the user's sessions is the current one instead of guessing by recency.

    Legacy access tokens (issued before `sid` existed) lack the claim and yield
    None; callers fall back to a best-effort heuristic in that case.
    """
    try:
        payload = decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        return None
    return payload.get("sid")


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права администратора")
    return user


async def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права суперадминистратора")
    return user
