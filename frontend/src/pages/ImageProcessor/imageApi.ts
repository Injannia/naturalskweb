import api from '../../api/client'
import type {
  ImageOperation,
  ImageUploadResponse,
  ImageTaskStatus,
  ImageTaskListItem,
  ImageQuota,
  MaskShape,
  InpaintMethod,
} from './types'

export const imageApi = {
  upload(
    file: File,
    operation: ImageOperation,
    onProgress?: (loaded: number, total: number) => void,
  ): Promise<ImageUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    return api
      .post<ImageUploadResponse>(`/image/upload?operation=${operation}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(e.loaded, e.total)
        },
      })
      .then((r) => r.data)
  },

  removeBg(taskId: string): Promise<ImageTaskStatus> {
    return api
      .post<ImageTaskStatus>('/image/remove-bg', { task_id: taskId })
      .then((r) => r.data)
  },

  removeWatermark(
    taskId: string,
    mask: MaskShape[],
    inpaintMethod: InpaintMethod,
    naturalWidth: number,
  ): Promise<ImageTaskStatus> {
    return api
      .post<ImageTaskStatus>('/image/remove-watermark', {
        task_id: taskId,
        mask: mask.map((s) => ({
          type: s.isEraser ? 'brush' : s.type,
          points: s.points,
          brush_size: s.brushSize && naturalWidth > 0 ? s.brushSize / naturalWidth : s.brushSize,
          is_eraser: s.isEraser || false,
        })),
        inpaint_method: inpaintMethod,
      })
      .then((r) => r.data)
  },

  getStatus(taskId: string): Promise<ImageTaskStatus> {
    return api
      .get<ImageTaskStatus>(`/image/status/${taskId}`)
      .then((r) => r.data)
  },

  getPreview(taskId: string): Promise<string> {
    return api
      .get(`/image/preview/${taskId}`, { responseType: 'blob' })
      .then((r) => URL.createObjectURL(r.data as Blob))
  },

  getResultPreview(taskId: string): Promise<string> {
    return api
      .get(`/image/preview-result/${taskId}`, { responseType: 'blob' })
      .then((r) => URL.createObjectURL(r.data as Blob))
  },

  downloadResult(taskId: string): Promise<{ blob: Blob; filename: string }> {
    return api
      .get(`/image/result/${taskId}`, { responseType: 'blob' })
      .then((r) => {
        const disposition: string = r.headers['content-disposition'] ?? ''
        const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i)
        const filename = match ? decodeURIComponent(match[1]) : 'result'
        return { blob: r.data as Blob, filename }
      })
  },

  getTasks(): Promise<ImageTaskListItem[]> {
    return api
      .get<ImageTaskListItem[]>('/image/tasks')
      .then((r) => r.data)
  },

  getHistory(): Promise<ImageTaskListItem[]> {
    return api
      .get<ImageTaskListItem[]>('/image/tasks/history')
      .then((r) => r.data)
  },

  dismissTask(taskId: string): Promise<void> {
    return api.delete(`/image/task/${taskId}`).then(() => undefined)
  },

  dismissCompleted(): Promise<{ dismissed: number }> {
    return api
      .delete<{ dismissed: number }>('/image/tasks/completed')
      .then((r) => r.data)
  },

  restoreTask(taskId: string): Promise<void> {
    return api.post(`/image/task/${taskId}/restore`).then(() => undefined)
  },

  deleteTaskPermanent(taskId: string): Promise<void> {
    return api.delete(`/image/task/${taskId}/permanent`).then(() => undefined)
  },

  getQuota(): Promise<ImageQuota> {
    return api
      .get<ImageQuota>('/image/quota')
      .then((r) => r.data)
  },
}
