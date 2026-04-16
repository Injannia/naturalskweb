import api from '../../api/client'
import type {
  UploadResponse,
  CapabilitiesResponse,
  StatusResponse,
  TaskListItem,
  QuotaResponse,
  ConvertOptions,
} from './types'

export const converterApi = {
  // Upload one or more files as multipart/form-data with optional progress tracking
  upload(
    files: File[],
    batchId: string | null,
    onProgress?: (loaded: number, total: number) => void,
  ): Promise<UploadResponse[]> {
    const formData = new FormData()
    files.forEach((f) => formData.append('files', f))
    const params = batchId ? { batch_id: batchId } : {}
    return api
      .post<UploadResponse[]>('/convert/upload', formData, {
        params,
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(e.loaded, e.total)
        },
      })
      .then((r) => r.data)
  },

  // Returns the supported target formats and configurable fields for a given source extension
  getCapabilities(ext: string): Promise<CapabilitiesResponse> {
    return api
      .get<CapabilitiesResponse>(`/convert/capabilities/${ext}`)
      .then((r) => r.data)
  },

  // Start a single-file conversion
  startConvert(
    taskId: string,
    targetFormat: string,
    options?: ConvertOptions,
  ): Promise<StatusResponse> {
    return api
      .post<StatusResponse>('/convert/start', {
        task_id: taskId,
        target_format: targetFormat,
        options: options ?? null,
      })
      .then((r) => r.data)
  },

  // Start a batch conversion for multiple tasks in one request
  startBatch(
    items: Array<{ task_id: string; target_format: string; options?: ConvertOptions }>,
  ): Promise<StatusResponse[]> {
    return api
      .post<StatusResponse[]>('/convert/batch', { items })
      .then((r) => r.data)
  },

  getStatus(taskId: string): Promise<StatusResponse> {
    return api
      .get<StatusResponse>(`/convert/status/${taskId}`)
      .then((r) => r.data)
  },

  downloadFile(taskId: string): Promise<{ blob: Blob; filename: string }> {
    return api
      .get(`/convert/file/${taskId}`, { responseType: 'blob' })
      .then((r) => {
        const disposition: string = r.headers['content-disposition'] ?? ''
        const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i)
        const filename = match ? decodeURIComponent(match[1]) : 'converted_file'
        return { blob: r.data as Blob, filename }
      })
  },

  // Download all files in a batch as a ZIP archive
  downloadBatchZip(batchId: string): Promise<{ blob: Blob; filename: string }> {
    return api
      .get(`/convert/batch/${batchId}/zip`, { responseType: 'blob' })
      .then((r) => {
        const disposition: string = r.headers['content-disposition'] ?? ''
        const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i)
        const filename = match ? decodeURIComponent(match[1]) : 'converted_files.zip'
        return { blob: r.data as Blob, filename }
      })
  },

  // Returns the user's active and recent task list from the backend SQLite store
  getTasks(): Promise<TaskListItem[]> {
    return api
      .get<TaskListItem[]>('/convert/tasks')
      .then((r) => r.data)
  },

  // Dismissed tasks that still have files on disk (within 6h TTL)
  getHistoryTasks(): Promise<TaskListItem[]> {
    return api
      .get<TaskListItem[]>('/convert/tasks/history')
      .then((r) => r.data)
  },

  // Persist-hide a single task from the active list
  dismissTask(taskId: string): Promise<void> {
    return api.delete(`/convert/task/${taskId}`).then(() => undefined)
  },

  // Persist-hide all terminal tasks (ready / error / cancelled); returns { dismissed: N }
  dismissCompletedTasks(): Promise<{ dismissed: number }> {
    return api
      .delete<{ dismissed: number }>('/convert/tasks/completed')
      .then((r) => r.data)
  },

  // Un-dismiss a task — moves it back to the active list
  restoreTask(taskId: string): Promise<void> {
    return api.post(`/convert/task/${taskId}/restore`).then(() => undefined)
  },

  cancelConvert(taskId: string): Promise<void> {
    return api.delete(`/convert/cancel/${taskId}`).then(() => undefined)
  },

  // Delete a pending upload (before conversion) — removes file + DB record
  deletePendingUpload(taskId: string): Promise<void> {
    return api.delete(`/convert/upload/${taskId}`).then(() => undefined)
  },

  // Permanently delete a task — removes file from disk + DB record
  deleteTaskPermanent(taskId: string): Promise<void> {
    return api.delete(`/convert/task/${taskId}/permanent`).then(() => undefined)
  },

  getQuota(): Promise<QuotaResponse> {
    return api
      .get<QuotaResponse>('/convert/quota')
      .then((r) => r.data)
  },
}
