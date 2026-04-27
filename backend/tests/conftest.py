import os
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hmac-sha256-ok!!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("UPLOAD_DIR", "/tmp/naturalsk_test_uploads")
os.environ.setdefault("AVATARS_DIR", "/tmp/naturalsk_test_avatars")


@pytest_asyncio.fixture(scope="function")
async def db_session():
    from app.core.database import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        from app.models import download_task, shared_file  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
