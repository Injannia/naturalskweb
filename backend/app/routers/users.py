import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Serve a user's WebP avatar to any authenticated user.

    Soft-deleted users' avatars are not served.
    """
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if not user or not user.avatar_path:
        raise HTTPException(status_code=404, detail="Аватар не найден")

    abs_path = os.path.join(settings.AVATARS_DIR, f"{user.id}.webp")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Файл аватара отсутствует")

    return FileResponse(abs_path, media_type="image/webp")
