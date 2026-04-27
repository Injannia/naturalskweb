import subprocess
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
    python_line = _run_first_line(["python", "--version"])
    ffmpeg_line = _run_first_line(["ffmpeg", "-version"])
    yt_dlp_line = _run_first_line(["yt-dlp", "--version"])

    python_version = python_line.replace("Python ", "") if python_line != "недоступно" else "недоступно"
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
