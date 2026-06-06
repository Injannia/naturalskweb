import api from '../../api/client'
import type { InfoResponse, DownloadStatus, QuotaResponse } from './types'

export const multidlApi = {
  getInfo(url: string): Promise<InfoResponse> {
    return api.post<InfoResponse>('/multidl/info', { url }).then((r) => r.data)
  },
  startDownload(url: string, audioOnly: boolean, title?: string | null): Promise<DownloadStatus> {
    return api
      .post<DownloadStatus>('/multidl/download', { url, audio_only: audioOnly, title: title ?? null })
      .then((r) => r.data)
  },
  getStatus(taskId: string): Promise<DownloadStatus> {
    return api.get<DownloadStatus>(`/multidl/status/${taskId}`).then((r) => r.data)
  },
  getTasks(): Promise<DownloadStatus[]> {
    return api.get<DownloadStatus[]>('/multidl/tasks').then((r) => r.data)
  },
  cancelDownload(taskId: string): Promise<void> {
    return api.delete(`/multidl/cancel/${taskId}`).then(() => undefined)
  },
  retryDownload(taskId: string): Promise<DownloadStatus> {
    return api.post<DownloadStatus>(`/multidl/retry/${taskId}`).then((r) => r.data)
  },
  dismissTask(taskId: string): Promise<void> {
    return api.delete(`/multidl/task/${taskId}`).then(() => undefined)
  },
  getQuota(): Promise<QuotaResponse> {
    return api.get<QuotaResponse>('/multidl/quota').then((r) => r.data)
  },
  downloadFile(taskId: string): Promise<{ blob: Blob; filename: string }> {
    return api.get(`/multidl/file/${taskId}`, { responseType: 'blob' }).then((r) => {
      const disposition: string = r.headers['content-disposition'] ?? ''
      const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)/i)
      const filename = match ? decodeURIComponent(match[1]) : 'download'
      return { blob: r.data as Blob, filename }
    })
  },
}
