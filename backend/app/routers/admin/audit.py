import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import require_admin
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.admin import AuditLogItem, AuditLogListResponse
from app.schemas._types import _utc_iso

router = APIRouter()


def _apply_audit_filter(stmt, *, user_id, action, date_from, date_to):
    """Apply audit-log filters to a select() statement (used by both endpoints)."""
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return stmt


@router.get(
    "/audit-log",
    response_model=AuditLogListResponse,
    dependencies=[Depends(require_admin)],
)
async def get_audit_log(
    user_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    offset: int = 0,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    base = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.user_id)
    )
    base = _apply_audit_filter(
        base, user_id=user_id, action=action, date_from=date_from, date_to=date_to
    )
    base = (
        base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(base)).all()

    cnt = select(func.count(AuditLog.id))
    cnt = _apply_audit_filter(
        cnt, user_id=user_id, action=action, date_from=date_from, date_to=date_to
    )
    total = (await db.execute(cnt)).scalar() or 0

    items = [
        AuditLogItem(
            id=log.id,
            user_id=log.user_id,
            username=username,
            action=log.action,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at,
        )
        for (log, username) in rows
    ]
    return AuditLogListResponse(items=items, total=total)


@router.get(
    "/audit-log/export.csv",
    dependencies=[Depends(require_admin)],
)
async def export_audit_log(
    user_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
):
    base = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.user_id)
    )
    base = _apply_audit_filter(
        base, user_id=user_id, action=action, date_from=date_from, date_to=date_to
    )
    base = base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    rows = (await db.execute(base)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "created_at", "user_id", "username", "action", "ip_address", "details"]
    )
    for (log, username) in rows:
        details_cell = (
            json.dumps(log.details, ensure_ascii=False)
            if log.details is not None
            else ""
        )
        writer.writerow(
            [
                log.id,
                _utc_iso(log.created_at) if log.created_at else "",
                log.user_id if log.user_id is not None else "",
                username or "",
                log.action,
                log.ip_address or "",
                details_cell,
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )
