from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, Float, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DownloadTask(Base):
    """Persisted record of a YouTube download task.

    Task state is updated in-place throughout the download lifecycle so that
    progress survives backend restarts and is visible to all workers.
    """

    __tablename__ = "download_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Lifecycle state
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Output metadata — populated on completion
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Original request parameters — stored so the frontend can retry
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    quality: Mapped[str] = mapped_column(String(10), nullable=False)
    # JSON-encoded list of video IDs for playlist partial downloads; NULL = all
    video_ids: Mapped[str | None] = mapped_column(String(4096), nullable=True)

    # Cache fields — video_id enables cache lookups; shared_file_id points to
    # the SharedFile record whose file is re-used by a cache-hit task.
    # For playlists, video_id stores a deterministic hash of sorted video IDs +
    # format + quality so it uniquely identifies the cached output.
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    shared_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    # Soft-delete flag: hidden tasks are excluded from list responses
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
