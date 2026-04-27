from datetime import datetime, date, timezone
from sqlalchemy import String, Boolean, Integer, JSON, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    permissions: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"youtube": True, "converter": True, "image": True}, nullable=False
    )
    limits: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"youtube_daily": 50, "convert_daily": 100, "image_daily": 50}, nullable=False
    )
    usage_today: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"youtube": 0, "converter": 0, "image": 0}, nullable=False
    )
    usage_reset_date: Mapped[date] = mapped_column(
        Date, default=lambda: date.today(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    kicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
