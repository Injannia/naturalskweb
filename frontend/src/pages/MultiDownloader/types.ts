export interface InfoResponse {
  title: string
  thumbnail?: string | null
  duration: number
  platform?: string | null
}

export type TaskStatus = 'pending' | 'downloading' | 'converting' | 'ready' | 'error' | 'cancelled'

export interface DownloadStatus {
  task_id: string
  status: TaskStatus
  progress: number
  filename?: string | null
  error?: string | null
  download_url?: string | null
  file_size?: number | null
  url?: string | null
  title?: string | null
  thumbnail?: string | null
  platform?: string | null
  audio_only: boolean
  speed?: number | null
  eta?: number | null
  created_at?: string | null
  completed_at?: string | null
  file_exists: boolean
}

export interface QuotaResponse {
  used: number
  limit: number
}
