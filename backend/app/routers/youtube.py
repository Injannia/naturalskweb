"""
YouTube downloader API router.

Endpoints
---------
POST   /api/youtube/info              — fetch video / playlist metadata
POST   /api/youtube/download          — start a background download
GET    /api/youtube/status/{task_id}  — poll download progress
GET    /api/youtube/file/{task_id}    — stream the finished file
DELETE /api/youtube/cancel/{task_id} — cancel an active download
GET    /api/youtube/quota             — current user's daily quota usage
POST   /api/youtube/retry/{task_id}  — re-run a failed/cancelled task
"""

import logging
import os
import uuid
from datetime import date

import yt_dlp
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.limits import UNLIMITED, has_unlimited_quota
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.youtube import (
    DownloadRequest,
    DownloadStatus,
    InfoResponse,
    PlaylistInfo,
    QuotaResponse,
    VideoInfo,
    VideoInfoRequest,
)
from app.services import youtube_service
from app.utils.youtube_helpers import extract_video_id, compute_playlist_cache_key, locate_task_file

logger = logging.getLogger("naturalsk.youtube")

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


# ---------------------------------------------------------------------------
# Helpers / shared guards
# ---------------------------------------------------------------------------


def _require_youtube_permission(user: User) -> None:
    """Raise 403 when the user lacks the *youtube* permission."""
    if not user.permissions.get("youtube", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к YouTube загрузчику",
        )


def _get_quota(user: User) -> tuple[int, int]:
    """Return (used, limit) for today's youtube downloads."""
    reset = user.usage_reset_date
    today = date.today()
    used = user.usage_today.get("youtube", 0) if reset == today else 0
    limit = UNLIMITED if has_unlimited_quota(user) else user.limits.get("youtube_daily", 50)
    return used, limit


def _check_daily_limit(user: User) -> None:
    """Raise 429 when the user has exhausted their daily download quota."""
    if has_unlimited_quota(user):
        return
    used, limit = _get_quota(user)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Достигнут дневной лимит загрузок ({limit} загрузок/день)",
        )


async def _increment_usage(user: User, db: AsyncSession) -> None:
    """Atomically increment the youtube usage counter for today."""
    today = date.today()
    if user.usage_reset_date != today:
        user.usage_today = {"youtube": 0, "converter": 0, "image": 0}
        user.usage_reset_date = today
    # NOTE: We assign a new dict object to trigger SQLAlchemy change detection.
    # Do NOT mutate user.usage_today in-place — changes won't be persisted.
    today_usage = dict(user.usage_today)
    today_usage["youtube"] = today_usage.get("youtube", 0) + 1
    user.usage_today = today_usage
    await db.commit()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/info", response_model=InfoResponse)
async def get_info(
    body: VideoInfoRequest,
    user: User = Depends(get_current_user),
) -> InfoResponse:
    """
    Fetch metadata for a YouTube video or playlist.

    Returns an :class:`InfoResponse` wrapper with ``type`` set to ``"video"``
    or ``"playlist"`` and the corresponding nested object populated.
    """
    _require_youtube_permission(user)

    try:
        result = await youtube_service.get_video_info(body.url)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Превышено время ожидания при получении информации о видео. Попробуйте снова.",
        )
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc).lower()
        if any(kw in msg for kw in ("private", "unavailable", "not available", "removed", "deleted")):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Видео недоступно (приватное, удалено или заблокировано в вашем регионе)",
            )
        logger.error("yt-dlp DownloadError for %s: %s", body.url, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось получить информацию о видео",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error fetching info for %s: %s", body.url, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Непредвиденная ошибка при получении информации о видео",
        )

    # Enforce playlist size limit
    if isinstance(result, PlaylistInfo) and result.video_count > youtube_service.MAX_PLAYLIST_VIDEOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Плейлист превышает максимальный размер в {youtube_service.MAX_PLAYLIST_VIDEOS} видео",
        )

    # Enforce per-video duration limit for single videos
    if isinstance(result, VideoInfo):
        if result.duration > youtube_service.MAX_VIDEO_DURATION_SECONDS:
            hours = youtube_service.MAX_VIDEO_DURATION_SECONDS // 3600
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Длительность видео превышает лимит в {hours} ч.",
            )

    # Wrap in discriminated union so the frontend can branch on `type`.
    if isinstance(result, PlaylistInfo):
        return InfoResponse(type="playlist", playlist=result)
    return InfoResponse(type="video", video=result)


@router.post("/download", response_model=DownloadStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_download(
    body: DownloadRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DownloadStatus:
    """
    Enqueue a download job and immediately return a task_id for polling.

    When a matching ready task exists and ``force_download`` is False, the
    response is returned immediately with ``status="ready"`` and
    ``cached=True`` — no background job is started.

    The actual download runs as a FastAPI background task for cache misses.
    """
    _require_youtube_permission(user)
    _check_daily_limit(user)

    # ------------------------------------------------------------------
    # Compute the cache lookup key for this request
    # ------------------------------------------------------------------
    is_playlist = youtube_service._is_playlist_url(body.url)

    if is_playlist:
        # For playlists we need the list of video IDs.  If the caller
        # supplied an explicit selection, use it directly; otherwise we
        # cannot compute a cache key without an additional yt-dlp call,
        # so skip the cache lookup when video_ids are not specified.
        if body.video_ids:
            cache_key: str | None = compute_playlist_cache_key(
                body.video_ids, body.format, body.quality
            )
        else:
            cache_key = None
    else:
        cache_key = extract_video_id(body.url)

    # ------------------------------------------------------------------
    # Cache lookup (skipped when force_download=True or key unavailable)
    # ------------------------------------------------------------------
    if cache_key and not body.force_download:
        cached_sf = await youtube_service.find_cached_shared_file(
            video_id=cache_key,
            fmt=body.format,
            quality=body.quality,
            db=db,
        )
        if cached_sf is not None:
            task_id = str(uuid.uuid4())
            cached_status = await youtube_service.create_cached_task(
                task_id=task_id,
                user_id=user.id,
                request=body,
                shared_file=cached_sf,
                video_id=cache_key,
                db=db,
            )
            await _increment_usage(user, db)
            logger.info(
                "Cache hit: task %s for user %d reuses SharedFile %s (format=%s quality=%s)",
                task_id, user.id, cached_sf.id, body.format, body.quality,
            )
            return cached_status

    # ------------------------------------------------------------------
    # In-progress deduplication — join an existing active download
    # ------------------------------------------------------------------
    if cache_key:
        in_progress = await youtube_service.find_in_progress_task(
            video_id=cache_key,
            fmt=body.format,
            quality=body.quality,
            db=db,
        )
        if in_progress is not None:
            task_id = str(uuid.uuid4())
            watcher_status = await youtube_service.create_task(
                task_id=task_id,
                user_id=user.id,
                request=body,
                db=db,
                video_id=cache_key,
            )

            await _increment_usage(user, db)

            background_tasks.add_task(
                youtube_service.wait_for_source_task,
                watcher_task_id=task_id,
                source_task_id=in_progress.id,
            )

            logger.info(
                "Dedup: task %s for user %d joins in-progress task %s (format=%s quality=%s)",
                task_id,
                user.id,
                in_progress.id,
                body.format,
                body.quality,
            )
            return watcher_status

    # ------------------------------------------------------------------
    # Cache miss — start a real download
    # ------------------------------------------------------------------
    task_id = str(uuid.uuid4())
    shared_file_id = str(uuid.uuid4())
    initial_status = await youtube_service.create_task(
        task_id=task_id,
        user_id=user.id,
        request=body,
        db=db,
        video_id=cache_key,
    )

    await _increment_usage(user, db)

    background_tasks.add_task(
        youtube_service.download_video,
        request=body,
        task_id=task_id,
        user_id=user.id,
        shared_file_id=shared_file_id,
    )

    logger.info(
        "Download task %s enqueued by user %d (format=%s quality=%s cache_key=%s shared_file=%s)",
        task_id, user.id, body.format, body.quality, cache_key, shared_file_id,
    )

    return initial_status


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(
    user: User = Depends(get_current_user),
) -> QuotaResponse:
    """Return the current user's daily download quota usage."""
    _require_youtube_permission(user)
    used, limit = _get_quota(user)
    return QuotaResponse(used=used, limit=limit)


@router.get("/tasks", response_model=list[DownloadStatus])
async def list_tasks(
    user: User = Depends(get_current_user),
) -> list[DownloadStatus]:
    """
    Return the current user's recent download tasks.

    Tasks from the last FILE_TTL_HOURS hours are returned, ordered newest
    first, capped at 50 entries.  This endpoint enables the frontend to
    restore task references after a page refresh.
    """
    _require_youtube_permission(user)
    return await youtube_service.get_user_tasks(user_id=user.id)


@router.get("/tasks/history", response_model=list[DownloadStatus])
async def list_history_tasks(
    user: User = Depends(get_current_user),
) -> list[DownloadStatus]:
    """
    Return the current user's dismissed tasks that still have files available.

    Only tasks within the file retention window (hidden=True) are returned,
    so the frontend can offer re-download of dismissed-but-not-yet-expired files.
    """
    _require_youtube_permission(user)
    return await youtube_service.get_hidden_tasks(user_id=user.id)


@router.get("/status/{task_id}", response_model=DownloadStatus)
async def get_status(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DownloadStatus:
    """Return the current progress of a download task."""
    _require_youtube_permission(user)

    db_task = await youtube_service.get_task_for_user(task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или истекла",
        )

    task = await youtube_service.get_download_progress(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или истекла",
        )
    return task


@router.get("/file/{task_id}")
async def download_file(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Stream the finished file to the client.

    Only works once the task status is ``ready``.

    For all tasks the file is served from the SharedFile directory
    (``uploads/{shared_file_id}/``), resolved via :func:`resolve_shared_file_dir`.
    """
    _require_youtube_permission(user)

    task = await youtube_service.get_download_progress(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или истекла",
        )

    if task.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Файл ещё не готов (текущий статус: {task.status})",
        )

    if not task.filename:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Задача завершена, но имя файла отсутствует",
        )

    # Resolve the shared file directory for this task.
    shared_file_dir = await youtube_service.resolve_shared_file_dir(task_id, user.id, db)
    if shared_file_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или файл ещё не готов",
        )

    file_path = locate_task_file(shared_file_dir, task.filename)

    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл не найден на диске. Возможно, он был удалён по истечении срока хранения.",
        )

    return FileResponse(
        path=file_path,
        filename=task.filename,
        media_type="application/octet-stream",
    )


@router.delete("/cancel/{task_id}", response_model=dict)
async def cancel_download(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel an active download task."""
    _require_youtube_permission(user)

    db_task = await youtube_service.get_task_for_user(task_id, user.id, db)
    if db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    existed = await youtube_service.cancel_task(task_id)
    if not existed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Download task %s cancelled by user %d", task_id, user.id)
    return {"task_id": task_id, "cancelled": True}


@router.post("/task/{task_id}/restore", response_model=dict)
async def restore_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """
    Un-dismiss a task, making it reappear in the active task list.
    """
    _require_youtube_permission(user)

    found = await youtube_service.restore_task(task_id=task_id, user_id=user.id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Task %s restored by user %d", task_id, user.id)
    return {"task_id": task_id, "restored": True}


@router.delete("/task/{task_id}/permanent", response_model=dict)
async def delete_task_permanent(
    task_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Permanently delete a download task — removes file from disk and record from DB.

    Only works for terminal tasks (ready/error/cancelled).
    Handles cache relationships safely.
    """
    _require_youtube_permission(user)

    deleted = await youtube_service.delete_task_permanent(
        task_id=task_id, user_id=user.id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или ещё активна",
        )

    logger.info("Task %s permanently deleted by user %d", task_id, user.id)
    return {"ok": True}


@router.delete("/task/{task_id}", response_model=dict)
async def dismiss_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """
    Persistently hide a single download task for the current user.

    The task record is kept in the database but will no longer be returned by
    GET /api/youtube/tasks.  This prevents hidden tasks from reappearing after
    a page refresh.
    """
    _require_youtube_permission(user)

    found = await youtube_service.dismiss_task(task_id=task_id, user_id=user.id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена",
        )

    logger.info("Task %s dismissed by user %d", task_id, user.id)
    return {"task_id": task_id, "dismissed": True}


@router.delete("/tasks/completed", response_model=dict)
async def dismiss_completed_tasks(
    user: User = Depends(get_current_user),
) -> dict:
    """
    Persistently hide all completed tasks (ready, error, cancelled) for the
    current user.

    Returns the number of tasks that were hidden.
    """
    _require_youtube_permission(user)

    count = await youtube_service.dismiss_completed_tasks(user_id=user.id)

    logger.info("User %d dismissed %d completed tasks", user.id, count)
    return {"dismissed": count}


@router.post("/retry/{task_id}", response_model=DownloadStatus, status_code=status.HTTP_202_ACCEPTED)
async def retry_download(
    task_id: str,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DownloadStatus:
    """
    Create a new download task with the same parameters as a failed/cancelled task.

    Only tasks in ``error`` or ``cancelled`` state can be retried.
    """
    _require_youtube_permission(user)
    _check_daily_limit(user)

    orig_db_task = await youtube_service.get_task_for_user(task_id, user.id, db)
    if orig_db_task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Исходная задача не найдена или истекла",
        )

    original = await youtube_service.get_download_progress(task_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Исходная задача не найдена или истекла",
        )

    if original.status not in ("error", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Повторить можно только неудачные или отменённые задачи (текущий статус: {original.status})",
        )

    if not original.url or not original.format or not original.quality:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В исходной задаче отсутствуют параметры, необходимые для повтора",
        )

    retry_request = DownloadRequest(
        url=original.url,
        title=original.title,
        format=original.format,  # type: ignore[arg-type]
        quality=original.quality,  # type: ignore[arg-type]
        video_ids=original.video_ids,
    )

    cache_key: str | None = None
    if retry_request.video_ids:
        cache_key = compute_playlist_cache_key(
            retry_request.video_ids, retry_request.format, retry_request.quality
        )
    else:
        cache_key = extract_video_id(retry_request.url)

    # ------------------------------------------------------------------
    # Cache lookup — serve from an existing ready task if available
    # ------------------------------------------------------------------
    if cache_key:
        cached_sf = await youtube_service.find_cached_shared_file(
            video_id=cache_key,
            fmt=retry_request.format,
            quality=retry_request.quality,
            db=db,
        )
        if cached_sf is not None:
            new_task_id = str(uuid.uuid4())
            cached_status = await youtube_service.create_cached_task(
                task_id=new_task_id,
                user_id=user.id,
                request=retry_request,
                shared_file=cached_sf,
                video_id=cache_key,
                db=db,
            )
            await _increment_usage(user, db)
            logger.info(
                "Retry cache hit: task %s for user %d reuses SharedFile %s (original=%s)",
                new_task_id, user.id, cached_sf.id, task_id,
            )
            return cached_status

    # ------------------------------------------------------------------
    # In-progress deduplication — join an existing active download
    # ------------------------------------------------------------------
    if cache_key:
        in_progress = await youtube_service.find_in_progress_task(
            video_id=cache_key,
            fmt=retry_request.format,
            quality=retry_request.quality,
            db=db,
        )
        if in_progress is not None:
            new_task_id = str(uuid.uuid4())
            watcher_status = await youtube_service.create_task(
                task_id=new_task_id,
                user_id=user.id,
                request=retry_request,
                db=db,
                video_id=cache_key,
            )

            await _increment_usage(user, db)

            background_tasks.add_task(
                youtube_service.wait_for_source_task,
                watcher_task_id=new_task_id,
                source_task_id=in_progress.id,
            )

            logger.info(
                "Retry dedup: task %s for user %d joins in-progress task %s (original=%s)",
                new_task_id,
                user.id,
                in_progress.id,
                task_id,
            )
            return watcher_status

    # ------------------------------------------------------------------
    # Cache miss — start a fresh download
    # ------------------------------------------------------------------
    new_task_id = str(uuid.uuid4())
    shared_file_id = str(uuid.uuid4())
    new_status = await youtube_service.create_task(
        task_id=new_task_id,
        user_id=user.id,
        request=retry_request,
        db=db,
        video_id=cache_key,
    )

    await _increment_usage(user, db)

    background_tasks.add_task(
        youtube_service.download_video,
        request=retry_request,
        task_id=new_task_id,
        user_id=user.id,
        shared_file_id=shared_file_id,
    )

    logger.info(
        "Retry task %s created by user %d for original task %s (shared_file=%s)",
        new_task_id, user.id, task_id, shared_file_id,
    )

    return new_status


# _locate_file is now locate_task_file, imported from app.utils.youtube_helpers
