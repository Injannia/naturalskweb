import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas._types import UtcDatetime

# ---------------------------------------------------------------------------
# Allowed quality and format literals
# ---------------------------------------------------------------------------
ALLOWED_QUALITIES = Literal["best", "1080p", "720p", "480p", "360p"]
ALLOWED_FORMATS = Literal["mp4", "mp3", "wav"]

# YouTube URL pattern — accepts only video/playlist/shorts/live URLs.
# Rejects channel pages (/channel/, /@username), user pages, and other
# non-downloadable YouTube paths that yt-dlp cannot handle as single items.
#
# Accepted forms:
#   youtube.com/watch?v=XXXXXXXXXXX         (11-char video ID required)
#   youtube.com/playlist?list=...
#   youtube.com/shorts/XXXXXXXXXXX          (11-char video ID required)
#   youtube.com/live/XXXXXXXXXXX            (11-char video ID required)
#   youtu.be/XXXXXXXXXXX                    (11-char video ID required)
#   m.youtube.com/... and www.youtube.com/... variants of all the above
_YT_PATTERN = re.compile(
    r"^https?://(www\.|m\.)?("
    r"youtube\.com/watch\?.*v=[A-Za-z0-9_-]{11}"
    r"|youtube\.com/playlist\?.*list=[A-Za-z0-9_-]+"
    r"|youtube\.com/shorts/[A-Za-z0-9_-]{11}"
    r"|youtube\.com/live/[A-Za-z0-9_-]{11}"
    r"|youtu\.be/[A-Za-z0-9_-]{11}"
    r")"
)


def _validate_youtube_url(url: str) -> str:
    """Raise ValueError when *url* is not a supported YouTube content link.

    Rejects channel URLs (``/channel/``, ``/@username``), user pages, and
    any other path that does not resolve to a downloadable video or playlist.
    """
    if not _YT_PATTERN.match(url):
        raise ValueError(
            "Неверный URL. Принимаются только ссылки на видео, плейлист, Shorts или Live. "
            "Ссылки на каналы и страницы пользователей не поддерживаются."
        )
    return url


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class VideoInfoRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048, description="URL of a YouTube video or playlist")

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        return _validate_youtube_url(v.strip())


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048, description="URL of a YouTube video or playlist")
    title: str | None = Field(default=None, max_length=512, description="Human-readable title for display; shown in the UI instead of the raw URL")
    video_ids: list[str] | None = Field(
        default=None,
        description="Specific video IDs to download from a playlist; None means download everything",
    )
    format: ALLOWED_FORMATS = Field(..., description="Output format: mp4, mp3, or wav")
    quality: ALLOWED_QUALITIES = Field(..., description="Video quality; ignored for mp3/wav")
    force_download: bool = Field(
        default=False,
        description="When True, skip cache lookup and always perform a fresh download",
    )

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        return _validate_youtube_url(v.strip())

    @field_validator("video_ids")
    @classmethod
    def validate_video_ids(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) == 0:
            raise ValueError("video_ids must contain at least one ID when provided")
        return v


# ---------------------------------------------------------------------------
# Response / data schemas
# ---------------------------------------------------------------------------


class VideoFormat(BaseModel):
    format_id: str
    ext: str
    resolution: str
    filesize: int | None = None
    fps: int | None = None
    vcodec: str
    acodec: str


class VideoInfo(BaseModel):
    id: str
    title: str
    thumbnail: str
    duration: int  # seconds
    channel: str
    upload_date: str
    formats: list[VideoFormat]


class PlaylistInfo(BaseModel):
    id: str
    title: str
    channel: str
    video_count: int
    videos: list[VideoInfo]


class DownloadStatus(BaseModel):
    task_id: str
    status: Literal["pending", "downloading", "converting", "zipping", "ready", "error", "cancelled"]
    progress: float = Field(ge=0.0, le=100.0)
    filename: str | None = None
    error: str | None = None
    download_url: str | None = None
    file_size: int | None = None
    # Original request parameters — used by the frontend for retry
    url: str | None = None
    title: str | None = None
    format: str | None = None
    quality: str | None = None
    video_ids: list[str] | None = None
    # Live transfer metrics (in-memory only; not persisted to DB)
    speed: float | None = None  # bytes per second reported by yt-dlp
    eta: int | None = None      # seconds remaining reported by yt-dlp
    # Timestamps for expiry countdown
    created_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    # Cache metadata — True when this task was served from a previous download's files
    cached: bool = False
    # Whether the downloaded file still exists on disk
    file_exists: bool = False


class InfoResponse(BaseModel):
    """Discriminated union wrapper returned by the /info endpoint.

    The ``type`` field tells the frontend whether ``video`` or ``playlist``
    is populated.
    """

    type: Literal["video", "playlist"]
    video: VideoInfo | None = None
    playlist: PlaylistInfo | None = None


class QuotaResponse(BaseModel):
    """Daily download quota status for the current user."""

    used: int
    limit: int
