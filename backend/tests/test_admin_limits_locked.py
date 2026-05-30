"""Limit-editing policy.

Limits apply only to regular users and may be set/changed only by a
superadmin:
  - superadmin → regular user: limits applied (on create and update)
  - admin actor: cannot change limits (covered in test_admin_users)
  - target is admin/superadmin: limits ignored (those roles are unlimited)
"""
import pytest
from sqlalchemy import select
from starlette.requests import Request

from app.core.security import hash_password
from app.models.user import User
from app.routers.admin import create_user, update_user
from app.schemas.admin import CreateUserRequest, UpdateUserRequest

CUSTOM = {"youtube_daily": 7, "convert_daily": 8, "image_daily": 9}


def _req() -> Request:
    return Request(scope={"type": "http", "headers": [(b"user-agent", b"pytest")], "client": ("127.0.0.1", 0)})


async def _make_user(db, *, username: str, role: str = "user") -> User:
    u = User(username=username, password_hash=hash_password("Password1"), role=role,
             must_change_password=False)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_superadmin_create_honors_limits(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    await create_user(
        body=CreateUserRequest(username="bob", role="user", limits=dict(CUSTOM)),
        request=_req(), actor=sa, db=db_session,
    )
    bob = (await db_session.execute(select(User).where(User.username == "bob"))).scalar_one()
    assert bob.limits == CUSTOM


@pytest.mark.asyncio
async def test_superadmin_can_edit_regular_user_limits(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="bob", role="user")

    await update_user(
        user_id=target.id, body=UpdateUserRequest(limits=dict(CUSTOM)),
        request=_req(), actor=sa, db=db_session,
    )
    await db_session.refresh(target)
    assert target.limits == CUSTOM


@pytest.mark.asyncio
async def test_superadmin_cannot_edit_admin_limits(db_session):
    # Admins are unlimited; their limits field is meaningless and not editable.
    sa = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="adm", role="admin")
    before = dict(target.limits)

    await update_user(
        user_id=target.id, body=UpdateUserRequest(limits=dict(CUSTOM)),
        request=_req(), actor=sa, db=db_session,
    )
    await db_session.refresh(target)
    assert target.limits == before
