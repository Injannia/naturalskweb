"""
YouTube URL, cache-key, and file-location utilities.

These are pure functions with no I/O (except ``locate_task_file``, which
only does an ``os.walk``).  They are importable from both the router and
the service layer without creating circular imports.
"""

import hashlib
import os
import re
import urllib.parse

# ---------------------------------------------------------------------------
# Video ID extraction
# ---------------------------------------------------------------------------

# Matches the ?v= query parameter on watch URLs
_WATCH_V_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")

# Matches youtu.be/<id> short links
_SHORT_RE = re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})")

# Matches /shorts/<id>, /live/<id>, /embed/<id> path-style URLs
_PATH_RE = re.compile(r"/(?:shorts|live|embed)/([A-Za-z0-9_-]{11})")


def extract_video_id(url: str) -> str | None:
    """Return the YouTube video ID embedded in *url*, or ``None``.

    Handles the following URL forms:
    - ``https://www.youtube.com/watch?v=VIDEO_ID``
    - ``https://youtu.be/VIDEO_ID``
    - ``https://www.youtube.com/shorts/VIDEO_ID``
    - ``https://www.youtube.com/live/VIDEO_ID``
    - ``https://www.youtube.com/embed/VIDEO_ID``

    Returns ``None`` for playlist-only URLs (``list=`` without ``v=``).
    """
    for pattern in (_WATCH_V_RE, _SHORT_RE, _PATH_RE):
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Playlist cache key
# ---------------------------------------------------------------------------


def compute_playlist_cache_key(
    video_ids: list[str],
    fmt: str,
    quality: str,
) -> str:
    """Return a deterministic 40-char hex digest for a playlist download config.

    The key encodes the sorted set of video IDs plus the requested format and
    quality so that two requests that ask for the same videos in the same
    format will map to the same cache entry regardless of submission order.

    The resulting string is always exactly 40 hex characters (SHA-1), which
    safely fits in the ``video_id`` column (String(64)).
    """
    sorted_ids = sorted(video_ids)
    # Separator chosen to be unambiguous in both the ID list and format/quality
    raw = "|".join(sorted_ids) + f"||{fmt}||{quality}"
    return hashlib.sha1(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# File location helper
# ---------------------------------------------------------------------------


def locate_task_file(task_dir: str, filename: str) -> str | None:
    """Walk *task_dir* recursively and return the absolute path of *filename*.

    Returns ``None`` if the file is not found.  This utility lives here (rather
    than in the router) so both the router and the service layer can use it
    without creating circular imports.
    """
    for root, _dirs, files in os.walk(task_dir):
        if filename in files:
            file_path = os.path.join(root, filename)
            if not os.path.abspath(file_path).startswith(os.path.abspath(task_dir)):
                continue
            return file_path
    return None
