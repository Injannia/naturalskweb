// ── YouTube Downloader Types ──

export type VideoFormat = 'mp4' | 'mp3' | 'wav'
export type VideoQuality = '360p' | '480p' | '720p' | '1080p' | 'best'
export type DownloadStatus =
  | 'pending'
  | 'downloading'
  | 'converting'
  | 'zipping'
  | 'ready'
  | 'error'
  | 'cancelled'

export interface VideoFormatDetail {
  format_id: string
  ext: string
  resolution: string
  filesize: number | null
  fps: number | null
  vcodec: string
  acodec: string
}

export interface VideoInfo {
  id: string
  title: string
  channel: string
  duration: number // seconds
  thumbnail: string
  upload_date: string
  formats: VideoFormatDetail[]
}

export interface PlaylistInfo {
  id: string
  title: string
  channel: string
  video_count: number
  videos: VideoInfo[]
}

export type MediaInfo =
  | { type: 'video'; data: VideoInfo }
  | { type: 'playlist'; data: PlaylistInfo }

export interface InfoResponse {
  type: 'video' | 'playlist'
  video?: VideoInfo
  playlist?: PlaylistInfo
}

export interface DownloadRequest {
  url: string
  video_ids?: string[]
  format: VideoFormat
  quality: VideoQuality
  title?: string
  // When true the backend skips the cache and forces a fresh download
  force_download?: boolean
}

// Matches the full DownloadStatus shape the backend returns on start
export interface DownloadStartResponse {
  task_id: string
  status: DownloadStatus
  progress: number
  filename: string | null
  error: string | null
  download_url: string | null
  file_size: number | null
  // ISO timestamp — backend agent is adding this field
  created_at?: string
  completed_at?: string | null
  // True when the file was served from the server-side cache
  cached?: boolean
  file_exists?: boolean
}

export interface DownloadTask {
  task_id: string
  status: DownloadStatus
  progress: number // 0-100
  filename: string | null
  file_size: number | null // bytes
  error: string | null
  // Transfer stats — only present while status === 'downloading'
  speed: number | null
  eta: number | null
  title: string
  format: VideoFormat
  // Original request params — stored so the task can be retried
  url: string
  quality: VideoQuality
  video_ids?: string[]
  // ISO timestamps from backend; used to calculate file expiry countdown
  created_at: string | null
  // completed_at is preferred over created_at for expiry calculation when available
  completed_at?: string | null
  // True when the file was served from the server-side cache (instant ready)
  cached?: boolean
  file_exists?: boolean
}

export interface QuotaResponse {
  used: number
  limit: number
}

export interface StatusResponse {
  task_id: string
  status: DownloadStatus
  progress: number
  filename: string | null
  file_size: number | null
  error: string | null
  // Transfer stats — only present while status === 'downloading'
  speed: number | null
  eta: number | null
  title?: string
  url?: string
  format?: VideoFormat
  quality?: VideoQuality
  video_ids?: string[]
  created_at?: string | null
  completed_at?: string | null
  // True when the file was served from the server-side cache
  cached?: boolean
  file_exists?: boolean
}

// Compact shape used for dismissed tasks displayed in the history panel.
// Only the fields needed for re-download and restore are required.
export interface HistoryTask {
  task_id: string
  status: DownloadStatus
  title: string
  format: VideoFormat
  url: string
  quality: VideoQuality
  filename: string | null
  file_size: number | null
  created_at: string | null
  completed_at: string | null
  file_exists?: boolean
}

// Shape returned by GET /youtube/tasks
export interface TaskListItem {
  task_id: string
  status: DownloadStatus
  progress: number
  filename: string | null
  file_size: number | null
  error: string | null
  url: string
  format: VideoFormat
  quality: VideoQuality
  video_ids?: string[]
  created_at: string | null
  completed_at?: string | null
  // title is not stored by the backend; we derive a fallback from the url
  title?: string
  file_exists?: boolean
}
