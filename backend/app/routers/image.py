"""
Image processing API router.

Endpoints
---------
POST   /api/image/upload                  — upload an image for processing
GET    /api/image/preview/{task_id}       — preview the uploaded image
POST   /api/image/remove-bg               — remove background (rembg)
POST   /api/image/remove-watermark        — remove watermark (OpenCV inpaint)
GET    /api/image/status/{task_id}        — poll task progress
GET    /api/image/result/{task_id}        — download processed full-res image
GET    /api/image/preview-result/{task_id} — download result preview (800px)
GET    /api/image/quota                   — daily image processing quota
GET    /api/image/tasks                   — list active (non-hidden) tasks
GET    /api/image/tasks/history           — list hidden tasks
DELETE /api/image/task/{task_id}          — dismiss (soft-delete) a task
DELETE /api/image/tasks/completed         — dismiss all terminal tasks
POST   /api/image/task/{task_id}/restore  — un-dismiss a task
"""

import asyncio
import logging
import os
import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.image import (
    ImageQuotaResponse,
    ImageTaskListItem,
    ImageTaskStatus,
    ImageUploadResponse,
    RemoveBgRequest,
    RemoveWatermarkRequest,
)
from app.services import image_service

logger = logging.getLogger("naturalsk.image")

router = APIRouter(prefix="/api/image", tags=["image"])


# ---------------------------------------------------------------------------
# Helpers / shared guards
# ---------------------------------------------------------------------------


def _require_image_permission(user: User) -> None:
    """Raise 403 when the user lacks the *image* permission."""
    if not user.permissions.get("image", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к обработке изображений",
        )


def _get_quota(user: User) -> tuple[int, int]:
    """Return (used, limit) for today's image processing operations."""
    reset = user.usage_reset_date
    today = date.today()
    used = user.usage_today.get("image", 0) if reset == today else 0
    limit = user.limits.get("image_daily", 100)
    return used, limit


def _check_daily_limit(user: User) -> None:
    """Raise 429 when the user has exhausted their daily image quota."""
    used, limit = _get_quota(user)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Достигнут дневной лимит обработки изображений ({limit} операций/день)",
        )


async def _increment_usage(user: User, db: AsyncSession) -> None:
    """Increment the image usage counter for today.

    Uses flush (not commit) so the increment participates in the caller's
    transaction.
    """
    today = date.today()
    if user.usage_reset_date != today:
        user.usage_today = {"youtube": 0, "converter": 0, "image": 0}
        user.usage_reset_date = today
    # Assign a new dict to trigger SQLAlchemy change detection.
    today_usage = dict(user.usage_today)
    today_usage["image"] = today_usage.get("image", 0) + 1
    user.usage_today = today_usage
    await db.flush()
    await db.refresh(user)


async def _log_audit(
    db: AsyncSession,
    user_id: int,
    action: str,
    details: dict,
    request: Request,
) -> None:
    """Append an audit log entry to the current session (no commit — caller commits)."""
    log = AuditLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", "")[:256],
    )
    db.add(log)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    request: Request,
    file: UploadFile,
    operation: str = Query(..., description="Operation: 'remove_bg' or 'remove_watermark'"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImageUploadResponse:
    """
    Upload a single image for later processing.

    The file is validated, saved to disk under its own task directory,
    and an ImageTask row with status="pending" is created.  A preview
    thumbnail is generated for the frontend canvas.
    """
    _require_image_permission(user)

    if operation not in ("remove_bg", "remove_watermark"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Параметр operation должен быть 'remove_bg' или 'remove_watermark'",
        )

    raw_bytes = await file.read()
    filename = file.filename or ""

    try:
        sanitized_name, ext = image_service.validate_image_upload(
            filename=filename,
            content_type=file.content_type,
            size=len(raw_bytes),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    task_id = str(uuid.uuid4())

    # Persist file bytes to disk
    saved_path = await image_service.save_upload(task_id, raw_bytes, ext)

    # Generate input preview
    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    await asyncio.to_thread(image_service._generate_preview, saved_path, task_dir)

    # Create DB row + in-memory cache entry
    task_dict = await image_service.create_task(
        task_id=task_id,
        user_id=user.id,
        original_filename=sanitized_name,
        original_ext=ext,
        operation=operation,
        db=db,
    )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="image_upload",
        details={"task_id": task_id, "operation": operation, "filename": sanitized_name},
        request=request,
    )
    await db.commit()

    logger.info(
        "Image upload task %s created by user %d (file=%s op=%s size=%d)",
        task_id,
        user.id,
        sanitized_name,
        operation,
        len(raw_bytes),
    )

    return ImageUploadResponse(
        task_id=task_id,
        original_filename=sanitized_name,
        original_ext=ext,
        file_size=len(raw_bytes),
    )


@router.get("/preview/{task_id}")
async def get_preview(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Return the input preview image (800px thumbnail)."""
    _require_image_permission(user)

    db_task = await image_service.get_task_for_user(task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    # Find the preview file (starts with "preview_")
    preview_path = _find_preview(task_dir)
    if preview_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Превью не найдено",
        )

    return FileResponse(
        path=preview_path,
        media_type="image/jpeg",
    )


@router.post("/remove-bg", response_model=ImageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
async def remove_background(
    body: RemoveBgRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImageTaskStatus:
    """
    Launch background removal for a previously uploaded image task.

    The task must be in "pending" status and belong to the current user.
    """
    _require_image_permission(user)
    _check_daily_limit(user)

    db_task = await image_service.get_task_for_user(body.task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    if db_task.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Задача уже обрабатывается или завершена (статус: {db_task.status})",
        )

    if db_task.operation != "remove_bg":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Эта задача не предназначена для удаления фона",
        )

    await _increment_usage(user, db)

    background_tasks.add_task(
        image_service.remove_background,
        task_id=body.task_id,
    )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="image_remove_bg",
        details={"task_id": body.task_id},
        request=request,
    )
    await db.commit()

    logger.info(
        "Background removal task %s started by user %d",
        body.task_id,
        user.id,
    )

    task_dict = image_service.get_task_status(body.task_id)
    if task_dict is None:
        task_dict = image_service.row_to_dict(db_task)

    return ImageTaskStatus(**task_dict)


@router.post("/remove-watermark", response_model=ImageTaskStatus, status_code=status.HTTP_202_ACCEPTED)
async def remove_watermark(
    body: RemoveWatermarkRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImageTaskStatus:
    """
    Launch watermark removal for a previously uploaded image task.

    The task must be in "pending" status and belong to the current user.
    A non-empty mask must be provided.
    """
    _require_image_permission(user)
    _check_daily_limit(user)

    if not body.mask:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Маска не может быть пустой — отметьте область водяного знака",
        )

    db_task = await image_service.get_task_for_user(body.task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    if db_task.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Задача уже обрабатывается или завершена (статус: {db_task.status})",
        )

    if db_task.operation != "remove_watermark":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Эта задача не предназначена для удаления водяного знака",
        )

    await _increment_usage(user, db)

    # Convert mask shapes to dicts for the service layer
    mask_dicts = [shape.model_dump() for shape in body.mask]

    background_tasks.add_task(
        image_service.remove_watermark,
        task_id=body.task_id,
        mask_shapes=mask_dicts,
        inpaint_method=body.inpaint_method,
    )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="image_remove_watermark",
        details={
            "task_id": body.task_id,
            "inpaint_method": body.inpaint_method,
            "mask_count": len(body.mask),
        },
        request=request,
    )
    await db.commit()

    logger.info(
        "Watermark removal task %s started by user %d (method=%s)",
        body.task_id,
        user.id,
        body.inpaint_method,
    )

    task_dict = image_service.get_task_status(body.task_id)
    if task_dict is None:
        task_dict = image_service.row_to_dict(db_task)

    return ImageTaskStatus(**task_dict)


@router.get("/status/{task_id}", response_model=ImageTaskStatus)
async def get_status(
    task_id: str,
    user: User = Depends(get_current_user),
) -> ImageTaskStatus:
    """Return the current progress of an image processing task."""
    _require_image_permission(user)

    # Hot-path: check in-memory cache first (avoids DB during processing)
    task_dict = image_service.get_task_status(task_id)
    if task_dict is not None:
        return ImageTaskStatus(**task_dict)

    # Cold-path: task not in cache, use own session to avoid contention
    async with async_session() as db:
        db_task = await image_service.get_task_for_user(task_id, user.id, db)
        if db_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена или истекла",
            )
        task_dict = image_service.row_to_dict(db_task)
    return ImageTaskStatus(**task_dict)


@router.get("/result/{task_id}")
async def download_result(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Stream the processed full-resolution image to the client.

    Only works once the task status is ``ready``.
    """
    _require_image_permission(user)

    db_task = await image_service.get_task_for_user(task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или истекла",
        )

    task_dict = image_service.get_task_status(task_id)
    if task_dict is None:
        task_dict = image_service.row_to_dict(db_task)

    if task_dict["status"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Файл ещё не готов (текущий статус: {task_dict['status']})",
        )

    output_filename = task_dict.get("filename")
    if not output_filename:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Задача завершена, но имя файла отсутствует",
        )

    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    file_path = os.path.join(task_dir, output_filename)

    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл не найден на диске. Возможно, он был удалён по истечении срока хранения.",
        )

    # Build a user-friendly download name
    stem = os.path.splitext(db_task.original_filename)[0]
    download_name = f"{stem}_processed.png"

    await _log_audit(
        db=db,
        user_id=user.id,
        action="image_download",
        details={"task_id": task_id, "filename": output_filename},
        request=request,
    )
    await db.commit()

    logger.info(
        "Image result download for task %s served to user %d",
        task_id,
        user.id,
    )

    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/octet-stream",
    )


@router.get("/preview-result/{task_id}")
async def get_result_preview(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Return the result preview image (800px thumbnail)."""
    _require_image_permission(user)

    db_task = await image_service.get_task_for_user(task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    task_dict = image_service.get_task_status(task_id)
    if task_dict is None:
        task_dict = image_service.row_to_dict(db_task)

    if task_dict["status"] != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Результат ещё не готов (текущий статус: {task_dict['status']})",
        )

    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)

    # The result preview is generated after the result file.
    # Find the *last* preview file (there may be an input preview too).
    result_filename = task_dict.get("filename")
    if not result_filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл результата не найден",
        )

    # Find preview files, pick the one created after the result
    preview_path = _find_result_preview(task_dir, result_filename)
    if preview_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Превью результата не найдено",
        )

    return FileResponse(
        path=preview_path,
        media_type="image/jpeg",
    )


@router.get("/quota", response_model=ImageQuotaResponse)
async def get_quota(
    user: User = Depends(get_current_user),
) -> ImageQuotaResponse:
    """Return the current user's daily image processing quota usage."""
    _require_image_permission(user)
    used, limit = _get_quota(user)
    return ImageQuotaResponse(used=used, limit=limit)


@router.get("/tasks", response_model=list[ImageTaskListItem])
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImageTaskListItem]:
    """
    Return the current user's active (non-hidden) image tasks.

    Tasks from the last FILE_TTL_HOURS hours are returned, ordered newest first.
    """
    _require_image_permission(user)
    rows = await image_service.get_user_tasks(user_id=user.id, db=db)
    return [ImageTaskListItem(**image_service.row_to_dict(row, check_file=True)) for row in rows]


@router.get("/tasks/history", response_model=list[ImageTaskListItem])
async def list_history_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImageTaskListItem]:
    """
    Return the current user's dismissed image tasks that still have files available.
    """
    _require_image_permission(user)
    rows = await image_service.get_hidden_tasks(user_id=user.id, db=db)
    return [ImageTaskListItem(**image_service.row_to_dict(row, check_file=True)) for row in rows]


@router.delete("/task/{task_id}", response_model=dict)
async def dismiss_task(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Persistently hide a single image task for the current user."""
    _require_image_permission(user)

    found = await image_service.dismiss_task(task_id=task_id, user_id=user.id, db=db)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Image task %s dismissed by user %d", task_id, user.id)
    return {"detail": "ok"}


@router.delete("/tasks/completed", response_model=dict)
async def dismiss_completed_tasks(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Persistently hide all completed image tasks (ready, error) for the current user."""
    _require_image_permission(user)

    count = await image_service.dismiss_completed_tasks(user_id=user.id, db=db)

    logger.info("User %d dismissed %d completed image tasks", user.id, count)
    return {"dismissed": count}


@router.post("/task/{task_id}/restore", response_model=dict)
async def restore_task(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Un-dismiss a task, making it reappear in the active task list."""
    _require_image_permission(user)

    found = await image_service.restore_task(task_id=task_id, user_id=user.id, db=db)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Image task %s restored by user %d", task_id, user.id)
    return {"detail": "ok"}


@router.delete("/task/{task_id}/permanent", response_model=dict)
async def delete_task_permanent(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete an image task — removes files from disk and DB record.

    Only works for terminal tasks (ready/error).
    """
    _require_image_permission(user)

    deleted = await image_service.delete_task_permanent(
        task_id=task_id, user_id=user.id, db=db,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или ещё активна",
        )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="image_delete_permanent",
        details={"task_id": task_id},
        request=request,
    )
    await db.commit()

    logger.info("Image task %s permanently deleted by user %d", task_id, user.id)
    return {"detail": "ok"}


# ---------------------------------------------------------------------------
# File lookup helpers
# ---------------------------------------------------------------------------


def _list_previews_by_mtime(task_dir: str) -> list[str]:
    """Return preview file paths sorted by mtime ascending (oldest first).

    Preview filenames are ``preview_{uuid}.jpg`` — UUID hex is random, so
    lexicographic order does not correlate with creation time. Always sort
    by mtime: input preview is written first (at upload), result preview
    later (at end of processing).
    """
    if not os.path.isdir(task_dir):
        return []
    names = [n for n in os.listdir(task_dir) if n.startswith("preview_")]
    paths = [os.path.join(task_dir, n) for n in names]
    paths.sort(key=os.path.getmtime)
    return paths


def _find_preview(task_dir: str) -> str | None:
    """Return the input preview — the oldest ``preview_*.jpg`` in task_dir."""
    previews = _list_previews_by_mtime(task_dir)
    return previews[0] if previews else None


def _find_result_preview(task_dir: str, result_filename: str) -> str | None:
    """Return the result preview — the newest ``preview_*.jpg`` in task_dir.

    Requires at least two previews (input + result) OR a single preview
    created after the result file (e.g. when the input preview was
    cleaned up).
    """
    previews = _list_previews_by_mtime(task_dir)
    if len(previews) >= 2:
        return previews[-1]
    if len(previews) == 1:
        result_path = os.path.join(task_dir, result_filename)
        if os.path.isfile(result_path):
            if os.path.getmtime(previews[0]) >= os.path.getmtime(result_path):
                return previews[0]
    return None
