"""Tests for image_service.get_user_tasks active-list filtering.

A pending task is an uploaded-but-not-started image: the file is on disk and
a DB row exists, but the user has not yet pressed "Удалить фон". Such tasks
must NOT appear in the "Активные задачи" list — otherwise every upload the
user abandons lingers there as «Ожидание» forever (until the stale-pending
cleanup job runs).
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_task import ImageTask
from app.services import image_service


async def _make_task(db: AsyncSession, *, status: str, user_id: int = 1) -> ImageTask:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task = ImageTask(
        id=str(uuid.uuid4()),
        user_id=user_id,
        original_filename="test.png",
        original_ext="png",
        operation="remove_bg",
        status=status,
        progress=100 if status == "ready" else 0,
        hidden=False,
        filename="result.png" if status == "ready" else None,
        file_size=1024 if status == "ready" else None,
        inpaint_method=None,
        error=None,
        created_at=now,
        updated_at=now,
        completed_at=now if status == "ready" else None,
    )
    db.add(task)
    await db.commit()
    return task


@pytest.mark.asyncio
async def test_get_user_tasks_excludes_pending(db_session):
    pending = await _make_task(db_session, status="pending")
    processing = await _make_task(db_session, status="processing")
    ready = await _make_task(db_session, status="ready")
    error = await _make_task(db_session, status="error")

    rows = await image_service.get_user_tasks(user_id=1, db=db_session)
    ids = {r.id for r in rows}

    assert pending.id not in ids, "pending (un-started upload) must not show in active tasks"
    assert processing.id in ids
    assert ready.id in ids
    assert error.id in ids
