// ── ConverterPage — orchestrates the entire File Converter page ──
//
// Architecture mirrors YouTubePage.tsx:
//   - upload queue (UploadedFile[]) → active tasks (ConvertTask[]) → history (HistoryTask[])
//   - polling pattern with pauseRef + pollRefs Map is a direct copy of the YouTube implementation
//   - dismiss/restore use queueMicrotask to avoid side-effects inside React state updaters

import { useState, useRef, useCallback, useEffect } from 'react'
import {
  FileBox,
  RefreshCw,
  Download,
  History,
  ChevronDown,
  ChevronUp,
  Archive,
  Trash2,
  Play,
} from 'lucide-react'
import { toast } from 'react-toastify'
import axios from 'axios'
import { converterApi } from './converterApi'
import { FileDropZone } from './FileDropZone'
import FileItem from './FileItem'
import ConvertSettings from './ConvertSettings'
import ConvertProgress from './ConvertProgress'
import {
  detectCategory,
  getDefaultTargetFormat,
  getDefaultOptions,
  triggerBlobDownload,
} from './utils'
import type {
  UploadedFile,
  ConvertTask,
  HistoryTask,
  ConvertOptions,
  TaskListItem,
  StatusResponse,
} from './types'
import styles from './ConverterPage.module.css'

// Polling interval in ms — matches YouTubePage
const POLL_INTERVAL = 2000

// Terminal statuses: polling stops and task can be dismissed
const TERMINAL_STATUSES = new Set(['ready', 'error', 'cancelled'])
// Active statuses: polling must be running
const ACTIVE_STATUSES = new Set(['pending', 'uploading', 'converting'])

// ── UUID v4 — minimal inline implementation, avoids a dependency ──
function generateId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

// ── Map a raw TaskListItem from the backend into a ConvertTask ──
function taskListItemToConvertTask(item: TaskListItem): ConvertTask {
  return {
    task_id: item.task_id,
    status: item.status,
    progress: item.progress,
    filename: item.filename,
    file_size: item.file_size,
    error: item.error,
    original_filename: item.original_filename,
    original_ext: item.original_ext,
    category: item.category,
    target_format: item.target_format ?? '',
    options: null,
    created_at: item.created_at,
    completed_at: item.completed_at ?? null,
    batch_id: item.batch_id,
    file_exists: item.file_exists,
  }
}

// ── Map a raw TaskListItem into a HistoryTask ──
function taskListItemToHistoryTask(item: TaskListItem): HistoryTask {
  return {
    task_id: item.task_id,
    status: item.status,
    filename: item.filename,
    file_size: item.file_size,
    original_filename: item.original_filename,
    original_ext: item.original_ext,
    category: item.category,
    target_format: item.target_format ?? '',
    created_at: item.created_at,
    completed_at: item.completed_at ?? null,
    batch_id: item.batch_id,
    file_exists: item.file_exists,
  }
}

// ── Map a ConvertTask into a HistoryTask (for local dismiss) ──
function convertTaskToHistory(task: ConvertTask): HistoryTask {
  return {
    task_id: task.task_id,
    status: task.status,
    filename: task.filename,
    file_size: task.file_size,
    original_filename: task.original_filename,
    original_ext: task.original_ext,
    category: task.category,
    target_format: task.target_format,
    created_at: task.created_at,
    completed_at: task.completed_at,
    batch_id: task.batch_id,
    file_exists: task.file_exists,
  }
}

export default function ConverterPage() {
  // ── Upload queue ──────────────────────────────────────────────────────────
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [uploading, setUploading] = useState(false)

  // ── Active conversions ────────────────────────────────────────────────────
  const [tasks, setTasks] = useState<ConvertTask[]>([])

  // ── History panel ─────────────────────────────────────────────────────────
  const [historyTasks, setHistoryTasks] = useState<HistoryTask[]>([])
  const [showHistory, setShowHistory] = useState(false)

  // ── UI state ──────────────────────────────────────────────────────────────
  const [settingsOpenId, setSettingsOpenId] = useState<string | null>(null)
  const [converting, setConverting] = useState(false)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [fetchingHistoryId, setFetchingHistoryId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [downloadingBatchId, setDownloadingBatchId] = useState<string | null>(null)

  // ── Quota ─────────────────────────────────────────────────────────────────
  const [quota, setQuota] = useState<{ used: number; limit: number } | null>(null)

  // ── Polling refs (exact YouTubePage pattern) ──────────────────────────────
  const pollRefs = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map())
  const isPausedRef = useRef(false)
  // Keep a ref in sync so polling callbacks can read current tasks without
  // capturing a stale closure.
  const tasksRef = useRef(tasks)
  tasksRef.current = tasks

  // ── Cleanup all intervals on unmount ─────────────────────────────────────
  useEffect(() => {
    return () => {
      pollRefs.current.forEach((id) => clearInterval(id))
    }
  }, [])

  // ── Pause polling while the browser tab is hidden ─────────────────────────
  useEffect(() => {
    function handleVisibilityChange() {
      isPausedRef.current = document.hidden
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  // ── Fetch quota silently on mount ─────────────────────────────────────────
  useEffect(() => {
    converterApi.getQuota().then(setQuota).catch(() => {
      // Endpoint not yet deployed — hide the counter
    })
  }, [])

  // ── Load active tasks on mount, resume polling for in-flight ones ─────────
  useEffect(() => {
    converterApi.getTasks().then((items: TaskListItem[]) => {
      const restored = items.map(taskListItemToConvertTask)
      setTasks(restored)
      restored.forEach((t) => {
        if (ACTIVE_STATUSES.has(t.status)) {
          startPolling(t.task_id)
        }
      })
    }).catch(() => {
      // Silently ignore — the page is fully functional without persisted history
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Load dismissed tasks for the history panel on mount ──────────────────
  useEffect(() => {
    converterApi.getHistoryTasks().then((items: TaskListItem[]) => {
      setHistoryTasks(items.map(taskListItemToHistoryTask))
    }).catch(() => {
      // History is non-critical — silently ignore failures
    })
  }, [])

  // ── Polling ───────────────────────────────────────────────────────────────
  //
  // Exact copy of the YouTubePage pattern:
  //   - stores intervalId in pollRefs Map keyed by taskId
  //   - skips ticks while isPausedRef is true (tab hidden)
  //   - aborts after 3 consecutive network errors
  //   - stops and cleans up when a terminal status is received
  const startPolling = useCallback((taskId: string) => {
    if (pollRefs.current.has(taskId)) return

    let consecutiveErrors = 0

    const intervalId = setInterval(async () => {
      if (isPausedRef.current) return

      try {
        const status: StatusResponse = await converterApi.getStatus(taskId)
        consecutiveErrors = 0

        setTasks((prev) =>
          prev.map((t) =>
            t.task_id === taskId
              ? {
                  ...t,
                  status: status.status,
                  progress: status.progress,
                  filename: status.filename,
                  file_size: status.file_size,
                  error: status.error,
                  completed_at: status.completed_at ?? t.completed_at ?? null,
                  file_exists: status.status === 'ready' ? true : t.file_exists,
                }
              : t,
          ),
        )

        if (TERMINAL_STATUSES.has(status.status)) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)

          if (status.status === 'ready') {
            toast.success(`Конвертация завершена: ${status.original_filename}`)
            // Refresh quota after a successful conversion
            converterApi.getQuota().then(setQuota).catch(() => undefined)
          } else if (status.status === 'error') {
            toast.error(`Ошибка конвертации: ${status.original_filename}`)
          }
        }
      } catch (err: unknown) {
        if (axios.isAxiosError(err) && (err.response?.status === 401 || err.response?.status === 403)) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          return
        }
        consecutiveErrors += 1
        if (consecutiveErrors >= 3) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          toast.error('Потеряна связь с сервером. Обновите страницу для проверки статуса конвертации.')
        }
      }
    }, POLL_INTERVAL)

    pollRefs.current.set(taskId, intervalId)
  }, [])

  // ── File management helpers ───────────────────────────────────────────────

  const handleTargetFormatChange = useCallback((taskId: string, format: string) => {
    setUploadedFiles((prev) =>
      prev.map((f) => (f.task_id === taskId ? { ...f, target_format: format } : f)),
    )
  }, [])

  const handleOptionsChange = useCallback((taskId: string, options: ConvertOptions) => {
    setUploadedFiles((prev) =>
      prev.map((f) => (f.task_id === taskId ? { ...f, options } : f)),
    )
  }, [])

  const handleRemoveFile = useCallback((taskId: string) => {
    setUploadedFiles((prev) => prev.filter((f) => f.task_id !== taskId))
    setSettingsOpenId((prev) => (prev === taskId ? null : prev))
    // Clean up the uploaded file from the server immediately
    converterApi.deletePendingUpload(taskId).catch(() => {})
  }, [])

  const handleToggleSettings = useCallback((taskId: string) => {
    setSettingsOpenId((prev) => (prev === taskId ? null : taskId))
  }, [])

  const handleClearUploadList = useCallback(() => {
    // Clean up all pending uploads from the server
    setUploadedFiles((prev) => {
      prev.forEach((f) => converterApi.deletePendingUpload(f.task_id).catch(() => {}))
      return []
    })
    setSettingsOpenId(null)
  }, [])

  // ── File upload flow ──────────────────────────────────────────────────────
  //
  // Why batch_id: when multiple files are uploaded together, the backend groups
  // them so we can later offer a "Download all as ZIP" button.
  const handleFilesSelected = useCallback(async (files: File[]) => {
    const batchId = files.length > 1 ? generateId() : null

    // Build optimistic UploadedFile entries before the upload starts so the
    // user immediately sees the queue grow. We derive a temporary task_id
    // locally — it will be replaced with the real backend id on success.
    const optimistic: UploadedFile[] = files.map((file) => {
      const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
      const category = detectCategory(file.name) ?? 'document'
      return {
        task_id: generateId(),
        file,
        original_filename: file.name,
        original_ext: ext,
        category,
        file_size: file.size,
        target_format: getDefaultTargetFormat(ext, category),
        options: getDefaultOptions(),
        uploadProgress: 0,
        uploadComplete: false,
      }
    })

    setUploadedFiles((prev) => [...prev, ...optimistic])
    setUploading(true)

    try {
      const responses = await converterApi.upload(files, batchId, (loaded, total) => {
        const pct = Math.round((loaded / total) * 100)
        // Apply the same upload progress to all files in this batch — the
        // API reports a single aggregate progress for the multipart upload.
        setUploadedFiles((prev) =>
          prev.map((f) =>
            optimistic.some((o) => o.task_id === f.task_id)
              ? { ...f, uploadProgress: pct }
              : f,
          ),
        )
      })

      // Merge real task_ids from the backend into the optimistic entries.
      // Responses are ordered to match the input files array.
      setUploadedFiles((prev) => {
        const updated = [...prev]
        responses.forEach((resp, idx) => {
          const targetLocalId = optimistic[idx]?.task_id
          const pos = updated.findIndex((f) => f.task_id === targetLocalId)
          if (pos !== -1) {
            updated[pos] = {
              ...updated[pos],
              task_id: resp.task_id,
              original_filename: resp.original_filename,
              original_ext: resp.original_ext,
              category: resp.category,
              file_size: resp.file_size,
              // Recalculate target format now that we have the server-confirmed ext
              target_format: getDefaultTargetFormat(resp.original_ext, resp.category),
              uploadProgress: 100,
              uploadComplete: true,
            }
          }
        })
        return updated
      })
    } catch (err: unknown) {
      // Remove the optimistic entries that failed
      setUploadedFiles((prev) =>
        prev.filter((f) => !optimistic.some((o) => o.task_id === f.task_id)),
      )
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        toast.error(detail ?? 'Ошибка загрузки файлов на сервер.')
      } else {
        toast.error('Не удалось загрузить файлы.')
      }
    } finally {
      setUploading(false)
    }
  }, [])

  // ── Start conversion ──────────────────────────────────────────────────────
  const handleConvertAll = useCallback(async () => {
    const ready = uploadedFiles.filter((f) => f.uploadComplete && f.target_format)
    if (ready.length === 0) {
      toast.warning('Дождитесь завершения загрузки файлов.')
      return
    }

    setConverting(true)

    const items = ready.map((f) => ({
      task_id: f.task_id,
      target_format: f.target_format,
      options: Object.keys(f.options).length > 0 ? f.options : undefined,
    }))

    try {
      const responses = await (
        items.length === 1
          ? converterApi.startConvert(items[0].task_id, items[0].target_format, items[0].options).then((r) => [r])
          : converterApi.startBatch(items)
      )

      // Convert API responses into ConvertTask objects and prepend to the task list
      const newTasks: ConvertTask[] = responses.map((resp) => {
        const source = ready.find((f) => f.task_id === resp.task_id)
        return {
          task_id: resp.task_id,
          status: resp.status,
          progress: resp.progress,
          filename: resp.filename,
          file_size: resp.file_size,
          error: resp.error,
          original_filename: resp.original_filename,
          original_ext: resp.original_ext,
          category: resp.category,
          target_format: resp.target_format ?? source?.target_format ?? '',
          options: resp.options,
          created_at: resp.created_at,
          completed_at: resp.completed_at ?? null,
          // Preserve the batch_id so the ZIP download button can appear
          batch_id: source
            ? (uploadedFiles.filter((f) => f.task_id !== source.task_id && ready.some((r) => r.task_id === f.task_id)).length > 0
                ? (resp.task_id ? null : null) // batch_id comes from the API
                : null)
            : null,
        }
      })

      // Batch responses may carry a batch_id from the backend — re-read from response
      const finalTasks: ConvertTask[] = responses.map((resp, idx) => ({
        ...newTasks[idx],
        batch_id: resp.batch_id ?? null,
      }))

      setTasks((prev) => [...finalTasks, ...prev])

      // Remove converted files from the upload queue
      const convertedIds = new Set(ready.map((f) => f.task_id))
      setUploadedFiles((prev) => prev.filter((f) => !convertedIds.has(f.task_id)))
      if (settingsOpenId && convertedIds.has(settingsOpenId)) {
        setSettingsOpenId(null)
      }

      // Start polling for non-terminal tasks
      finalTasks.forEach((t) => {
        if (ACTIVE_STATUSES.has(t.status)) {
          startPolling(t.task_id)
        }
      })

      toast.info(
        finalTasks.length === 1
          ? 'Конвертация запущена.'
          : `Конвертация ${finalTasks.length} файлов запущена.`,
      )

      // Refresh quota after queuing
      converterApi.getQuota().then(setQuota).catch(() => undefined)
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        if (err.response?.status === 429) {
          toast.error('Достигнут дневной лимит конвертаций.')
        } else {
          toast.error(detail ?? 'Не удалось запустить конвертацию.')
        }
      } else {
        toast.error('Не удалось запустить конвертацию.')
      }
    } finally {
      setConverting(false)
    }
  }, [uploadedFiles, settingsOpenId, startPolling])

  // ── Download file ─────────────────────────────────────────────────────────
  const handleDownload = useCallback(async (taskId: string) => {
    setDownloadingId(taskId)
    try {
      const { blob, filename } = await converterApi.downloadFile(taskId)
      triggerBlobDownload(blob, filename)
    } catch {
      toast.error('Не удалось получить файл. Возможно, он уже удалён.')
    } finally {
      setDownloadingId(null)
    }
  }, [])

  // ── Download batch ZIP ────────────────────────────────────────────────────
  const handleDownloadBatchZip = useCallback(async (batchId: string) => {
    setDownloadingBatchId(batchId)
    try {
      const { blob, filename } = await converterApi.downloadBatchZip(batchId)
      triggerBlobDownload(blob, filename)
    } catch {
      toast.error('Не удалось скачать архив.')
    } finally {
      setDownloadingBatchId(null)
    }
  }, [])

  // ── Cancel conversion ─────────────────────────────────────────────────────
  const handleCancel = useCallback(async (taskId: string) => {
    try {
      await converterApi.cancelConvert(taskId)
    } catch {
      // Ignore cancel errors — update UI regardless
    }
    const intervalId = pollRefs.current.get(taskId)
    if (intervalId) {
      clearInterval(intervalId)
      pollRefs.current.delete(taskId)
    }
    setTasks((prev) =>
      prev.map((t) => (t.task_id === taskId ? { ...t, status: 'cancelled' } : t)),
    )
  }, [])

  // ── Dismiss task — moves it to history ────────────────────────────────────
  // queueMicrotask avoids side-effects inside the state updater (StrictMode safety)
  const handleDismiss = useCallback((taskId: string) => {
    converterApi.dismissTask(taskId).catch(() => undefined)
    setTasks((prev) => {
      const dismissed = prev.find((t) => t.task_id === taskId)
      if (dismissed) {
        const historyItem = convertTaskToHistory(dismissed)
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            if (h.some((item) => item.task_id === historyItem.task_id)) return h
            return [historyItem, ...h]
          })
        })
      }
      return prev.filter((t) => t.task_id !== taskId)
    })
  }, [])

  // ── Dismiss all terminal tasks at once ────────────────────────────────────
  const handleDismissCompleted = useCallback(async () => {
    try {
      await converterApi.dismissCompletedTasks()
    } catch {
      // Ignore backend errors — clean up UI regardless
    }
    setTasks((prev) => {
      const terminal = prev.filter((t) => TERMINAL_STATUSES.has(t.status))
      if (terminal.length > 0) {
        const newHistory: HistoryTask[] = terminal.map(convertTaskToHistory)
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            const existingIds = new Set(h.map((item) => item.task_id))
            const deduped = newHistory.filter((item) => !existingIds.has(item.task_id))
            return [...deduped, ...h]
          })
        })
      }
      return prev.filter((t) => !TERMINAL_STATUSES.has(t.status))
    })
  }, [])

  // ── Restore a history task back to active list ────────────────────────────
  const handleRestore = useCallback(async (histTask: HistoryTask) => {
    setRestoringId(histTask.task_id)
    try {
      await converterApi.restoreTask(histTask.task_id)
      const restored: ConvertTask = {
        task_id: histTask.task_id,
        status: histTask.status,
        progress: histTask.status === 'ready' ? 100 : 0,
        filename: histTask.filename,
        file_size: histTask.file_size,
        error: null,
        original_filename: histTask.original_filename,
        original_ext: histTask.original_ext,
        category: histTask.category,
        target_format: histTask.target_format,
        options: null,
        created_at: histTask.created_at,
        completed_at: histTask.completed_at,
        batch_id: histTask.batch_id,
        file_exists: histTask.file_exists,
      }
      setTasks((prev) => [restored, ...prev])
      setHistoryTasks((prev) => prev.filter((h) => h.task_id !== histTask.task_id))
      toast.info('Задача восстановлена.')
    } catch {
      toast.error('Не удалось восстановить задачу.')
    } finally {
      setRestoringId(null)
    }
  }, [])

  // ── Download from history panel ────────────────────────────────────────────
  const handleHistoryDownload = useCallback(async (taskId: string) => {
    setFetchingHistoryId(taskId)
    try {
      const { blob, filename } = await converterApi.downloadFile(taskId)
      triggerBlobDownload(blob, filename)
    } catch {
      toast.error('Не удалось получить файл. Возможно, он уже удалён.')
    } finally {
      setFetchingHistoryId(null)
    }
  }, [])

  // ── Memoized restore handler for history items ──────────────────────────
  const handleRestoreFromHistory = useCallback((taskId: string) => {
    const histTask = historyTasks.find((h) => h.task_id === taskId)
    if (histTask) handleRestore(histTask)
  }, [historyTasks, handleRestore])

  // ── Permanently delete a task (file + DB record) ────────────────────────
  const handleDeletePermanent = useCallback(async (taskId: string) => {
    setDeletingId(taskId)
    try {
      await converterApi.deleteTaskPermanent(taskId)
      setTasks((prev) => prev.filter((t) => t.task_id !== taskId))
      setHistoryTasks((prev) => prev.filter((h) => h.task_id !== taskId))
    } catch {
      toast.error('Не удалось удалить задачу.')
    } finally {
      setDeletingId(null)
    }
  }, [])

  // ── Derived state ─────────────────────────────────────────────────────────

  const uploadedCount = uploadedFiles.length
  const readyToConvert = uploadedFiles.filter((f) => f.uploadComplete && f.target_format)
  const hasCompleted = tasks.some((t) => TERMINAL_STATUSES.has(t.status))

  // Find batches where all tasks are ready — offer ZIP download
  const readyBatches = (() => {
    const batchMap = new Map<string, ConvertTask[]>()
    tasks.forEach((t) => {
      if (t.batch_id) {
        const group = batchMap.get(t.batch_id) ?? []
        group.push(t)
        batchMap.set(t.batch_id, group)
      }
    })
    const result: string[] = []
    batchMap.forEach((group, batchId) => {
      if (group.length > 1 && group.every((t) => t.status === 'ready')) {
        result.push(batchId)
      }
    })
    return result
  })()

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>

      {/* ── Page header ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageTitleRow}>
          <h1 className={styles.pageTitle}>
            <FileBox size={24} aria-hidden="true" />
            Конвертер файлов
          </h1>
          {quota !== null && (
            <span
              className={styles.quotaBadge}
              aria-label={`Осталось конвертаций: ${Math.max(0, quota.limit - quota.used)} из ${quota.limit}`}
            >
              Осталось: {Math.max(0, quota.limit - quota.used)}/{quota.limit}
            </span>
          )}
        </div>
        <p className={styles.pageSubtitle}>
          Конвертируйте видео, аудио, изображения и документы
        </p>
      </div>

      {/* ── Drop zone ── */}
      <FileDropZone
        onFilesSelected={handleFilesSelected}
        disabled={uploading || converting}
        currentFileCount={uploadedCount}
      />

      {/* ── Upload queue ── */}
      {uploadedCount > 0 && (
        <div className={styles.queueSection}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>
              Загруженные файлы
              <span className={styles.countBadge}>{uploadedCount}</span>
            </span>
            <button
              type="button"
              className={styles.clearBtn}
              onClick={handleClearUploadList}
              disabled={uploading || converting}
              aria-label="Очистить список загруженных файлов"
            >
              <Trash2 size={13} aria-hidden="true" />
              Очистить список
            </button>
          </div>

          <div className={styles.fileList}>
            {uploadedFiles.map((file) => (
              <div key={file.task_id} className={styles.fileItemWrap}>
                <FileItem
                  file={file}
                  onTargetFormatChange={handleTargetFormatChange}
                  onOptionsChange={handleOptionsChange}
                  onRemove={handleRemoveFile}
                  onToggleSettings={handleToggleSettings}
                  showSettings={settingsOpenId === file.task_id}
                  disabled={uploading || converting}
                />
                {settingsOpenId === file.task_id && (
                  <ConvertSettings
                    category={file.category}
                    options={file.options}
                    onChange={(opts) => handleOptionsChange(file.task_id, opts)}
                    disabled={uploading || converting}
                    taskId={file.task_id}
                  />
                )}
              </div>
            ))}
          </div>

          {/* ── Action row ── */}
          <div className={styles.queueActions}>
            <button
              type="button"
              className={styles.convertBtn}
              onClick={handleConvertAll}
              disabled={converting || uploading || readyToConvert.length === 0}
              aria-busy={converting}
              aria-label="Конвертировать все файлы"
            >
              {converting ? (
                <>
                  <RefreshCw size={15} aria-hidden="true" className={styles.iconSpin} />
                  Конвертация...
                </>
              ) : (
                <>
                  <Play size={15} aria-hidden="true" />
                  Конвертировать всё ({readyToConvert.length})
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ── Active conversions ── */}
      {tasks.length > 0 && (
        <div className={styles.tasksSection}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>
              Активные конвертации
              <span className={styles.countBadge}>{tasks.length}</span>
            </span>

            {/* ZIP download buttons for completed batches */}
            {readyBatches.map((batchId) => (
              <button
                key={batchId}
                type="button"
                className={styles.zipBtn}
                onClick={() => handleDownloadBatchZip(batchId)}
                disabled={downloadingBatchId === batchId}
                aria-busy={downloadingBatchId === batchId}
                aria-label="Скачать все файлы батча в ZIP-архиве"
              >
                <Archive size={13} aria-hidden="true" />
                {downloadingBatchId === batchId ? 'Архивирование...' : 'Скачать всё (ZIP)'}
              </button>
            ))}

            {hasCompleted && (
              <button
                type="button"
                className={styles.clearCompletedBtn}
                onClick={handleDismissCompleted}
                aria-label="Скрыть все завершённые задачи"
              >
                Скрыть завершённые
              </button>
            )}
          </div>

          <div className={styles.taskList} aria-live="polite">
            {tasks.map((task) => (
              <ConvertProgress
                key={task.task_id}
                task={task}
                onDismiss={handleDismiss}
                onCancel={handleCancel}
                onDownload={handleDownload}
                onDelete={handleDeletePermanent}
                downloadingId={downloadingId}
                restoringId={restoringId}
                deletingId={deletingId}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── History (collapsible) ── */}
      {historyTasks.length > 0 && (
        <div className={styles.historySection}>
          <button
            type="button"
            className={styles.historyToggle}
            onClick={() => setShowHistory((v) => !v)}
            aria-expanded={showHistory}
            aria-controls="converter-history-list"
            aria-label={`История конвертаций, ${historyTasks.length} записей`}
          >
            <History size={13} aria-hidden="true" />
            История конвертаций
            <span className={styles.countBadge}>{historyTasks.length}</span>
            {showHistory
              ? <ChevronUp size={13} aria-hidden="true" />
              : <ChevronDown size={13} aria-hidden="true" />
            }
          </button>

          {showHistory && (
            <div
              id="converter-history-list"
              className={styles.historyList}
              aria-live="polite"
            >
              {historyTasks.map((item) => (
                <ConvertProgress
                  key={item.task_id}
                  task={item}
                  isHistory
                  onDismiss={handleDismiss}
                  onCancel={() => undefined}
                  onDownload={handleHistoryDownload}
                  onRestore={handleRestoreFromHistory}
                  onDelete={handleDeletePermanent}
                  downloadingId={fetchingHistoryId}
                  restoringId={restoringId}
                  deletingId={deletingId}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Empty state: no files, no tasks, no history ── */}
      {uploadedCount === 0 && tasks.length === 0 && historyTasks.length === 0 && (
        <div className={styles.emptyState} aria-live="polite">
          <Download size={40} aria-hidden="true" className={styles.emptyIcon} />
          <p className={styles.emptyText}>
            Перетащите файлы в зону выше или нажмите для выбора
          </p>
          <p className={styles.emptyHint}>
            Поддерживаются видео, аудио, изображения и документы
          </p>
        </div>
      )}
    </div>
  )
}
