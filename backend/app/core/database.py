import logging
import os
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


os.makedirs("data", exist_ok=True)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and set busy timeout on every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    async with engine.begin() as conn:
        # Enable WAL mode for concurrent read/write support
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))
        from app.models import user, audit, download_task  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    await _apply_migrations()


async def _apply_migrations():
    """Add columns that create_all cannot add to existing tables."""
    migrations = [
        ("download_tasks", "video_id", "ALTER TABLE download_tasks ADD COLUMN video_id TEXT"),
        ("download_tasks", "cache_source_task_id", "ALTER TABLE download_tasks ADD COLUMN cache_source_task_id TEXT"),
    ]
    async with engine.begin() as conn:
        for table, column, ddl in migrations:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM pragma_table_info(:table) WHERE name = :col"),
                {"table": table, "col": column},
            )
            if result.scalar() == 0:
                await conn.execute(text(ddl))
                logger.info("Migration: added column %s.%s", table, column)

        # Ensure index exists for video_id lookups
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_download_tasks_video_id "
            "ON download_tasks (video_id)"
        ))
