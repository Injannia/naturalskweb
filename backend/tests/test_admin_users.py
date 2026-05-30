"""Tests for /api/admin/users endpoints (Phase 5, Task 6).

These tests follow the project's pattern (see tests/test_me.py): the only
fixture available is `db_session`, so we call the router functions directly
instead of going through HTTP/TestClient.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.core.security import hash_password
from app.models.audit import ActiveSession, AuditLog
from app.models.user import User
from app.routers.admin import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)
from app.schemas.admin import CreateUserRequest, UpdateUserRequest
from app.utils import audit_actions


def _make_request() -> Request:
    """Minimal ASGI Request acceptable to log_audit."""
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


# ---------------------------------------------------------------------------
# GET /api/admin/users — list with pagination & filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_returns_items_and_total(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    await _make_user(db_session, username="user1")
    await _make_user(db_session, username="user2")
    await _make_user(db_session, username="user3")

    result = await list_users(
        offset=0,
        limit=10,
        search=None,
        role=None,
        status_filter=None,
        include_deleted=False,
        actor=admin,
        db=db_session,
    )

    assert hasattr(result, "items")
    assert hasattr(result, "total")
    # admin + 3 regular users = 4 total
    assert result.total == 4
    assert len(result.items) == 4


@pytest.mark.asyncio
async def test_list_users_pagination_limits_results(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    for i in range(5):
        await _make_user(db_session, username=f"u{i}")

    page1 = await list_users(
        offset=0,
        limit=2,
        search=None,
        role=None,
        status_filter=None,
        include_deleted=False,
        actor=admin,
        db=db_session,
    )
    assert len(page1.items) == 2
    assert page1.total == 6  # 1 admin + 5 users

    page2 = await list_users(
        offset=2,
        limit=2,
        search=None,
        role=None,
        status_filter=None,
        include_deleted=False,
        actor=admin,
        db=db_session,
    )
    assert len(page2.items) == 2
    assert page2.items[0].id != page1.items[0].id


@pytest.mark.asyncio
async def test_list_users_default_excludes_deleted(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    await _make_user(db_session, username="alive")
    await _make_user(db_session, username="dead", is_deleted=True)

    result = await list_users(
        offset=0,
        limit=10,
        search=None,
        role=None,
        status_filter=None,
        include_deleted=False,
        actor=admin,
        db=db_session,
    )
    usernames = [u.username for u in result.items]
    assert "alive" in usernames
    assert "dead" not in usernames


@pytest.mark.asyncio
async def test_list_users_admin_cannot_use_include_deleted(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")

    with pytest.raises(HTTPException) as exc:
        await list_users(
            offset=0,
            limit=10,
            search=None,
            role=None,
            status_filter=None,
            include_deleted=True,
            actor=admin,
            db=db_session,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_users_superadmin_include_deleted(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    await _make_user(db_session, username="alive")
    await _make_user(db_session, username="dead", is_deleted=True)

    result = await list_users(
        offset=0,
        limit=10,
        search=None,
        role=None,
        status_filter=None,
        include_deleted=True,
        actor=sa,
        db=db_session,
    )
    usernames = [u.username for u in result.items]
    assert "alive" in usernames
    assert "dead" in usernames


@pytest.mark.asyncio
async def test_list_users_admin_cannot_filter_by_status_deleted(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")

    with pytest.raises(HTTPException) as exc:
        await list_users(
            offset=0,
            limit=10,
            search=None,
            role=None,
            status_filter="deleted",
            include_deleted=False,
            actor=admin,
            db=db_session,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_users_search_by_username(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    await _make_user(db_session, username="alice")
    await _make_user(db_session, username="bob")

    result = await list_users(
        offset=0,
        limit=10,
        search="ali",
        role=None,
        status_filter=None,
        include_deleted=False,
        actor=admin,
        db=db_session,
    )
    usernames = [u.username for u in result.items]
    assert usernames == ["alice"]


# ---------------------------------------------------------------------------
# GET /api/admin/users/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_returns_detail(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    target = await _make_user(db_session, username="someone")

    result = await get_user(user_id=target.id, actor=admin, db=db_session)
    assert result.id == target.id
    assert result.username == "someone"
    assert isinstance(result.permissions, dict)


@pytest.mark.asyncio
async def test_get_user_not_found(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")

    with pytest.raises(HTTPException) as exc:
        await get_user(user_id=9999, actor=admin, db=db_session)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/admin/users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_superadmin_creates_user(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    body = CreateUserRequest(username="newone", role="user")
    result = await create_user(body=body, request=_make_request(), actor=sa, db=db_session)

    assert result.username == "newone"
    assert result.role == "user"
    assert result.password  # one-shot password returned
    assert result.id

    fresh = (
        await db_session.execute(select(User).where(User.username == "newone"))
    ).scalar_one()
    assert fresh.must_change_password is True


@pytest.mark.asyncio
async def test_admin_cannot_create_user(db_session):
    # Only superadmin may create accounts now.
    admin = await _make_user(db_session, username="admin1", role="admin")
    body = CreateUserRequest(username="anyone", role="user")

    with pytest.raises(HTTPException) as exc:
        await create_user(body=body, request=_make_request(), actor=admin, db=db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_can_create_admin(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    body = CreateUserRequest(username="newadm", role="admin")
    result = await create_user(body=body, request=_make_request(), actor=sa, db=db_session)
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_create_user_writes_audit_log(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    body = CreateUserRequest(username="newuser", role="user")
    await create_user(body=body, request=_make_request(), actor=sa, db=db_session)

    log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == audit_actions.USER_CREATED)
        )
    ).scalars().first()
    assert log is not None
    assert log.user_id == sa.id
    assert log.details["target_username"] == "newuser"


@pytest.mark.asyncio
async def test_create_user_duplicate_username_returns_409(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    await _make_user(db_session, username="dup")

    body = CreateUserRequest(username="dup", role="user")
    with pytest.raises(HTTPException) as exc:
        await create_user(body=body, request=_make_request(), actor=sa, db=db_session)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_cannot_edit_superadmin(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    sa = await _make_user(db_session, username="root", role="superadmin")

    body = UpdateUserRequest(limits={"youtube_daily": 999})
    with pytest.raises(HTTPException) as exc:
        await update_user(
            user_id=sa.id, body=body, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_edit_self(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")

    body = UpdateUserRequest(permissions={"youtube": False, "converter": False, "image": False})
    with pytest.raises(HTTPException) as exc:
        await update_user(
            user_id=admin.id, body=body, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_promote_to_admin(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    target = await _make_user(db_session, username="regular")

    body = UpdateUserRequest(role="admin")
    with pytest.raises(HTTPException) as exc:
        await update_user(
            user_id=target.id, body=body, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_ignores_limits(db_session):
    # Limits are fixed defaults and not editable — update_user ignores them.
    admin = await _make_user(db_session, username="admin1", role="admin")
    target = await _make_user(db_session, username="regular")
    before = dict(target.limits)

    body = UpdateUserRequest(limits={"youtube_daily": 999, "convert_daily": 999, "image_daily": 999})
    result = await update_user(
        user_id=target.id, body=body, request=_make_request(), actor=admin, db=db_session
    )
    assert result.limits == before

    fresh = (
        await db_session.execute(select(User).where(User.id == target.id))
    ).scalar_one()
    assert fresh.limits == before


@pytest.mark.asyncio
async def test_superadmin_can_promote_to_admin(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="regular")

    body = UpdateUserRequest(role="admin")
    result = await update_user(
        user_id=target.id, body=body, request=_make_request(), actor=sa, db=db_session
    )
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_update_user_writes_audit_log(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    target = await _make_user(db_session, username="regular")

    body = UpdateUserRequest(is_active=False)
    await update_user(
        user_id=target.id, body=body, request=_make_request(), actor=admin, db=db_session
    )

    log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == audit_actions.USER_UPDATED)
        )
    ).scalars().first()
    assert log is not None
    assert log.user_id == admin.id
    assert log.details["target_user_id"] == target.id
    assert "is_active" in log.details["changes"]


@pytest.mark.asyncio
async def test_update_user_not_found(db_session):
    admin = await _make_user(db_session, username="admin1", role="admin")
    body = UpdateUserRequest(is_active=False)
    with pytest.raises(HTTPException) as exc:
        await update_user(
            user_id=9999, body=body, request=_make_request(), actor=admin, db=db_session
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_superadmin_soft_deletes_user(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="victim")

    # Add a session for the target so we can verify it's removed.
    s = ActiveSession(
        user_id=target.id,
        token_jti="jti-xyz",
        ip_address="1.1.1.1",
        user_agent="ua",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(s)
    await db_session.commit()

    msg = await delete_user(
        user_id=target.id, request=_make_request(), actor=sa, db=db_session
    )
    assert msg.message

    fresh = (
        await db_session.execute(select(User).where(User.id == target.id))
    ).scalar_one()
    assert fresh.is_deleted is True
    assert fresh.kicked_at is not None

    remaining_sessions = (
        await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == target.id)
        )
    ).scalars().all()
    assert remaining_sessions == []

    # Default list should not show the deleted user.
    listed = await list_users(
        offset=0,
        limit=10,
        search=None,
        role=None,
        status_filter=None,
        include_deleted=False,
        actor=sa,
        db=db_session,
    )
    ids = [u.id for u in listed.items]
    assert target.id not in ids

    # With include_deleted=True it should appear.
    listed2 = await list_users(
        offset=0,
        limit=10,
        search=None,
        role=None,
        status_filter=None,
        include_deleted=True,
        actor=sa,
        db=db_session,
    )
    ids2 = [u.id for u in listed2.items]
    assert target.id in ids2


@pytest.mark.asyncio
async def test_superadmin_cannot_delete_self(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")

    with pytest.raises(HTTPException) as exc:
        await delete_user(
            user_id=sa.id, request=_make_request(), actor=sa, db=db_session
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_writes_audit_log(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="victim2")

    await delete_user(user_id=target.id, request=_make_request(), actor=sa, db=db_session)

    log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == audit_actions.USER_DELETED)
        )
    ).scalars().first()
    assert log is not None
    assert log.user_id == sa.id
    assert log.details["target_user_id"] == target.id


@pytest.mark.asyncio
async def test_delete_user_not_found(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    with pytest.raises(HTTPException) as exc:
        await delete_user(
            user_id=9999, request=_make_request(), actor=sa, db=db_session
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Soft-deleted user visibility (regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_get_user_404_on_soft_deleted(db_session):
    """Admin must not see a soft-deleted user via GET /users/{id}."""
    admin = await _make_user(db_session, username="adm", role="admin")
    target = await _make_user(db_session, username="ghost", is_deleted=True)

    with pytest.raises(HTTPException) as exc:
        await get_user(user_id=target.id, actor=admin, db=db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_superadmin_get_user_sees_soft_deleted(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="ghost", is_deleted=True)

    result = await get_user(user_id=target.id, actor=sa, db=db_session)
    assert result.id == target.id
    assert result.is_deleted is True


@pytest.mark.asyncio
async def test_admin_cannot_patch_soft_deleted_user(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    target = await _make_user(db_session, username="ghost", is_deleted=True)

    with pytest.raises(HTTPException) as exc:
        await update_user(
            user_id=target.id,
            body=UpdateUserRequest(is_active=False),
            request=_make_request(),
            actor=admin,
            db=db_session,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_already_deleted_user_returns_409(db_session):
    """Re-deleting a soft-deleted user must not silently emit another audit row."""
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="ghost", is_deleted=True)

    with pytest.raises(HTTPException) as exc:
        await delete_user(
            user_id=target.id, request=_make_request(), actor=sa, db=db_session
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_status_deleted_with_default_include_returns_deleted(db_session):
    """status=deleted (without include_deleted) must list deleted users for superadmin,
    not produce a contradictory empty result."""
    sa = await _make_user(db_session, username="root", role="superadmin")
    await _make_user(db_session, username="alive")
    deleted = await _make_user(db_session, username="ghost", is_deleted=True)

    result = await list_users(
        offset=0,
        limit=10,
        search=None,
        role=None,
        status_filter="deleted",
        include_deleted=False,
        actor=sa,
        db=db_session,
    )
    ids = [u.id for u in result.items]
    assert deleted.id in ids
    assert result.total >= 1


@pytest.mark.asyncio
async def test_update_user_audit_log_records_old_value(db_session):
    """Audit log must capture the *pre-mutation* permissions/limits — not aliased to the new dict."""
    admin = await _make_user(db_session, username="adm", role="admin")
    target = await _make_user(db_session, username="bob")

    old_perms = dict(target.permissions)
    new_perms = {"youtube": False, "converter": True, "image": True}

    await update_user(
        user_id=target.id,
        body=UpdateUserRequest(permissions=new_perms),
        request=_make_request(),
        actor=admin,
        db=db_session,
    )

    log = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == audit_actions.USER_UPDATED)
            .order_by(AuditLog.id.desc())
        )
    ).scalars().first()
    assert log is not None
    before, after = log.details["changes"]["permissions"]
    assert before == old_perms
    assert after == new_perms


# ---------------------------------------------------------------------------
# CASCADE on ActiveSession.user_id (FK enforcement)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_session_cascade_on_user_delete():
    """Hard-deleting a User must cascade-delete every ActiveSession row.
    The shared db_session fixture has FK enforcement off; spin up a dedicated
    engine with PRAGMA foreign_keys=ON to verify the schema-level cascade.
    """
    from datetime import timedelta
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy import text
    from app.core.database import Base
    from app.core.security import hash_password
    from app.models.audit import ActiveSession

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        from app.models import download_task, shared_file  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            await db.execute(text("PRAGMA foreign_keys = ON"))
            user = User(
                username="cascade_target",
                password_hash=hash_password("Password1"),
                role="user",
                is_active=True,
                must_change_password=False,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            session_row = ActiveSession(
                user_id=user.id,
                token_jti="cascade-jti",
                ip_address="127.0.0.1",
                user_agent="pytest",
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            db.add(session_row)
            await db.commit()

            await db.delete(user)
            await db.commit()

            remaining = (
                await db.execute(select(ActiveSession).where(ActiveSession.user_id == user.id))
            ).scalars().all()
            assert remaining == []
    finally:
        await engine.dispose()
