"""API datetime fields must serialize as UTC ISO-8601 with a 'Z' suffix.

DB datetimes are naive UTC. Emitted without a designator, the frontend
parses them as local time and shows the wrong clock. These tests pin the
wire contract so every timestamp the SPA receives is unambiguous UTC.
"""
from datetime import datetime, timezone

from app.schemas.admin import AuditLogItem, AdminSessionItem
from app.schemas.youtube import DownloadStatus


def test_naive_datetime_serializes_with_z():
    item = AuditLogItem(
        id=1, user_id=1, username="a", action="x", details=None,
        ip_address="", created_at=datetime(2026, 5, 30, 4, 17, 0),
    )
    assert item.model_dump(mode="json")["created_at"] == "2026-05-30T04:17:00Z"


def test_tz_aware_datetime_normalized_to_utc_z():
    # +03:00 wall clock 07:17 == 04:17 UTC
    from datetime import timedelta
    aware = datetime(2026, 5, 30, 7, 17, 0, tzinfo=timezone(timedelta(hours=3)))
    item = AuditLogItem(
        id=1, user_id=1, username="a", action="x", details=None,
        ip_address="", created_at=aware,
    )
    assert item.model_dump(mode="json")["created_at"] == "2026-05-30T04:17:00Z"


def test_session_timestamps_have_z():
    s = AdminSessionItem(
        id=1, user_id=1, username="a", ip_address="", user_agent="",
        created_at=datetime(2026, 5, 30, 4, 0, 0),
        expires_at=datetime(2026, 5, 31, 4, 0, 0),
    )
    dumped = s.model_dump(mode="json")
    assert dumped["created_at"].endswith("Z")
    assert dumped["expires_at"].endswith("Z")


def test_optional_datetime_none_stays_null():
    t = DownloadStatus(task_id="t1", status="ready", progress=100.0, created_at=None, completed_at=None)
    dumped = t.model_dump(mode="json")
    assert dumped["created_at"] is None
    assert dumped["completed_at"] is None
