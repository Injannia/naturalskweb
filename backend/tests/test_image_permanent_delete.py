"""Tests for image_service.delete_task_permanent."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_task import ImageTask
from app.services import image_service


async def _make_task(
    db: AsyncSession,
    *,
    user_id: int = 1,
    status: str = "ready",
    hidden: bool = False,
) -> ImageTask:
    task = ImageTask(
        id=str(uuid.uuid4()),
        user_id=user_id,
        original_filename="test.png",
        original_ext="png",
        operation="remove_bg",
        status=status,
        progress=100 if status == "ready" else 0,
        hidden=hidden,
        filename="result.png" if status == "ready" else None,
        file_size=1024 if status == "ready" else None,
        inpaint_method=None,
        error=None,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None) if status == "ready" else None,
    )
    db.add(task)
    await db.commit()
    return task


@pytest.mark.asyncio
async def test_delete_permanent_happy_path(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    task = await _make_task(db_session)
    task_dir = tmp_path / task.id
    task_dir.mkdir()
    (task_dir / "result.png").write_bytes(b"\x89PNG\x00")

    result = await image_service.delete_task_permanent(
        task_id=task.id, user_id=1, db=db_session,
    )
    assert result is True
    assert not task_dir.exists()
    found = (await db_session.execute(select(ImageTask).where(ImageTask.id == task.id))).scalar_one_or_none()
    assert found is None


@pytest.mark.asyncio
async def test_delete_permanent_wrong_user(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    task = await _make_task(db_session, user_id=1)
    result = await image_service.delete_task_permanent(
        task_id=task.id, user_id=2, db=db_session,
    )
    assert result is False
    found = (await db_session.execute(select(ImageTask).where(ImageTask.id == task.id))).scalar_one_or_none()
    assert found is not None


@pytest.mark.asyncio
async def test_delete_permanent_nonexistent(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    result = await image_service.delete_task_permanent(
        task_id="does-not-exist", user_id=1, db=db_session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_delete_permanent_rejects_non_terminal_status(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service.settings, "UPLOAD_DIR", str(tmp_path))
    task = await _make_task(db_session, status="processing")
    result = await image_service.delete_task_permanent(
        task_id=task.id, user_id=1, db=db_session,
    )
    assert result is False
