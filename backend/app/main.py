import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session
from app.core.security import hash_password, generate_random_password
from app.middleware.audit import RequestLoggerMiddleware
from starlette.middleware.gzip import GZipMiddleware
from app.middleware.security import RateLimitMiddleware, SecurityHeadersMiddleware
from app.models.user import User
from app.routers import auth, admin, youtube, convert, image, users, me

from app.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("naturalsk")


async def _create_superadmin():
    async with async_session() as db:
        result = await db.execute(select(User).where(User.role == "superadmin").limit(1))
        if result.scalar_one_or_none() is not None:
            return

        password = generate_random_password()
        superadmin = User(
            username="admin",
            password_hash=hash_password(password),
            role="superadmin",
            must_change_password=True,
            permissions={"youtube": True, "converter": True, "image": True},
            limits={"youtube_daily": 999, "convert_daily": 999, "image_daily": 999},
        )
        db.add(superadmin)
        await db.commit()

        creds_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "initial_admin_password.txt"
        )
        creds_path = os.path.abspath(creds_path)
        os.makedirs(os.path.dirname(creds_path), exist_ok=True)
        with open(creds_path, "w") as f:
            f.write(f"Username: admin\nPassword: {password}\n")
        try:
            os.chmod(creds_path, 0o600)
        except OSError:
            pass
        logger.info(
            "NaturalskWeb -- First Launch\n"
            "Superadmin created. Credentials written to: %s\n"
            "Change this password on first login and delete the file!",
            creds_path,
        )


def _setup_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()

    async def cleanup_expired_shared_files():
        """Delete expired SharedFile records and their upload directories."""
        import shutil
        from datetime import datetime, timezone
        from sqlalchemy import select, update as sa_update
        from app.models.shared_file import SharedFile
        from app.models.download_task import DownloadTask

        now = datetime.now(timezone.utc)
        now_naive = now.replace(tzinfo=None)

        try:
            async with async_session() as db:
                result = await db.execute(
                    select(SharedFile).where(SharedFile.expires_at < now_naive)
                )
                expired = result.scalars().all()

                for sf in expired:
                    shared_dir = os.path.join(settings.UPLOAD_DIR, sf.id)
                    if os.path.isdir(shared_dir):
                        shutil.rmtree(shared_dir, ignore_errors=True)
                        logger.info("Cleanup: removed shared dir %s (file: %s)", sf.id, sf.filename)
                    # Null out task references (SQLite FK not enforced)
                    await db.execute(
                        sa_update(DownloadTask)
                        .where(DownloadTask.shared_file_id == sf.id)
                        .values(shared_file_id=None)
                    )
                    await db.delete(sf)

                if expired:
                    await db.commit()
                    logger.info("Cleanup: removed %d expired SharedFile records", len(expired))

        except Exception as exc:
            logger.warning("cleanup_expired_shared_files failed: %s", exc)

        # Fallback: scan for orphaned upload directories (no SharedFile record)
        upload_dir = settings.UPLOAD_DIR
        if not os.path.exists(upload_dir):
            return

        import time
        now_ts = time.time()
        max_age = settings.FILE_TTL_HOURS * 3600

        # Collect known SharedFile IDs to avoid deleting active directories
        known_sf_ids: set[str] = set()
        try:
            async with async_session() as db:
                result = await db.execute(select(SharedFile.id))
                known_sf_ids = {row[0] for row in result.all()}
        except Exception:
            pass  # If DB fails, skip fallback to avoid data loss

        for entry in os.scandir(upload_dir):
            if not entry.is_dir():
                continue
            if entry.name in known_sf_ids:
                continue
            try:
                dir_mtime = entry.stat().st_mtime
                if now_ts - dir_mtime > max_age:
                    shutil.rmtree(entry.path, ignore_errors=True)
                    logger.info("Cleanup: removed orphaned upload dir %s", entry.name)
            except OSError:
                pass

    async def reset_daily_usage():
        async with async_session() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
            today = date.today()
            for user in users:
                if user.usage_reset_date != today:
                    user.usage_today = {"youtube": 0, "converter": 0, "image": 0}
                    user.usage_reset_date = today
            await db.commit()

    async def cleanup_stale_pending_tasks():
        """Remove pending tasks with no target_format older than 30 minutes."""
        import shutil
        from app.models.convert_task import ConvertTask
        from app.models.image_task import ImageTask as ImageTaskModel

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        cutoff_naive = cutoff.replace(tzinfo=None)

        try:
            async with async_session() as db:
                # Clean stale convert tasks
                result = await db.execute(
                    select(ConvertTask).where(
                        ConvertTask.status == "pending",
                        ConvertTask.target_format.is_(None),
                        ConvertTask.created_at < cutoff_naive,
                    )
                )
                stale_tasks = result.scalars().all()

                for task in stale_tasks:
                    task_dir = os.path.join(settings.UPLOAD_DIR, task.id)
                    if os.path.isdir(task_dir):
                        shutil.rmtree(task_dir, ignore_errors=True)
                    await db.delete(task)

                # Clean stale image tasks
                result_img = await db.execute(
                    select(ImageTaskModel).where(
                        ImageTaskModel.status == "pending",
                        ImageTaskModel.created_at < cutoff_naive,
                    )
                )
                stale_image_tasks = result_img.scalars().all()

                for task in stale_image_tasks:
                    task_dir = os.path.join(settings.UPLOAD_DIR, task.id)
                    if os.path.isdir(task_dir):
                        shutil.rmtree(task_dir, ignore_errors=True)
                    await db.delete(task)

                total = len(stale_tasks) + len(stale_image_tasks)
                if total:
                    await db.commit()
                    logger.info(
                        "Cleaned up %d stale pending tasks (%d convert, %d image)",
                        total,
                        len(stale_tasks),
                        len(stale_image_tasks),
                    )
        except Exception as exc:
            logger.warning("cleanup_stale_pending_tasks failed: %s", exc)

    scheduler.add_job(cleanup_expired_shared_files, "interval", minutes=30, id="cleanup")
    scheduler.add_job(reset_daily_usage, "cron", hour=0, minute=0, id="reset_usage")
    scheduler.add_job(cleanup_stale_pending_tasks, "interval", minutes=30, id="cleanup_stale_pending")
    scheduler.start()
    return scheduler


async def _warmup_image_models() -> None:
    """Background task: preload rembg and LaMa models so first request is fast."""
    from app.services.image_service import _get_rembg_session, _get_lama_session

    try:
        await asyncio.to_thread(_get_rembg_session)
        logger.info("warmup: rembg session ready")
    except Exception:
        logger.exception("warmup: rembg session failed")

    try:
        await asyncio.to_thread(_get_lama_session)
        logger.info("warmup: LaMa session ready")
    except Exception:
        logger.exception("warmup: LaMa session failed")


async def _warmup_tool_versions() -> None:
    """Background task: prime the tool-version cache (subprocesses for ffmpeg/yt-dlp).
    Without this, the first /api/admin/system call eats the cold subprocess cost."""
    from app.utils.system_info import get_tool_versions

    try:
        await asyncio.to_thread(get_tool_versions)
        logger.info("warmup: tool versions cached")
    except Exception:
        logger.exception("warmup: tool versions failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.AVATARS_DIR, exist_ok=True)
    # Schema is applied by the container entrypoint via `alembic upgrade head`.
    await _create_superadmin()
    scheduler = _setup_scheduler()
    asyncio.create_task(_warmup_image_models())
    asyncio.create_task(_warmup_tool_versions())
    logger.info("NaturalskWeb backend started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("NaturalskWeb backend stopped")


app = FastAPI(
    title="NaturalskWeb",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(youtube.router)
app.include_router(convert.router)
app.include_router(image.router)
app.include_router(users.router)
app.include_router(me.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/health")
async def health_alias():
    return {"status": "ok"}


# --- Статика фронтенда (single-container prod). API-роуты объявлены выше и
# имеют приоритет; этот блок ловит всё остальное и отдаёт SPA. ---
if os.path.isdir(settings.FRONTEND_DIST_DIR):
    _assets_dir = os.path.join(settings.FRONTEND_DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    _index_file = os.path.join(settings.FRONTEND_DIST_DIR, "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = os.path.abspath(os.path.join(settings.FRONTEND_DIST_DIR, full_path))
        dist_root = os.path.abspath(settings.FRONTEND_DIST_DIR)
        # Containment: reject anything that escapes the dist tree (path traversal)
        if candidate.startswith(dist_root + os.sep) and full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_index_file)
