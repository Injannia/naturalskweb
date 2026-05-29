import subprocess
import sys
import time

_CACHE_TTL = 3600
_cache: dict | None = None
_cache_at: float = 0.0


def _run_first_line(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if not result.stdout:
            return "недоступно"
        return result.stdout.strip().splitlines()[0]
    except Exception:
        return "недоступно"


def get_tool_versions() -> dict:
    global _cache, _cache_at
    now = time.time()
    if _cache is not None and now - _cache_at < _CACHE_TTL:
        return _cache
    python_version = sys.version.split()[0]
    ffmpeg_line = _run_first_line(["ffmpeg", "-version"])
    # Запускаем yt-dlp как модуль текущего интерпретатора, а не CLI из PATH:
    # при старте через .venv/bin/uvicorn каталог .venv/bin в PATH не попадает,
    # хотя пакет yt_dlp установлен в venv (его же использует youtube_service).
    yt_dlp_line = _run_first_line([sys.executable, "-m", "yt_dlp", "--version"])

    if ffmpeg_line != "недоступно":
        parts = ffmpeg_line.split(" ")
        ffmpeg_version = parts[2] if len(parts) >= 3 else "недоступно"
    else:
        ffmpeg_version = "недоступно"

    _cache = {
        "python_version": python_version,
        "ffmpeg_version": ffmpeg_version,
        "yt_dlp_version": yt_dlp_line,
    }
    _cache_at = now
    return _cache
