"""Pydantic schemas for the multi-platform downloader (multidl) router."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas._types import UtcDatetime


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class InfoRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2048)

    @field_validator("url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("URL не должен быть пустым")
        return s


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=2048)
    title: str | None = Field(default=None, max_length=512)
    audio_only: bool = Field(
        default=False,
        description="Download audio only and convert to mp3",
    )

    @field_validator("url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("URL не должен быть пустым")
        return s


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class InfoResponse(BaseModel):
    title: str
    thumbnail: str | None = None
    duration: int = 0  # seconds
    platform: str | None = None  # detected extractor key, e.g. "TikTok"


class DownloadStatus(BaseModel):
    task_id: str
    status: Literal["pending", "downloading", "converting", "ready", "error", "cancelled"]
    progress: float = Field(ge=0.0, le=100.0)
    filename: str | None = None
    error: str | None = None
    download_url: str | None = None
    file_size: int | None = None
    # Original request parameters — used by the frontend for retry / display
    url: str | None = None
    title: str | None = None
    thumbnail: str | None = None
    platform: str | None = None
    audio_only: bool = False
    # Live transfer metrics (in-memory only; not persisted to DB)
    speed: float | None = None  # bytes per second reported by yt-dlp
    eta: int | None = None  # seconds remaining reported by yt-dlp
    # Timestamps for expiry countdown
    created_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None
    # Whether the downloaded file still exists on disk
    file_exists: bool = False


class QuotaResponse(BaseModel):
    """Daily download quota status for the current user."""

    used: int
    limit: int
