import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_limit: int = 60, auth_limit: int = 10, window: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        self.auth_limit = auth_limit
        self.window = window
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup: float = time.time()

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
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

        # Auth-specific rate limit (stricter)
        is_auth = "/api/auth/" in path
        if is_auth:
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
