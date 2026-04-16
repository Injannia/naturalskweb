from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SharedFile(Base):
    __tablename__ = "shared_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(64), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    quality: Mapped[str] = mapped_column(String(10), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_shared_files_cache_lookup", "video_id", "format", "quality"),
    )
