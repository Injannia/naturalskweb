"""Limits are fixed defaults — not customizable on create or update.

Previously an admin could not edit their own limits (self-edit is blocked
at every layer) yet could mint new accounts with arbitrary limits. To
remove that inconsistency, limits are no longer editable anywhere: every
account gets the server defaults and update_user ignores any limits field.
"""
import pytest
from sqlalchemy import select
from starlette.requests import Request

from app.core.security import hash_password
from app.models.user import User
from app.routers.admin import create_user, update_user
from app.schemas.admin import CreateUserRequest, UpdateUserRequest

DEFAULT_LIMITS = {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50}


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
async def test_create_user_ignores_custom_limits(db_session):
    admin = await _make_user(db_session, username="root", role="superadmin")
    await create_user(
        body=CreateUserRequest(
            username="bob", role="user",
            limits={"youtube_daily": 99999, "convert_daily": 99999, "image_daily": 99999},
        ),
        request=_req(), actor=admin, db=db_session,
    )
    bob = (await db_session.execute(select(User).where(User.username == "bob"))).scalar_one()
    assert bob.limits == DEFAULT_LIMITS


@pytest.mark.asyncio
async def test_update_user_ignores_limits(db_session):
    admin = await _make_user(db_session, username="root", role="superadmin")
    target = await _make_user(db_session, username="bob", role="user")
    target.limits = dict(DEFAULT_LIMITS)
    await db_session.commit()

    await update_user(
        user_id=target.id,
        body=UpdateUserRequest(limits={"youtube_daily": 99999, "convert_daily": 99999, "image_daily": 99999}),
        request=_req(), actor=admin, db=db_session,
    )
    await db_session.refresh(target)
    assert target.limits == DEFAULT_LIMITS
