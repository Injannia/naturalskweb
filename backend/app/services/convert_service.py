"""
File conversion service.

Responsibilities
----------------
* Validate and persist uploaded files to disk.
* Execute conversions in the background via FFmpeg (video/audio),
  Pillow (image), or LibreOffice headless (document).
* Maintain an in-memory task dict for high-frequency progress updates,
  persisting only at meaningful status transitions to SQLite.
* Provide CRUD helpers mirroring the youtube_service pattern.

Design note — progress storage
------------------------------
FFmpeg progress hooks fire frequently; LibreOffice and Pillow produce only a
single progress event.  To avoid hammering SQLite we keep a lightweight
in-memory dict (_active_tasks) for the hot-path and write to the DB only at
status transitions (pending → converting → ready / error / cancelled).
Progress percentage is lost on restart; the terminal state survives.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import threading
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.convert_task import ConvertTask
from app.schemas.convert import (
    ALLOWED_INPUT_EXTS,
    AUDIO_OUTPUT_FORMATS,
    BLOCKED_EXTENSIONS,
    DOCUMENT_OUTPUT_FORMATS,
    IMAGE_OUTPUT_FORMATS,
    MAX_FILE_SIZE,
    VIDEO_OUTPUT_FORMATS,
)

logger = logging.getLogger("naturalsk.convert")

# Valid output formats by category — used for defense-in-depth validation
# inside start_conversion() (the router also validates, but the service
# should not blindly trust its caller).
_VALID_OUTPUT_FORMATS: dict[str, list[str]] = {
    "video": VIDEO_OUTPUT_FORMATS,
    "audio": AUDIO_OUTPUT_FORMATS,
    "image": IMAGE_OUTPUT_FORMATS,
    "document": DOCUMENT_OUTPUT_FORMATS,
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = frozenset({"ready", "error", "cancelled"})
EVICT_DELAY_SECONDS = 30

# ---------------------------------------------------------------------------
# FFmpeg / FFprobe binary detection (cached on first call)
# ---------------------------------------------------------------------------

_ffmpeg_path: str | None = None
_ffprobe_path: str | None = None
_binary_lock = threading.Lock()


def _find_ffmpeg() -> str | None:
    """Locate the ffmpeg binary, checking known paths before falling back to PATH."""
    global _ffmpeg_path
    with _binary_lock:
        if _ffmpeg_path is not None:
            return _ffmpeg_path
        candidates = [
            os.path.join(
                os.path.expanduser("~"),
                r"AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe",
            ),
        ]
        for c in candidates:
            if os.path.isfile(c):
                _ffmpeg_path = c
                logger.info("Using ffmpeg: %s", _ffmpeg_path)
                return _ffmpeg_path
        found = shutil.which("ffmpeg")
        if found:
            _ffmpeg_path = found
            logger.info("Using ffmpeg: %s", _ffmpeg_path)
            return _ffmpeg_path
        # Fall back to bare name — let the OS resolve it
        _ffmpeg_path = "ffmpeg"
        logger.warning("ffmpeg not found in known locations; using bare 'ffmpeg'")
        return _ffmpeg_path


def _find_ffprobe() -> str | None:
    """Locate the ffprobe binary, checking known paths before falling back to PATH."""
    global _ffprobe_path
    with _binary_lock:
        if _ffprobe_path is not None:
            return _ffprobe_path
        candidates = [
            os.path.join(
                os.path.expanduser("~"),
                r"AppData\Local\Microsoft\WinGet\Links\ffprobe.exe",
            ),
        ]
        for c in candidates:
            if os.path.isfile(c):
                _ffprobe_path = c
                logger.info("Using ffprobe: %s", _ffprobe_path)
                return _ffprobe_path
        found = shutil.which("ffprobe")
        if found:
            _ffprobe_path = found
            logger.info("Using ffprobe: %s", _ffprobe_path)
            return _ffprobe_path
        _ffprobe_path = "ffprobe"
        logger.warning("ffprobe not found in known locations; using bare 'ffprobe'")
        return _ffprobe_path


# ---------------------------------------------------------------------------
# In-memory task cache (hot-path progress updates during active conversions)
# ---------------------------------------------------------------------------

# Maps task_id → plain dict for tasks that are actively running or recently
# completed.  Plain dicts are used (unlike youtube_service's Pydantic model)
# because progress updates happen inside asyncio callbacks and thread callbacks
# where dict mutation is cheaper and simpler.
_active_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Category & format detection
# ---------------------------------------------------------------------------


def detect_category(ext: str) -> str:
    """Map a file extension to its category string.

    Parameters
    ----------
    ext:
        Lowercase file extension without the leading dot.

    Raises
    ------
    ValueError
        When the extension is not in the allowed set.
    """
    category = ALLOWED_INPUT_EXTS.get(ext.lower())
    if category is None:
        raise ValueError(f"Unsupported file extension: .{ext}")
    return category


def get_capabilities(ext: str) -> dict:
    """Return conversion capabilities for a given input extension.

    Returns a dict with:
    - ``category`` — the file category string
    - ``target_formats`` — list of supported output format strings
    - ``settings_fields`` — dict describing available conversion options
    """
    category = detect_category(ext)

    if category == "video":
        return {
            "category": category,
            "target_formats": VIDEO_OUTPUT_FORMATS,
            "settings_fields": {
                "resolution": "string (e.g. '1920x1080', '1280x720')",
                "codec": "string (e.g. 'h264', 'h265', 'vp9')",
                "bitrate": "string (e.g. '2M', '5M')",
                "fps": "integer 1-120",
                "audio_codec": "string (e.g. 'aac', 'mp3', 'copy')",
            },
        }
    if category == "audio":
        return {
            "category": category,
            "target_formats": AUDIO_OUTPUT_FORMATS,
            "settings_fields": {
                "bitrate": "string (e.g. '128k', '320k')",
                "sample_rate": "integer 8000-192000",
                "channels": "integer 1-2",
            },
        }
    if category == "image":
        return {
            "category": category,
            "target_formats": IMAGE_OUTPUT_FORMATS,
            "settings_fields": {
                "quality": "integer 1-100",
                "width": "integer 1-10000",
                "height": "integer 1-10000",
                "keep_aspect": "boolean",
            },
        }
    # document
    return {
        "category": category,
        "target_formats": DOCUMENT_OUTPUT_FORMATS,
        "settings_fields": {},
    }


# ---------------------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------------------

_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename(name: str) -> str:
    """Strip characters that are invalid in file/directory names."""
    return _UNSAFE_NAME_RE.sub("_", name).strip(" .")[:200]


def validate_upload(
    filename: str, content_type: str | None, size: int
) -> tuple[str, str, str]:
    """Validate an incoming upload.

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
    tuple[str, str, str]
        ``(sanitized_filename, ext, category)``

    Raises
    ------
    ValueError
        On blocked extension, unknown format, or oversized file.
    """
    if not filename or not filename.strip():
        raise ValueError("Filename must not be empty")

    sanitized = _sanitize_filename(filename)
    if not sanitized:
        raise ValueError("Filename is invalid after sanitization")

    _, raw_ext = os.path.splitext(sanitized)
    ext = raw_ext.lstrip(".").lower()

    if ext in BLOCKED_EXTENSIONS:
        raise ValueError(f"File type .{ext} is not allowed")

    if ext not in ALLOWED_INPUT_EXTS:
        raise ValueError(f"Unsupported file type: .{ext}")

    if size > MAX_FILE_SIZE:
        raise ValueError(
            f"File size {size} bytes exceeds the maximum of {MAX_FILE_SIZE} bytes"
        )

    category = ALLOWED_INPUT_EXTS[ext]
    return sanitized, ext, category


async def save_upload(task_id: str, file_bytes: bytes, original_ext: str) -> str:
    """Persist raw upload bytes to ``uploads/{task_id}/{uuid}.{ext}``.

    The file is named with a UUID on disk to prevent path-traversal attacks.
    Returns the absolute path to the saved file.
    """
    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)

    def _write() -> str:
        os.makedirs(task_dir, exist_ok=True)
        disk_name = f"{uuid.uuid4().hex}.{original_ext}"
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
    """Write *updates* to the ConvertTask row identified by *task_id*."""
    updates.setdefault("updated_at", datetime.now(timezone.utc))
    async with async_session() as db:
        result = await db.execute(
            select(ConvertTask).where(ConvertTask.id == task_id)
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


def _update_progress(task_id: str, progress: float) -> None:
    """Update the in-memory progress value for *task_id* (thread-safe)."""
    with _tasks_lock:
        task = _active_tasks.get(task_id)
        if task is not None:
            task["progress"] = round(min(progress, 100.0), 1)


async def _set_status(
    task_id: str,
    status: str,
    db_session: AsyncSession,
    **kwargs,
) -> None:
    """Set status in memory and persist to DB atomically.

    ``kwargs`` may include any ConvertTask column: ``filename``, ``file_size``,
    ``error``, ``completed_at``, ``target_format``.
    """
    with _tasks_lock:
        task = _active_tasks.get(task_id)
        if task is not None:
            task["status"] = status
            task.update(kwargs)

    # Persist to DB using the provided session
    db_updates = {"status": status, **kwargs}
    db_updates.setdefault("updated_at", datetime.now(timezone.utc))
    result = await db_session.execute(
        select(ConvertTask).where(ConvertTask.id == task_id)
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


def _is_cancelled(task_id: str) -> bool:
    """Return True if the task was cancelled by the user."""
    with _tasks_lock:
        task = _active_tasks.get(task_id)
        return task is not None and task.get("status") == "cancelled"


def _schedule_eviction(task_id: str) -> None:
    """Schedule removal from the in-memory cache after EVICT_DELAY_SECONDS."""

    async def _evict() -> None:
        await asyncio.sleep(EVICT_DELAY_SECONDS)
        with _tasks_lock:
            _active_tasks.pop(task_id, None)

    asyncio.create_task(_evict())


# ---------------------------------------------------------------------------
# FFprobe helper
# ---------------------------------------------------------------------------


async def _get_media_duration(input_path: str) -> float | None:
    """Run ffprobe to get stream duration in seconds.

    Returns None if the probe fails for any reason (e.g. non-media file).
    """
    ffprobe = _find_ffprobe()
    if ffprobe is None:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = stdout.decode(errors="replace").strip()
        if text and text != "N/A":
            return float(text)
    except (asyncio.TimeoutError, ValueError, OSError) as exc:
        logger.debug("ffprobe failed for %s: %s", input_path, exc)
    return None


async def _run_ffmpeg_with_progress(
    task_id: str,
    args: list[str],
    duration_s: float | None,
    timeout: int,
    label: str,
) -> None:
    """Run an FFmpeg command with real-time progress tracking.

    Reads stdout (progress) and stderr (errors) via separate coroutines
    to avoid the race condition where communicate() and an async-for loop
    both attempt to read the same pipe.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _read_progress() -> None:
        assert proc.stdout is not None
        async for line in proc.stdout:
            text = line.decode(errors="replace").strip()
            if text.startswith("out_time_us=") and duration_s and duration_s > 0:
                try:
                    us = int(text.split("=", 1)[1])
                    pct = min(us / (duration_s * 1_000_000) * 100, 99.0)
                    _update_progress(task_id, pct)
                except (ValueError, IndexError):
                    pass

    async def _read_stderr() -> bytes:
        assert proc.stderr is not None
        return await proc.stderr.read()

    try:
        _, stderr_data, _ = await asyncio.wait_for(
            asyncio.gather(_read_progress(), _read_stderr(), proc.wait()),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"{label} conversion timed out after {timeout // 60} minutes")

    if proc.returncode != 0:
        msg = stderr_data.decode(errors="replace")[-600:]
        raise RuntimeError(
            f"FFmpeg {label.lower()} conversion failed (rc={proc.returncode}): {msg}"
        )


# ---------------------------------------------------------------------------
# Conversion engines
# ---------------------------------------------------------------------------


async def _convert_video(
    task_id: str,
    input_path: str,
    output_path: str,
    options: dict,
) -> None:
    """FFmpeg video conversion with real-time progress tracking.

    Uses ``-progress pipe:1`` and parses ``out_time_us`` for percentage.
    """
    ffmpeg = _find_ffmpeg()
    duration_s = await _get_media_duration(input_path)

    args: list[str] = [ffmpeg, "-y", "-i", input_path]

    # Video filters
    vf_parts: list[str] = []
    resolution = options.get("resolution")
    if resolution:
        # Accept "WxH" or "W:H"
        normalized = resolution.replace("x", ":").replace("X", ":")
        vf_parts.append(f"scale={normalized}")
    if vf_parts:
        args += ["-vf", ",".join(vf_parts)]

    codec = options.get("codec")
    if codec:
        codec_map = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9"}
        args += ["-c:v", codec_map.get(codec, codec)]

    bitrate = options.get("bitrate")
    if bitrate:
        args += ["-b:v", bitrate]

    fps = options.get("fps")
    if fps:
        args += ["-r", str(fps)]

    audio_codec = options.get("audio_codec")
    if audio_codec:
        args += ["-c:a", audio_codec]

    args += ["-progress", "pipe:1", output_path]

    await _run_ffmpeg_with_progress(
        task_id=task_id,
        args=args,
        duration_s=duration_s,
        timeout=1800,
        label="Video",
    )


async def _convert_audio(
    task_id: str,
    input_path: str,
    output_path: str,
    options: dict,
) -> None:
    """FFmpeg audio conversion with real-time progress tracking."""
    ffmpeg = _find_ffmpeg()
    duration_s = await _get_media_duration(input_path)

    args: list[str] = [ffmpeg, "-y", "-i", input_path]

    bitrate = options.get("bitrate")
    if bitrate:
        args += ["-b:a", bitrate]

    sample_rate = options.get("sample_rate")
    if sample_rate:
        args += ["-ar", str(sample_rate)]

    channels = options.get("channels")
    if channels:
        args += ["-ac", str(channels)]

    args += ["-progress", "pipe:1", output_path]

    await _run_ffmpeg_with_progress(
        task_id=task_id,
        args=args,
        duration_s=duration_s,
        timeout=600,
        label="Audio",
    )


async def _convert_image(
    task_id: str,
    input_path: str,
    output_path: str,
    options: dict,
) -> None:
    """Pillow image conversion, run in a thread to avoid blocking the loop."""

    def _do_convert() -> None:
        from PIL import Image  # noqa: deferred heavy import

        Image.MAX_IMAGE_PIXELS = 200_000_000

        with Image.open(input_path) as img:
            # Convert palette/transparency modes for broader format compatibility
            output_ext = os.path.splitext(output_path)[1].lstrip(".").lower()
            if output_ext in ("jpg", "jpeg") and img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            width = options.get("width")
            height = options.get("height")
            keep_aspect = options.get("keep_aspect", True)

            if width or height:
                target_w = int(width) if width else img.width
                target_h = int(height) if height else img.height
                if keep_aspect:
                    img.thumbnail((target_w, target_h), Image.LANCZOS)
                else:
                    img = img.resize((target_w, target_h), Image.LANCZOS)

            save_kwargs: dict = {}
            quality = options.get("quality")
            if quality is not None:
                save_kwargs["quality"] = int(quality)

            fmt_map = {
                "jpg": "JPEG",
                "jpeg": "JPEG",
                "tiff": "TIFF",
                "ico": "ICO",
                "webp": "WEBP",
                "png": "PNG",
                "bmp": "BMP",
                "gif": "GIF",
            }
            pil_format = fmt_map.get(output_ext, output_ext.upper())
            img.save(output_path, format=pil_format, **save_kwargs)

    _update_progress(task_id, 0.0)
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_do_convert),
            timeout=120,  # 2 minutes
        )
    except asyncio.TimeoutError:
        raise RuntimeError("Image conversion timed out after 2 minutes")
    _update_progress(task_id, 100.0)


async def _convert_document(
    task_id: str,
    input_path: str,
    output_dir: str,
    target_format: str,
) -> str:
    """LibreOffice headless document conversion.

    Returns the absolute path of the converted output file.
    """
    _update_progress(task_id, 0.0)

    soffice = shutil.which("soffice") or "soffice"

    proc = await asyncio.create_subprocess_exec(
        soffice,
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--convert-to", target_format,
        "--outdir", output_dir,
        input_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            proc.communicate(), timeout=120
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Document conversion timed out after 120 seconds")

    if proc.returncode != 0:
        msg = stderr_data.decode(errors="replace")[-600:]
        raise RuntimeError(f"LibreOffice conversion failed (rc={proc.returncode}): {msg}")

    # LibreOffice names the output after the input stem
    input_stem = os.path.splitext(os.path.basename(input_path))[0]
    expected = os.path.join(output_dir, f"{input_stem}.{target_format}")
    if not os.path.isfile(expected):
        # Scan the directory for any newly created file matching the format
        for fname in os.listdir(output_dir):
            if fname.lower().endswith(f".{target_format}"):
                candidate = os.path.join(output_dir, fname)
                if os.path.isfile(candidate):
                    expected = candidate
                    break
        else:
            raise RuntimeError(
                f"LibreOffice conversion produced no .{target_format} file in {output_dir}"
            )

    _update_progress(task_id, 100.0)
    return expected


# ---------------------------------------------------------------------------
# Main conversion dispatcher
# ---------------------------------------------------------------------------


async def start_conversion(
    task_id: str,
    target_format: str,
    options: dict | None,
) -> None:
    """Background task entry point — dispatches to the correct conversion engine.

    Lifecycle
    ---------
    1. Set status = "converting" in memory + DB
    2. Locate the uploaded source file in the task directory
    3. Dispatch to the appropriate engine
    4. On success: status = "ready", populate filename/file_size/completed_at
    5. On error:   status = "error", populate error message
    6. Always:     schedule in-memory eviction after EVICT_DELAY_SECONDS
    """
    opts = options or {}

    async with async_session() as db:
        result = await db.execute(
            select(ConvertTask).where(ConvertTask.id == task_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            logger.error("start_conversion: task %s not found in DB", task_id)
            return

        original_filename = row.original_filename
        original_ext = row.original_ext
        category = row.category

        # Defense-in-depth: validate target_format even though the router
        # already checks it.  Prevents misuse if called from non-router code.
        valid_formats = _VALID_OUTPUT_FORMATS.get(category, [])
        if target_format not in valid_formats:
            logger.error(
                "start_conversion: invalid target_format %r for category %s (task %s)",
                target_format, category, task_id,
            )
            await _set_status(
                task_id, "error", db,
                error=f"Недопустимый формат: {target_format}",
            )
            _schedule_eviction(task_id)
            return

        # Step 1: transition to "converting"
        await _set_status(task_id, "converting", db)

    # Locate the input file in uploads/{task_id}/
    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    input_path: str | None = None
    try:
        for fname in os.listdir(task_dir):
            fpath = os.path.join(task_dir, fname)
            if os.path.isfile(fpath) and fname.lower().endswith(f".{original_ext}"):
                input_path = fpath
                break
    except OSError as exc:
        logger.error("start_conversion: cannot read task dir %s: %s", task_dir, exc)

    if input_path is None:
        async with async_session() as db:
            await _set_status(
                task_id, "error", db,
                error="Uploaded file not found on disk",
            )
        _schedule_eviction(task_id)
        return

    # Derive output filename from the original stem + target extension
    original_stem = os.path.splitext(original_filename)[0]
    safe_stem = _sanitize_filename(original_stem)
    output_filename = f"{safe_stem}.{target_format}"
    output_path = os.path.join(task_dir, output_filename)

    try:
        if _is_cancelled(task_id):
            return

        if category == "video":
            await _convert_video(task_id, input_path, output_path, opts)
        elif category == "audio":
            await _convert_audio(task_id, input_path, output_path, opts)
        elif category == "image":
            await _convert_image(task_id, input_path, output_path, opts)
        elif category == "document":
            # LibreOffice writes into the task dir; update output_path to its return value
            output_path = await _convert_document(
                task_id, input_path, task_dir, target_format
            )
            output_filename = os.path.basename(output_path)
        else:
            raise RuntimeError(f"Unknown category: {category}")

        if _is_cancelled(task_id):
            return

        try:
            file_size: int | None = os.path.getsize(output_path)
        except OSError:
            file_size = None

        completed_now = datetime.now(timezone.utc)

        with _tasks_lock:
            task = _active_tasks.get(task_id)
            if task is not None:
                task["status"] = "ready"
                task["progress"] = 100.0
                task["filename"] = output_filename
                task["file_size"] = file_size
                task["completed_at"] = completed_now.isoformat()

        await _persist_task(
            task_id,
            status="ready",
            progress=100.0,
            filename=output_filename,
            file_size=file_size,
            target_format=target_format,
            completed_at=completed_now,
        )

        logger.info(
            "Conversion task %s completed: %s (%s bytes)",
            task_id, output_filename, file_size,
        )

    except asyncio.CancelledError:
        async with async_session() as db:
            await _set_status(task_id, "cancelled", db, error="Conversion was cancelled")
        logger.info("Conversion task %s was cancelled (CancelledError)", task_id)

    except Exception as exc:
        if _is_cancelled(task_id):
            logger.info(
                "Conversion task %s aborted due to cancellation: %s", task_id, exc
            )
            return
        error_msg = str(exc)[:800]
        logger.error(
            "Conversion task %s failed: %s", task_id, error_msg, exc_info=True
        )
        async with async_session() as db:
            await _set_status(task_id, "error", db, error=error_msg)

    finally:
        _schedule_eviction(task_id)


# ---------------------------------------------------------------------------
# Row-to-dict helper
# ---------------------------------------------------------------------------


def row_to_dict(task: ConvertTask, *, check_file: bool = False) -> dict:
    """Convert a ConvertTask ORM row to a plain dict for API responses.

    Timestamps are serialised as ISO-8601 strings.
    The ``options`` JSON column is parsed back to a dict (or None).

    When *check_file* is ``True``, an ``file_exists`` key is added indicating
    whether the output file is still present on disk.
    """
    options_parsed: dict | None = None
    if task.options:
        try:
            options_parsed = json.loads(task.options)
        except (ValueError, TypeError):
            options_parsed = None

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
        "filename": task.filename,
        "file_size": task.file_size,
        "error": task.error,
        "original_filename": task.original_filename,
        "original_ext": task.original_ext,
        "category": task.category,
        "target_format": task.target_format,
        "options": options_parsed,
        "batch_id": task.batch_id,
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
    category: str,
    db: AsyncSession,
    batch_id: str | None = None,
) -> dict:
    """Persist a new ConvertTask row and register it in the in-memory cache.

    Returns the initial task dict (status="pending", progress=0.0).
    """
    row = ConvertTask(
        id=task_id,
        user_id=user_id,
        status="pending",
        progress=0.0,
        original_filename=original_filename,
        original_ext=original_ext,
        category=category,
        batch_id=batch_id,
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
) -> ConvertTask | None:
    """Fetch a task by ID, returning None if not found or not owned by user_id."""
    result = await db.execute(
        select(ConvertTask).where(ConvertTask.id == task_id)
    )
    row = result.scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None
    return row


async def get_user_tasks(user_id: int, db: AsyncSession) -> list[ConvertTask]:
    """Return active (non-hidden) tasks for user_id within the TTL window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)
    cutoff_naive = cutoff.replace(tzinfo=None)

    result = await db.execute(
        select(ConvertTask)
        .where(
            ConvertTask.user_id == user_id,
            ConvertTask.created_at >= cutoff_naive,
            ConvertTask.hidden == False,  # noqa: E712
            # BUG-2: exclude orphaned pending tasks that never received a target_format
            or_(
                ConvertTask.status != "pending",
                ConvertTask.target_format.isnot(None),
            ),
        )
        .order_by(ConvertTask.created_at.desc())
    )
    return list(result.scalars().all())


async def get_hidden_tasks(user_id: int, db: AsyncSession) -> list[ConvertTask]:
    """Return hidden tasks for user_id within the TTL window (for history)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)
    cutoff_naive = cutoff.replace(tzinfo=None)

    result = await db.execute(
        select(ConvertTask)
        .where(
            ConvertTask.user_id == user_id,
            ConvertTask.created_at >= cutoff_naive,
            ConvertTask.hidden == True,  # noqa: E712
        )
        .order_by(ConvertTask.created_at.desc())
    )
    return list(result.scalars().all())


async def dismiss_task(task_id: str, user_id: int, db: AsyncSession) -> bool:
    """Set hidden=True on the task. Returns True if found and owned by user."""
    result = await db.execute(
        select(ConvertTask).where(
            ConvertTask.id == task_id,
            ConvertTask.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    row.hidden = True
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.debug("Convert task %s dismissed by user %d", task_id, user_id)
    return True


async def dismiss_completed_tasks(user_id: int, db: AsyncSession) -> int:
    """Set hidden=True on all terminal tasks for user_id. Returns count."""
    stmt = (
        update(ConvertTask)
        .where(
            ConvertTask.user_id == user_id,
            ConvertTask.status.in_(list(TERMINAL_STATUSES)),
            ConvertTask.hidden == False,  # noqa: E712
        )
        .values(hidden=True, updated_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    logger.debug(
        "Dismissed %d completed convert tasks for user %d", count, user_id
    )
    return count


async def restore_task(task_id: str, user_id: int, db: AsyncSession) -> bool:
    """Set hidden=False on the task. Returns True if found and owned by user."""
    result = await db.execute(
        select(ConvertTask).where(
            ConvertTask.id == task_id,
            ConvertTask.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    row.hidden = False
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.debug("Convert task %s restored by user %d", task_id, user_id)
    return True


async def delete_pending_upload(
    task_id: str, user_id: int, db: AsyncSession
) -> bool:
    """Delete a pending upload that has not started conversion.

    Only tasks with status='pending' and target_format=NULL can be deleted
    this way.  Removes both the on-disk directory and the DB row.

    Returns True if found and deleted, False otherwise.
    """
    row = await get_task_for_user(task_id, user_id, db)
    if row is None:
        return False
    if row.status != "pending" or row.target_format is not None:
        return False

    # Remove files from disk
    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    shutil.rmtree(task_dir, ignore_errors=True)

    # Remove from in-memory cache
    with _tasks_lock:
        _active_tasks.pop(task_id, None)

    # Remove DB row
    await db.delete(row)
    await db.commit()
    logger.info("Pending upload %s deleted by user %d", task_id, user_id)
    return True


async def delete_task_permanent(
    task_id: str, user_id: int, db: AsyncSession
) -> bool:
    """Permanently delete a task — removes file from disk and record from DB.

    Only allowed for terminal tasks (ready/error/cancelled).
    If the file has already been cleaned up, only the DB record is removed.

    Returns True if found and deleted, False otherwise.
    """
    row = await get_task_for_user(task_id, user_id, db)
    if row is None:
        return False
    if row.status not in TERMINAL_STATUSES:
        return False

    # Remove files from disk (may already be gone — that's fine)
    task_dir = os.path.join(settings.UPLOAD_DIR, task_id)
    shutil.rmtree(task_dir, ignore_errors=True)

    # Remove from in-memory cache
    with _tasks_lock:
        _active_tasks.pop(task_id, None)

    # Remove DB row
    await db.delete(row)
    await db.commit()
    logger.info("Convert task %s permanently deleted by user %d", task_id, user_id)
    return True


async def cancel_task(task_id: str, user_id: int, db: AsyncSession) -> bool:
    """Cancel an active conversion task.

    Sets status="cancelled" in memory immediately so the running engine
    detects it at its next _is_cancelled() check.  Persists via a guarded
    UPDATE that will not overwrite an already-terminal state.

    Returns True if the task exists and belongs to user_id.
    """
    row = await get_task_for_user(task_id, user_id, db)
    if row is None:
        return False

    with _tasks_lock:
        task = _active_tasks.get(task_id)
        if task is not None and task.get("status") not in TERMINAL_STATUSES:
            task["status"] = "cancelled"
            task["error"] = "Cancelled by user"

    stmt = (
        update(ConvertTask)
        .where(
            ConvertTask.id == task_id,
            ConvertTask.status.not_in(list(TERMINAL_STATUSES)),
        )
        .values(
            status="cancelled",
            error="Cancelled by user",
            updated_at=datetime.now(timezone.utc),
        )
        .execution_options(synchronize_session=False)
    )
    await db.execute(stmt)
    await db.commit()

    logger.info("Convert task %s cancelled by user %d", task_id, user_id)
    return True


# ---------------------------------------------------------------------------
# Batch ZIP
# ---------------------------------------------------------------------------


async def create_batch_zip(
    batch_id: str, user_id: int, db: AsyncSession
) -> str | None:
    """Collect all ready tasks in the batch and produce a ZIP archive.

    The ZIP is written to ``uploads/{batch_id}/batch_{batch_id[:8]}.zip``.
    Returns the ZIP file path, or None if no ready files were found.
    """
    result = await db.execute(
        select(ConvertTask).where(
            ConvertTask.batch_id == batch_id,
            ConvertTask.user_id == user_id,
            ConvertTask.status == "ready",
        )
    )
    rows = result.scalars().all()

    ready_files: list[tuple[str, str]] = []  # (abs_path, arcname)
    for row in rows:
        if not row.filename:
            continue
        task_dir = os.path.join(settings.UPLOAD_DIR, row.id)
        file_path = os.path.join(task_dir, row.filename)
        if os.path.isfile(file_path):
            ready_files.append((file_path, row.filename))

    if not ready_files:
        logger.debug("create_batch_zip: no ready files for batch %s", batch_id)
        return None

    zip_dir = os.path.join(settings.UPLOAD_DIR, batch_id)

    def _build_zip() -> str:
        os.makedirs(zip_dir, exist_ok=True)
        zip_path = os.path.join(zip_dir, f"batch_{batch_id[:8]}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            seen_names: dict[str, int] = {}
            for abs_path, arcname in ready_files:
                # Deduplicate arcnames so two files named "output.mp3" don't
                # silently overwrite each other inside the archive.
                stem, ext = os.path.splitext(arcname)
                if arcname in seen_names:
                    seen_names[arcname] += 1
                    arcname = f"{stem}_{seen_names[arcname]}{ext}"
                else:
                    seen_names[arcname] = 0
                zf.write(abs_path, arcname=arcname)
        return zip_path

    zip_path = await asyncio.to_thread(_build_zip)
    logger.info(
        "Batch ZIP created for batch %s: %s (%d files)",
        batch_id, zip_path, len(ready_files),
    )
    return zip_path
