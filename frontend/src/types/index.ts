export type Role = 'user' | 'admin' | 'superadmin'

export interface User {
  id: number
  username: string
  role: Role
  is_active: boolean
  is_deleted?: boolean
  must_change_password: boolean
  permissions: {
    youtube: boolean
    converter: boolean
    image: boolean
  }
  limits: {
    youtube_daily: number
    convert_daily: number
    image_daily: number
  }
  usage_today: {
    youtube: number
    converter: number
    image: number
  }
  usage_reset_date?: string
  avatar_version?: number
  created_at?: string
  last_login?: string | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  must_change_password: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

export interface UpdateMeRequest {
  username: string
}

export interface AvatarUploadResponse {
  avatar_path: string
  avatar_version: number
}

export interface UserListItem {
  id: number
  username: string
  role: Role
  is_active: boolean
  is_deleted: boolean
  avatar_version: number
  created_at: string
  last_login: string | null
  usage_today: Record<string, number>
  limits: Record<string, number>
}

export interface UserListResponse {
  items: UserListItem[]
  total: number
}

export interface UserDetail extends UserListItem {
  permissions: Record<string, boolean>
}

export interface CreateUserRequest {
  username: string
  role: Role
  permissions?: Record<string, boolean>
  limits?: Record<string, number>
}

export interface CreateUserResponse {
  id: number
  username: string
  password: string
  role: Role
}

export interface UpdateUserRequest {
  role?: Role
  permissions?: Record<string, boolean>
  limits?: Record<string, number>
  is_active?: boolean
}

export interface ResetPasswordResponse {
  id: number
  username: string
  password: string
}

export interface ToggleActiveResponse {
  id: number
  is_active: boolean
}

export interface MySessionItem {
  id: number
  ip_address: string
  user_agent: string
  created_at: string
  expires_at: string
  is_current: boolean
}

export interface AdminSessionItem {
  id: number
  user_id: number
  username: string
  ip_address: string
  user_agent: string
  created_at: string
  expires_at: string
}

export interface AuditLogItem {
  id: number
  user_id: number | null
  username: string | null
  action: string
  details: Record<string, unknown> | null
  ip_address: string
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogItem[]
  total: number
}

export interface TopUser {
  user_id: number
  username: string
  avatar_version: number
  total_today: number
}

export interface AdminStats {
  total_users: number
  active_users: number
  deleted_users: number
  total_downloads_today: number
  total_conversions_today: number
  total_image_ops_today: number
  storage_used_mb: number
  active_sessions: number
  top_users: TopUser[]
  total_audit_logs: number
}

export interface SystemInfo {
  cpu_percent: number
  ram_used_mb: number
  ram_total_mb: number
  disk_used_gb: number
  disk_total_gb: number
  uptime_seconds: number
  python_version: string
  ffmpeg_version: string
  yt_dlp_version: string
}

export interface StorageInfo {
  data_size_mb: number
  uploads_size_mb: number
  avatars_size_mb: number
  total_files: number
}

export interface MessageResponse {
  message: string
}
