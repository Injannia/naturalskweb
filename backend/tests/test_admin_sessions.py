"""Tests for admin sessions endpoints (Phase 5, Task 8).

Covers GET /api/admin/sessions and DELETE /api/admin/sessions/{id}.

Follows the project's pattern: only `db_session` fixture, router functions
called directly with manually-constructed Request.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.core.security import hash_password
from app.models.audit import ActiveSession, AuditLog
from app.models.user import User
from app.routers.admin import kill_session, list_all_sessions
from app.utils import audit_actions


def _make_request() -> Request:
    return Request(
        scope={
            "type": "http",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 0),
        }
    )


async def _make_user(
    db,
    *,
    username: str,
    role: str = "user",
    is_active: bool = True,
    is_deleted: bool = False,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password("Password1"),
        role=role,
        is_active=is_active,
        must_change_password=False,
        is_deleted=is_deleted,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _add_session(
    db,
    user_id: int,
    jti: str = "jti-test",
    *,
    created_at: datetime | None = None,
) -> ActiveSession:
    s = ActiveSession(
        user_id=user_id,
        token_jti=jti,
        ip_address="127.0.0.1",
        user_agent="pytest",
        created_at=created_at or datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# GET /api/admin/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_returns_all_with_username(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    u1 = await _make_user(db_session, username="alice")
    u2 = await _make_user(db_session, username="bob")

    await _add_session(db_session, u1.id, jti="jti-a")
    await _add_session(db_session, u2.id, jti="jti-b")

    result = await list_all_sessions(actor=sa, db=db_session)

    assert len(result) == 2
    by_username = {item.username: item for item in result}
    assert "alice" in by_username
    assert "bob" in by_username

    item = by_username["alice"]
    assert item.user_id == u1.id
    assert item.ip_address == "127.0.0.1"
    assert item.user_agent == "pytest"
    assert item.created_at is not None
    assert item.expires_at is not None


@pytest.mark.asyncio
async def test_list_sessions_ordered_by_created_at_desc(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    u = await _make_user(db_session, username="alice")

    now = datetime.now(timezone.utc)
    s_old = await _add_session(
        db_session, u.id, jti="jti-old", created_at=now - timedelta(hours=2)
    )
    s_mid = await _add_session(
        db_session, u.id, jti="jti-mid", created_at=now - timedelta(hours=1)
    )
    s_new = await _add_session(
        db_session, u.id, jti="jti-new", created_at=now
    )

    result = await list_all_sessions(actor=sa, db=db_session)

    assert len(result) == 3
    ids = [item.id for item in result]
    assert ids == [s_new.id, s_mid.id, s_old.id]


@pytest.mark.asyncio
async def test_list_sessions_empty(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    result = await list_all_sessions(actor=sa, db=db_session)
    assert result == []


# ---------------------------------------------------------------------------
# DELETE /api/admin/sessions/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kill_session_deletes_and_sets_kicked_at(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="victim")
    s = await _add_session(db_session, target.id, jti="jti-kill")

    result = await kill_session(
        session_id=s.id, request=_make_request(), actor=sa, db=db_session
    )
    assert result.message

    gone = (
        await db_session.execute(select(ActiveSession).where(ActiveSession.id == s.id))
    ).scalar_one_or_none()
    assert gone is None

    fresh = (
        await db_session.execute(select(User).where(User.id == target.id))
    ).scalar_one()
    assert fresh.kicked_at is not None
    assert fresh.kicked_at.tzinfo is not None


@pytest.mark.asyncio
async def test_kill_session_404_not_found(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    with pytest.raises(HTTPException) as exc:
        await kill_session(
            session_id=9999, request=_make_request(), actor=sa, db=db_session
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_kill_superadmin_session(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    sa = await _make_user(db_session, username="root", role="superadmin")
    s = await _add_session(db_session, sa.id, jti="jti-sa")

    with pytest.raises(HTTPException) as exc:
        await kill_session(
            session_id=s.id, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403

    # Session must still exist.
    still_there = (
        await db_session.execute(select(ActiveSession).where(ActiveSession.id == s.id))
    ).scalar_one_or_none()
    assert still_there is not None


@pytest.mark.asyncio
async def test_superadmin_can_kill_any_session(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    admin = await _make_user(db_session, username="adm", role="admin")
    s = await _add_session(db_session, admin.id, jti="jti-adm")

    result = await kill_session(
        session_id=s.id, request=_make_request(), actor=sa, db=db_session
    )
    assert result.message

    gone = (
        await db_session.execute(select(ActiveSession).where(ActiveSession.id == s.id))
    ).scalar_one_or_none()
    assert gone is None

    fresh = (
        await db_session.execute(select(User).where(User.id == admin.id))
    ).scalar_one()
    assert fresh.kicked_at is not None


@pytest.mark.asyncio
async def test_admin_can_kill_user_session(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    user = await _make_user(db_session, username="alice")
    s = await _add_session(db_session, user.id, jti="jti-u")

    result = await kill_session(
        session_id=s.id, request=_make_request(), actor=admin, db=db_session
    )
    assert result.message

    gone = (
        await db_session.execute(select(ActiveSession).where(ActiveSession.id == s.id))
    ).scalar_one_or_none()
    assert gone is None


@pytest.mark.asyncio
async def test_kill_session_writes_audit_log(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="victim")
    s = await _add_session(db_session, target.id, jti="jti-audit")
    session_id = s.id

    await kill_session(
        session_id=session_id, request=_make_request(), actor=sa, db=db_session
    )

    log = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == audit_actions.SESSION_KILLED_BY_ADMIN)
            .order_by(AuditLog.id.desc())
        )
    ).scalars().first()

    assert log is not None
    assert log.user_id == sa.id
    assert log.details["target_user_id"] == target.id
    assert log.details["target_username"] == target.username
    assert log.details["session_id"] == session_id
