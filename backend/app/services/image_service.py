"""
Image processing service.

Responsibilities
----------------
* Validate and persist uploaded image files to disk.
* Execute background removal (rembg) and watermark removal (OpenCV inpaint)
  in background threads via asyncio.to_thread.
* Maintain an in-memory task dict for high-frequency progress updates,
  persisting only at meaningful status transitions to SQLite.
* Provide CRUD helpers mirroring the convert_service pattern.

Design note — progress storage
------------------------------
Image processing operations are relatively fast but we still keep an
in-memory dict (_active_tasks) for the hot-path and write to the DB only at
status transitions (pending -> processing -> ready / error).
Progress percentage is lost on restart; the terminal state survives.
"""

import asyncio
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.image_task import ImageTask
from app.schemas.image import ALLOWED_IMAGE_EXTS, MAX_IMAGE_SIZE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = frozenset({"ready", "error"})
EVICT_DELAY_SECONDS = 30

# ---------------------------------------------------------------------------
# In-memory task cache
# ---------------------------------------------------------------------------

_active_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Lazy-loaded rembg session
# ---------------------------------------------------------------------------

_rembg_session = None
_rembg_lock = threading.Lock()


def _get_rembg_session():
    """Thread-safe lazy initialisation of the rembg u2netp session."""
    global _rembg_session
    with _rembg_lock:
        if _rembg_session is None:
            from rembg import new_session
            _rembg_session = new_session("u2netp")
            logger.info("rembg u2netp session initialised")
        return _rembg_session


# ---------------------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------------------

_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename(name: str) -> str:
    """Strip characters that are invalid in file/directory names."""
    return _UNSAFE_NAME_RE.sub("_", name).strip(" .")[:200]


def validate_image_upload(
    filename: str, content_type: str | None, size: int
) -> tuple[str, str]:
    """Validate an incoming image upload.

    Parameters
    ----------
    filename:
        Original client-supplied filename.
    content_type:
        MIME type from the upload (may be None or unreliable).
    size:
        File size in bytes.

    Returns
    -------
    tuple[str, str]
        ``(sanitized_filename, ext)``

    Raises
    ------
    ValueError
        On unsupported extension or oversized file.
    """
    if not filename or not filename.strip():
        raise ValueError("Filename must not be empty")

    sanitized = _sanitize_filename(filename)
    if not sanitized:
        raise ValueError("Filename is invalid after sanitization")

    _, raw_ext = os.path.splitext(sanitized)
    ext = raw_ext.lstrip(".").lower()

    if ext not in ALLOWED_IMAGE_EXTS:
        raise ValueError(f"Unsupported image type: .{ext}")

    if size > MAX_IMAGE_SIZE:
        raise ValueError(
            f"File size {size} bytes exceeds the maximum of {MAX_IMAGE_SIZE} bytes"
        )

    return sanitized, ext


async def save_upload(task_id: str, file_bytes: bytes, ext: str) -> str:
    """Persist raw upload bytes to ``uploads/{task_id}/{uuid}.{ext}``.

    The file is named with a UUID on disk to prevent path-traversal attacks.
    Returns the absolute path to the saved file.
    """
    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)

    def _write() -> str:
        os.makedirs(task_dir, exist_ok=True)
        disk_name = f"input_{uuid.uuid4().hex}.{ext}"
        dest = os.path.join(task_dir, disk_name)
        with open(dest, "wb") as fh:
            fh.write(file_bytes)
        return dest

    saved_path = await asyncio.to_thread(_write)
    logger.debug("Saved upload for task %s -> %s", task_id, saved_path)
    return saved_path


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Attach UTC timezone to naive datetimes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _persist_task(task_id: str, **updates) -> None:
    """Write *updates* to the ImageTask row identified by *task_id*."""
    updates.setdefault("updated_at", datetime.now(timezone.utc))
    async with async_session() as db:
        result = await db.execute(
            select(ImageTask).where(ImageTask.id == task_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            logger.warning("_persist_task: task %s not found in DB", task_id)
            return
        for key, value in updates.items():
            setattr(row, key, value)
        await db.commit()


# ---------------------------------------------------------------------------
# In-memory progress helpers
# ---------------------------------------------------------------------------


def _update_status(
    task_id: str,
    status: str,
    progress: float | None = None,
    error: str | None = None,
) -> None:
    """Update the in-memory cache entry for *task_id* (thread-safe)."""
    with _tasks_lock:
        task = _active_tasks.get(task_id)
        if task is not None:
            task["status"] = status
            if progress is not None:
                task["progress"] = round(min(progress, 100.0), 1)
            if error is not None:
                task["error"] = error[:500]


async def _set_status(
    task_id: str,
    status: str,
    **kwargs,
) -> None:
    """Set status in memory and persist to DB atomically.

    ``kwargs`` may include any ImageTask column: ``filename``, ``file_size``,
    ``error``, ``completed_at``, ``inpaint_method``.

    Creates its own DB session so it is safe to call from background tasks
    after the original request session has been closed.
    """
    with _tasks_lock:
        task = _active_tasks.get(task_id)
        if task is not None:
            task["status"] = status
            # Serialise datetime values to ISO strings for the in-memory cache
            # so that ImageTaskStatus (which expects str | None) doesn't choke.
            for k, v in kwargs.items():
                task[k] = v.isoformat() if isinstance(v, datetime) else v

    # Persist to DB using a fresh session
    db_updates = {"status": status, **kwargs}
    db_updates.setdefault("updated_at", datetime.now(timezone.utc))
    async with async_session() as db_session:
        result = await db_session.execute(
            select(ImageTask).where(ImageTask.id == task_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            logger.warning("_set_status: task %s not found in DB", task_id)
            return
        for key, value in db_updates.items():
            setattr(row, key, value)
        await db_session.commit()


def get_task_status(task_id: str) -> dict | None:
    """Return the in-memory task dict, or None if not cached.

    Callers should fall back to the DB when this returns None.
    """
    with _tasks_lock:
        task = _active_tasks.get(task_id)
        return dict(task) if task is not None else None


def _schedule_eviction(task_id: str) -> None:
    """Schedule removal from the in-memory cache after EVICT_DELAY_SECONDS."""

    async def _evict() -> None:
        await asyncio.sleep(EVICT_DELAY_SECONDS)
        with _tasks_lock:
            _active_tasks.pop(task_id, None)

    asyncio.create_task(_evict())


# ---------------------------------------------------------------------------
# Preview generation
# ---------------------------------------------------------------------------


def _generate_preview(input_path: str, task_dir: str) -> str:
    """Create a JPEG thumbnail (max 800px) of the given image.

    Returns the filename (not full path) of the generated preview.
    """
    from PIL import Image

    preview_name = f"preview_{uuid.uuid4().hex}.jpg"
    preview_path = os.path.join(task_dir, preview_name)

    with Image.open(input_path) as img:
        img.thumbnail((800, 800))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(preview_path, "JPEG", quality=85)

    return preview_name


# ---------------------------------------------------------------------------
# Background removal
# ---------------------------------------------------------------------------


async def remove_background(task_id: str) -> None:
    """Orchestrate background removal: update status, run in thread, handle result.

    Creates its own DB sessions — safe to run as a background task after the
    original request has finished.
    """
    await _set_status(task_id, "processing")
    _update_status(task_id, "processing", progress=10.0)

    try:
        result_info = await asyncio.to_thread(_remove_bg_sync, task_id)
        await _set_status(
            task_id,
            "ready",
            filename=result_info["filename"],
            file_size=result_info["file_size"],
            progress=100.0,
            completed_at=datetime.now(timezone.utc),
        )
        _update_status(task_id, "ready", progress=100.0)
        _schedule_eviction(task_id)
    except Exception as exc:
        error_msg = str(exc)[:500]
        logger.exception("remove_background failed for task %s", task_id)
        await _set_status(
            task_id,
            "error",
            error=error_msg,
            completed_at=datetime.now(timezone.utc),
        )
        _update_status(task_id, "error", error=error_msg)
        _schedule_eviction(task_id)


def _remove_bg_sync(task_id: str) -> dict:
    """Synchronous background removal using rembg (runs in a worker thread).

    Returns dict with ``filename`` and ``file_size`` of the result.
    """
    from rembg import remove

    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)

    # Find the uploaded input file
    input_path = _find_input_file(task_dir)
    if input_path is None:
        raise FileNotFoundError(f"No input file found in {task_dir}")

    _update_status(task_id, "processing", progress=20.0)

    # Read input and process
    with open(input_path, "rb") as f:
        input_bytes = f.read()

    session = _get_rembg_session()
    _update_status(task_id, "processing", progress=40.0)

    output_bytes = remove(input_bytes, session=session)
    _update_status(task_id, "processing", progress=80.0)

    # Save result as PNG (preserves transparency)
    result_name = f"{uuid.uuid4().hex}.png"
    result_path = os.path.join(task_dir, result_name)
    with open(result_path, "wb") as f:
        f.write(output_bytes)

    file_size = os.path.getsize(result_path)

    # Generate preview of result
    _generate_preview(result_path, task_dir)

    _update_status(task_id, "processing", progress=95.0)

    return {"filename": result_name, "file_size": file_size}


# ---------------------------------------------------------------------------
# Watermark removal
# ---------------------------------------------------------------------------


async def remove_watermark(
    task_id: str,
    mask_shapes: list,
    inpaint_method: str,
) -> None:
    """Orchestrate watermark removal: update status, run in thread, handle result.

    Creates its own DB sessions — safe to run as a background task after the
    original request has finished.
    """
    await _set_status(task_id, "processing", inpaint_method=inpaint_method)
    _update_status(task_id, "processing", progress=10.0)

    try:
        result_info = await asyncio.to_thread(
            _remove_watermark_sync, task_id, mask_shapes, inpaint_method
        )
        await _set_status(
            task_id,
            "ready",
            filename=result_info["filename"],
            file_size=result_info["file_size"],
            progress=100.0,
            completed_at=datetime.now(timezone.utc),
        )
        _update_status(task_id, "ready", progress=100.0)
        _schedule_eviction(task_id)
    except Exception as exc:
        error_msg = str(exc)[:500]
        logger.exception("remove_watermark failed for task %s", task_id)
        await _set_status(
            task_id,
            "error",
            error=error_msg,
            completed_at=datetime.now(timezone.utc),
        )
        _update_status(task_id, "error", error=error_msg)
        _schedule_eviction(task_id)


def _remove_watermark_sync(
    task_id: str,
    mask_shapes: list,
    inpaint_method: str,
) -> dict:
    """Synchronous watermark removal using OpenCV inpaint (runs in a worker thread).

    Mask coordinates are normalised to [0, 1] by the frontend and scaled here
    to actual image dimensions.

    Returns dict with ``filename`` and ``file_size`` of the result.
    """
    import cv2
    import numpy as np

    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)

    # Find the uploaded input file
    input_path = _find_input_file(task_dir)
    if input_path is None:
        raise FileNotFoundError(f"No input file found in {task_dir}")

    _update_status(task_id, "processing", progress=20.0)

    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Failed to read image: {input_path}")

    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    _update_status(task_id, "processing", progress=30.0)

    # Build mask from normalised shapes — first draw additive shapes (white),
    # then eraser shapes (black) to subtract from the mask.
    def _get(shape, key, default=None):
        return shape.get(key, default) if isinstance(shape, dict) else getattr(shape, key, default)

    normal_shapes = [s for s in mask_shapes if not _get(s, "is_eraser", False)]
    eraser_shapes = [s for s in mask_shapes if _get(s, "is_eraser", False)]

    for shape in normal_shapes:
        shape_type = _get(shape, "type")
        points = _get(shape, "points")
        brush_size = _get(shape, "brush_size")

        if shape_type == "brush" and points:
            pts = np.array(
                [[int(p[0] * w), int(p[1] * h)] for p in points],
                dtype=np.int32,
            )
            thickness = max(1, int((brush_size or 0.02) * min(w, h)))
            cv2.polylines(mask, [pts], isClosed=False, color=255, thickness=thickness)

        elif shape_type == "rect" and len(points) >= 2:
            x1, y1 = int(points[0][0] * w), int(points[0][1] * h)
            x2, y2 = int(points[1][0] * w), int(points[1][1] * h)
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)

    # Eraser shapes subtract from the mask (draw in black / 0)
    for shape in eraser_shapes:
        shape_type = _get(shape, "type")
        points = _get(shape, "points")
        brush_size = _get(shape, "brush_size")

        if shape_type == "brush" and points:
            pts = np.array(
                [[int(p[0] * w), int(p[1] * h)] for p in points],
                dtype=np.int32,
            )
            thickness = max(1, int((brush_size or 0.02) * min(w, h)))
            cv2.polylines(mask, [pts], isClosed=False, color=0, thickness=thickness)

    _update_status(task_id, "processing", progress=50.0)

    # Select inpainting method
    flags = cv2.INPAINT_TELEA if inpaint_method == "telea" else cv2.INPAINT_NS
    result = cv2.inpaint(img, mask, 3, flags)

    _update_status(task_id, "processing", progress=80.0)

    # Save result
    result_name = f"{uuid.uuid4().hex}.png"
    result_path = os.path.join(task_dir, result_name)
    cv2.imwrite(result_path, result)

    file_size = os.path.getsize(result_path)

    # Generate preview of result
    _generate_preview(result_path, task_dir)

    _update_status(task_id, "processing", progress=95.0)

    return {"filename": result_name, "file_size": file_size}


# ---------------------------------------------------------------------------
# File lookup helper
# ---------------------------------------------------------------------------


def _find_input_file(task_dir: str) -> str | None:
    """Find the original uploaded file in the task directory.

    Input files are prefixed with ``input_`` by :func:`save_upload`.
    Returns the full path, or None if not found.
    """
    if not os.path.isdir(task_dir):
        return None
    for name in os.listdir(task_dir):
        if name.startswith("input_"):
            full = os.path.join(task_dir, name)
            if os.path.isfile(full):
                return full
    return None


# ---------------------------------------------------------------------------
# Row serialisation
# ---------------------------------------------------------------------------


def row_to_dict(task: ImageTask, *, check_file: bool = False) -> dict:
    """Convert an ImageTask ORM row to a plain dict for API responses.

    Timestamps are serialised as ISO-8601 strings.

    When *check_file* is ``True``, a ``file_exists`` key is added indicating
    whether the output file is still present on disk.
    """
    created_at = _ensure_utc(task.created_at)
    completed_at = _ensure_utc(task.completed_at)

    file_exists = False
    if check_file and task.filename:
        task_dir = os.path.join(settings.UPLOAD_DIR, task.id)
        file_exists = os.path.isfile(os.path.join(task_dir, task.filename))

    return {
        "task_id": task.id,
        "status": task.status,
        "progress": task.progress,
        "operation": task.operation,
        "filename": task.filename,
        "file_size": task.file_size,
        "error": task.error,
        "original_filename": task.original_filename,
        "original_ext": task.original_ext,
        "inpaint_method": task.inpaint_method,
        "created_at": created_at.isoformat() if created_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "file_exists": file_exists,
    }


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


async def create_task(
    task_id: str,
    user_id: int,
    original_filename: str,
    original_ext: str,
    operation: str,
    db: AsyncSession,
    inpaint_method: str | None = None,
) -> dict:
    """Persist a new ImageTask row and register it in the in-memory cache.

    Returns the initial task dict (status="pending", progress=0.0).
    """
    row = ImageTask(
        id=task_id,
        user_id=user_id,
        status="pending",
        progress=0.0,
        original_filename=original_filename,
        original_ext=original_ext,
        operation=operation,
        inpaint_method=inpaint_method,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    task_dict = row_to_dict(row)
    with _tasks_lock:
        _active_tasks[task_id] = dict(task_dict)

    return task_dict


async def get_task_for_user(
    task_id: str,
    user_id: int,
    db: AsyncSession,
) -> ImageTask | None:
    """Fetch a task by ID, returning None if not found or not owned by user_id."""
    result = await db.execute(
        select(ImageTask).where(ImageTask.id == task_id)
    )
    row = result.scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None
    return row


async def get_user_tasks(user_id: int, db: AsyncSession) -> list[ImageTask]:
    """Return active (non-hidden) tasks for user_id within the TTL window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)
    cutoff_naive = cutoff.replace(tzinfo=None)

    result = await db.execute(
        select(ImageTask)
        .where(
            ImageTask.user_id == user_id,
            ImageTask.created_at >= cutoff_naive,
            ImageTask.hidden == False,  # noqa: E712
        )
        .order_by(ImageTask.created_at.desc())
    )
    return list(result.scalars().all())


async def get_hidden_tasks(user_id: int, db: AsyncSession) -> list[ImageTask]:
    """Return hidden tasks for user_id within the TTL window (for history)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)
    cutoff_naive = cutoff.replace(tzinfo=None)

    result = await db.execute(
        select(ImageTask)
        .where(
            ImageTask.user_id == user_id,
            ImageTask.created_at >= cutoff_naive,
            ImageTask.hidden == True,  # noqa: E712
        )
        .order_by(ImageTask.created_at.desc())
    )
    return list(result.scalars().all())


async def dismiss_task(task_id: str, user_id: int, db: AsyncSession) -> bool:
    """Set hidden=True on the task. Returns True if found and owned by user."""
    result = await db.execute(
        select(ImageTask).where(
            ImageTask.id == task_id,
            ImageTask.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    row.hidden = True
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.debug("Image task %s dismissed by user %d", task_id, user_id)
    return True


async def dismiss_completed_tasks(user_id: int, db: AsyncSession) -> int:
    """Set hidden=True on all terminal tasks for user_id. Returns count."""
    stmt = (
        update(ImageTask)
        .where(
            ImageTask.user_id == user_id,
            ImageTask.status.in_(list(TERMINAL_STATUSES)),
            ImageTask.hidden == False,  # noqa: E712
        )
        .values(hidden=True, updated_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    logger.debug(
        "Dismissed %d completed image tasks for user %d", count, user_id
    )
    return count


async def restore_task(task_id: str, user_id: int, db: AsyncSession) -> bool:
    """Set hidden=False on the task. Returns True if found and owned by user."""
    result = await db.execute(
        select(ImageTask).where(
            ImageTask.id == task_id,
            ImageTask.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    row.hidden = False
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.debug("Image task %s restored by user %d", task_id, user_id)
    return True
