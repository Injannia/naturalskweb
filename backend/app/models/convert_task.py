from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConvertTask(Base):
    """Persisted record of a file conversion task.

    Tracks the full lifecycle of a single file conversion — from initial
    upload through active conversion to the final ready or error state.
    Multiple tasks sharing the same batch_id belong to a single batch
    conversion initiated by the user in one request.
    """

    __tablename__ = "convert_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Groups tasks created together in a batch conversion request
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Lifecycle state
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Output metadata — populated on completion
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Original upload metadata — stored at upload time, never mutated
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_ext: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)

    # Conversion parameters — set when the user triggers conversion
    target_format: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # JSON-encoded conversion settings (VideoConvertOptions, AudioConvertOptions, etc.)
    options: Mapped[str | None] = mapped_column(String(4096), nullable=True)

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
