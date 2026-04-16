import { useState, useEffect, useRef } from 'react'
import { FileDown, X, AlertCircle, Loader, RefreshCw, Trash2, HardDrive, HardDriveDownload } from 'lucide-react'
import { toast } from 'react-toastify'
import { youtubeApi } from './youtubeApi'
import { formatFileSize, formatSpeed, formatEta, triggerBlobDownload } from './utils'
import type { DownloadTask, DownloadStatus } from './types'
import styles from './DownloadProgress.module.css'

// File is available for this many milliseconds after the task becomes ready
const FILE_TTL_MS = 6 * 60 * 60 * 1000 // 6 hours

interface DownloadProgressProps {
  task: DownloadTask
  // Parent handles the API call and polling cleanup; child simply delegates
  onCancel: (taskId: string) => void | Promise<void>
  onDismiss: (taskId: string) => void
  // Task 5: called when the user wants to retry a failed download
  onRetry: (task: DownloadTask) => void | Promise<void>
  // Called when user wants to permanently delete the task (file + DB record)
  onDelete?: (taskId: string) => void
  // Task id whose permanent deletion is in progress
  deletingId?: string | null
}

const STATUS_LABELS: Record<DownloadStatus, string> = {
  pending: 'Ожидание',
  downloading: 'Загрузка',
  converting: 'Конвертация',
  zipping: 'Архивация',
  ready: 'Готово',
  error: 'Ошибка',
  cancelled: 'Отменено',
}

const ACTIVE_STATUSES: DownloadStatus[] = ['pending', 'downloading', 'converting', 'zipping']

/** Format a millisecond duration into "Xч Yм" */
function formatCountdown(ms: number): string {
  if (ms <= 0) return '0м'
  const totalMinutes = Math.floor(ms / 60_000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours > 0) return `${hours}ч ${minutes}м`
  return `${minutes}м`
}

/**
 * Custom hook that returns the remaining TTL in ms for a ready task.
 * Re-evaluates every minute. Prefers completed_at (most accurate expiry anchor),
 * falls back to created_at, then to a client-side timestamp if neither is available.
 */
function useExpiryCountdown(
  status: DownloadStatus,
  createdAt: string | null,
  completedAt: string | null | undefined,
): number | null {
  // Client-side fallback: record when the task first became ready in this session
  const readyAtRef = useRef<number | null>(null)

  useEffect(() => {
    if (status === 'ready' && readyAtRef.current === null) {
      readyAtRef.current = Date.now()
    }
  }, [status])

  const [remaining, setRemaining] = useState<number | null>(null)

  useEffect(() => {
    if (status !== 'ready') {
      setRemaining(null)
      return
    }

    function calcRemaining() {
      // Prefer completed_at (most accurate), then created_at, then client-side
      const anchor = completedAt ?? createdAt
      const startMs = anchor
        ? (() => {
            // Treat timezone-naive strings as UTC (SQLite may omit timezone info)
            const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(anchor) ? anchor : anchor + 'Z'
            return new Date(normalized).getTime()
          })()
        : (readyAtRef.current ?? Date.now())
      const elapsed = Date.now() - startMs
      return Math.max(0, FILE_TTL_MS - elapsed)
    }

    setRemaining(calcRemaining())

    const id = setInterval(() => {
      setRemaining(calcRemaining())
    }, 60_000)

    return () => clearInterval(id)
  }, [status, createdAt, completedAt])

  return remaining
}

export default function DownloadProgress({
  task,
  onCancel,
  onDismiss,
  onRetry,
  onDelete,
  deletingId,
}: DownloadProgressProps) {
  const [fetching, setFetching] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const isActive = ACTIVE_STATUSES.includes(task.status)
  const isReady = task.status === 'ready'
  const isError = task.status === 'error'
  const isCancelled = task.status === 'cancelled'
  const isTerminal = isReady || isError || isCancelled
  const isDeleting = deletingId === task.task_id
  const fileExists = task.file_exists === true

  // Remaining file availability time; prefers completed_at for accuracy
  const expiryMs = useExpiryCountdown(task.status, task.created_at, task.completed_at)
  const expiryWarning = expiryMs !== null && expiryMs < 60 * 60 * 1000 // < 1 hour

  async function handleDownloadFile() {
    if (fetching) return
    setFetching(true)
    try {
      const { blob, filename } = await youtubeApi.downloadFile(task.task_id)
      triggerBlobDownload(blob, filename)
    } catch {
      toast.error('Не удалось получить файл. Попробуйте снова.')
    } finally {
      setFetching(false)
    }
  }

  // Delegates entirely to parent — parent owns the API call and polling cleanup
  function handleCancel() {
    onCancel(task.task_id)
  }

  // Task 5: delegate retry to parent
  async function handleRetry() {
    if (retrying) return
    setRetrying(true)
    try {
      await onRetry(task)
    } finally {
      setRetrying(false)
    }
  }

  const badgeClass = (() => {
    switch (task.status) {
      case 'downloading':
        return styles.badgeDownloading
      case 'converting':
      case 'zipping':
        return styles.badgeConverting
      case 'ready':
        return styles.badgeReady
      case 'error':
        return styles.badgeError
      case 'cancelled':
        return styles.badgeCancelled
      default:
        return styles.badgePending
    }
  })()

  const progressFillClass = [
    styles.progressFill,
    isReady ? styles.ready : '',
    isError ? styles.error : '',
    isCancelled ? styles.cancelled : '',
  ]
    .filter(Boolean)
    .join(' ')

  const cardClass = [
    styles.card,
    isReady ? styles.ready : '',
    isError ? styles.error : '',
    isCancelled ? styles.cancelled : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={cardClass} role="region" aria-label={`Загрузка: ${task.title}`}>
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <div className={styles.title} title={task.title}>
            {task.title}
          </div>
          <div className={styles.metaRow}>
            <span className={`${styles.badge} ${badgeClass}`}>
              {isActive && <span className={styles.spinnerInline} aria-hidden="true" />}
              {STATUS_LABELS[task.status]}
            </span>
            <span className={styles.fileSize}>
              {task.format.toUpperCase()}
              {task.file_size !== null &&
                task.file_size > 0 &&
                ` · ${formatFileSize(task.file_size)}`}
            </span>
            {/* Cache hit indicator — shown only when the backend served from cache */}
            {task.cached && (
              <span className={styles.cachedBadge} aria-label="Файл из кэша">
                из кэша
              </span>
            )}
            {/* Task 7: expiry countdown for ready tasks */}
            {isReady && expiryMs !== null && (
              <span
                className={`${styles.expiryCountdown} ${expiryWarning ? styles.expiryWarning : ''}`}
                aria-label={`Файл доступен ещё ${formatCountdown(expiryMs)}`}
              >
                Доступно ещё: {formatCountdown(expiryMs)}
              </span>
            )}
            {/* File existence indicator — shown for terminal tasks */}
            {isTerminal && (
              <span
                className={`${styles.fileIndicator} ${fileExists ? styles.fileExists : styles.fileGone}`}
                aria-label={fileExists ? 'Файл на сервере' : 'Файл удалён с сервера'}
                title={fileExists ? 'Файл на сервере' : 'Файл удалён с сервера'}
              >
                {fileExists
                  ? <HardDriveDownload size={11} aria-hidden="true" />
                  : <HardDrive size={11} aria-hidden="true" />
                }
                {fileExists ? 'На сервере' : 'Удалён'}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Progress bar */}
      {!isError && (
        <div className={styles.progressWrap}>
          <div
            className={styles.progressBar}
            role="progressbar"
            aria-valuenow={task.progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Прогресс загрузки"
          >
            <div
              className={progressFillClass}
              style={{ width: `${isReady ? 100 : task.progress}%` }}
            />
          </div>
          <span className={styles.progressText}>
            {isReady ? '100%' : `${Math.round(task.progress)}%`}
          </span>
          {/* Speed and ETA — only meaningful while actively downloading */}
          {task.status === 'downloading' && task.speed !== null && task.eta !== null && (
            <span className={styles.transferStats}>
              {formatSpeed(task.speed)} — {formatEta(task.eta)}
            </span>
          )}
        </div>
      )}

      {/* Error message */}
      {isError && task.error && (
        <div className={styles.errorMsg}>
          <AlertCircle size={12} aria-hidden="true" />
          {task.error}
        </div>
      )}

      {/* Actions */}
      <div className={styles.actions}>
        {isReady && (
          <button
            type="button"
            className={styles.btnDownload}
            onClick={handleDownloadFile}
            disabled={fetching || !fileExists}
            aria-busy={fetching}
          >
            {fetching ? (
              <Loader size={16} aria-hidden="true" className={styles.iconSpin} />
            ) : (
              <FileDown size={16} aria-hidden="true" />
            )}
            Скачать файл
          </button>
        )}

        {isActive && (
          <button
            type="button"
            className={styles.btnCancel}
            onClick={handleCancel}
          >
            <X size={14} aria-hidden="true" />
            Отмена
          </button>
        )}

        {/* Retry button for failed and cancelled tasks */}
        {(isError || isCancelled) && (
          <button
            type="button"
            className={styles.btnRetry}
            onClick={handleRetry}
            disabled={retrying}
            aria-busy={retrying}
          >
            {retrying ? (
              <Loader size={14} aria-hidden="true" className={styles.iconSpin} />
            ) : (
              <RefreshCw size={14} aria-hidden="true" />
            )}
            Повторить
          </button>
        )}

        {isTerminal && (
          <button
            type="button"
            className={styles.btnDismiss}
            onClick={() => onDismiss(task.task_id)}
            aria-label="Скрыть"
          >
            <X size={14} aria-hidden="true" />
            Скрыть
          </button>
        )}

        {/* Permanent delete — terminal tasks */}
        {isTerminal && onDelete && (
          <button
            type="button"
            className={styles.btnDelete}
            onClick={() => onDelete(task.task_id)}
            disabled={isDeleting}
            aria-busy={isDeleting}
            aria-label={fileExists ? 'Удалить файл с сервера' : 'Удалить из истории'}
          >
            {isDeleting ? (
              <Loader size={14} aria-hidden="true" className={styles.iconSpin} />
            ) : (
              <Trash2 size={14} aria-hidden="true" />
            )}
            Удалить
          </button>
        )}
      </div>
    </div>
  )
}
