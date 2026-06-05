"""Multi downloader API router.

POST   /api/multidl/info            — preview metadata
POST   /api/multidl/download        — start a background download
GET    /api/multidl/status/{id}     — poll progress
GET    /api/multidl/file/{id}       — stream finished file
DELETE /api/multidl/cancel/{id}     — cancel active download
GET    /api/multidl/tasks           — user's recent tasks
POST   /api/multidl/retry/{id}      — re-run a failed/cancelled task
DELETE /api/multidl/task/{id}       — dismiss (hide) a task
GET    /api/multidl/quota           — daily quota usage
"""

import logging
import os
import uuid
from datetime import date

import yt_dlp
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.limits import UNLIMITED, has_unlimited_quota
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.multidl import DownloadRequest, DownloadStatus, InfoRequest, InfoResponse, QuotaResponse
from app.services import multidl_service

logger = logging.getLogger("naturalsk.multidl")
router = APIRouter(prefix="/api/multidl", tags=["multidl"])


def _require_permission(user: User) -> None:
    if not user.permissions.get("multidl", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="У вас нет доступа к Multi downloader")


def _get_quota(user: User) -> tuple[int, int]:
    used = user.usage_today.get("multidl", 0) if user.usage_reset_date == date.today() else 0
    limit = UNLIMITED if has_unlimited_quota(user) else user.limits.get("multidl_daily", 50)
    return used, limit


def _check_daily_limit(user: User) -> None:
    if has_unlimited_quota(user):
        return
    used, limit = _get_quota(user)
    if used >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Достигнут дневной лимит загрузок ({limit} загрузок/день)")


async def _increment_usage(user: User, db: AsyncSession) -> None:
    today = date.today()
    if user.usage_reset_date != today:
        user.usage_today = {"youtube": 0, "converter": 0, "image": 0, "multidl": 0}
        user.usage_reset_date = today
    today_usage = dict(user.usage_today)
    today_usage["multidl"] = today_usage.get("multidl", 0) + 1
    user.usage_today = today_usage
    await db.commit()


@router.post("/info", response_model=InfoResponse)
async def get_info(body: InfoRequest, user: User = Depends(get_current_user)) -> InfoResponse:
    _require_permission(user)
    try:
        return await multidl_service.get_info(body.url)
    except TimeoutError:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT,
                            detail="Превышено время ожидания. Попробуйте снова.")
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ("private", "unavailable", "not available", "removed", "deleted")):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Видео недоступно (приватное, удалено или заблокировано)")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Не удалось обработать ссылку. Проверьте, что она ведёт на видео.")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("multidl info error for %s: %s", body.url, exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Непредвиденная ошибка при получении информации")


@router.post("/download", response_model=DownloadStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_download(body: DownloadRequest, background_tasks: BackgroundTasks,
                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> DownloadStatus:
    _require_permission(user)
    _check_daily_limit(user)
    task_id = str(uuid.uuid4())
    shared_file_id = str(uuid.uuid4())
    initial = await multidl_service.create_task(task_id, user.id, body, db)
    await _increment_usage(user, db)
    background_tasks.add_task(multidl_service.download, request=body, task_id=task_id,
                             user_id=user.id, shared_file_id=shared_file_id)
    logger.info("Multidl task %s enqueued by user %d (audio_only=%s)", task_id, user.id, body.audio_only)
    return initial


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(user: User = Depends(get_current_user)) -> QuotaResponse:
    _require_permission(user)
    used, limit = _get_quota(user)
    return QuotaResponse(used=used, limit=limit)


@router.get("/tasks", response_model=list[DownloadStatus])
async def list_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[DownloadStatus]:
    _require_permission(user)
    return await multidl_service.get_user_tasks(user_id=user.id, db=db)


@router.get("/status/{task_id}", response_model=DownloadStatus)
async def get_status(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> DownloadStatus:
    _require_permission(user)
    if await multidl_service.get_task_for_user(task_id, user.id, db) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или истекла")
    task = await multidl_service.get_download_progress(task_id, db)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или истекла")
    return task


@router.get("/file/{task_id}")
async def download_file(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> FileResponse:
    _require_permission(user)
    task = await multidl_service.get_download_progress(task_id, db)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или истекла")
    if task.status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Файл ещё не готов (статус: {task.status})")
    if not task.filename:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Имя файла отсутствует")
    shared_dir = await multidl_service.resolve_shared_file_dir(task_id, user.id, db)
    if shared_dir is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена или файл не готов")
    file_path = os.path.join(shared_dir, task.filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Файл не найден. Возможно, он был удалён по истечении срока хранения.")
    return FileResponse(path=file_path, filename=task.filename, media_type="application/octet-stream")


@router.delete("/cancel/{task_id}", response_model=dict)
async def cancel_download(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    _require_permission(user)
    if await multidl_service.get_task_for_user(task_id, user.id, db) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    if not await multidl_service.cancel_task(task_id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return {"task_id": task_id, "cancelled": True}


@router.delete("/task/{task_id}", response_model=dict)
async def dismiss_task(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    _require_permission(user)
    if not await multidl_service.dismiss_task(task_id=task_id, user_id=user.id, db=db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")
    return {"task_id": task_id, "dismissed": True}


@router.post("/retry/{task_id}", response_model=DownloadStatus, status_code=status.HTTP_202_ACCEPTED)
async def retry_download(task_id: str, background_tasks: BackgroundTasks,
                         user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> DownloadStatus:
    _require_permission(user)
    _check_daily_limit(user)
    orig = await multidl_service.get_task_for_user(task_id, user.id, db)
    if orig is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Исходная задача не найдена")
    current = await multidl_service.get_download_progress(task_id, db)
    if current is None or current.status not in ("error", "cancelled"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Повторить можно только неудачные или отменённые задачи")
    retry_req = DownloadRequest(url=orig.url, title=orig.title, audio_only=orig.audio_only)
    new_id = str(uuid.uuid4())
    shared_file_id = str(uuid.uuid4())
    new_status = await multidl_service.create_task(new_id, user.id, retry_req, db)
    await _increment_usage(user, db)
    background_tasks.add_task(multidl_service.download, request=retry_req, task_id=new_id,
                             user_id=user.id, shared_file_id=shared_file_id)
    return new_status
