export interface User {
  id: number
  username: string
  role: 'user' | 'admin' | 'superadmin'
  is_active: boolean
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

export interface UserListItem {
  id: number
  username: string
  role: string
  is_active: boolean
  last_login: string | null
  usage_today: Record<string, number>
}

export interface CreateUserRequest {
  username: string
  role: string
  permissions?: Record<string, boolean>
  limits?: Record<string, number>
}

export interface CreateUserResponse {
  id: number
  username: string
  password: string
  role: string
}

export interface AuditLogEntry {
  id: number
  user_id: number | null
  action: string
  details: Record<string, unknown> | null
  ip_address: string
  created_at: string
}

export interface AdminStats {
  total_users: number
  active_users: number
  total_audit_logs: number
}
