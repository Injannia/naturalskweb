// ── Image Processor Types ──

export type ImageOperation = 'remove_bg' | 'remove_watermark'
export type ImageStatus = 'pending' | 'uploading' | 'processing' | 'ready' | 'error'
export type MaskTool = 'brush' | 'rect' | 'eraser'
export type InpaintMethod = 'lama' | 'telea' | 'ns'

export interface MaskShape {
  type: 'brush' | 'rect'       // eraser is stored as brush with isEraser flag
  points: number[][]            // normalized 0-1 [[x,y], ...]
  brushSize: number | null      // only for brush/eraser
  isEraser?: boolean
}

export interface ImageTaskStatus {
  task_id: string
  status: ImageStatus
  progress: number
  operation: ImageOperation
  filename: string | null
  file_size: number | null
  error: string | null
  original_filename: string
  original_ext: string
  inpaint_method: InpaintMethod | null
  created_at: string | null
  completed_at: string | null
}

export interface ImageTaskListItem extends ImageTaskStatus {
  file_exists: boolean
}

export interface ImageUploadResponse {
  task_id: string
  original_filename: string
  original_ext: string
  file_size: number
}

export interface ImageQuota {
  used: number
  limit: number
}

// State machines for each tab
export type BgPhase = 'idle' | 'uploading' | 'preview' | 'processing' | 'result' | 'error'
export type WmPhase = 'idle' | 'uploading' | 'editing' | 'processing' | 'result' | 'error'
