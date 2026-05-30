"""Uptime reported by /admin/system is the app's uptime, not OS boot time."""
import time

import pytest

from app.routers.admin import monitoring


@pytest.mark.asyncio
async def test_uptime_counts_from_app_start(monkeypatch):
    monkeypatch.setattr(monitoring, "_APP_START", time.time() - 123)
    info = await monitoring.get_system_info()
    # ~123s since the (patched) app start, not the machine's multi-hour boot uptime.
    assert 120 <= info.uptime_seconds <= 140
