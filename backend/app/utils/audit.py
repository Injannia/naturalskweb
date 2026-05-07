from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_audit(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    request: Request,
    details: dict | None = None,
) -> None:
    """Append an audit-log row in the current transaction (no commit, no flush).

    Declared `async` for forward compatibility — future versions may flush
    inline for high-volume logging. Callers must `await` regardless.
    """
    log = AuditLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")[:256],
    )
    db.add(log)
