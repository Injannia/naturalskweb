from datetime import datetime

from pydantic import BaseModel, Field


class UserListItemAdmin(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    is_deleted: bool
    avatar_version: int
    created_at: datetime
    last_login: datetime | None
    usage_today: dict
    limits: dict

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserListItemAdmin]
    total: int


class UserDetailResponse(UserListItemAdmin):
    permissions: dict


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    role: str = Field(default="user", pattern=r"^(user|admin|superadmin)$")
    permissions: dict | None = None
    limits: dict | None = None


class CreateUserResponse(BaseModel):
    id: int
    username: str
    password: str
    role: str


class UpdateUserRequest(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(user|admin|superadmin)$")
    permissions: dict | None = None
    limits: dict | None = None
    is_active: bool | None = None


class ResetPasswordResponse(BaseModel):
    id: int
    username: str
    password: str


class ToggleActiveResponse(BaseModel):
    id: int
    is_active: bool


class AdminSessionItem(BaseModel):
    id: int
    user_id: int
    username: str
    ip_address: str
    user_agent: str
    created_at: datetime
    expires_at: datetime
