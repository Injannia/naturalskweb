"""Admins and superadmins have unlimited daily quota.

_check_daily_limit must never raise for those roles, and _get_quota must
report the UNLIMITED sentinel (-1) so the frontend renders ∞.
"""
from datetime import date

import pytest
from fastapi import HTTPException

from app.core.limits import UNLIMITED, has_unlimited_quota
from app.models.user import User
from app.routers.image import _check_daily_limit, _get_quota


def _user(role: str) -> User:
    return User(
        username=f"u_{role}",
        password_hash="x",
        role=role,
        usage_today={"youtube": 99, "converter": 99, "image": 99},
        usage_reset_date=date.today(),
        limits={"youtube_daily": 0, "convert_daily": 0, "image_daily": 0},
    )


@pytest.mark.parametrize("role", ["admin", "superadmin"])
def test_unlimited_roles_bypass_quota(role):
    u = _user(role)
    assert has_unlimited_quota(u) is True
    # Way over the (zero) limit, but must not raise.
    _check_daily_limit(u)
    used, limit = _get_quota(u)
    assert used == 99
    assert limit == UNLIMITED


def test_regular_user_is_capped():
    u = _user("user")
    assert has_unlimited_quota(u) is False
    used, limit = _get_quota(u)
    assert limit == 0
    with pytest.raises(HTTPException) as exc:
        _check_daily_limit(u)
    assert exc.value.status_code == 429
