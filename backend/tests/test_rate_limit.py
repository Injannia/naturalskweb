"""Tests for RateLimitMiddleware.

The SPA polls heavily: each active task hits /status every 2 s (30 req/min
per task), /auth/me polls every 15 s, and each module page fans out to
quota + tasks + tasks/history on mount — doubled again in dev by React
StrictMode. A 60 req/min global ceiling is below legitimate steady-state
(two concurrent tasks alone = 60/min) and was returning 429 during normal
use. The global limit must comfortably exceed real polling while still
capping runaway clients.
"""
import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.security import RateLimitMiddleware


def _make_request(path: str = "/api/image/status/abc", ip: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": (ip, 12345),
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


async def _call_next(_req: Request) -> Response:
    return Response("ok", status_code=200)


@pytest.mark.asyncio
async def test_allows_realistic_polling_burst():
    """A minute of legitimate polling (well over the old 60 cap) must pass."""
    mw = RateLimitMiddleware(app=None)
    statuses = []
    for _ in range(120):
        resp = await mw.dispatch(_make_request(), _call_next)
        statuses.append(resp.status_code)
    assert all(s == 200 for s in statuses), f"polling got throttled: {statuses.count(429)} x 429"


@pytest.mark.asyncio
async def test_still_caps_runaway_client():
    """Abuse protection intact — the limit still trips eventually."""
    mw = RateLimitMiddleware(app=None)
    last = None
    for _ in range(mw.default_limit + 1):
        last = await mw.dispatch(_make_request(), _call_next)
    assert last.status_code == 429


@pytest.mark.asyncio
async def test_login_brute_force_still_strict():
    """Auth-sensitive endpoints keep the stricter (10/min) limit."""
    mw = RateLimitMiddleware(app=None)
    last = None
    for _ in range(mw.auth_limit + 1):
        last = await mw.dispatch(_make_request(path="/api/auth/login"), _call_next)
    assert last.status_code == 429
