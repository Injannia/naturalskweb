from pydantic import BaseModel, Field

from app.schemas._types import UtcDatetime


class UserListItemAdmin(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    is_deleted: bool
    avatar_version: int
    created_at: UtcDatetime
    last_login: UtcDatetime | None
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
    created_at: UtcDatetime
    expires_at: UtcDatetime


class TopUser(BaseModel):
    user_id: int
    username: str
    avatar_version: int
    total_today: int


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    deleted_users: int
    total_downloads_today: int
    total_conversions_today: int
    total_image_ops_today: int
    storage_used_mb: float
    active_sessions: int
    top_users: list[TopUser]
    total_audit_logs: int


class SystemInfo(BaseModel):
    cpu_percent: float
    ram_used_mb: float
    ram_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: int
    python_version: str
    ffmpeg_version: str
    yt_dlp_version: str


class StorageInfo(BaseModel):
    data_size_mb: float
    uploads_size_mb: float
    avatars_size_mb: float
    total_files: int


class AuditLogItem(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    action: str
    details: dict | None
    ip_address: str
    created_at: UtcDatetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
