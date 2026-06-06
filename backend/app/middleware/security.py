import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.utils.client_ip import get_client_ip


class RateLimitMiddleware(BaseHTTPMiddleware):
    # default_limit is intentionally generous: the SPA polls /status every 2 s
    # per active task (30 req/min each), /auth/me every 15 s, and fans out to
    # quota + tasks + tasks/history per page — doubled in dev by React
    # StrictMode. 60/min throttled normal use; 300/min (5 req/s) clears
    # realistic polling while still capping runaway clients. Brute-forceable
    # endpoints keep the stricter auth_limit below.
    def __init__(self, app, default_limit: int = 300, auth_limit: int = 10, window: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        self.auth_limit = auth_limit
        self.window = window
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup: float = time.time()

    async def dispatch(self, request: Request, call_next):
        client_ip = get_client_ip(request) or "unknown"
        path = request.url.path
        now = time.time()

        # Periodic cleanup
        if now - self._last_cleanup > 300:
            stale_keys = [
                k for k, timestamps in self.requests.items()
                if all(now - t >= self.window for t in timestamps)
            ]
            for k in stale_keys:
                del self.requests[k]
            self._last_cleanup = now

        # Global rate limit (per IP)
        global_key = client_ip
        self.requests[global_key] = [t for t in self.requests[global_key] if now - t < self.window]
        if len(self.requests[global_key]) >= self.default_limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later."},
            )

        # Auth-specific rate limit (stricter): only the brute-forceable
        # endpoints — login (password guessing) and refresh (refresh-token
        # abuse). /auth/me, /auth/logout, /auth/change-password require an
        # already-valid token and were causing 429s in normal use:
        # /auth/me is polled every 15 s, runs twice on mount under React
        # StrictMode, and is hit on every page reload, easily exceeding 10/min.
        is_auth_sensitive = path in ("/api/auth/login", "/api/auth/refresh")
        if is_auth_sensitive:
            auth_key = f"{client_ip}:auth"
            self.requests[auth_key] = [t for t in self.requests[auth_key] if now - t < self.window]
            if len(self.requests[auth_key]) >= self.auth_limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Try again later."},
                )
            self.requests[auth_key].append(now)

        self.requests[global_key].append(now)
        return await call_next(request)


CSP_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: blob: https://i.ytimg.com; "
    "media-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to every response.

    X-XSS-Protection is intentionally omitted — deprecated and can introduce
    XS-Leak vulnerabilities in legacy browsers. CSP covers what it tried to do.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = CSP_POLICY
        return response
