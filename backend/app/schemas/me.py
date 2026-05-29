from datetime import date

from pydantic import BaseModel, Field

from app.schemas._types import UtcDatetime


class UserMeResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool
    permissions: dict
    limits: dict
    usage_today: dict
    usage_reset_date: date
    avatar_version: int
    created_at: UtcDatetime
    last_login: UtcDatetime | None

    model_config = {"from_attributes": True}


class UpdateMeRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")


class MySessionItem(BaseModel):
    id: int
    ip_address: str
    user_agent: str
    created_at: UtcDatetime
    expires_at: UtcDatetime
    is_current: bool

    model_config = {"from_attributes": True}


class AvatarUploadResponse(BaseModel):
    avatar_path: str
    avatar_version: int
