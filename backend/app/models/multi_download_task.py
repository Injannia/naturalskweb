from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MultiDownloadTask(Base):
    """Persisted record of a Multi downloader task (single video/audio, any yt-dlp site)."""

    __tablename__ = "multi_download_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    audio_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    shared_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
