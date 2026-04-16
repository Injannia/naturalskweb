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
        from app.models import user, audit, download_task, shared_file  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    await _apply_migrations()


async def _apply_migrations():
    """Add columns and tables that create_all cannot add to existing tables."""
    import uuid
    import datetime as _dt

    async with engine.begin() as conn:
        # --- download_tasks columns ---
        column_migrations = [
            ("download_tasks", "video_id", "ALTER TABLE download_tasks ADD COLUMN video_id TEXT"),
            ("download_tasks", "shared_file_id", "ALTER TABLE download_tasks ADD COLUMN shared_file_id TEXT"),
            ("download_tasks", "is_cache_hit", "ALTER TABLE download_tasks ADD COLUMN is_cache_hit INTEGER NOT NULL DEFAULT 0"),
        ]
        for table, column, ddl in column_migrations:
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

        # --- shared_files table (create if not exists) ---
        sf_exists = await conn.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='shared_files'")
        )
        if sf_exists.scalar() == 0:
            await conn.execute(text("""
                CREATE TABLE shared_files (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    format TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    title TEXT,
                    file_size INTEGER,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_shared_files_cache_lookup "
                "ON shared_files (video_id, format, quality)"
            ))
            logger.info("Migration: created shared_files table")

        # --- data migration: create SharedFile records for existing ready tasks ---
        has_cache_src_col = await conn.execute(
            text("SELECT COUNT(*) FROM pragma_table_info('download_tasks') WHERE name = 'cache_source_task_id'")
        )
        if has_cache_src_col.scalar() > 0:
            # Source tasks: ready, no cache_source_task_id, no shared_file_id yet
            source_tasks = await conn.execute(text("""
                SELECT id, video_id, format, quality, filename, title, file_size, completed_at
                FROM download_tasks
                WHERE status = 'ready'
                  AND cache_source_task_id IS NULL
                  AND shared_file_id IS NULL
                  AND video_id IS NOT NULL
                  AND filename IS NOT NULL
            """))
            rows = source_tasks.fetchall()

            ttl_seconds = settings.FILE_TTL_HOURS * 3600
            for row in rows:
                task_id, video_id, fmt, quality, filename, title, file_size, completed_at = row
                sf_id = str(uuid.uuid4())
                if completed_at:
                    try:
                        base = _dt.datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
                        if base.tzinfo is None:
                            base = base.replace(tzinfo=_dt.timezone.utc)
                    except (ValueError, TypeError):
                        base = _dt.datetime.now(_dt.timezone.utc)
                else:
                    base = _dt.datetime.now(_dt.timezone.utc)
                expires_at = base + _dt.timedelta(seconds=ttl_seconds)

                await conn.execute(text("""
                    INSERT INTO shared_files (id, video_id, format, quality, filename, title, file_size, expires_at)
                    VALUES (:id, :video_id, :format, :quality, :filename, :title, :file_size, :expires_at)
                """), {
                    "id": sf_id,
                    "video_id": video_id,
                    "format": fmt,
                    "quality": quality,
                    "filename": filename,
                    "title": title,
                    "file_size": file_size,
                    "expires_at": expires_at.isoformat(),
                })
                await conn.execute(text(
                    "UPDATE download_tasks SET shared_file_id = :sf_id WHERE id = :task_id"
                ), {"sf_id": sf_id, "task_id": task_id})
                logger.info("Migration: created SharedFile %s for task %s", sf_id, task_id)

            # Cache-hit tasks: find shared_file_id from their source task
            hit_tasks = await conn.execute(text("""
                SELECT dt.id, dt.cache_source_task_id
                FROM download_tasks dt
                WHERE dt.status = 'ready'
                  AND dt.cache_source_task_id IS NOT NULL
                  AND dt.shared_file_id IS NULL
            """))
            for hit_id, src_id in hit_tasks.fetchall():
                src_sf = await conn.execute(text(
                    "SELECT shared_file_id FROM download_tasks WHERE id = :id"
                ), {"id": src_id})
                sf_id = src_sf.scalar_one_or_none()
                if sf_id:
                    await conn.execute(text(
                        "UPDATE download_tasks SET shared_file_id = :sf_id, is_cache_hit = 1 WHERE id = :task_id"
                    ), {"sf_id": sf_id, "task_id": hit_id})
                    logger.info("Migration: linked cache-hit task %s to SharedFile %s", hit_id, sf_id)
