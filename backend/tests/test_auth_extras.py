"""Tests for is_deleted, kicked_at and require_superadmin (Phase 5, Task 2).

The repo's test infrastructure (see tests/conftest.py) only exposes a
`db_session` fixture and uses an in-memory SQLite DB. There is no
TestClient/httpx setup, so these tests call the auth router and
dependency functions directly.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password
from app.dependencies import get_current_user, require_admin, require_superadmin
from app.models.audit import ActiveSession
from app.models.user import User
from app.routers.auth import login as auth_login, refresh as auth_refresh
from app.schemas.auth import LoginRequest, RefreshRequest


def _make_request() -> Request:
    """Minimal ASGI Request acceptable to log_audit."""
    scope = {
        "type": "http",
        "headers": [(b"user-agent", b"pytest")],
        "client": ("127.0.0.1", 0),
    }
    return Request(scope)


async def _make_user(
    db,
    *,
    username: str = "user1",
    password: str = "Password1",
    role: str = "user",
    is_active: bool = True,
    is_deleted: bool = False,
    kicked_at: datetime | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        is_deleted=is_deleted,
        kicked_at=kicked_at,
        must_change_password=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_login_deleted_user_returns_invalid_credentials(db_session):
    """Login for a soft-deleted user must NOT reveal deletion."""
    await _make_user(db_session, username="del1", password="Password1", is_deleted=True)

    body = LoginRequest(username="del1", password="Password1")
    request = _make_request()

    with pytest.raises(HTTPException) as exc_info:
        await auth_login(body, request, db_session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Неверный логин или пароль"


@pytest.mark.asyncio
async def test_get_current_user_rejects_deleted_user(db_session):
    """A valid token whose user has is_deleted=True must yield 401."""
    user = await _make_user(db_session, username="del2", password="Password1")

    token = create_access_token({"sub": str(user.id), "role": user.role})

    # Now soft-delete the user.
    user.is_deleted = True
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_bearer(token), db_session)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_kicked_at_invalidates_old_tokens(db_session):
    """Tokens with iat < kicked_at must be rejected by get_current_user."""
    user = await _make_user(db_session, username="kicked1", password="Password1")

    token = create_access_token({"sub": str(user.id), "role": user.role})

    # Kick happens 5 s after the token was issued — old token must be rejected.
    user.kicked_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_bearer(token), db_session)

    assert exc_info.value.status_code == 401
    assert "Сессия завершена администратором" in exc_info.value.detail


@pytest.mark.asyncio
async def test_kicked_at_allows_fresh_tokens(db_session):
    """A token issued AFTER kicked_at must still pass."""
    user = await _make_user(db_session, username="kicked2", password="Password1")

    # Kick happened in the past.
    user.kicked_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    await db_session.commit()

    # Token issued now (after kicked_at) is valid.
    token = create_access_token({"sub": str(user.id), "role": user.role})

    result = await get_current_user(_bearer(token), db_session)
    assert result.id == user.id


@pytest.mark.asyncio
async def test_require_superadmin_blocks_user_role():
    fake = SimpleNamespace(role="user")
    with pytest.raises(HTTPException) as exc_info:
        await require_superadmin(fake)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_superadmin_blocks_admin_role():
    fake = SimpleNamespace(role="admin")
    with pytest.raises(HTTPException) as exc_info:
        await require_superadmin(fake)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_superadmin_allows_superadmin_role():
    fake = SimpleNamespace(role="superadmin")
    result = await require_superadmin(fake)
    assert result is fake


@pytest.mark.asyncio
async def test_require_admin_blocks_plain_user():
    fake = SimpleNamespace(role="user")
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(fake)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_kicked_at_works_with_naive_datetime_from_db(db_session):
    """Regression: SQLite returns naive datetimes; comparison must still work."""
    user = await _make_user(db_session, username="kicked_naive", password="Password1")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    user.kicked_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    await db_session.commit()
    db_session.expunge_all()  # force fresh SELECT, returns naive datetime

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(_bearer(token), db_session)
    assert exc_info.value.status_code == 401
    assert "Сессия завершена администратором" in exc_info.value.detail


@pytest.mark.asyncio
async def test_refresh_blocks_deleted_user(db_session):
    """Regression: /auth/refresh must enforce is_deleted (not just is_active)."""
    user = await _make_user(db_session, username="del_refresh", password="Password1")
    refresh_token = create_refresh_token({"sub": str(user.id), "role": user.role})
    payload = decode_token(refresh_token)
    sess = ActiveSession(
        user_id=user.id,
        token_jti=payload["jti"],
        ip_address="",
        user_agent="",
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )
    db_session.add(sess)
    user.is_deleted = True
    await db_session.commit()

    request = _make_request()

    with pytest.raises(HTTPException) as exc_info:
        await auth_refresh(RefreshRequest(refresh_token=refresh_token), request, db_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_response_preserves_avatar_version(db_session):
    """GET /auth/me must serialize avatar_version (and other Phase 5 fields).
    The 15s frontend polling does setUser(/auth/me-response). If those fields
    are stripped by the response_model schema, AvatarImage falls back to the
    default icon ~15s after upload — user.avatar_version becomes undefined
    → 0 → cache-busted URL becomes null → blob is revoked.
    """
    from app.routers.auth import me as auth_me
    from app.schemas.me import UserMeResponse

    user = User(
        username="me_avatar",
        password_hash=hash_password("Password1"),
        role="user",
        is_active=True,
        must_change_password=False,
        avatar_version=7,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await auth_me(user=user)
    # Apply the response_model the route declares — that's what the HTTP
    # layer serializes and sends to the client.
    serialized = UserMeResponse.model_validate(result)

    assert serialized.avatar_version == 7
    assert serialized.id == user.id
    assert serialized.username == "me_avatar"
