"""
File converter API router.

Endpoints
---------
POST   /api/convert/upload                  — upload one or more files (up to 20)
GET    /api/convert/capabilities/{ext}      — supported output formats for an extension
POST   /api/convert/start                   — start a single conversion
POST   /api/convert/batch                   — start multiple conversions at once
GET    /api/convert/status/{task_id}        — poll conversion progress
GET    /api/convert/file/{task_id}          — download the converted file
GET    /api/convert/batch/{batch_id}/zip    — download a batch as ZIP
GET    /api/convert/tasks                   — list active tasks for current user
GET    /api/convert/tasks/history           — list dismissed (hidden) tasks
DELETE /api/convert/task/{task_id}          — dismiss (soft-delete) a single task
DELETE /api/convert/tasks/completed         — dismiss all completed tasks
POST   /api/convert/task/{task_id}/restore  — un-dismiss a dismissed task
DELETE /api/convert/cancel/{task_id}        — cancel an active conversion
GET    /api/convert/quota                   — daily converter quota usage
"""

import json
import logging
import os
import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.limits import UNLIMITED, has_unlimited_quota
from app.dependencies import get_current_user
from app.models.audit import AuditLog
from app.models.user import User
from app.utils.client_ip import get_client_ip
from app.schemas.convert import (
    BatchConvertRequest,
    CapabilitiesResponse,
    ConvertStartRequest,
    ConvertTaskListItem,
    ConvertTaskStatus,
    QuotaResponse,
    UploadResponse,
    MAX_BATCH_SIZE,
)
from app.services import convert_service

logger = logging.getLogger("naturalsk.convert")

router = APIRouter(prefix="/api/convert", tags=["convert"])


# ---------------------------------------------------------------------------
# Helpers / shared guards
# ---------------------------------------------------------------------------


def _require_converter_permission(user: User) -> None:
    """Raise 403 when the user lacks the *converter* permission."""
    if not user.permissions.get("converter", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к конвертеру файлов",
        )


def _get_quota(user: User) -> tuple[int, int]:
    """Return (used, limit) for today's conversions."""
    reset = user.usage_reset_date
    today = date.today()
    used = user.usage_today.get("converter", 0) if reset == today else 0
    limit = UNLIMITED if has_unlimited_quota(user) else user.limits.get("convert_daily", 100)
    return used, limit


def _check_daily_limit(user: User) -> None:
    """Raise 429 when the user has exhausted their daily conversion quota."""
    if has_unlimited_quota(user):
        return
    used, limit = _get_quota(user)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Достигнут дневной лимит конвертаций ({limit} конвертаций/день)",
        )


async def _increment_usage(user: User, db: AsyncSession) -> None:
    """Increment the converter usage counter for today.

    Uses flush (not commit) so the increment participates in the caller's
    transaction.  This prevents TOCTOU races where two concurrent requests
    both pass _check_daily_limit before either commits.
    """
    today = date.today()
    if user.usage_reset_date != today:
        user.usage_today = {"youtube": 0, "converter": 0, "image": 0}
        user.usage_reset_date = today
    # Assign a new dict to trigger SQLAlchemy change detection.
    today_usage = dict(user.usage_today)
    today_usage["converter"] = today_usage.get("converter", 0) + 1
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
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:256],
    )
    db.add(log)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=list[UploadResponse], status_code=status.HTTP_201_CREATED)
async def upload_files(
    request: Request,
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    batch_id: str | None = Query(default=None, description="Optional batch group ID"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UploadResponse]:
    """
    Upload one or more files for later conversion.

    Each file is validated, saved to disk under its own task directory,
    and a ConvertTask row with status="pending" is created.  Returns the
    list of task descriptors the caller can use in subsequent /start calls.

    At most 20 files are accepted per request.
    """
    _require_converter_permission(user)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не выбрано ни одного файла",
        )

    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"За один запрос можно загрузить не более {MAX_BATCH_SIZE} файлов",
        )

    responses: list[UploadResponse] = []

    for upload in files:
        raw_bytes = await upload.read()
        filename = upload.filename or ""

        try:
            sanitized_name, ext, category = convert_service.validate_upload(
                filename=filename,
                content_type=upload.content_type,
                size=len(raw_bytes),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )

        task_id = str(uuid.uuid4())

        # Persist file bytes to disk via the service (runs in a thread to avoid
        # blocking the event loop with synchronous I/O)
        await convert_service.save_upload(task_id, raw_bytes, ext)

        # Create DB row + in-memory cache entry
        task_dict = await convert_service.create_task(
            task_id=task_id,
            user_id=user.id,
            original_filename=sanitized_name,
            original_ext=ext,
            category=category,
            db=db,
            batch_id=batch_id,
        )

        responses.append(
            UploadResponse(
                task_id=task_id,
                original_filename=sanitized_name,
                original_ext=ext,
                category=category,
                file_size=len(raw_bytes),
            )
        )

        logger.info(
            "Upload task %s created by user %d (file=%s category=%s size=%d)",
            task_id,
            user.id,
            sanitized_name,
            category,
            len(raw_bytes),
        )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="convert_upload",
        details={"file_count": len(responses), "batch_id": batch_id},
        request=request,
    )
    await db.commit()

    return responses


@router.get("/capabilities/{ext}", response_model=CapabilitiesResponse)
async def get_capabilities(
    ext: str,
    user: User = Depends(get_current_user),
) -> CapabilitiesResponse:
    """Return the output formats and options available for the given input extension."""
    _require_converter_permission(user)

    try:
        caps = convert_service.get_capabilities(ext.lower().lstrip("."))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return CapabilitiesResponse(**caps)


@router.post("/start", response_model=ConvertTaskStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_conversion(
    body: ConvertStartRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConvertTaskStatus:
    """
    Trigger conversion for a previously uploaded task.

    The task must be in "pending" status and belong to the current user.
    Increments the daily usage counter and launches the conversion as a
    background task.
    """
    _require_converter_permission(user)
    _check_daily_limit(user)

    db_task = await convert_service.get_task_for_user(body.task_id, user.id, db)
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

    # Validate target_format against the category's allowed outputs
    try:
        caps = convert_service.get_capabilities(db_task.original_ext)
    except ValueError:
        caps = {"target_formats": []}

    if body.target_format not in caps["target_formats"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Формат '{body.target_format}' не поддерживается для файлов .{db_task.original_ext}",
        )

    # Persist target_format and options onto the DB row before handing off
    db_task.target_format = body.target_format
    db_task.options = json.dumps(body.options) if body.options else None
    await db.commit()

    await _increment_usage(user, db)

    background_tasks.add_task(
        convert_service.start_conversion,
        task_id=body.task_id,
        target_format=body.target_format,
        options=body.options,
    )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="convert_start",
        details={
            "task_id": body.task_id,
            "target_format": body.target_format,
        },
        request=request,
    )
    await db.commit()

    logger.info(
        "Conversion task %s started by user %d (format=%s)",
        body.task_id,
        user.id,
        body.target_format,
    )

    # Reflect the updated row as a ConvertTaskStatus
    task_dict = convert_service.get_task_status(body.task_id)
    if task_dict is None:
        task_dict = convert_service.row_to_dict(db_task)

    return ConvertTaskStatus(**task_dict)


@router.post("/batch", response_model=list[ConvertTaskStatus], status_code=status.HTTP_202_ACCEPTED)
async def batch_convert(
    body: BatchConvertRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConvertTaskStatus]:
    """
    Trigger conversion for multiple uploaded tasks in one call.

    Each item must refer to a pending task owned by the current user.
    Usage is incremented once per item that is actually started.
    """
    _require_converter_permission(user)

    if not body.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Список задач не может быть пустым",
        )

    results: list[ConvertTaskStatus] = []

    for item in body.items:
        _check_daily_limit(user)

        db_task = await convert_service.get_task_for_user(item.task_id, user.id, db)
        if db_task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Задача {item.task_id} не найдена",
            )

        if db_task.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Задача {item.task_id} уже обрабатывается или завершена (статус: {db_task.status})",
            )

        try:
            caps = convert_service.get_capabilities(db_task.original_ext)
        except ValueError:
            caps = {"target_formats": []}

        if item.target_format not in caps["target_formats"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Формат '{item.target_format}' не поддерживается для файлов .{db_task.original_ext} (задача {item.task_id})",
            )

        db_task.target_format = item.target_format
        db_task.options = json.dumps(item.options) if item.options else None
        await db.commit()

        await _increment_usage(user, db)

        background_tasks.add_task(
            convert_service.start_conversion,
            task_id=item.task_id,
            target_format=item.target_format,
            options=item.options,
        )

        task_dict = convert_service.get_task_status(item.task_id)
        if task_dict is None:
            task_dict = convert_service.row_to_dict(db_task)

        results.append(ConvertTaskStatus(**task_dict))

        logger.info(
            "Batch conversion task %s started by user %d (format=%s)",
            item.task_id,
            user.id,
            item.target_format,
        )

    await _log_audit(
        db=db,
        user_id=user.id,
        action="convert_batch",
        details={"task_count": len(results)},
        request=request,
    )
    await db.commit()

    return results


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(
    user: User = Depends(get_current_user),
) -> QuotaResponse:
    """Return the current user's daily conversion quota usage."""
    _require_converter_permission(user)
    used, limit = _get_quota(user)
    return QuotaResponse(used=used, limit=limit)


@router.get("/tasks", response_model=list[ConvertTaskListItem])
async def list_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConvertTaskListItem]:
    """
    Return the current user's active (non-hidden) conversion tasks.

    Tasks from the last FILE_TTL_HOURS hours are returned, ordered newest
    first.  This endpoint enables the frontend to restore task references
    after a page refresh.
    """
    _require_converter_permission(user)
    rows = await convert_service.get_user_tasks(user_id=user.id, db=db)
    return [ConvertTaskListItem(**convert_service.row_to_dict(row, check_file=True)) for row in rows]


@router.get("/tasks/history", response_model=list[ConvertTaskListItem])
async def list_history_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConvertTaskListItem]:
    """
    Return the current user's dismissed tasks that still have files available.

    Only tasks within the file retention window (hidden=True) are returned,
    so the frontend can offer re-download of dismissed-but-not-yet-expired files.
    """
    _require_converter_permission(user)
    rows = await convert_service.get_hidden_tasks(user_id=user.id, db=db)
    return [ConvertTaskListItem(**convert_service.row_to_dict(row, check_file=True)) for row in rows]


@router.get("/status/{task_id}", response_model=ConvertTaskStatus)
async def get_status(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConvertTaskStatus:
    """Return the current progress of a conversion task."""
    _require_converter_permission(user)

    db_task = await convert_service.get_task_for_user(task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или истекла",
        )

    # Hot-path: check in-memory cache first (active or recently completed)
    task_dict = convert_service.get_task_status(task_id)
    if task_dict is None:
        # Cold-path: build from the DB row (task completed before cache entry)
        task_dict = convert_service.row_to_dict(db_task)

    return ConvertTaskStatus(**task_dict)


@router.get("/file/{task_id}")
async def download_file(
    task_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Stream the converted file to the client.

    Only works once the task status is ``ready``.  The download filename is
    constructed from the original file stem and the target extension.
    """
    _require_converter_permission(user)

    db_task = await convert_service.get_task_for_user(task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или истекла",
        )

    # Merge in-memory progress in case the task is mid-flight
    task_dict = convert_service.get_task_status(task_id)
    if task_dict is None:
        task_dict = convert_service.row_to_dict(db_task)

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

    await _log_audit(
        db=db,
        user_id=user.id,
        action="convert_download",
        details={"task_id": task_id, "filename": output_filename},
        request=request,
    )
    await db.commit()

    logger.info(
        "File download for task %s served to user %d (%s)",
        task_id,
        user.id,
        output_filename,
    )

    return FileResponse(
        path=file_path,
        filename=output_filename,
        media_type="application/octet-stream",
    )


@router.get("/batch/{batch_id}/zip")
async def download_batch_zip(
    batch_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Collect all ready tasks in the batch into a ZIP archive and return it.

    The ZIP is created on-the-fly the first time this endpoint is called for a
    batch; subsequent calls serve the already-created archive.
    """
    _require_converter_permission(user)

    zip_path = await convert_service.create_batch_zip(
        batch_id=batch_id,
        user_id=user.id,
        db=db,
    )

    if zip_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="В этом пакете нет готовых файлов",
        )

    if not os.path.isfile(zip_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ZIP-архив не найден на диске",
        )

    zip_filename = f"batch_{batch_id[:8]}.zip"

    await _log_audit(
        db=db,
        user_id=user.id,
        action="convert_download_zip",
        details={"batch_id": batch_id},
        request=request,
    )
    await db.commit()

    logger.info(
        "Batch ZIP for batch %s served to user %d",
        batch_id,
        user.id,
    )

    return FileResponse(
        path=zip_path,
        filename=zip_filename,
        media_type="application/zip",
    )


@router.delete("/task/{task_id}", response_model=dict)
async def dismiss_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Persistently hide a single conversion task for the current user.

    The task record is kept in the database but will no longer be returned by
    GET /api/convert/tasks.  This prevents hidden tasks from reappearing after
    a page refresh.
    """
    _require_converter_permission(user)

    found = await convert_service.dismiss_task(task_id=task_id, user_id=user.id, db=db)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Convert task %s dismissed by user %d", task_id, user.id)
    return {"ok": True}


@router.delete("/tasks/completed", response_model=dict)
async def dismiss_completed_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Persistently hide all completed tasks (ready, error, cancelled) for the
    current user.

    Returns the number of tasks that were hidden.
    """
    _require_converter_permission(user)

    count = await convert_service.dismiss_completed_tasks(user_id=user.id, db=db)

    logger.info("User %d dismissed %d completed convert tasks", user.id, count)
    return {"dismissed": count}


@router.post("/task/{task_id}/restore", response_model=dict)
async def restore_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Un-dismiss a task, making it reappear in the active task list."""
    _require_converter_permission(user)

    found = await convert_service.restore_task(task_id=task_id, user_id=user.id, db=db)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Convert task %s restored by user %d", task_id, user.id)
    return {"ok": True}


@router.delete("/task/{task_id}/permanent", response_model=dict)
async def delete_task_permanent(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete a task — removes file from disk and record from DB.

    Only works for terminal tasks (ready/error/cancelled).
    """
    _require_converter_permission(user)

    deleted = await convert_service.delete_task_permanent(
        task_id=task_id, user_id=user.id, db=db
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или ещё активна",
        )

    return {"ok": True}


@router.delete("/upload/{task_id}", response_model=dict)
async def delete_pending_upload(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a pending upload that has not started conversion.

    Removes the uploaded file from disk and the task record from the database.
    Only works for tasks with status='pending' and no target_format set.
    """
    _require_converter_permission(user)

    deleted = await convert_service.delete_pending_upload(
        task_id=task_id, user_id=user.id, db=db
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или уже запущена",
        )

    return {"ok": True}


@router.delete("/cancel/{task_id}", response_model=dict)
async def cancel_conversion(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel an active or pending conversion task."""
    _require_converter_permission(user)

    found = await convert_service.cancel_task(task_id=task_id, user_id=user.id, db=db)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Convert task %s cancelled by user %d", task_id, user.id)
    return {"ok": True}
