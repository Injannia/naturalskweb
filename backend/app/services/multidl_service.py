"""Multi downloader service — single video/audio downloads from any yt-dlp site.

Lean by design: no playlist, no quality ladder, no cache-hit, no dedup. Reuses
SharedFile for storage/TTL/cleanup (video_id prefixed "multidl:" to avoid any
collision with YouTube cache lookups).

Router-facing query/mutate helpers take an explicit ``db`` session so they are
unit-testable against the test fixture's engine; background-only helpers
(_persist_task and the SharedFile insert in download()) open their own
async_session() because they run after the request session has closed.
"""

import asyncio
import logging
import os
import shutil
import threading
from datetime import datetime, timedelta, timezone

import yt_dlp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.multi_download_task import MultiDownloadTask
from app.models.shared_file import SharedFile
from app.schemas.multidl import DownloadRequest, DownloadStatus, InfoResponse
from app.utils.ffmpeg import find_ffmpeg

logger = logging.getLogger("naturalsk.multidl")
FFMPEG_PATH = find_ffmpeg()

_TERMINAL = ("ready", "error", "cancelled")

_active_tasks: dict[str, DownloadStatus] = {}
_tasks_lock = threading.Lock()
_active_ytdlp: dict[str, yt_dlp.YoutubeDL] = {}


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _row_to_status(row: MultiDownloadTask, *, check_file: bool = False) -> DownloadStatus:
    download_url = f"/api/multidl/file/{row.id}" if row.status == "ready" else None
    file_exists = False
    if check_file and row.filename and row.shared_file_id:
        shared_dir = os.path.join(settings.UPLOAD_DIR, row.shared_file_id)
        file_exists = os.path.isfile(os.path.join(shared_dir, row.filename))
    return DownloadStatus(
        task_id=row.id,
        status=row.status,  # type: ignore[arg-type]
        progress=row.progress,
        filename=row.filename,
        error=row.error,
        download_url=download_url,
        file_size=row.file_size,
        url=row.url,
        title=row.title,
        thumbnail=row.thumbnail,
        platform=row.platform,
        audio_only=row.audio_only,
        created_at=_ensure_utc(row.created_at),
        completed_at=_ensure_utc(row.completed_at),
        file_exists=file_exists,
    )


async def _persist_task(task_id: str, **updates) -> None:
    """Background-only: write updates to the task row using a fresh session."""
    updates.setdefault("updated_at", datetime.now(timezone.utc))
    async with async_session() as db:
        row = (await db.execute(select(MultiDownloadTask).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
        if row is None:
            logger.warning("_persist_task: task %s not found", task_id)
            return
        for k, v in updates.items():
            setattr(row, k, v)
        await db.commit()


def _update_active(task_id: str, **updates) -> None:
    with _tasks_lock:
        if task_id in _active_tasks:
            _active_tasks[task_id] = _active_tasks[task_id].model_copy(update=updates)


def _is_cancelled(task_id: str) -> bool:
    with _tasks_lock:
        t = _active_tasks.get(task_id)
        return t is not None and t.status == "cancelled"


# --- info ------------------------------------------------------------------

def _extract_info_sync(url: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "socket_timeout": 30, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


async def get_info(url: str) -> InfoResponse:
    """Fetch lightweight metadata for the preview card."""
    try:
        info = await asyncio.wait_for(asyncio.to_thread(_extract_info_sync, url), timeout=30.0)
    except asyncio.TimeoutError:
        raise TimeoutError("Timed out while fetching info")
    if not info:
        raise ValueError("yt-dlp returned no info for the given URL")
    return InfoResponse(
        title=info.get("title") or info.get("id") or "",
        thumbnail=info.get("thumbnail"),
        duration=int(info.get("duration") or 0),
        platform=info.get("extractor_key") or info.get("extractor"),
    )


# --- task CRUD (router-facing: explicit db) --------------------------------

async def create_task(task_id: str, user_id: int, request: DownloadRequest, db: AsyncSession) -> DownloadStatus:
    row = MultiDownloadTask(
        id=task_id,
        user_id=user_id,
        status="pending",
        progress=0.0,
        url=request.url,
        title=request.title,
        audio_only=request.audio_only,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    initial = _row_to_status(row)
    with _tasks_lock:
        _active_tasks[task_id] = initial
    return initial


async def get_task_for_user(task_id: str, user_id: int, db: AsyncSession) -> MultiDownloadTask | None:
    row = (await db.execute(select(MultiDownloadTask).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None
    return row


async def resolve_shared_file_dir(task_id: str, user_id: int, db: AsyncSession) -> str | None:
    row = await get_task_for_user(task_id, user_id, db)
    if row is None or row.shared_file_id is None:
        return None
    return os.path.join(settings.UPLOAD_DIR, row.shared_file_id)


async def get_download_progress(task_id: str, db: AsyncSession) -> DownloadStatus | None:
    with _tasks_lock:
        cached = _active_tasks.get(task_id)
    if cached is not None:
        return cached
    row = (await db.execute(select(MultiDownloadTask).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
    return _row_to_status(row) if row else None


async def get_user_tasks(user_id: int, db: AsyncSession, limit: int = 50) -> list[DownloadStatus]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)).replace(tzinfo=None)
    rows = (await db.execute(
        select(MultiDownloadTask)
        .where(
            MultiDownloadTask.user_id == user_id,
            MultiDownloadTask.created_at >= cutoff,
            MultiDownloadTask.hidden == False,  # noqa: E712
        )
        .order_by(MultiDownloadTask.created_at.desc())
        .limit(limit)
    )).scalars().all()
    out: list[DownloadStatus] = []
    for row in rows:
        with _tasks_lock:
            cached = _active_tasks.get(row.id)
        out.append(cached if cached is not None else _row_to_status(row, check_file=True))
    return out


async def cancel_task(task_id: str, db: AsyncSession) -> bool:
    with _tasks_lock:
        t = _active_tasks.get(task_id)
        if t is not None:
            if t.status in _TERMINAL:
                return True
            _active_tasks[task_id] = t.model_copy(update={"status": "cancelled", "error": "Cancelled by user"})
    ydl = _active_ytdlp.pop(task_id, None)
    if ydl:
        try:
            ydl.params["abort_on_error"] = True
        except Exception:
            pass
    result = await db.execute(
        update(MultiDownloadTask)
        .where(MultiDownloadTask.id == task_id, MultiDownloadTask.status.not_in(_TERMINAL))
        .values(status="cancelled", error="Cancelled by user", updated_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        exists = (await db.execute(select(MultiDownloadTask.id).where(MultiDownloadTask.id == task_id))).scalar_one_or_none()
        await db.commit()
        return exists is not None
    await db.commit()
    return True


async def dismiss_task(task_id: str, user_id: int, db: AsyncSession) -> bool:
    row = (await db.execute(
        select(MultiDownloadTask).where(MultiDownloadTask.id == task_id, MultiDownloadTask.user_id == user_id)
    )).scalar_one_or_none()
    if row is None:
        return False
    row.hidden = True
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return True


# --- download pipeline (background) ----------------------------------------

def _build_progress_hook(task_id: str):
    def hook(d: dict) -> None:
        with _tasks_lock:
            if task_id not in _active_tasks:
                return
            if _active_tasks[task_id].status == "cancelled":
                raise Exception("Download cancelled by user")
            if d.get("status") == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                pct = min(downloaded / total * 100, 99.0) if total > 0 else _active_tasks[task_id].progress
                raw_speed, raw_eta = d.get("speed"), d.get("eta")
                _active_tasks[task_id] = _active_tasks[task_id].model_copy(update={
                    "status": "downloading",
                    "progress": round(pct, 1),
                    "speed": float(raw_speed) if raw_speed is not None else None,
                    "eta": int(raw_eta) if raw_eta is not None else None,
                })
            elif d.get("status") == "finished":
                _active_tasks[task_id] = _active_tasks[task_id].model_copy(update={"progress": 99.0, "speed": None, "eta": None})
    return hook


def _run_ytdlp(ydl_opts: dict, url: str, task_id: str) -> None:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        _active_ytdlp[task_id] = ydl
        try:
            ydl.download([url])
        finally:
            _active_ytdlp.pop(task_id, None)


def _find_output(directory: str, extensions: tuple[str, ...]) -> str | None:
    temp = (".part", ".ytdl", ".tmp")
    fallback: str | None = None
    for fname in os.listdir(directory):
        fpath = os.path.join(directory, fname)
        if not os.path.isfile(fpath):
            continue
        low = fname.lower()
        if low.endswith(temp):
            continue
        if low.endswith(extensions):
            return fpath
        if fallback is None:
            fallback = fpath
    return fallback


async def _run_ffmpeg(args: list[str], task_id: str) -> None:
    _update_active(task_id, status="converting")
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("FFmpeg conversion timed out")
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg failed (rc={proc.returncode}): {stderr.decode(errors='replace')[-500:]}")


async def download(request: DownloadRequest, task_id: str, user_id: int, shared_file_id: str) -> None:
    """Background coroutine: download mp4 or extract mp3, then register a SharedFile."""
    url = request.url
    out_dir = os.path.join(settings.UPLOAD_DIR, shared_file_id)
    # Persist a "downloading" transition BEFORE creating any files. This moves the
    # row out of "pending" immediately so cleanup_stale_pending_tasks (which targets
    # pending rows older than 30 min) never race-deletes a live, long-running
    # download. A row left in "pending" therefore means the background task never
    # ran (e.g. lost on a restart) and is a genuine orphan — and has no out_dir yet.
    _update_active(task_id, status="downloading")
    await _persist_task(task_id, status="downloading")
    os.makedirs(out_dir, exist_ok=True)
    try:
        if request.audio_only:
            audio_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                "quiet": True, "no_warnings": True, "socket_timeout": 30, "noplaylist": True,
                "progress_hooks": [_build_progress_hook(task_id)],
                "ffmpeg_location": os.path.dirname(FFMPEG_PATH),
            }
            await asyncio.to_thread(_run_ytdlp, audio_opts, url, task_id)
            src = _find_output(out_dir, (".m4a", ".webm", ".ogg", ".opus", ".mp3", ".mp4", ".mkv"))
            if not src:
                raise RuntimeError("Downloaded audio file not found")
            base = os.path.splitext(os.path.basename(src))[0]
            output_file = os.path.join(out_dir, f"{base}.mp3")
            await _run_ffmpeg([FFMPEG_PATH, "-y", "-i", src, "-vn", "-acodec", "libmp3lame", output_file], task_id)
            if os.path.abspath(src) != os.path.abspath(output_file):
                try:
                    os.remove(src)
                except OSError:
                    pass
        else:
            video_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
                "quiet": True, "no_warnings": True, "socket_timeout": 30, "noplaylist": True,
                "progress_hooks": [_build_progress_hook(task_id)],
                "ffmpeg_location": os.path.dirname(FFMPEG_PATH),
            }
            await asyncio.to_thread(_run_ytdlp, video_opts, url, task_id)
            output_file = _find_output(out_dir, (".mp4", ".mkv", ".webm"))
            if not output_file:
                raise RuntimeError("Downloaded video file not found")

        if _is_cancelled(task_id):
            return

        final_filename = os.path.basename(output_file)
        try:
            final_size: int | None = os.path.getsize(output_file)
        except OSError:
            final_size = None
        completed_now = datetime.now(timezone.utc)

        async with async_session() as db_sf:
            db_sf.add(SharedFile(
                id=shared_file_id,
                video_id=f"multidl:{shared_file_id}",
                format="mp3" if request.audio_only else "mp4",
                quality="audio" if request.audio_only else "best",
                filename=final_filename,
                title=request.title,
                file_size=final_size,
                expires_at=completed_now + timedelta(hours=settings.FILE_TTL_HOURS),
                created_at=completed_now,
            ))
            await db_sf.commit()

        _update_active(task_id, status="ready", progress=100.0, filename=final_filename,
                       download_url=f"/api/multidl/file/{task_id}", file_size=final_size,
                       completed_at=completed_now, file_exists=True)
        await _persist_task(task_id, status="ready", progress=100.0, filename=final_filename,
                            file_size=final_size, shared_file_id=shared_file_id, completed_at=completed_now)
        logger.info("Multidl task %s ready: %s", task_id, final_filename)

    except Exception as exc:
        if _is_cancelled(task_id):
            shutil.rmtree(out_dir, ignore_errors=True)
            return
        msg = str(exc)
        logger.error("Multidl task %s failed: %s", task_id, msg, exc_info=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        _update_active(task_id, status="error", error=msg[:500])
        await _persist_task(task_id, status="error", error=msg[:500])
    finally:
        async def _evict() -> None:
            await asyncio.sleep(30)
            with _tasks_lock:
                _active_tasks.pop(task_id, None)
        asyncio.create_task(_evict())
