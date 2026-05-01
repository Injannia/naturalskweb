from datetime import datetime, date

from pydantic import BaseModel, Field


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
    created_at: datetime
    last_login: datetime | None

    model_config = {"from_attributes": True}


class UpdateMeRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")


class MySessionItem(BaseModel):
    id: int
    ip_address: str
    user_agent: str
    created_at: datetime
    expires_at: datetime
    is_current: bool

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str
