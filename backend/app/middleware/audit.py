import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.utils.client_ip import get_client_ip

logger = logging.getLogger("naturalsk.access")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        client_ip = get_client_ip(request) or "unknown"

        logger.info(
            "%s %s %s %dms %s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_ip,
        )
        return response
