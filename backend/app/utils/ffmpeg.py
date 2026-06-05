"""Shared FFmpeg locator."""
import os
import shutil


def find_ffmpeg() -> str:
    """Return the path to ffmpeg, preferring known install locations over PATH."""
    candidates = [
        os.path.join(os.path.expanduser("~"), r"AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"
