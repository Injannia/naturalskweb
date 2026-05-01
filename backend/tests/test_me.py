"""Tests for /api/me endpoints (Phase 5, Task 4).

The repo's test infrastructure (see tests/conftest.py) only exposes a
`db_session` fixture and uses an in-memory SQLite DB. There is no
TestClient/httpx setup, so these tests call the router functions directly.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from starlette.requests import Request

from app.core.security import hash_password
from app.models.audit import ActiveSession, AuditLog
from app.models.user import User
from app.routers.me import (
    delete_all_my_sessions_except_current,
    delete_my_session,
    get_me,
    list_my_sessions,
    update_me,
)
from app.schemas.me import UpdateMeRequest
from app.utils import audit_actions


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
    avatar_version: int = 0,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        must_change_password=False,
        avatar_version=avatar_version,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_session(
    db,
    *,
    user_id: int,
    jti: str,
    created_at: datetime,
    ip: str = "1.2.3.4",
    ua: str = "ua",
) -> ActiveSession:
    session = ActiveSession(
        user_id=user_id,
        token_jti=jti,
        ip_address=ip,
        user_agent=ua,
        created_at=created_at,
        expires_at=created_at + timedelta(days=7),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


# ---------------------------------------------------------------------------
# GET /api/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_returns_extended_fields(db_session):
    user = await _make_user(db_session, username="alice")
    user.avatar_version = 3
    user.last_login = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(user)

    result = await get_me(user=user)
    # The endpoint returns the SQLAlchemy User; FastAPI normally serializes via
    # UserMeResponse. We assert the relevant attributes are accessible.
    assert result.id == user.id
    assert result.username == "alice"
    assert result.role == "user"
    assert result.is_active is True
    assert result.must_change_password is False
    assert isinstance(result.permissions, dict)
    assert isinstance(result.limits, dict)
    assert isinstance(result.usage_today, dict)
    assert result.usage_reset_date is not None
    assert result.avatar_version == 3
    assert result.created_at is not None
    assert result.last_login is not None


# ---------------------------------------------------------------------------
# PATCH /api/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_me_changes_username(db_session):
    user = await _make_user(db_session, username="oldname")
    request = _make_request()
    body = UpdateMeRequest(username="newname")

    result = await update_me(body=body, request=request, user=user, db=db_session)
    assert result.username == "newname"

    # Reload from DB to be sure it persisted.
    fresh = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one()
    assert fresh.username == "newname"


@pytest.mark.asyncio
async def test_patch_me_writes_audit_log(db_session):
    user = await _make_user(db_session, username="oldname")
    request = _make_request()
    body = UpdateMeRequest(username="brandnew")

    await update_me(body=body, request=request, user=user, db=db_session)

    log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.id.desc())
        )
    ).scalars().first()
    assert log is not None
    assert log.action == audit_actions.USERNAME_CHANGED
    assert log.details == {"old_username": "oldname", "new_username": "brandnew"}


@pytest.mark.asyncio
async def test_patch_me_same_username_is_noop(db_session):
    user = await _make_user(db_session, username="same")
    request = _make_request()
    body = UpdateMeRequest(username="same")

    result = await update_me(body=body, request=request, user=user, db=db_session)
    assert result.username == "same"

    # No audit log should be written.
    log = (
        await db_session.execute(select(AuditLog).where(AuditLog.user_id == user.id))
    ).scalars().first()
    assert log is None


@pytest.mark.asyncio
async def test_patch_me_username_taken_returns_409(db_session):
    await _make_user(db_session, username="taken")
    user = await _make_user(db_session, username="me")
    request = _make_request()
    body = UpdateMeRequest(username="taken")

    with pytest.raises(HTTPException) as exc_info:
        await update_me(body=body, request=request, user=user, db=db_session)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_patch_me_invalid_username_raises_validation_error():
    """Pydantic should reject usernames with disallowed characters or wrong length."""
    with pytest.raises(ValidationError):
        UpdateMeRequest(username="bad name!")  # space and !
    with pytest.raises(ValidationError):
        UpdateMeRequest(username="x")  # too short (min 2)
    with pytest.raises(ValidationError):
        UpdateMeRequest(username="a" * 51)  # too long
    with pytest.raises(ValidationError):
        UpdateMeRequest(username="hello-world")  # dash not allowed


@pytest.mark.asyncio
async def test_patch_me_valid_username_passes_validation():
    body = UpdateMeRequest(username="abc_123")
    assert body.username == "abc_123"


# ---------------------------------------------------------------------------
# GET /api/me/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_marks_most_recent_as_current(db_session):
    user = await _make_user(db_session, username="multisess")
    base = datetime.now(timezone.utc)

    older = await _make_session(
        db_session, user_id=user.id, jti="jti-old", created_at=base - timedelta(hours=2)
    )
    middle = await _make_session(
        db_session, user_id=user.id, jti="jti-mid", created_at=base - timedelta(hours=1)
    )
    newest = await _make_session(
        db_session, user_id=user.id, jti="jti-new", created_at=base
    )

    items = await list_my_sessions(user=user, db=db_session)
    assert len(items) == 3

    # Sorted desc by created_at. The first item is the newest and is_current=True.
    assert items[0].id == newest.id
    assert items[0].is_current is True
    assert items[1].id == middle.id
    assert items[1].is_current is False
    assert items[2].id == older.id
    assert items[2].is_current is False


@pytest.mark.asyncio
async def test_list_sessions_only_own_sessions(db_session):
    me = await _make_user(db_session, username="me_only")
    other = await _make_user(db_session, username="other")
    base = datetime.now(timezone.utc)

    await _make_session(db_session, user_id=me.id, jti="jti-me", created_at=base)
    await _make_session(db_session, user_id=other.id, jti="jti-other", created_at=base)

    items = await list_my_sessions(user=me, db=db_session)
    assert len(items) == 1
    assert items[0].ip_address == "1.2.3.4"


# ---------------------------------------------------------------------------
# DELETE /api/me/sessions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_my_session_deletes_own(db_session):
    user = await _make_user(db_session, username="killmine")
    base = datetime.now(timezone.utc)
    session = await _make_session(
        db_session, user_id=user.id, jti="jti-1", created_at=base
    )

    msg = await delete_my_session(session_id=session.id, user=user, db=db_session)
    assert msg.message

    remaining = (
        await db_session.execute(select(ActiveSession).where(ActiveSession.id == session.id))
    ).scalar_one_or_none()
    assert remaining is None


@pytest.mark.asyncio
async def test_delete_my_session_not_found_raises_404(db_session):
    user = await _make_user(db_session, username="nope")

    with pytest.raises(HTTPException) as exc_info:
        await delete_my_session(session_id=9999, user=user, db=db_session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_my_session_other_users_session_returns_404(db_session):
    me = await _make_user(db_session, username="meuser")
    other = await _make_user(db_session, username="otheruser")
    base = datetime.now(timezone.utc)
    other_session = await _make_session(
        db_session, user_id=other.id, jti="jti-other", created_at=base
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_my_session(session_id=other_session.id, user=me, db=db_session)
    assert exc_info.value.status_code == 404

    # The other user's session must remain intact.
    still_there = (
        await db_session.execute(
            select(ActiveSession).where(ActiveSession.id == other_session.id)
        )
    ).scalar_one_or_none()
    assert still_there is not None


# ---------------------------------------------------------------------------
# DELETE /api/me/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_all_sessions_keeps_only_most_recent(db_session):
    user = await _make_user(db_session, username="masskill")
    base = datetime.now(timezone.utc)

    await _make_session(
        db_session, user_id=user.id, jti="jti-old", created_at=base - timedelta(hours=2)
    )
    await _make_session(
        db_session, user_id=user.id, jti="jti-mid", created_at=base - timedelta(hours=1)
    )
    newest = await _make_session(
        db_session, user_id=user.id, jti="jti-new", created_at=base
    )

    msg = await delete_all_my_sessions_except_current(user=user, db=db_session)
    assert msg.message

    remaining = (
        await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id == newest.id


@pytest.mark.asyncio
async def test_delete_all_sessions_with_zero_or_one_session_is_noop(db_session):
    user = await _make_user(db_session, username="lonely")
    base = datetime.now(timezone.utc)

    # Zero sessions.
    msg = await delete_all_my_sessions_except_current(user=user, db=db_session)
    assert msg.message

    # One session — must remain after the call.
    only = await _make_session(
        db_session, user_id=user.id, jti="jti-only", created_at=base
    )
    msg = await delete_all_my_sessions_except_current(user=user, db=db_session)
    assert msg.message

    remaining = (
        await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id == only.id


@pytest.mark.asyncio
async def test_delete_all_sessions_does_not_touch_other_users(db_session):
    me = await _make_user(db_session, username="me_kill_all")
    other = await _make_user(db_session, username="other_safe")
    base = datetime.now(timezone.utc)

    await _make_session(
        db_session, user_id=me.id, jti="jti-me-1", created_at=base - timedelta(hours=2)
    )
    await _make_session(
        db_session, user_id=me.id, jti="jti-me-2", created_at=base
    )
    other_session = await _make_session(
        db_session, user_id=other.id, jti="jti-other", created_at=base - timedelta(hours=3)
    )

    await delete_all_my_sessions_except_current(user=me, db=db_session)

    # Other user's session remains.
    still_there = (
        await db_session.execute(
            select(ActiveSession).where(ActiveSession.id == other_session.id)
        )
    ).scalar_one_or_none()
    assert still_there is not None
