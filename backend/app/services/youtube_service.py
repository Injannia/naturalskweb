"""
YouTube download service.

Responsibilities
----------------
* Fetch video / playlist metadata via yt-dlp (sync, run in thread).
* Execute downloads in the background, updating progress in-memory and
  persisting task state to SQLite via SQLAlchemy.
* Convert audio to mp3 / wav via FFmpeg subprocess.
* Package multi-video downloads (playlists) as a ZIP archive.

Design note — progress storage
------------------------------
yt-dlp progress hooks fire at very high frequency from a worker thread.
Writing to SQLite on every hook invocation would be extremely slow.
Instead we maintain a lightweight in-memory dict for the hot-path progress
updates (polled by the status endpoint) and persist to the database at every
meaningful *status transition* (pending → downloading → ready / error /
cancelled).  This means progress percentage is lost on restart but the task
record (including the terminal state and the download URL) survives.
"""

import asyncio
import json
import logging
import os
import re
import threading
import urllib.parse
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Union

import shutil

import yt_dlp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session

# ---------------------------------------------------------------------------
# Locate FFmpeg
# ---------------------------------------------------------------------------

def _find_ffmpeg() -> str:
    """Return the path to ffmpeg, preferring known install locations over PATH."""
    candidates = [
        # WinGet install path (Windows-specific)
        os.path.join(
            os.path.expanduser("~"),
            r"AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe",
        ),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"  # fall back to bare name; let the OS resolve it


from app.models.download_task import DownloadTask
from app.models.shared_file import SharedFile
from app.schemas.youtube import (
    DownloadRequest,
    DownloadStatus,
    PlaylistInfo,
    VideoFormat,
    VideoInfo,
)
from app.utils.youtube_helpers import extract_video_id, compute_playlist_cache_key, locate_task_file

logger = logging.getLogger("naturalsk.youtube")

FFMPEG_PATH = _find_ffmpeg()
logger.info("Using ffmpeg: %s", FFMPEG_PATH)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_VIDEO_DURATION_SECONDS = 4 * 60 * 60  # 4 hours
MAX_PLAYLIST_VIDEOS = 50

# Resolutions we expose to the user (height in pixels → label)
_RESOLUTION_MAP: dict[int, str] = {
    1080: "1080p",
    720: "720p",
    480: "480p",
    360: "360p",
}

# quality label → yt-dlp format selector for video+audio merge
_QUALITY_FORMAT: dict[str, str] = {
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]",
}

# ---------------------------------------------------------------------------
# In-memory task cache (hot-path progress updates during active downloads)
# ---------------------------------------------------------------------------

# Maps task_id → current DownloadStatus for tasks that are actively running.
# Terminal states (ready / error / cancelled) are flushed to DB then removed.
_active_tasks: dict[str, DownloadStatus] = {}
_tasks_lock = threading.Lock()

# Track which yt-dlp downloader is running for a given task so cancel works.
_active_ytdlp: dict[str, yt_dlp.YoutubeDL] = {}


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Return *dt* with UTC timezone, treating naive datetimes as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _row_to_status(row: DownloadTask, *, check_file: bool = False) -> DownloadStatus:
    """Convert a :class:`DownloadTask` ORM row to a :class:`DownloadStatus`."""
    video_ids: list[str] | None = None
    if row.video_ids:
        try:
            video_ids = json.loads(row.video_ids)
        except (ValueError, TypeError):
            video_ids = None

    download_url: str | None = None
    if row.status == "ready":
        download_url = f"/api/youtube/file/{row.id}"

    file_exists = False
    if check_file and row.filename and row.shared_file_id:
        shared_dir = os.path.join(settings.UPLOAD_DIR, row.shared_file_id)
        file_path = locate_task_file(shared_dir, row.filename)
        file_exists = file_path is not None and os.path.isfile(file_path)

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
        format=row.format,
        quality=row.quality,
        video_ids=video_ids,
        created_at=_ensure_utc(row.created_at),
        completed_at=_ensure_utc(row.completed_at),
        cached=row.is_cache_hit,
        file_exists=file_exists,
    )


async def _persist_task(task_id: str, **updates) -> None:
    """Write *updates* to the :class:`DownloadTask` row identified by *task_id*."""
    # Always stamp updated_at
    updates.setdefault("updated_at", datetime.now(timezone.utc))
    async with async_session() as db:
        result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id))
        row = result.scalar_one_or_none()
        if row is None:
            logger.warning("_persist_task: task %s not found in DB", task_id)
            return
        for key, value in updates.items():
            setattr(row, key, value)
        await db.commit()


async def get_task_for_user(
    task_id: str,
    user_id: int,
    db: AsyncSession,
) -> DownloadTask | None:
    """Fetch a task by ID, returning None if not found or not owned by *user_id*."""
    result = await db.execute(
        select(DownloadTask).where(DownloadTask.id == task_id)
    )
    row = result.scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None
    return row


async def resolve_shared_file_dir(
    task_id: str,
    user_id: int,
    db: AsyncSession,
) -> str | None:
    """Return the uploads directory path for the SharedFile linked to this task.

    Returns None if task not found, not owned by user, or has no shared_file_id yet.
    """
    row = await get_task_for_user(task_id, user_id, db)
    if row is None or row.shared_file_id is None:
        return None
    return os.path.join(settings.UPLOAD_DIR, row.shared_file_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_playlist_url(url: str) -> bool:
    """Return True when the URL points to a standalone playlist (no video ID).

    A URL with both ``watch?v=`` and ``list=`` means the user opened a specific
    video that happens to be part of a playlist — treat it as a single video.
    Only a URL that has ``list=`` *without* a ``v`` query param is a true
    playlist URL.
    """
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    return "list" in params and "v" not in params


def _update_active_task(task_id: str, **updates) -> None:
    """Thread-safe update of the in-memory active task entry."""
    with _tasks_lock:
        if task_id in _active_tasks:
            _active_tasks[task_id] = _active_tasks[task_id].model_copy(update=updates)


def _is_cancelled(task_id: str) -> bool:
    """Return True if the task was cancelled by the user."""
    with _tasks_lock:
        task = _active_tasks.get(task_id)
        return task is not None and task.status == "cancelled"


def _safe_filename(name: str) -> str:
    """Strip characters that are invalid in file/directory names."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:200]


def _parse_formats(raw_formats: list[dict]) -> list[VideoFormat]:
    """
    Extract video formats, keeping only the target resolutions.
    Deduplicates by resolution (keeps the highest-bitrate entry).
    """
    seen: dict[str, VideoFormat] = {}
    for fmt in raw_formats:
        height = fmt.get("height")
        if not height or height not in _RESOLUTION_MAP:
            continue
        label = _RESOLUTION_MAP[height]
        vcodec = fmt.get("vcodec") or "none"
        acodec = fmt.get("acodec") or "none"
        # Skip audio-only tracks
        if vcodec == "none":
            continue
        entry = VideoFormat(
            format_id=fmt.get("format_id", ""),
            ext=fmt.get("ext", ""),
            resolution=label,
            filesize=fmt.get("filesize") or fmt.get("filesize_approx"),
            fps=fmt.get("fps"),
            vcodec=vcodec,
            acodec=acodec,
        )
        # Prefer the entry with a known filesize (proxy for higher quality)
        if label not in seen or (entry.filesize and not seen[label].filesize):
            seen[label] = entry
    return list(seen.values())


def _extract_video_info_sync(url: str) -> VideoInfo:
    """Blocking yt-dlp extraction for a single video."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("yt-dlp returned no info for the given URL")

    return VideoInfo(
        id=info.get("id", ""),
        title=info.get("title", ""),
        thumbnail=info.get("thumbnail", ""),
        duration=int(info.get("duration") or 0),
        channel=info.get("channel") or info.get("uploader") or "",
        upload_date=info.get("upload_date") or "",
        formats=_parse_formats(info.get("formats") or []),
    )


def _extract_playlist_info_sync(url: str) -> PlaylistInfo:
    """Blocking yt-dlp extraction for a playlist.

    Uses flat extraction only — no per-video full format fetching.
    Flat entries include title, duration, and thumbnail from the playlist
    manifest, making this near-instant compared to the previous approach of
    doing a full yt-dlp call per video.

    Format information is intentionally omitted for playlist previews; it is
    only fetched at actual download time via ``_download_single_video``.
    """
    flat_opts = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "extract_flat": True,
        "playlistend": MAX_PLAYLIST_VIDEOS,
    }
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        playlist_info = ydl.extract_info(url, download=False)

    if not playlist_info or playlist_info.get("_type") != "playlist":
        raise ValueError("URL does not point to a playlist")

    entries_raw = playlist_info.get("entries") or []
    playlist_id = playlist_info.get("id") or ""
    playlist_title = playlist_info.get("title") or ""
    channel = (
        playlist_info.get("channel")
        or playlist_info.get("uploader")
        or ""
    )

    videos: list[VideoInfo] = []
    for entry in entries_raw[:MAX_PLAYLIST_VIDEOS]:
        if not entry:
            continue
        video_id = entry.get("id") or ""
        # Flat entries carry basic metadata without format details.
        videos.append(
            VideoInfo(
                id=video_id,
                title=entry.get("title") or video_id,
                thumbnail=entry.get("thumbnail") or entry.get("thumbnails", [{}])[0].get("url", "") if entry.get("thumbnails") else "",
                duration=int(entry.get("duration") or 0),
                channel=entry.get("channel") or entry.get("uploader") or channel,
                upload_date=entry.get("upload_date") or "",
                # No format details available from flat extraction.
                formats=[],
            )
        )

    return PlaylistInfo(
        id=playlist_id,
        title=playlist_title,
        channel=channel,
        video_count=len(videos),
        videos=videos,
    )


def _build_progress_hook(task_id: str):
    """Return a yt-dlp progress_hook that updates the in-memory registry.

    This hook is called from a worker thread managed by asyncio.to_thread, so
    all reads and writes to _active_tasks must go through _tasks_lock.
    """

    def hook(d: dict) -> None:
        with _tasks_lock:
            if task_id not in _active_tasks:
                return
            # If the task was already cancelled, do not overwrite the cancelled
            # status with a stale "downloading" update from the still-running
            # yt-dlp thread.  Raising an exception here also signals yt-dlp to
            # abort the current download immediately.
            if _active_tasks[task_id].status == "cancelled":
                raise Exception("Download cancelled by user")
            hook_status = d.get("status")
            if hook_status == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if total > 0:
                    pct = min(downloaded / total * 100, 99.0)
                else:
                    pct = _active_tasks[task_id].progress
                raw_speed = d.get("speed")
                raw_eta = d.get("eta")
                _active_tasks[task_id] = _active_tasks[task_id].model_copy(
                    update={
                        "status": "downloading",
                        "progress": round(pct, 1),
                        "speed": float(raw_speed) if raw_speed is not None else None,
                        "eta": int(raw_eta) if raw_eta is not None else None,
                    }
                )
            elif hook_status == "finished":
                # yt-dlp signals finished per-file; post-processing may still run.
                # Clear transfer metrics as they are no longer meaningful.
                _active_tasks[task_id] = _active_tasks[task_id].model_copy(
                    update={"progress": 99.0, "speed": None, "eta": None}
                )

    return hook


async def _run_ffmpeg(args: list[str], task_id: str) -> None:
    """Run FFmpeg as an async subprocess; raise RuntimeError on non-zero exit."""
    _update_active_task(task_id, status="converting")
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("FFmpeg conversion timed out")

    if proc.returncode != 0:
        msg = stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"FFmpeg failed (rc={proc.returncode}): {msg}")


def _find_single_file(directory: str, extensions: tuple[str, ...]) -> str | None:
    """Return the first file found in *directory* with one of *extensions*.

    Falls back to any non-temporary file if no extension match is found,
    because yt-dlp can produce unexpected extensions (.weba, .aac, etc.)
    depending on the source and platform.
    """
    _TEMP_SUFFIXES = (".part", ".ytdl", ".tmp")
    fallback: str | None = None
    for fname in os.listdir(directory):
        fpath = os.path.join(directory, fname)
        if not os.path.isfile(fpath):
            continue
        lower = fname.lower()
        if lower.endswith(_TEMP_SUFFIXES):
            continue
        if lower.endswith(extensions):
            return fpath
        if fallback is None:
            fallback = fpath
    return fallback


async def _download_single_video(
    url: str,
    task_id: str,
    fmt: str,
    quality: str,
    out_dir: str,
) -> str:
    """
    Download a single video/audio track.

    Returns the absolute path to the final output file.
    """
    os.makedirs(out_dir, exist_ok=True)

    if fmt == "mp4":
        format_selector = _QUALITY_FORMAT.get(quality, _QUALITY_FORMAT["best"])
        ydl_opts: dict = {
            "format": format_selector,
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "noplaylist": True,
            "progress_hooks": [_build_progress_hook(task_id)],
            "ffmpeg_location": os.path.dirname(FFMPEG_PATH),
        }
        await asyncio.to_thread(_run_ytdlp_download, ydl_opts, url, task_id)
        # yt-dlp may fall back to .mkv or .webm when the mp4 streams are
        # unavailable; accept all common video containers.
        output_file = _find_single_file(out_dir, (".mp4", ".mkv", ".webm"))
        if not output_file:
            raise RuntimeError("Downloaded video file not found in output directory")
        return output_file

    else:  # mp3 or wav
        # Download best audio as m4a/webm/best
        audio_opts: dict = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "noplaylist": True,
            "progress_hooks": [_build_progress_hook(task_id)],
            "ffmpeg_location": os.path.dirname(FFMPEG_PATH),
        }
        await asyncio.to_thread(_run_ytdlp_download, audio_opts, url, task_id)

        # Locate the downloaded audio file.
        # Include video container extensions (.mp4, .mkv) because the
        # "bestaudio/best" format selector can fall back to "best" which
        # downloads a muxed video file when no audio-only stream exists.
        audio_file = _find_single_file(out_dir, (".m4a", ".webm", ".ogg", ".opus", ".mp3", ".wav", ".mp4", ".mkv"))
        if not audio_file:
            raise RuntimeError("Downloaded audio file not found in output directory")

        # Derive a safe output filename from the audio file stem
        base = os.path.splitext(os.path.basename(audio_file))[0]
        output_file = os.path.join(out_dir, f"{base}.{fmt}")

        codec = "libmp3lame" if fmt == "mp3" else "pcm_s16le"
        ffmpeg_args = [
            FFMPEG_PATH, "-y",
            "-i", audio_file,
            "-vn",
            "-acodec", codec,
            output_file,
        ]
        await _run_ffmpeg(ffmpeg_args, task_id)

        # Remove the intermediate audio file to save space
        try:
            os.remove(audio_file)
        except OSError:
            pass

        return output_file


def _run_ytdlp_download(ydl_opts: dict, url: str, task_id: str) -> None:
    """Synchronous wrapper called inside asyncio.to_thread."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        _active_ytdlp[task_id] = ydl
        try:
            ydl.download([url])
        finally:
            _active_ytdlp.pop(task_id, None)


def _flat_extract(ydl_opts: dict, url: str) -> dict:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_video_info(url: str) -> Union[VideoInfo, PlaylistInfo]:
    """
    Fetch metadata for a single video or an entire playlist.

    Raises
    ------
    TimeoutError
        When yt-dlp does not respond within the allowed time.
    yt_dlp.utils.DownloadError
        When the video is unavailable (private, deleted, geo-blocked, etc.).
    ValueError
        When yt-dlp returns no usable data.
    """
    is_playlist = _is_playlist_url(url)
    try:
        if is_playlist:
            return await asyncio.wait_for(
                asyncio.to_thread(_extract_playlist_info_sync, url),
                timeout=60.0,
            )
        else:
            return await asyncio.wait_for(
                asyncio.to_thread(_extract_video_info_sync, url),
                timeout=30.0,
            )
    except asyncio.TimeoutError:
        raise TimeoutError("Timed out while fetching video information")


async def create_task(
    task_id: str,
    user_id: int,
    request: DownloadRequest,
    db: AsyncSession,
    video_id: str | None = None,
) -> DownloadStatus:
    """Persist a new pending task row and register it in the in-memory cache."""
    video_ids_json: str | None = None
    if request.video_ids:
        video_ids_json = json.dumps(request.video_ids)

    row = DownloadTask(
        id=task_id,
        user_id=user_id,
        status="pending",
        progress=0.0,
        url=request.url,
        title=request.title,
        format=request.format,
        quality=request.quality,
        video_ids=video_ids_json,
        video_id=video_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    initial = _row_to_status(row)
    with _tasks_lock:
        _active_tasks[task_id] = initial
    return initial


async def find_in_progress_task(
    video_id: str,
    fmt: str,
    quality: str,
    db: AsyncSession,
) -> DownloadTask | None:
    """Look up an existing task that is currently being downloaded.

    A task qualifies when:
    - ``video_id`` matches exactly
    - ``format`` and ``quality`` match
    - ``status`` is one of the active non-terminal states

    Returns the most recently created matching task, or ``None``.
    """
    active_statuses = ("pending", "downloading", "converting", "zipping")
    result = await db.execute(
        select(DownloadTask).where(
            DownloadTask.video_id == video_id,
            DownloadTask.format == fmt,
            DownloadTask.quality == quality,
            DownloadTask.status.in_(active_statuses),
        ).order_by(DownloadTask.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def wait_for_source_task(
    watcher_task_id: str,
    source_task_id: str,
) -> None:
    """Background coroutine that tracks a source download and mirrors its outcome.

    Polls ``source_task_id`` every 2 seconds.  When the source reaches a
    terminal state the watcher task is updated to match:
    - ``ready``  → watcher becomes ready with the same filename/file_size
    - ``error``  → watcher becomes error with the same message
    - ``cancelled`` → watcher becomes cancelled

    If the source does not complete within 2 hours the watcher is failed.
    """
    POLL_INTERVAL = 2.0       # seconds between status checks
    MAX_WAIT = 7200.0         # 2 hours hard cap
    elapsed = 0.0

    logger.info(
        "Watcher task %s is waiting for source task %s",
        watcher_task_id,
        source_task_id,
    )

    while elapsed < MAX_WAIT:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        source = await get_download_progress(source_task_id)
        if source is None:
            # Source was cleaned up — fail the watcher
            error_msg = "Source download task no longer exists"
            _update_active_task(watcher_task_id, status="error", error=error_msg)
            await _persist_task(watcher_task_id, status="error", error=error_msg)
            logger.warning(
                "Watcher task %s: source %s disappeared", watcher_task_id, source_task_id
            )
            return

        if source.status in ("pending", "downloading", "converting", "zipping"):
            # Mirror progress so the watcher user sees meaningful feedback
            _update_active_task(
                watcher_task_id,
                status=source.status,
                progress=source.progress,
            )
            continue

        if source.status == "ready":
            # Wait for source task's shared_file_id to be persisted
            # (small delay possible between status=ready and shared_file_id commit)
            source_shared_file_id: str | None = None
            for _attempt in range(5):
                async with async_session() as db_inner:
                    sf_result = await db_inner.execute(
                        select(DownloadTask.shared_file_id).where(DownloadTask.id == source_task_id)
                    )
                    source_shared_file_id = sf_result.scalar_one_or_none()
                if source_shared_file_id is not None:
                    break
                await asyncio.sleep(1.0)

            if source_shared_file_id is None:
                error_msg = "Source task completed but shared_file_id not available"
                _update_active_task(watcher_task_id, status="error", error=error_msg)
                await _persist_task(watcher_task_id, status="error", error=error_msg)
                logger.warning("Watcher task %s: %s", watcher_task_id, error_msg)
                return

            completed_now = datetime.now(timezone.utc)
            _update_active_task(
                watcher_task_id,
                status="ready",
                progress=100.0,
                filename=source.filename,
                file_size=source.file_size,
                download_url=f"/api/youtube/file/{watcher_task_id}",
                completed_at=completed_now,
            )
            await _persist_task(
                watcher_task_id,
                status="ready",
                progress=100.0,
                filename=source.filename,
                file_size=source.file_size,
                shared_file_id=source_shared_file_id,
                completed_at=completed_now,
            )
            logger.info(
                "Watcher task %s resolved via source %s: %s (shared_file_id=%s)",
                watcher_task_id,
                source_task_id,
                source.filename,
                source_shared_file_id,
            )
            return

        if source.status == "error":
            error_msg = source.error or "Source download failed"
            _update_active_task(watcher_task_id, status="error", error=error_msg)
            await _persist_task(watcher_task_id, status="error", error=error_msg)
            logger.warning(
                "Watcher task %s: source %s errored: %s",
                watcher_task_id,
                source_task_id,
                error_msg,
            )
            return

        if source.status == "cancelled":
            error_msg = "Загрузка не выполнена: оригинальный процесс был отменён"
            _update_active_task(watcher_task_id, status="error", error=error_msg)
            await _persist_task(watcher_task_id, status="error", error=error_msg)
            logger.info(
                "Watcher task %s: source %s was cancelled", watcher_task_id, source_task_id
            )
            return

        # Unknown terminal state — treat as error
        error_msg = f"Source task ended with unexpected status: {source.status}"
        _update_active_task(watcher_task_id, status="error", error=error_msg)
        await _persist_task(watcher_task_id, status="error", error=error_msg)
        return

    # Timed out
    error_msg = "Timed out waiting for source download to complete"
    _update_active_task(watcher_task_id, status="error", error=error_msg)
    await _persist_task(watcher_task_id, status="error", error=error_msg)
    logger.error(
        "Watcher task %s: timed out after %.0fs waiting for source %s",
        watcher_task_id,
        elapsed,
        source_task_id,
    )


async def find_cached_shared_file(
    video_id: str,
    fmt: str,
    quality: str,
    db: AsyncSession,
) -> SharedFile | None:
    """Look up an existing SharedFile that can be reused as a cache hit.

    Returns the most recently created SharedFile matching video_id+format+quality
    that expires more than 5 minutes from now and has its file still on disk.
    """
    min_expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    # SQLite stores datetimes as naive strings — compare without tz
    min_expires_naive = min_expires.replace(tzinfo=None)

    result = await db.execute(
        select(SharedFile).where(
            SharedFile.video_id == video_id,
            SharedFile.format == fmt,
            SharedFile.quality == quality,
            SharedFile.expires_at > min_expires_naive,
        ).order_by(SharedFile.created_at.desc()).limit(5)
    )
    candidates = result.scalars().all()

    for sf in candidates:
        shared_dir = os.path.join(settings.UPLOAD_DIR, sf.id)
        file_path = locate_task_file(shared_dir, sf.filename)
        if file_path and os.path.isfile(file_path):
            return sf

    return None


async def create_cached_task(
    task_id: str,
    user_id: int,
    request: DownloadRequest,
    shared_file: SharedFile,
    video_id: str | None,
    db: AsyncSession,
) -> DownloadStatus:
    """Persist a cache-hit task row that re-uses an existing SharedFile.

    Status is set to "ready" immediately — no download is queued.
    completed_at inherits shared_file.created_at so the frontend TTL countdown
    reflects the actual time remaining on the cached file.
    """
    video_ids_json: str | None = None
    if request.video_ids:
        video_ids_json = json.dumps(request.video_ids)

    inherited_completed_at = _ensure_utc(shared_file.created_at) or datetime.now(timezone.utc)

    row = DownloadTask(
        id=task_id,
        user_id=user_id,
        status="ready",
        progress=100.0,
        url=request.url,
        title=shared_file.title or request.title,
        format=request.format,
        quality=request.quality,
        video_ids=video_ids_json,
        video_id=video_id,
        filename=shared_file.filename,
        file_size=shared_file.file_size,
        shared_file_id=shared_file.id,
        is_cache_hit=True,
        completed_at=inherited_completed_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return _row_to_status(row)


async def get_download_progress(task_id: str) -> DownloadStatus | None:
    """Return the current :class:`DownloadStatus` for *task_id*, or ``None``.

    Checks the in-memory cache first (active downloads); falls back to the
    database for completed / cancelled tasks that are no longer in-memory.
    """
    with _tasks_lock:
        cached = _active_tasks.get(task_id)
    if cached is not None:
        return cached

    # Task not in memory — look it up in the database
    async with async_session() as db:
        result = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id))
        row = result.scalar_one_or_none()
    if row is None:
        return None
    return _row_to_status(row)


async def get_user_tasks(user_id: int, limit: int = 50) -> list[DownloadStatus]:
    """Return the most recent download tasks for *user_id*.

    Queries the database for tasks created within the last FILE_TTL_HOURS hours
    (matching the server-side file retention window), ordered by creation time
    descending, capped at *limit* rows.  In-memory state for active tasks is
    merged in so progress values are accurate.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)
    cutoff_naive = cutoff.replace(tzinfo=None)

    async with async_session() as db:
        stmt = (
            select(DownloadTask)
            .where(
                DownloadTask.user_id == user_id,
                DownloadTask.created_at >= cutoff_naive,
                DownloadTask.hidden == False,  # noqa: E712
            )
            .order_by(DownloadTask.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

    statuses: list[DownloadStatus] = []
    for row in rows:
        # Prefer live in-memory state for active tasks (has up-to-date progress).
        with _tasks_lock:
            cached = _active_tasks.get(row.id)
        if cached is not None:
            statuses.append(cached)
        else:
            statuses.append(_row_to_status(row, check_file=True))

    return statuses


async def cancel_task(task_id: str) -> bool:
    """
    Best-effort cancellation.

    Marks the task as cancelled immediately so the background coroutine can
    detect it, and interrupts any running yt-dlp instance.

    Returns ``True`` if the task existed, ``False`` otherwise.
    """
    with _tasks_lock:
        if task_id not in _active_tasks:
            # Check DB for tasks that finished but are still reachable
            pass
        else:
            task = _active_tasks[task_id]
            if task.status in ("ready", "error", "cancelled"):
                return True  # nothing to do

            _active_tasks[task_id] = task.model_copy(
                update={"status": "cancelled", "error": "Cancelled by user"}
            )

    # Interrupt the yt-dlp downloader if it is active
    ydl = _active_ytdlp.pop(task_id, None)
    if ydl:
        try:
            ydl.params["abort_on_error"] = True
        except Exception:
            pass

    # Persist cancellation to DB atomically.
    # The WHERE clause guards against overwriting a terminal status that was
    # written concurrently by the download coroutine (race condition fix).
    async with async_session() as db:
        stmt = (
            update(DownloadTask)
            .where(
                DownloadTask.id == task_id,
                DownloadTask.status.not_in(("ready", "error", "cancelled")),
            )
            .values(
                status="cancelled",
                error="Cancelled by user",
                updated_at=datetime.now(timezone.utc),
            )
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(stmt)
        if result.rowcount == 0:
            # Either the task does not exist, or it already reached a terminal
            # state before the cancellation landed — both cases are acceptable.
            # Re-check existence so we can return the correct bool to the caller.
            exists = await db.execute(
                select(DownloadTask.id).where(DownloadTask.id == task_id)
            )
            await db.commit()
            return exists.scalar_one_or_none() is not None
        await db.commit()

    return True


async def dismiss_task(task_id: str, user_id: int) -> bool:
    """Mark a single task as hidden so it no longer appears in list responses.

    Parameters
    ----------
    task_id:
        UUID of the task to hide.
    user_id:
        ID of the requesting user — ownership is enforced to prevent one user
        from hiding another user's tasks.

    Returns
    -------
    bool
        ``True`` if the row was found and updated, ``False`` if not found or
        the task belongs to a different user.
    """
    async with async_session() as db:
        result = await db.execute(
            select(DownloadTask).where(
                DownloadTask.id == task_id,
                DownloadTask.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.hidden = True
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()

    logger.debug("Task %s dismissed by user %d", task_id, user_id)
    return True


async def get_hidden_tasks(user_id: int, limit: int = 50) -> list[DownloadStatus]:
    """Return hidden (dismissed) tasks for *user_id* that still have files available.

    Only tasks within the FILE_TTL_HOURS window are returned — tasks whose
    files have been cleaned up from disk are excluded so the UI only shows
    items the user can actually re-download.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FILE_TTL_HOURS)
    cutoff_naive = cutoff.replace(tzinfo=None)

    async with async_session() as db:
        stmt = (
            select(DownloadTask)
            .where(
                DownloadTask.user_id == user_id,
                DownloadTask.created_at >= cutoff_naive,
                DownloadTask.hidden == True,  # noqa: E712
            )
            .order_by(DownloadTask.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

    return [_row_to_status(row, check_file=True) for row in rows]


async def restore_task(task_id: str, user_id: int) -> bool:
    """Un-dismiss a task so it appears in the active list again.

    Returns True if the row was found and updated, False otherwise.
    """
    async with async_session() as db:
        result = await db.execute(
            select(DownloadTask).where(
                DownloadTask.id == task_id,
                DownloadTask.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.hidden = False
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()

    logger.debug("Task %s restored by user %d", task_id, user_id)
    return True


async def dismiss_completed_tasks(user_id: int) -> int:
    """Mark all completed tasks for *user_id* as hidden.

    Completed is defined as status in ``ready``, ``error``, or ``cancelled``.

    Returns
    -------
    int
        The number of tasks that were hidden.
    """
    terminal_statuses = ("ready", "error", "cancelled")
    async with async_session() as db:
        result = await db.execute(
            update(DownloadTask)
            .where(
                DownloadTask.user_id == user_id,
                DownloadTask.status.in_(terminal_statuses),
                DownloadTask.hidden == False,  # noqa: E712
            )
            .values(hidden=True, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
        count = result.rowcount

    logger.debug("Dismissed %d completed tasks for user %d", count, user_id)
    return count


async def delete_task_permanent(task_id: str, user_id: int) -> bool:
    """Delete a download task record from DB.

    Only allowed for terminal tasks (ready/error/cancelled).
    SharedFile and actual files on disk are NOT touched —
    they expire naturally after FILE_TTL_HOURS.
    """
    terminal_statuses = ("ready", "error", "cancelled")

    async with async_session() as db:
        result = await db.execute(
            select(DownloadTask).where(
                DownloadTask.id == task_id,
                DownloadTask.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        if row.status not in terminal_statuses:
            return False

        with _tasks_lock:
            _active_tasks.pop(task_id, None)

        await db.delete(row)
        await db.commit()

    logger.info("Download task %s permanently deleted by user %d (files kept on disk)", task_id, user_id)
    return True


async def download_video(
    request: DownloadRequest,
    task_id: str,
    user_id: int,
    shared_file_id: str,
) -> None:
    """
    Background coroutine that performs the full download pipeline.

    Progress and final status are written to both the in-memory cache and the
    database.  The caller must have already called :func:`create_task`.
    """
    url = request.url
    fmt = request.format
    quality = request.quality
    out_dir = os.path.join(settings.UPLOAD_DIR, shared_file_id)
    os.makedirs(out_dir, exist_ok=True)

    try:
        is_playlist = _is_playlist_url(url)

        if is_playlist:
            # -----------------------------------------------------------
            # Playlist download: one file per video, then ZIP everything
            # -----------------------------------------------------------
            flat_opts = {
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
                "extract_flat": True,
                "playlistend": MAX_PLAYLIST_VIDEOS,
            }
            playlist_info = await asyncio.wait_for(
                asyncio.to_thread(lambda: _flat_extract(flat_opts, url)),
                timeout=30.0,
            )
            entries = playlist_info.get("entries") or []

            # Filter to requested video IDs if supplied
            if request.video_ids:
                requested = set(request.video_ids)
                entries = [e for e in entries if e.get("id") in requested]

            if not entries:
                raise ValueError("No matching videos found in playlist")

            downloaded_files: list[str] = []
            total = len(entries)

            for idx, entry in enumerate(entries):
                if _is_cancelled(task_id):
                    return

                video_url = (
                    entry.get("url")
                    or entry.get("webpage_url")
                    or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                )
                video_out_dir = os.path.join(out_dir, f"video_{idx}")
                try:
                    fpath = await _download_single_video(video_url, task_id, fmt, quality, video_out_dir)
                    downloaded_files.append(fpath)
                except Exception as exc:
                    logger.warning("Skipping video %s in playlist: %s", entry.get("id"), exc)

                # Stop processing if the task was cancelled during the download
                if _is_cancelled(task_id):
                    return

                # Update overall progress
                base_pct = (idx + 1) / total * 90.0  # reserve last 10% for zipping
                _update_active_task(task_id, progress=round(base_pct, 1))

            if not downloaded_files:
                raise RuntimeError("All playlist videos failed to download")

            # Create ZIP archive
            _update_active_task(task_id, status="zipping", progress=90.0)
            playlist_title = _safe_filename(playlist_info.get("title") or "playlist")
            zip_path = os.path.join(out_dir, f"{playlist_title}.zip")

            def _zip_files() -> None:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for fpath in downloaded_files:
                        zf.write(fpath, arcname=os.path.basename(fpath))

            await asyncio.to_thread(_zip_files)
            final_filename = os.path.basename(zip_path)
            download_url = f"/api/youtube/file/{task_id}"

        else:
            # -----------------------------------------------------------
            # Single video download
            # -----------------------------------------------------------
            output_file = await _download_single_video(url, task_id, fmt, quality, out_dir)
            final_filename = os.path.basename(output_file)
            download_url = f"/api/youtube/file/{task_id}"
            zip_path = output_file  # reuse variable for file_size lookup below

        # If the task was cancelled during download, do not overwrite the cancelled state.
        if _is_cancelled(task_id):
            return

        # Determine file size for reporting
        try:
            final_file_size: int | None = os.path.getsize(zip_path)
        except OSError:
            final_file_size = None

        completed_now = datetime.now(timezone.utc)

        # Compute video_id (cache key) for SharedFile
        if request.video_ids:
            sf_video_id = compute_playlist_cache_key(request.video_ids, fmt, quality)
        else:
            sf_video_id = extract_video_id(url) or shared_file_id

        async with async_session() as db_sf:
            sf = SharedFile(
                id=shared_file_id,
                video_id=sf_video_id,
                format=fmt,
                quality=quality,
                filename=final_filename,
                title=request.title,
                file_size=final_file_size,
                expires_at=completed_now + timedelta(hours=settings.FILE_TTL_HOURS),
                created_at=completed_now,
            )
            db_sf.add(sf)
            await db_sf.commit()

        _update_active_task(
            task_id,
            status="ready",
            progress=100.0,
            filename=final_filename,
            download_url=download_url,
            file_size=final_file_size,
            completed_at=completed_now,
        )

        # Persist terminal state to DB
        await _persist_task(
            task_id,
            status="ready",
            progress=100.0,
            filename=final_filename,
            file_size=final_file_size,
            shared_file_id=shared_file_id,
            completed_at=completed_now,
        )

        logger.info("Download task %s completed: %s (shared_file=%s)", task_id, final_filename, shared_file_id)

    except asyncio.CancelledError:
        # Clean up partial files — no SharedFile record was created, so
        # the directory would otherwise be orphaned until the fallback scanner runs.
        shutil.rmtree(out_dir, ignore_errors=True)
        _update_active_task(task_id, status="cancelled", error="Download was cancelled")
        await _persist_task(task_id, status="cancelled", error="Download was cancelled")
        logger.info("Download task %s was cancelled", task_id)

    except Exception as exc:
        # If the task was already cancelled (e.g. the progress hook raised to
        # abort yt-dlp), do not overwrite the persisted "cancelled" state.
        if _is_cancelled(task_id):
            logger.info("Download task %s aborted due to cancellation: %s", task_id, exc)
            shutil.rmtree(out_dir, ignore_errors=True)
            return
        error_msg = str(exc)
        logger.error("Download task %s failed: %s", task_id, error_msg, exc_info=True)
        shutil.rmtree(out_dir, ignore_errors=True)
        _update_active_task(task_id, status="error", error=error_msg[:500])
        await _persist_task(task_id, status="error", error=error_msg[:500])

    finally:
        # Remove from in-memory cache after a short grace period so the
        # status endpoint can still serve the terminal state from memory
        # before the next poll hits the DB.
        async def _evict() -> None:
            await asyncio.sleep(30)
            with _tasks_lock:
                _active_tasks.pop(task_id, None)

        asyncio.create_task(_evict())
