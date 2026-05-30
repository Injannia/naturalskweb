import { useState, useRef, useCallback, useEffect } from 'react'
import { Youtube, Link, AlertCircle, Download, ClipboardPaste, X, TriangleAlert, History, FileDown, RotateCcw, ChevronDown, ChevronUp, Trash2, Loader } from 'lucide-react'
import { toast } from 'react-toastify'
import axios from 'axios'
import { youtubeApi } from './youtubeApi'
import { isValidYouTubeUrl, estimatePlaylistSize, formatFileSize, triggerBlobDownload, FILE_TTL_MS } from './utils'
import VideoCard from './VideoCard'
import PlaylistView from './PlaylistView'
import DownloadOptions from './DownloadOptions'
import DownloadProgress from './DownloadProgress'
import type {
  MediaInfo,
  VideoFormat,
  VideoQuality,
  DownloadTask,
  StatusResponse,
  TaskListItem,
  HistoryTask,
} from './types'
import styles from './YouTubePage.module.css'

// Base poll period (ms) + per-poller random jitter, so concurrent task
// pollers don't all fire on the same boundary and burst the rate limiter.
const POLL_INTERVAL = 3000
const POLL_JITTER = 1000

// Threshold: playlists with this many or more selected videos require confirmation
const CONFIRMATION_THRESHOLD = 5

// Params captured when a large playlist download is about to be submitted
interface PendingConfirmation {
  downloadUrl: string
  dlFormat: VideoFormat
  dlQuality: VideoQuality
  title: string
  videoIds: string[]
  estimatedSize: string
}

// localStorage keys for persisted preferences
const LS_FORMAT_KEY = 'yt-format'
const LS_QUALITY_KEY = 'yt-quality'

/** Read a stored format preference, falling back to the given default */
function readStoredFormat(): VideoFormat {
  const stored = localStorage.getItem(LS_FORMAT_KEY)
  if (stored === 'mp4' || stored === 'mp3' || stored === 'wav') return stored
  return 'mp4'
}

/** Read a stored quality preference, falling back to the given default */
function readStoredQuality(): VideoQuality {
  const stored = localStorage.getItem(LS_QUALITY_KEY)
  if (
    stored === '360p' ||
    stored === '480p' ||
    stored === '720p' ||
    stored === '1080p' ||
    stored === 'best'
  )
    return stored
  return 'best'
}

export default function YouTubePage() {
  const [url, setUrl] = useState('')
  const [urlTouched, setUrlTouched] = useState(false)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const [mediaInfo, setMediaInfo] = useState<MediaInfo | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  // Task 1: initialise from localStorage
  const [format, setFormat] = useState<VideoFormat>(readStoredFormat)
  const [quality, setQuality] = useState<VideoQuality>(readStoredQuality)
  const [startingDownload, setStartingDownload] = useState(false)
  const [forceDownloadLoading, setForceDownloadLoading] = useState(false)
  const [tasks, setTasks] = useState<DownloadTask[]>([])
  const tasksRef = useRef(tasks)
  tasksRef.current = tasks
  // Task 6: quota state — null means unknown/unavailable
  const [quota, setQuota] = useState<{ used: number; limit: number } | null>(null)
  // Tracks which format+quality combos for the current URL were served from cache.
  // Key format: `${format}_${quality}`. Used to show the "Перекачать" button only
  // when the active combo is cached — switching format/quality hides the button.
  const [cachedDownloads, setCachedDownloads] = useState<Set<string>>(new Set())

  // Download history: dismissed tasks that still have files on disk
  const [historyTasks, setHistoryTasks] = useState<HistoryTask[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [fetchingHistoryId, setFetchingHistoryId] = useState<string | null>(null)
  const [deletingHistoryId, setDeletingHistoryId] = useState<string | null>(null)

  // Confirmation gate for large playlist downloads (5+ videos).
  // Holds the params needed to proceed so we can call initiateDownload after the user confirms.
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null)

  // Tracks the URL that was last submitted so we know when to clear results
  const fetchedUrlRef = useRef<string>('')

  // Polling refs: map of taskId → intervalId
  const pollRefs = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map())

  // Pause flag: true while the browser tab is hidden — polling ticks are skipped
  const isPausedRef = useRef(false)

  // Clean up all intervals on unmount
  useEffect(() => {
    return () => {
      pollRefs.current.forEach((id) => clearInterval(id))
    }
  }, [])

  // ISSUE-9: pause polling while the tab is hidden to avoid wasting requests
  useEffect(() => {
    function handleVisibilityChange() {
      isPausedRef.current = document.hidden
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  // Task 6: fetch quota on mount; silently swallow errors if endpoint is absent
  useEffect(() => {
    youtubeApi.getQuota().then(setQuota).catch(() => {
      // Endpoint not yet deployed — hide the counter
    })
  }, [])

  // Task 5: load persisted tasks from the backend on mount
  useEffect(() => {
    youtubeApi.getTasks().then((items: TaskListItem[]) => {
      const restored: DownloadTask[] = items.map((item) => ({
        task_id: item.task_id,
        status: item.status,
        progress: item.progress,
        filename: item.filename,
        file_size: item.file_size,
        error: item.error,
        // Backend does not store a display title — derive a short fallback from the URL
        title: item.title ?? item.url,
        format: item.format,
        url: item.url,
        quality: item.quality,
        video_ids: item.video_ids,
        created_at: item.created_at,
        completed_at: item.completed_at ?? null,
        // Historical tasks never have live transfer stats
        speed: null,
        eta: null,
        file_exists: item.file_exists,
      }))
      setTasks(restored)
      // Resume polling for any tasks that are still actively processing
      const activeStatuses = new Set<string>(['pending', 'downloading', 'converting', 'zipping'])
      restored.forEach((t) => {
        if (activeStatuses.has(t.status)) {
          startPolling(t.task_id, t.title)
        }
      })
    }).catch(() => {
      // Silently ignore history load failures — the page is still fully functional
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Load dismissed-but-available tasks for the history panel
  useEffect(() => {
    youtubeApi.getHistoryTasks().then((items: TaskListItem[]) => {
      const mapped: HistoryTask[] = items.map((item) => ({
        task_id: item.task_id,
        status: item.status,
        title: item.title ?? item.url,
        format: item.format,
        url: item.url,
        quality: item.quality,
        filename: item.filename,
        file_size: item.file_size,
        created_at: item.created_at,
        completed_at: item.completed_at ?? null,
        file_exists: item.file_exists,
      }))
      setHistoryTasks(mapped)
    }).catch(() => {
      // Silently ignore — history is a non-critical feature
    })
  }, [])

  // Task 1: persist format preference whenever it changes
  useEffect(() => {
    localStorage.setItem(LS_FORMAT_KEY, format)
  }, [format])

  // Task 1: persist quality preference whenever it changes
  useEffect(() => {
    localStorage.setItem(LS_QUALITY_KEY, quality)
  }, [quality])

  // Task 2: clear results when the URL changes from what was last fetched
  function handleUrlChange(e: React.ChangeEvent<HTMLInputElement>) {
    const next = e.target.value
    setUrl(next)
    // Only clear if there are results and the user has typed something different
    if (mediaInfo !== null && next !== fetchedUrlRef.current) {
      setMediaInfo(null)
      setSelectedIds(new Set())
      // Reset cache-hit tracking since this is a new URL
      setCachedDownloads(new Set())
    }
  }

  // ── Validation ──
  const urlIsValid = isValidYouTubeUrl(url)
  const showUrlError = urlTouched && url.trim().length > 0 && !urlIsValid

  // Task 4: clear URL + results
  function handleClearUrl() {
    setUrl('')
    setMediaInfo(null)
    setSelectedIds(new Set())
    setCachedDownloads(new Set())
    fetchedUrlRef.current = ''
  }

  // Task 3: paste from clipboard
  async function handlePasteFromClipboard() {
    if (!navigator.clipboard?.readText) {
      toast.info('Буфер обмена недоступен в этом браузере.')
      return
    }
    try {
      const text = await navigator.clipboard.readText()
      if (text.trim()) {
        setUrl(text.trim())
        // Clear stale results since we just replaced the URL
        if (mediaInfo !== null) {
          setMediaInfo(null)
          setSelectedIds(new Set())
        }
      }
    } catch {
      // Permission denied or other clipboard error — show nothing, just don't paste
      toast.warning('Нет доступа к буферу обмена. Разрешите доступ в настройках браузера.')
    }
  }

  // ── Drag-and-drop URL support ──
  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    // Allow drop by preventing the default "no-drop" behaviour
    e.preventDefault()
    e.stopPropagation()
  }

  function handleDragEnter(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(true)
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    // Only clear the highlight when leaving the card itself, not a child element
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setIsDragOver(false)
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)

    // Prefer plain text; fall back to the URI list format some browsers use
    const dropped =
      e.dataTransfer.getData('text/plain').trim() ||
      e.dataTransfer.getData('text/uri-list').trim()

    if (!dropped) return

    // Only accept URLs that look like YouTube links to avoid confusing the user
    if (!isValidYouTubeUrl(dropped)) {
      toast.warning('Это не ссылка на YouTube. Перетащите корректный YouTube URL.')
      return
    }

    setUrl(dropped)
    setUrlTouched(false)
    // Clear stale results — the URL has changed
    if (mediaInfo !== null) {
      setMediaInfo(null)
      setSelectedIds(new Set())
    }
    fetchedUrlRef.current = ''
  }

  // ── Get video/playlist info ──
  async function handleGetInfo() {
    if (!urlIsValid) {
      setUrlTouched(true)
      return
    }

    setLoadingInfo(true)
    setMediaInfo(null)
    setSelectedIds(new Set())
    fetchedUrlRef.current = url.trim()

    try {
      const info = await youtubeApi.getInfo(url.trim())
      if (info.type === 'video' && info.video) {
        setMediaInfo({ type: 'video', data: info.video })
        // Pre-select the single video
        setSelectedIds(new Set([info.video.id]))
      } else if (info.type === 'playlist' && info.playlist) {
        setMediaInfo({ type: 'playlist', data: info.playlist })
        // Select all by default
        setSelectedIds(new Set(info.playlist.videos.map((v) => v.id)))
      } else {
        toast.error('Не удалось получить информацию о видео.')
      }
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        if (err.response?.status === 400) {
          toast.error(detail ?? 'Неверный URL. Проверьте ссылку.')
        } else if (err.response?.status === 404) {
          toast.error('Видео не найдено или недоступно.')
        } else {
          toast.error(detail ?? 'Ошибка при получении информации о видео.')
        }
      } else {
        toast.error('Нет связи с сервером.')
      }
    } finally {
      setLoadingInfo(false)
    }
  }

  // ── Keyboard: Enter in URL input ──
  function handleUrlKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !loadingInfo) {
      handleGetInfo()
    }
  }

  // ── Playlist selection ──
  const handleToggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleSelectAll = useCallback(() => {
    if (mediaInfo?.type === 'playlist') {
      setSelectedIds(new Set(mediaInfo.data.videos.map((v) => v.id)))
    }
  }, [mediaInfo])

  const handleDeselectAll = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  // ── Polling for task status ──
  const startPolling = useCallback((taskId: string, title: string) => {
    if (pollRefs.current.has(taskId)) return

    // ISSUE-3: count consecutive errors to detect a dead backend
    let consecutiveErrors = 0

    const intervalId = setInterval(async () => {
      // ISSUE-9: skip fetch while the tab is hidden
      if (isPausedRef.current) return

      try {
        const status: StatusResponse = await youtubeApi.getStatus(taskId)

        // Successful response — reset the error streak
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
                  speed: status.speed ?? null,
                  eta: status.eta ?? null,
                  completed_at: status.completed_at ?? t.completed_at ?? null,
                  file_exists: status.status === 'ready' ? true : t.file_exists,
                }
              : t,
          ),
        )

        // Stop polling when terminal state reached
        if (
          status.status === 'ready' ||
          status.status === 'error' ||
          status.status === 'cancelled'
        ) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)

          if (status.status === 'ready') {
            toast.success(`Загрузка завершена: ${title}`)
            // Task 6: refresh quota after a successful download completes
            youtubeApi.getQuota().then(setQuota).catch(() => undefined)
          } else if (status.status === 'error') {
            toast.error(`Ошибка загрузки: ${title}`)
          }
        }
      } catch (err: unknown) {
        // Stop polling on auth errors — session expired or access denied
        if (axios.isAxiosError(err) && (err.response?.status === 401 || err.response?.status === 403)) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          return
        }
        // ISSUE-3: accumulate consecutive non-auth errors; abort after 3 in a row
        consecutiveErrors += 1
        if (consecutiveErrors >= 3) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          toast.error('Потеряна связь с сервером. Обновите страницу для проверки статуса загрузки.')
        }
        // Otherwise keep polling — transient network blip
      }
    }, POLL_INTERVAL + Math.random() * POLL_JITTER)

    pollRefs.current.set(taskId, intervalId)
  }, [])

  // ── Core download initiator — extracted so retry and force-redownload can call it ──
  const initiateDownload = useCallback(
    async (
      downloadUrl: string,
      dlFormat: VideoFormat,
      dlQuality: VideoQuality,
      title: string,
      videoIds?: string[],
      forceDownload?: boolean,
    ) => {
      const response = await youtubeApi.startDownload(
        {
          url: downloadUrl,
          video_ids: videoIds,
          format: dlFormat,
          quality: dlQuality,
          title,
        },
        forceDownload,
      )

      const { task_id, created_at, cached } = response

      // Cache hit: backend created the task as ready immediately
      const isCachedHit = cached === true
      const comboKey = `${dlFormat}_${dlQuality}`
      if (isCachedHit) {
        // Record that this format+quality combo is cached for the current URL
        setCachedDownloads((prev) => {
          const next = new Set(prev)
          next.add(comboKey)
          return next
        })
      } else if (forceDownload) {
        // Force-download succeeded — the cache for this combo is now invalidated
        setCachedDownloads((prev) => {
          const next = new Set(prev)
          next.delete(comboKey)
          return next
        })
      }

      const newTask: DownloadTask = {
        task_id,
        // Use the actual status from the response — may be 'ready' on a cache hit
        status: response.status ?? 'pending',
        progress: isCachedHit ? 100 : 0,
        filename: response.filename,
        file_size: response.file_size,
        error: null,
        speed: null,
        eta: null,
        title,
        format: dlFormat,
        url: downloadUrl,
        quality: dlQuality,
        video_ids: videoIds,
        created_at: created_at ?? null,
        completed_at: response.completed_at ?? null,
        cached: isCachedHit,
        // Cache hits skip polling, so seed file_exists from the response.
        file_exists: isCachedHit ? response.file_exists ?? true : undefined,
      }

      setTasks((prev) => [newTask, ...prev])

      if (isCachedHit) {
        // File is already ready — skip polling, notify the user with a specific message
        toast.success(`Файл получен из кэша: ${title}`)
        // Refresh quota since a cached hit still counts against quota
        youtubeApi.getQuota().then(setQuota).catch(() => undefined)
      } else {
        startPolling(task_id, title)
        toast.info('Загрузка поставлена в очередь.')
      }
    },
    [startPolling],
  )

  // BUG-1/ISSUE-6: shared helper — dismiss a cancelled/error duplicate before
  // starting a new task so it does not resurface after a page refresh.
  // Does nothing if no matching terminal duplicate exists.
  const dismissDuplicateIfNeeded = useCallback(
    (downloadUrl: string, dlFormat: VideoFormat, dlQuality: VideoQuality) => {
      const duplicate = tasksRef.current.find(
        (t) =>
          t.url === downloadUrl &&
          t.format === dlFormat &&
          t.quality === dlQuality &&
          (t.status === 'cancelled' || t.status === 'error'),
      )
      if (duplicate) {
        youtubeApi.dismissTask(duplicate.task_id).catch(() => undefined)
        setTasks((prev) => prev.filter((t) => t.task_id !== duplicate.task_id))
      }
    },
    [],
  )

  // ── Start download ──
  async function handleDownload() {
    if (!mediaInfo || selectedIds.size === 0) return

    // Guard against duplicate downloads for the same URL + format + quality
    const activeStatuses = new Set(['pending', 'downloading', 'converting', 'zipping'])
    const trimmedUrl = url.trim()
    const duplicate = tasks.find(
      (t) => t.url === trimmedUrl && t.format === format && t.quality === quality,
    )
    if (duplicate) {
      if (activeStatuses.has(duplicate.status)) {
        toast.warning('Это видео уже загружается.')
        return
      }
      if (duplicate.status === 'ready') {
        // File is already downloaded — do not create a redundant new task.
        // Direct the user to the existing ready entry in the list below.
        toast.info('Файл уже скачан и доступен в списке загрузок.')
        return
      }
      // Task is in a terminal non-ready state (cancelled / error).
      // Dismiss it from the backend so it won't resurface after a page refresh
      // alongside the new task that is about to be created.
      youtubeApi.dismissTask(duplicate.task_id).catch(() => undefined)
      setTasks((prev) => prev.filter((t) => t.task_id !== duplicate.task_id))
    }

    const videoIds =
      mediaInfo.type === 'playlist' ? Array.from(selectedIds) : undefined

    const title =
      mediaInfo.type === 'video'
        ? mediaInfo.data.title
        : `${mediaInfo.data.title} (${selectedIds.size} видео)`

    // Show inline confirmation for large playlist downloads before proceeding
    if (mediaInfo.type === 'playlist' && selectedIds.size >= CONFIRMATION_THRESHOLD) {
      setPendingConfirmation({
        downloadUrl: trimmedUrl,
        dlFormat: format,
        dlQuality: quality,
        title,
        videoIds: videoIds ?? [],
        estimatedSize: estimatePlaylistSize(selectedIds.size, quality, format),
      })
      return
    }

    setStartingDownload(true)
    try {
      await initiateDownload(trimmedUrl, format, quality, title, videoIds)

      // Task 6: refresh quota after queuing
      youtubeApi.getQuota().then(setQuota).catch(() => undefined)
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        if (err.response?.status === 429) {
          toast.error('Достигнут дневной лимит загрузок.')
        } else {
          toast.error(detail ?? 'Не удалось запустить загрузку.')
        }
      } else {
        toast.error('Не удалось запустить загрузку.')
      }
    } finally {
      setStartingDownload(false)
    }
  }

  // ── Force re-download: bypasses the server cache ──
  async function handleForceDownload() {
    if (!mediaInfo || selectedIds.size === 0) return

    const videoIds =
      mediaInfo.type === 'playlist' ? Array.from(selectedIds) : undefined

    const title =
      mediaInfo.type === 'video'
        ? mediaInfo.data.title
        : `${mediaInfo.data.title} (${selectedIds.size} видео)`

    const trimmedUrl = url.trim()
    // BUG-1: dismiss any stale cancelled/error duplicate before forcing a new download
    dismissDuplicateIfNeeded(trimmedUrl, format, quality)
    setForceDownloadLoading(true)
    try {
      await initiateDownload(trimmedUrl, format, quality, title, videoIds, true)
      youtubeApi.getQuota().then(setQuota).catch(() => undefined)
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        if (err.response?.status === 429) {
          toast.error('Достигнут дневной лимит загрузок.')
        } else {
          toast.error(detail ?? 'Не удалось запустить загрузку.')
        }
      } else {
        toast.error('Не удалось запустить загрузку.')
      }
    } finally {
      setForceDownloadLoading(false)
    }
  }

  // ── Large-playlist confirmation handlers ──
  async function handleConfirmDownload() {
    if (!pendingConfirmation) return
    const { downloadUrl, dlFormat, dlQuality, title, videoIds } = pendingConfirmation
    setPendingConfirmation(null)
    // BUG-1: dismiss any stale cancelled/error duplicate before proceeding
    dismissDuplicateIfNeeded(downloadUrl, dlFormat, dlQuality)
    setStartingDownload(true)
    try {
      await initiateDownload(downloadUrl, dlFormat, dlQuality, title, videoIds)
      youtubeApi.getQuota().then(setQuota).catch(() => undefined)
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail
        if (err.response?.status === 429) {
          toast.error('Достигнут дневной лимит загрузок.')
        } else {
          toast.error(detail ?? 'Не удалось запустить загрузку.')
        }
      } else {
        toast.error('Не удалось запустить загрузку.')
      }
    } finally {
      setStartingDownload(false)
    }
  }

  function handleCancelConfirmation() {
    setPendingConfirmation(null)
  }

  // Retry via the backend endpoint — preserves all original params including video_ids
  const handleRetry = useCallback(
    async (task: DownloadTask) => {
      try {
        const response = await youtubeApi.retryDownload(task.task_id)
        const { task_id, created_at, completed_at, cached } = response
        const isCachedHit = cached === true

        const newTask: DownloadTask = {
          task_id,
          // Use actual status from response — may be 'ready' on a cache hit
          status: response.status ?? 'pending',
          progress: isCachedHit ? 100 : 0,
          filename: response.filename ?? null,
          file_size: response.file_size ?? null,
          error: null,
          speed: null,
          eta: null,
          title: task.title,
          format: task.format,
          url: task.url,
          quality: task.quality,
          video_ids: task.video_ids,
          created_at: created_at ?? null,
          completed_at: completed_at ?? null,
          cached: isCachedHit,
          // Cache hits skip polling, so seed file_exists from the response.
          file_exists: isCachedHit ? response.file_exists ?? true : undefined,
        }

        // Dismiss the old failed/cancelled task in the backend so it does not
        // reappear alongside the new task after a page refresh.
        youtubeApi.dismissTask(task.task_id).catch(() => undefined)

        // Replace the old task in the UI with the new one
        setTasks((prev) =>
          prev.map((t) => (t.task_id === task.task_id ? newTask : t)),
        )

        if (isCachedHit) {
          toast.success(`Файл получен из кэша: ${task.title}`)
          youtubeApi.getQuota().then(setQuota).catch(() => undefined)
        } else {
          startPolling(task_id, task.title)
          toast.info('Загрузка поставлена в очередь.')
        }
      } catch (err: unknown) {
        if (axios.isAxiosError(err)) {
          const detail = err.response?.data?.detail
          toast.error(detail ?? 'Не удалось повторить загрузку.')
        } else {
          toast.error('Не удалось повторить загрузку.')
        }
      }
    },
    [startPolling],
  )

  // ── Cancel task ──
  // Calls the backend API, stops polling, and marks the task as cancelled.
  const handleCancel = useCallback(async (taskId: string) => {
    try {
      await youtubeApi.cancelDownload(taskId)
    } catch {
      // Ignore cancel errors — the task will be marked cancelled locally regardless
    }
    const intervalId = pollRefs.current.get(taskId)
    if (intervalId) {
      clearInterval(intervalId)
      pollRefs.current.delete(taskId)
    }
    setTasks((prev) =>
      prev.map((t) =>
        t.task_id === taskId ? { ...t, status: 'cancelled' } : t,
      ),
    )
  }, [])

  // ── Dismiss task from UI — moves it to the history panel ──
  const handleDismiss = useCallback((taskId: string) => {
    youtubeApi.dismissTask(taskId).catch(() => undefined)
    // Read the task to dismiss BEFORE updating state — the setTasks updater
    // must be a pure function (no side-effects like calling setHistoryTasks
    // inside it), otherwise React StrictMode's double-invocation of updaters
    // causes duplicate entries.
    setTasks((prev) => {
      const dismissed = prev.find((t) => t.task_id === taskId)
      if (dismissed) {
        const historyItem: HistoryTask = {
          task_id: dismissed.task_id,
          status: dismissed.status,
          title: dismissed.title,
          format: dismissed.format,
          url: dismissed.url,
          quality: dismissed.quality,
          filename: dismissed.filename,
          file_size: dismissed.file_size,
          created_at: dismissed.created_at,
          completed_at: dismissed.completed_at ?? null,
          file_exists: dismissed.file_exists,
        }
        // Defer historyTasks update to avoid side-effect inside updater
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            // Guard against duplicates (defensive)
            if (h.some((item) => item.task_id === historyItem.task_id)) return h
            return [historyItem, ...h]
          })
        })
      }
      return prev.filter((t) => t.task_id !== taskId)
    })
  }, [])

  // ── Clear all terminal tasks at once — moves them to history ──
  const handleClearCompleted = useCallback(async () => {
    try {
      await youtubeApi.dismissCompletedTasks()
    } catch {
      // Ignore backend errors — clean up UI regardless
    }
    setTasks((prev) => {
      const terminal = prev.filter(
        (t) => t.status === 'ready' || t.status === 'error' || t.status === 'cancelled',
      )
      if (terminal.length > 0) {
        const newHistory: HistoryTask[] = terminal.map((t) => ({
          task_id: t.task_id,
          status: t.status,
          title: t.title,
          format: t.format,
          url: t.url,
          quality: t.quality,
          filename: t.filename,
          file_size: t.file_size,
          created_at: t.created_at,
          completed_at: t.completed_at ?? null,
          file_exists: t.file_exists,
        }))
        // Defer to avoid side-effect inside updater (StrictMode double-invocation)
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            const existingIds = new Set(h.map((item) => item.task_id))
            const deduped = newHistory.filter((item) => !existingIds.has(item.task_id))
            return [...deduped, ...h]
          })
        })
      }
      return prev.filter(
        (t) => t.status !== 'ready' && t.status !== 'error' && t.status !== 'cancelled',
      )
    })
  }, [])

  // ── Restore a dismissed task back to the active list ──
  const handleRestore = useCallback(async (histTask: HistoryTask) => {
    setRestoringId(histTask.task_id)
    try {
      await youtubeApi.restoreTask(histTask.task_id)
      // Rebuild as a DownloadTask and prepend to the active list
      const restored: DownloadTask = {
        task_id: histTask.task_id,
        status: histTask.status,
        progress: histTask.status === 'ready' ? 100 : 0,
        filename: histTask.filename,
        file_size: histTask.file_size,
        error: null,
        speed: null,
        eta: null,
        title: histTask.title,
        format: histTask.format,
        url: histTask.url,
        quality: histTask.quality,
        created_at: histTask.created_at,
        completed_at: histTask.completed_at,
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

  // ── Download a file directly from the history panel ──
  const handleHistoryDownload = useCallback(async (taskId: string) => {
    setFetchingHistoryId(taskId)
    try {
      const { blob, filename } = await youtubeApi.downloadFile(taskId)
      triggerBlobDownload(blob, filename)
    } catch {
      toast.error('Не удалось получить файл. Возможно, он уже удалён.')
    } finally {
      setFetchingHistoryId(null)
    }
  }, [])

  // ── Permanently delete a task (file + DB record) ────────────────────────
  const handleDeletePermanent = useCallback(async (taskId: string) => {
    setDeletingHistoryId(taskId)
    try {
      await youtubeApi.deleteTaskPermanent(taskId)
      setTasks((prev) => prev.filter((t) => t.task_id !== taskId))
      setHistoryTasks((prev) => prev.filter((h) => h.task_id !== taskId))
    } catch {
      toast.error('Не удалось удалить задачу.')
    } finally {
      setDeletingHistoryId(null)
    }
  }, [])

  // ── Derived state ──
  const canDownload =
    mediaInfo !== null &&
    selectedIds.size > 0 &&
    !startingDownload

  // All tasks are shown; individual tasks can be dismissed via the dismiss button
  const visibleTasks = tasks

  const hasCompleted = tasks.some(
    (t) => t.status === 'ready' || t.status === 'error' || t.status === 'cancelled',
  )

  return (
    <div className={styles.page}>
      {/* ── Page Header ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageTitleRow}>
          <h1 className={styles.pageTitle}>
            <Youtube size={24} aria-hidden="true" />
            YouTube Downloader
          </h1>
          {/* Task 6: quota counter — only shown when data is available */}
          {quota !== null && (
            <span className={styles.quotaBadge} aria-label={quota.limit < 0 ? 'Безлимит загрузок' : `Осталось загрузок: ${Math.max(0, quota.limit - quota.used)} из ${quota.limit}`}>
              {quota.limit < 0 ? 'Безлимит загрузок' : `Осталось загрузок: ${Math.max(0, quota.limit - quota.used)}/${quota.limit}`}
            </span>
          )}
        </div>
        <p className={styles.pageSubtitle}>
          Скачивайте видео и плейлисты в форматах MP4, MP3 и WAV
        </p>
      </div>

      {/* ── URL Input ── */}
      <div
        className={`${styles.inputCard}${isDragOver ? ` ${styles.dragOver}` : ''}`}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className={styles.inputRow}>
          <div className={styles.inputWrap}>
            <Link className={styles.urlIcon} aria-hidden="true" />
            <input
              id="youtube-url"
              className={`${styles.urlInput} ${showUrlError ? styles.inputError : ''}`}
              type="url"
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={handleUrlChange}
              onBlur={() => setUrlTouched(true)}
              onKeyDown={handleUrlKeyDown}
              aria-label="YouTube URL"
              aria-invalid={showUrlError}
              aria-describedby={showUrlError ? 'url-error' : undefined}
              autoComplete="off"
              spellCheck={false}
            />
            {/* Task 3: paste from clipboard button */}
            <button
              type="button"
              className={styles.inputActionBtn}
              onClick={handlePasteFromClipboard}
              aria-label="Вставить из буфера обмена"
              title="Вставить из буфера обмена"
            >
              <ClipboardPaste size={15} aria-hidden="true" />
            </button>
            {/* Task 4: clear URL button — only visible when there is content */}
            {url.length > 0 && (
              <button
                type="button"
                className={`${styles.inputActionBtn} ${styles.inputClearBtn}`}
                onClick={handleClearUrl}
                aria-label="Очистить поле"
                title="Очистить"
              >
                <X size={15} aria-hidden="true" />
              </button>
            )}
          </div>
          <button
            type="button"
            className={styles.getInfoBtn}
            onClick={handleGetInfo}
            disabled={loadingInfo || !url.trim()}
            aria-busy={loadingInfo}
          >
            {loadingInfo ? (
              <>
                <span className={styles.spinner} aria-hidden="true" />
                Загрузка...
              </>
            ) : (
              <>
                Получить информацию
                {/* Task 8: keyboard shortcut hint */}
                <span className={styles.kbdHint} aria-hidden="true">Enter ↵</span>
              </>
            )}
          </button>
        </div>

        {showUrlError && (
          <div className={styles.validationError} id="url-error" role="alert">
            <AlertCircle size={12} aria-hidden="true" />
            Введите корректную ссылку на YouTube (youtube.com, m.youtube.com или youtu.be)
          </div>
        )}
      </div>

      {/* ── Loading info state ── */}
      {loadingInfo && (
        <div className={styles.loadingState} aria-live="polite" aria-label="Получение информации">
          <div className={styles.loadingSpinner} aria-hidden="true" />
          <div className={styles.loadingText}>Получение информации...</div>
        </div>
      )}

      {/* ── Results ── */}
      {mediaInfo && !loadingInfo && (
        <div className={styles.resultsSection}>
          <div className={styles.sectionTitle}>Результат</div>

          {mediaInfo.type === 'video' ? (
            <VideoCard
              video={mediaInfo.data}
              selectedFormat={format}
              selectedQuality={quality}
            />
          ) : (
            <PlaylistView
              playlist={mediaInfo.data}
              selectedIds={selectedIds}
              onToggle={handleToggle}
              onSelectAll={handleSelectAll}
              onDeselectAll={handleDeselectAll}
              selectedFormat={format}
              selectedQuality={quality}
            />
          )}

          {/* ── Large-playlist confirmation ── */}
          {pendingConfirmation && (
            <div className={styles.confirmationBox} role="alertdialog" aria-label="Подтверждение загрузки">
              <div className={styles.confirmationIcon} aria-hidden="true">
                <TriangleAlert size={16} />
              </div>
              <div className={styles.confirmationBody}>
                <p className={styles.confirmationMessage}>
                  Скачать{' '}
                  <strong>{pendingConfirmation.videoIds.length} видео</strong>{' '}
                  в формате{' '}
                  <strong>{pendingConfirmation.dlFormat.toUpperCase()}</strong>?{' '}
                  Примерный размер: <strong>{pendingConfirmation.estimatedSize}</strong>.{' '}
                  Это может занять значительное время.
                </p>
                <div className={styles.confirmationActions}>
                  <button
                    type="button"
                    className={styles.confirmBtn}
                    onClick={handleConfirmDownload}
                    autoFocus
                  >
                    Подтвердить
                  </button>
                  <button
                    type="button"
                    className={styles.cancelConfirmBtn}
                    onClick={handleCancelConfirmation}
                  >
                    Отмена
                  </button>
                </div>
              </div>
            </div>
          )}

          <DownloadOptions
            format={format}
            quality={quality}
            onFormatChange={setFormat}
            onQualityChange={setQuality}
            onDownload={handleDownload}
            disabled={!canDownload || pendingConfirmation !== null}
            loading={startingDownload}
            onForceDownload={cachedDownloads.has(`${format}_${quality}`) ? handleForceDownload : undefined}
            forceDownloadLoading={forceDownloadLoading}
          />
        </div>
      )}

      {/* ── Active downloads ── */}
      {visibleTasks.length > 0 && (
        <div className={styles.downloadsSection}>
          <div className={styles.downloadsHeader}>
            <Download size={14} aria-hidden="true" />
            Загрузки
            <span className={styles.downloadCount}>{visibleTasks.length}</span>
            {hasCompleted && (
              <button
                type="button"
                className={styles.clearCompletedBtn}
                onClick={handleClearCompleted}
                aria-label="Очистить завершённые загрузки"
              >
                Очистить завершённые
              </button>
            )}
          </div>
          <div className={styles.downloadsList} aria-live="polite">
            {visibleTasks.map((task) => (
              <DownloadProgress
                key={task.task_id}
                task={task}
                onCancel={handleCancel}
                onDismiss={handleDismiss}
                onRetry={handleRetry}
                onDelete={handleDeletePermanent}
                deletingId={deletingHistoryId}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Download history (dismissed tasks with files still on disk) ── */}
      {historyTasks.length > 0 && (
        <div className={styles.historySection}>
          <button
            type="button"
            className={styles.historyToggle}
            onClick={() => setShowHistory((v) => !v)}
            aria-expanded={showHistory}
            aria-controls="history-list"
          >
            <History size={13} aria-hidden="true" />
            История загрузок
            <span className={styles.downloadCount}>{historyTasks.length}</span>
            {showHistory
              ? <ChevronUp size={13} aria-hidden="true" />
              : <ChevronDown size={13} aria-hidden="true" />
            }
          </button>

          {showHistory && (
            <div
              id="history-list"
              className={styles.historyList}
              aria-live="polite"
            >
              {historyTasks.map((item) => {
                const isReady = item.status === 'ready'
                const isFetching = fetchingHistoryId === item.task_id
                const isRestoring = restoringId === item.task_id
                const isDeletingThis = deletingHistoryId === item.task_id
                const fileExists = item.file_exists === true
                // BUG-2: hide the download button when the server-side file TTL has elapsed
                const isExpired =
                  item.completed_at !== null &&
                  Date.now() - new Date(item.completed_at).getTime() > FILE_TTL_MS
                const dateStr = item.completed_at ?? item.created_at
                const formattedDate = dateStr
                  ? new Date(dateStr).toLocaleString('ru-RU', {
                      day: '2-digit',
                      month: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : null

                return (
                  <div key={item.task_id} className={styles.historyItem}>
                    <div className={styles.historyMeta}>
                      <span className={styles.historyTitle} title={item.title}>
                        {item.title}
                      </span>
                      <span className={styles.historyDetails}>
                        {item.format.toUpperCase()}
                        {item.file_size !== null && item.file_size > 0
                          ? ` · ${formatFileSize(item.file_size)}`
                          : ''}
                        {formattedDate ? ` · ${formattedDate}` : ''}
                        {' · '}
                        <span className={fileExists ? styles.fileExistsLabel : styles.fileGoneLabel}>
                          {fileExists ? 'На сервере' : 'Удалён'}
                        </span>
                      </span>
                    </div>
                    <div className={styles.historyActions}>
                      {isReady && !isExpired && fileExists && (
                        <button
                          type="button"
                          className={styles.historyBtnDownload}
                          onClick={() => handleHistoryDownload(item.task_id)}
                          disabled={isFetching}
                          aria-busy={isFetching}
                          aria-label="Скачать файл"
                        >
                          <FileDown size={13} aria-hidden="true" />
                          Скачать
                        </button>
                      )}
                      <button
                        type="button"
                        className={styles.historyBtnRestore}
                        onClick={() => handleRestore(item)}
                        disabled={isRestoring}
                        aria-busy={isRestoring}
                        aria-label="Восстановить в список загрузок"
                      >
                        <RotateCcw size={13} aria-hidden="true" />
                        Восстановить
                      </button>
                      <button
                        type="button"
                        className={styles.historyBtnDelete}
                        onClick={() => handleDeletePermanent(item.task_id)}
                        disabled={isDeletingThis}
                        aria-busy={isDeletingThis}
                        aria-label={fileExists ? 'Удалить файл с сервера' : 'Удалить из истории'}
                      >
                        {isDeletingThis ? (
                          <Loader size={13} aria-hidden="true" className={styles.iconSpin} />
                        ) : (
                          <Trash2 size={13} aria-hidden="true" />
                        )}
                        Удалить
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
