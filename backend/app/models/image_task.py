from datetime import datetime, timezone
from sqlalchemy import Boolean, String, Integer, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ImageTask(Base):
    """Persisted record of an image processing task.

    Tracks the full lifecycle of a single image operation — from initial
    upload through active processing to the final ready or error state.
    Supports background removal and watermark removal operations.
    """

    __tablename__ = "image_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

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

    # Operation parameters
    operation: Mapped[str] = mapped_column(String(30), nullable=False)  # "remove_bg" | "remove_watermark"
    inpaint_method: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "telea" | "ns"

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
