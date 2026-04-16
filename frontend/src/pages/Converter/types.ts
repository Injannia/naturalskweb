// ── File Converter Types ──

export type ConvertCategory = 'video' | 'audio' | 'image' | 'document'
export type ConvertStatus =
  | 'pending'
  | 'uploading'
  | 'converting'
  | 'ready'
  | 'error'
  | 'cancelled'

// All conversion options are optional — each category uses a subset
export interface ConvertOptions {
  // Video
  resolution?: string   // e.g. "1920x1080"
  codec?: string        // e.g. "h264", "h265", "vp9"
  bitrate?: string      // e.g. "2M", "5M"
  fps?: number          // 1-120
  audio_codec?: string  // e.g. "aac", "mp3", "copy"
  // Audio
  sample_rate?: number  // 8000-192000
  channels?: number     // 1 or 2
  // Image
  quality?: number      // 1-100
  width?: number
  height?: number
  keep_aspect?: boolean
}

// File held in the upload queue before conversion starts
export interface UploadedFile {
  task_id: string
  file: File               // local File reference — not sent to the server after upload
  original_filename: string
  original_ext: string
  category: ConvertCategory
  file_size: number
  target_format: string    // user-selected target format
  options: ConvertOptions
  uploadProgress: number   // 0-100
  uploadComplete: boolean
}

// Active conversion task as tracked by the UI (mirrors backend shape + local state)
export interface ConvertTask {
  task_id: string
  status: ConvertStatus
  progress: number
  filename: string | null
  file_size: number | null
  error: string | null
  original_filename: string
  original_ext: string
  category: ConvertCategory
  target_format: string
  options: ConvertOptions | null
  created_at: string | null
  completed_at: string | null
  batch_id: string | null
  file_exists?: boolean
}

// Compact shape for dismissed tasks displayed in the history panel
export interface HistoryTask {
  task_id: string
  status: ConvertStatus
  filename: string | null
  file_size: number | null
  original_filename: string
  original_ext: string
  category: ConvertCategory
  target_format: string
  created_at: string | null
  completed_at: string | null
  batch_id: string | null
  file_exists?: boolean
}

// ── API response types ──

export interface UploadResponse {
  task_id: string
  original_filename: string
  original_ext: string
  category: ConvertCategory
  file_size: number
}

export interface CapabilitiesResponse {
  category: ConvertCategory
  target_formats: string[]
  settings_fields: Record<string, unknown>
}

export interface StatusResponse {
  task_id: string
  status: ConvertStatus
  progress: number
  filename: string | null
  file_size: number | null
  error: string | null
  original_filename: string
  original_ext: string
  category: ConvertCategory
  target_format: string | null
  options: ConvertOptions | null
  created_at: string | null
  completed_at: string | null
  batch_id: string | null
}

// Shape returned by GET /convert/tasks and GET /convert/tasks/history
export interface TaskListItem {
  task_id: string
  status: ConvertStatus
  progress: number
  filename: string | null
  file_size: number | null
  error: string | null
  original_filename: string
  original_ext: string
  category: ConvertCategory
  target_format: string | null
  created_at: string | null
  completed_at: string | null
  batch_id: string | null
  file_exists?: boolean
}

export interface QuotaResponse {
  used: number
  limit: number
}
