"""Tests for /api/admin/stats endpoint (Phase 5, Task 9).

Follows the project's pattern: only `db_session` fixture, router function
called directly.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import hash_password
from app.models.audit import ActiveSession, AuditLog
from app.models.user import User
from app.routers.admin import get_stats


async def _make_user(
    db,
    *,
    username: str,
    role: str = "user",
    is_active: bool = True,
    is_deleted: bool = False,
    usage_today: dict | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password("Password1"),
        role=role,
        is_active=is_active,
        must_change_password=False,
        is_deleted=is_deleted,
        usage_today=usage_today
        if usage_today is not None
        else {"youtube": 0, "converter": 0, "image": 0},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _add_session(
    db,
    user_id: int,
    *,
    jti: str,
    expires_at: datetime,
) -> ActiveSession:
    s = ActiveSession(
        user_id=user_id,
        token_jti=jti,
        ip_address="127.0.0.1",
        user_agent="pytest",
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Acceptance criterion 1: full shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_returns_full_shape(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")

    result = await get_stats(actor=admin, db=db_session)

    assert isinstance(result.total_users, int)
    assert isinstance(result.active_users, int)
    assert isinstance(result.deleted_users, int)
    assert isinstance(result.total_downloads_today, int)
    assert isinstance(result.total_conversions_today, int)
    assert isinstance(result.total_image_ops_today, int)
    assert isinstance(result.storage_used_mb, float)
    assert isinstance(result.active_sessions, int)
    assert isinstance(result.top_users, list)
    assert isinstance(result.total_audit_logs, int)


# ---------------------------------------------------------------------------
# Acceptance criterion 2: user counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_counts_users_correctly(db_session):
    # 3 active non-deleted
    await _make_user(db_session, username="u1", is_active=True)
    await _make_user(db_session, username="u2", is_active=True)
    await _make_user(db_session, username="u3", is_active=True)
    # 2 inactive non-deleted
    await _make_user(db_session, username="u4", is_active=False)
    await _make_user(db_session, username="u5", is_active=False)
    # 2 deleted
    await _make_user(db_session, username="d1", is_deleted=True)
    await _make_user(db_session, username="d2", is_deleted=True)

    admin = await _make_user(db_session, username="adm", role="admin")

    result = await get_stats(actor=admin, db=db_session)

    # 5 non-deleted regular + admin = 6 total
    assert result.total_users == 6
    # 3 active regular + admin = 4 active
    assert result.active_users == 4
    assert result.deleted_users == 2


# ---------------------------------------------------------------------------
# Acceptance criterion 3: usage aggregation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_aggregates_usage_today(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")

    for i in range(3):
        await _make_user(
            db_session,
            username=f"live{i}",
            usage_today={"youtube": 5, "converter": 2, "image": 1},
        )
    # Deleted user with non-zero usage — must NOT be aggregated.
    await _make_user(
        db_session,
        username="dead",
        is_deleted=True,
        usage_today={"youtube": 100, "converter": 100, "image": 100},
    )

    result = await get_stats(actor=admin, db=db_session)

    assert result.total_downloads_today == 15  # 3 * 5
    assert result.total_conversions_today == 6  # 3 * 2
    assert result.total_image_ops_today == 3  # 3 * 1


# ---------------------------------------------------------------------------
# Acceptance criterion 5: top_users ≤ 5, sorted DESC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_top_users_top_5_sorted(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")

    # Create 7 users with descending totals: 70, 60, 50, 40, 30, 20, 10
    for i, total in enumerate([70, 60, 50, 40, 30, 20, 10]):
        await _make_user(
            db_session,
            username=f"u{i}",
            usage_today={"youtube": total, "converter": 0, "image": 0},
        )

    result = await get_stats(actor=admin, db=db_session)

    assert len(result.top_users) <= 5
    assert len(result.top_users) == 5
    totals = [tu.total_today for tu in result.top_users]
    assert totals == sorted(totals, reverse=True)
    # The top user should be 70.
    assert result.top_users[0].total_today == 70
    # All TopUser entries must have the required fields.
    for tu in result.top_users:
        assert tu.user_id
        assert tu.username
        assert isinstance(tu.avatar_version, int)


# ---------------------------------------------------------------------------
# Acceptance criterion 4: active_sessions filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_active_sessions_counts_unexpired(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    user = await _make_user(db_session, username="alice")

    now = datetime.now(timezone.utc)
    # Active: expires in 7 days.
    await _add_session(
        db_session, user.id, jti="jti-active", expires_at=now + timedelta(days=7)
    )
    # Expired: expires 1 day ago.
    await _add_session(
        db_session, user.id, jti="jti-expired", expires_at=now - timedelta(days=1)
    )

    result = await get_stats(actor=admin, db=db_session)
    assert result.active_sessions == 1


# ---------------------------------------------------------------------------
# Acceptance criterion 7: total_audit_logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_total_audit_logs(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")

    for i in range(3):
        log = AuditLog(
            user_id=admin.id,
            action="test.action",
            details={"i": i},
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
        db_session.add(log)
    await db_session.commit()

    result = await get_stats(actor=admin, db=db_session)
    assert result.total_audit_logs == 3


# ---------------------------------------------------------------------------
# Acceptance criterion 8: works for both admin and superadmin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_works_for_superadmin(db_session):
    sa = await _make_user(db_session, username="root", role="superadmin")
    result = await get_stats(actor=sa, db=db_session)
    assert result.total_users >= 1


# ---------------------------------------------------------------------------
# Acceptance criterion 6: storage_used_mb is non-negative float
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_storage_is_non_negative_float(db_session):
    admin = await _make_user(db_session, username="adm", role="admin")
    result = await get_stats(actor=admin, db=db_session)
    assert isinstance(result.storage_used_mb, float)
    assert result.storage_used_mb >= 0.0
