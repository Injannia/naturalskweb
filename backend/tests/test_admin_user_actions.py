"""Tests for admin user-action endpoints (Phase 5, Task 7).

Covers POST /api/admin/users/{id}/reset-password and
POST /api/admin/users/{id}/toggle-active.

Follows the project's pattern: only `db_session` fixture, router functions
called directly with manually-constructed Request.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.core.security import hash_password, verify_password
from app.models.audit import ActiveSession, AuditLog
from app.models.user import User
from app.routers.admin import reset_password, toggle_active
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


async def _add_session(db, user_id: int, jti: str = "jti-test") -> ActiveSession:
    s = ActiveSession(
        user_id=user_id,
        token_jti=jti,
        ip_address="127.0.0.1",
        user_agent="pytest",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(s)
    await db.commit()
    return s


# ---------------------------------------------------------------------------
# POST /api/admin/users/{id}/reset-password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_password_returns_password_and_invalidates_sessions(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="victim")
    old_hash = target.password_hash

    await _add_session(db_session, target.id, jti="jti-a")
    await _add_session(db_session, target.id, jti="jti-b")

    result = await reset_password(
        user_id=target.id, request=_make_request(), actor=sa, db=db_session
    )

    assert result.id == target.id
    assert result.username == target.username
    assert isinstance(result.password, str)
    assert len(result.password) >= 12

    fresh = (
        await db_session.execute(select(User).where(User.id == target.id))
    ).scalar_one()
    assert fresh.password_hash != old_hash
    assert verify_password(result.password, fresh.password_hash)
    assert fresh.must_change_password is True
    assert fresh.kicked_at is not None

    sessions = (
        await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == target.id)
        )
    ).scalars().all()
    assert sessions == []

    log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == audit_actions.USER_PASSWORD_RESET)
        )
    ).scalars().first()
    assert log is not None
    assert log.user_id == sa.id
    assert log.details["target_user_id"] == target.id
    assert log.details["target_username"] == target.username
    # The new password must never be persisted in the audit log.
    assert "password" not in log.details
    assert result.password not in str(log.details.values())


@pytest.mark.asyncio
async def test_admin_cannot_reset_superadmin_password(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    sa = await _make_user(db_session, username="root", role="superadmin")

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            user_id=sa.id, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_reset_own_password(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            user_id=admin.id, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_can_reset_own_password(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    old_hash = sa.password_hash

    result = await reset_password(
        user_id=sa.id, request=_make_request(), actor=sa, db=db_session
    )
    assert result.id == sa.id
    assert result.password

    fresh = (
        await db_session.execute(select(User).where(User.id == sa.id))
    ).scalar_one()
    assert fresh.password_hash != old_hash
    assert fresh.must_change_password is True


@pytest.mark.asyncio
async def test_reset_password_404_on_soft_deleted_for_admin(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    ghost = await _make_user(db_session, username="ghost", is_deleted=True)

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            user_id=ghost.id, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reset_password_404_not_found(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            user_id=9999, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/admin/users/{id}/toggle-active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_active_flips_state(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="bob", is_active=True)

    result1 = await toggle_active(
        user_id=target.id, request=_make_request(), actor=sa, db=db_session
    )
    assert result1.id == target.id
    assert result1.is_active is False

    fresh1 = (
        await db_session.execute(select(User).where(User.id == target.id))
    ).scalar_one()
    assert fresh1.is_active is False

    result2 = await toggle_active(
        user_id=target.id, request=_make_request(), actor=sa, db=db_session
    )
    assert result2.is_active is True

    fresh2 = (
        await db_session.execute(select(User).where(User.id == target.id))
    ).scalar_one()
    assert fresh2.is_active is True


@pytest.mark.asyncio
async def test_admin_cannot_toggle_superadmin(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    sa = await _make_user(db_session, username="root", role="superadmin")

    with pytest.raises(HTTPException) as exc:
        await toggle_active(
            user_id=sa.id, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_toggle_self(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")

    with pytest.raises(HTTPException) as exc:
        await toggle_active(
            user_id=admin.id, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_cannot_toggle_self(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")

    with pytest.raises(HTTPException) as exc:
        await toggle_active(
            user_id=sa.id, request=_make_request(), actor=sa, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_toggle_active_writes_audit_log(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="bob", is_active=True)

    await toggle_active(
        user_id=target.id, request=_make_request(), actor=sa, db=db_session
    )

    log = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == audit_actions.USER_TOGGLED_ACTIVE)
            .order_by(AuditLog.id.desc())
        )
    ).scalars().first()
    assert log is not None
    assert log.action == "user_toggled_active"
    assert log.user_id == sa.id
    assert log.details["target_user_id"] == target.id
    assert log.details["target_username"] == target.username
    assert log.details["new_state"] is False

    # Toggle again — audit must record the new value (True).
    await toggle_active(
        user_id=target.id, request=_make_request(), actor=sa, db=db_session
    )
    log2 = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == audit_actions.USER_TOGGLED_ACTIVE)
            .order_by(AuditLog.id.desc())
        )
    ).scalars().first()
    assert log2.details["new_state"] is True


@pytest.mark.asyncio
async def test_toggle_active_404_not_found(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    with pytest.raises(HTTPException) as exc:
        await toggle_active(
            user_id=9999, request=_make_request(), actor=sa, db=db_session
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_toggle_active_404_on_soft_deleted_for_admin(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    ghost = await _make_user(db_session, username="ghost", is_deleted=True)

    with pytest.raises(HTTPException) as exc:
        await toggle_active(
            user_id=ghost.id, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 404
