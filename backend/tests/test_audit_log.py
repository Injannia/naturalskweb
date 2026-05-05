"""Tests for /api/admin/audit-log and /api/admin/audit-log/export.csv (Phase 5, Task 11).

Follows the project's pattern: only `db_session` fixture, router function
called directly. All Query-aliased params must be passed explicitly because
calling the function directly skips FastAPI's dependency resolution.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.user import User
from app.routers.admin import export_audit_log, get_audit_log


async def _make_user(
    db,
    *,
    username: str,
    role: str = "user",
) -> User:
    user = User(
        username=username,
        password_hash=hash_password("Password1"),
        role=role,
        is_active=True,
        must_change_password=False,
        is_deleted=False,
        usage_today={"youtube": 0, "converter": 0, "image": 0},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _call_get_audit_log(
    db,
    *,
    user_id=None,
    action=None,
    date_from=None,
    date_to=None,
    offset=0,
    limit=50,
):
    return await get_audit_log(
        user_id=user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
        db=db,
    )


async def _call_export_audit_log(
    db,
    *,
    user_id=None,
    action=None,
    date_from=None,
    date_to=None,
):
    return await export_audit_log(
        user_id=user_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        db=db,
    )


# ---------------------------------------------------------------------------
# 1. items + total
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_returns_items_and_total(db_session):
    user = await _make_user(db_session, username="alice")
    for i in range(3):
        db_session.add(
            AuditLog(
                user_id=user.id,
                action="login",
                details={"i": i},
                ip_address="127.0.0.1",
            )
        )
    await db_session.commit()

    result = await _call_get_audit_log(db_session)

    assert result.total == 3
    assert len(result.items) == 3
    for item in result.items:
        assert item.action == "login"
        assert item.user_id == user.id
        assert item.username == "alice"


# ---------------------------------------------------------------------------
# 2. action filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_filter_by_action(db_session):
    user = await _make_user(db_session, username="alice")
    db_session.add(AuditLog(user_id=user.id, action="login", details={}, ip_address="1.1.1.1"))
    db_session.add(AuditLog(user_id=user.id, action="login", details={}, ip_address="1.1.1.1"))
    db_session.add(AuditLog(user_id=user.id, action="logout", details={}, ip_address="1.1.1.1"))
    await db_session.commit()

    result = await _call_get_audit_log(db_session, action="login")

    assert result.total == 2
    assert len(result.items) == 2
    assert all(item.action == "login" for item in result.items)


# ---------------------------------------------------------------------------
# 3. user_id filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_filter_by_user_id(db_session):
    u1 = await _make_user(db_session, username="alice")
    u2 = await _make_user(db_session, username="bob")
    db_session.add(AuditLog(user_id=u1.id, action="login", details={}, ip_address="1.1.1.1"))
    db_session.add(AuditLog(user_id=u2.id, action="login", details={}, ip_address="2.2.2.2"))
    await db_session.commit()

    result = await _call_get_audit_log(db_session, user_id=u1.id)

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].user_id == u1.id
    assert result.items[0].username == "alice"


# ---------------------------------------------------------------------------
# 4. date range filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_filter_by_date_range(db_session):
    user = await _make_user(db_session, username="alice")
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    db_session.add(
        AuditLog(
            user_id=user.id,
            action="a",
            details={},
            ip_address="1.1.1.1",
            created_at=base,
        )
    )
    db_session.add(
        AuditLog(
            user_id=user.id,
            action="b",
            details={},
            ip_address="1.1.1.1",
            created_at=base + timedelta(days=1),
        )
    )
    db_session.add(
        AuditLog(
            user_id=user.id,
            action="c",
            details={},
            ip_address="1.1.1.1",
            created_at=base + timedelta(days=2),
        )
    )
    await db_session.commit()

    # Filter: include only the middle entry.
    result = await _call_get_audit_log(
        db_session,
        date_from=base + timedelta(hours=12),
        date_to=base + timedelta(days=1, hours=12),
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].action == "b"


# ---------------------------------------------------------------------------
# 5. pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_pagination(db_session):
    user = await _make_user(db_session, username="alice")
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        db_session.add(
            AuditLog(
                user_id=user.id,
                action=f"a{i}",
                details={},
                ip_address="1.1.1.1",
                created_at=base + timedelta(seconds=i),
            )
        )
    await db_session.commit()

    result = await _call_get_audit_log(db_session, offset=2, limit=2)

    assert result.total == 5
    assert len(result.items) == 2


# ---------------------------------------------------------------------------
# 6. outerjoin: null user_id leaves username null
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_outerjoin_username(db_session):
    db_session.add(
        AuditLog(user_id=None, action="anonymous", details={}, ip_address="3.3.3.3")
    )
    await db_session.commit()

    result = await _call_get_audit_log(db_session)

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].user_id is None
    assert result.items[0].username is None


# ---------------------------------------------------------------------------
# 7. ordering: newest first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_orders_by_created_at_desc(db_session):
    user = await _make_user(db_session, username="alice")
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    db_session.add(
        AuditLog(
            user_id=user.id,
            action="oldest",
            details={},
            ip_address="1.1.1.1",
            created_at=base,
        )
    )
    db_session.add(
        AuditLog(
            user_id=user.id,
            action="middle",
            details={},
            ip_address="1.1.1.1",
            created_at=base + timedelta(hours=1),
        )
    )
    db_session.add(
        AuditLog(
            user_id=user.id,
            action="newest",
            details={},
            ip_address="1.1.1.1",
            created_at=base + timedelta(hours=2),
        )
    )
    await db_session.commit()

    result = await _call_get_audit_log(db_session)

    actions = [item.action for item in result.items]
    assert actions == ["newest", "middle", "oldest"]


# ---------------------------------------------------------------------------
# 8. CSV export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csv_export_contains_header_and_rows(db_session):
    user = await _make_user(db_session, username="alice")
    db_session.add(
        AuditLog(user_id=user.id, action="login", details={}, ip_address="1.1.1.1")
    )
    await db_session.commit()

    response = await _call_export_audit_log(db_session)

    assert response.media_type == "text/csv"
    assert "audit-log.csv" in response.headers.get("content-disposition", "")

    body = response.body.decode() if isinstance(response.body, bytes) else response.body
    assert "id,created_at,user_id,username,action,ip_address,details" in body
    assert "login" in body
    assert "1.1.1.1" in body
    assert "alice" in body


@pytest.mark.asyncio
async def test_csv_export_details_is_valid_json(db_session):
    """details cell must be valid JSON (not Python repr) so a downstream
    consumer can JSON.parse it. Also must preserve non-ASCII via
    ensure_ascii=False."""
    import csv as csv_mod
    import io as io_mod
    import json as json_mod

    user = await _make_user(db_session, username="bob")
    db_session.add(
        AuditLog(
            user_id=user.id,
            action="user_updated",
            details={"target_username": "Иван", "n": 1},
            ip_address="2.2.2.2",
        )
    )
    await db_session.commit()

    response = await _call_export_audit_log(db_session)
    body = response.body.decode() if isinstance(response.body, bytes) else response.body

    rows = list(csv_mod.reader(io_mod.StringIO(body)))
    header = rows[0]
    data = rows[1]
    details_idx = header.index("details")
    parsed = json_mod.loads(data[details_idx])
    assert parsed == {"target_username": "Иван", "n": 1}
