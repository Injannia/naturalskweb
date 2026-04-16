import api from '../../api/client'
import type {
  InfoResponse,
  DownloadRequest,
  DownloadStartResponse,
  StatusResponse,
  QuotaResponse,
  TaskListItem,
} from './types'

export const youtubeApi = {
  async getInfo(url: string): Promise<InfoResponse> {
    const { data } = await api.post('/youtube/info', { url })
    // Handle new wrapped format: { type: 'video', video: {...} } or { type: 'playlist', playlist: {...} }
    if (data.type === 'video' || data.type === 'playlist') {
      return data as InfoResponse
    }
    // Fallback: detect shape from raw response for backward compatibility
    if ('videos' in data && Array.isArray(data.videos)) {
      return { type: 'playlist', playlist: data } as InfoResponse
    }
    return { type: 'video', video: data } as InfoResponse
  },

  startDownload(payload: DownloadRequest, forceDownload?: boolean): Promise<DownloadStartResponse> {
    const body: DownloadRequest = forceDownload
      ? { ...payload, force_download: true }
      : payload
    return api
      .post<DownloadStartResponse>('/youtube/download', body)
      .then((r) => r.data)
  },

  getStatus(taskId: string): Promise<StatusResponse> {
    return api
      .get<StatusResponse>(`/youtube/status/${taskId}`)
      .then((r) => r.data)
  },

  // Re-creates a task from original backend-stored params (preserves video_ids for playlists)
  retryDownload(taskId: string): Promise<DownloadStartResponse> {
    return api
      .post<DownloadStartResponse>(`/youtube/retry/${taskId}`)
      .then((r) => r.data)
  },

  cancelDownload(taskId: string): Promise<void> {
    return api.delete(`/youtube/cancel/${taskId}`).then(() => undefined)
  },

  // Returns the user's recent task history from the backend SQLite store
  getTasks(): Promise<TaskListItem[]> {
    return api
      .get<TaskListItem[]>('/youtube/tasks')
      .then((r) => r.data)
  },

  getQuota(): Promise<QuotaResponse> {
    return api
      .get<QuotaResponse>('/youtube/quota')
      .then((r) => r.data)
  },

  // Dismissed tasks that still have files on disk (within 6h TTL)
  getHistoryTasks(): Promise<TaskListItem[]> {
    return api
      .get<TaskListItem[]>('/youtube/tasks/history')
      .then((r) => r.data)
  },

  // Un-dismiss a task — moves it back to the active list
  restoreTask(taskId: string): Promise<void> {
    return api.post(`/youtube/task/${taskId}/restore`).then(() => undefined)
  },

  // Persist-hide a single task; backend returns { task_id, dismissed: true }
  dismissTask(taskId: string): Promise<void> {
    return api.delete(`/youtube/task/${taskId}`).then(() => undefined)
  },

  // Persist-hide all terminal tasks (ready / error / cancelled); returns { dismissed: N }
  dismissCompletedTasks(): Promise<void> {
    return api.delete('/youtube/tasks/completed').then(() => undefined)
  },

  // Permanently delete a task — removes file from disk + DB record
  deleteTaskPermanent(taskId: string): Promise<void> {
    return api.delete(`/youtube/task/${taskId}/permanent`).then(() => undefined)
  },

  downloadFile(taskId: string): Promise<{ blob: Blob; filename: string }> {
    return api
      .get(`/youtube/file/${taskId}`, { responseType: 'blob' })
      .then((r) => {
        const disposition: string =
          r.headers['content-disposition'] ?? ''
        const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i)
        const filename = match ? decodeURIComponent(match[1]) : 'download'
        return { blob: r.data as Blob, filename }
      })
  },
}
