import { useState, useEffect, useRef } from 'react'
import {
  Download,
  X,
  AlertCircle,
  Loader,
  RotateCcw,
  Film,
  Music,
  ImageIcon,
  FileText,
  Clock,
  Trash2,
  HardDrive,
  HardDriveDownload,
} from 'lucide-react'
import type { ConvertTask, HistoryTask, ConvertStatus, ConvertCategory } from './types'
import { formatFileSize, FILE_TTL_MS, CATEGORY_LABELS } from './utils'
import styles from './ConvertProgress.module.css'

// ── Status labels in Russian ──────────────────────────────────────────────────

const STATUS_LABELS: Record<ConvertStatus, string> = {
  pending:    'Ожидание',
  uploading:  'Загрузка',
  converting: 'Конвертация',
  ready:      'Готово',
  error:      'Ошибка',
  cancelled:  'Отменено',
}

// Statuses where the task is still in progress (progress bar visible, cancel available)
const ACTIVE_STATUSES: ConvertStatus[] = ['pending', 'uploading', 'converting']

// ── Expiry countdown ──────────────────────────────────────────────────────────

/** Format a millisecond duration into a short Russian "Xч Yм" string */
function formatCountdown(ms: number): string {
  if (ms <= 0) return '0м'
  const totalMinutes = Math.floor(ms / 60_000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours > 0) return `${hours}ч ${minutes}м`
  return `${minutes}м`
}

// ── Category icon mapping ─────────────────────────────────────────────────────

function CategoryIcon({ category }: { category: ConvertCategory }) {
  const props = { size: 16, 'aria-hidden': true } as const
  switch (category) {
    case 'video':    return <Film {...props} />
    case 'audio':    return <Music {...props} />
    case 'image':    return <ImageIcon {...props} />
    case 'document': return <FileText {...props} />
  }
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface ConvertProgressProps {
  task: ConvertTask | HistoryTask
  /** When true, renders in compact history mode (no dismiss, show restore instead) */
  isHistory?: boolean
  onDismiss:  (taskId: string) => void
  onCancel:   (taskId: string) => void
  onDownload: (taskId: string) => void
  /** Pass the task id being restored to show a spinner on the Restore button */
  onRestore?: (taskId: string) => void
  /** Called when user wants to permanently delete the task (file + DB record) */
  onDelete?: (taskId: string) => void
  /** Task id whose file download is in progress — shows spinner on Download button */
  downloadingId: string | null
  /** Task id whose restore is in progress — shows spinner on Restore button */
  restoringId: string | null
  /** Task id whose permanent deletion is in progress */
  deletingId?: string | null
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ConvertProgress({
  task,
  isHistory = false,
  onDismiss,
  onCancel,
  onDownload,
  onRestore,
  onDelete,
  downloadingId,
  restoringId,
  deletingId,
}: ConvertProgressProps) {
  // ── Derived state booleans ─────────────────────────────────────────────────

  const isActive    = ACTIVE_STATUSES.includes(task.status)
  const isReady     = task.status === 'ready'
  const isError     = task.status === 'error'
  const isCancelled = task.status === 'cancelled'
  const isTerminal  = isReady || isError || isCancelled

  const isFetching  = downloadingId === task.task_id
  const isRestoring = restoringId   === task.task_id
  const isDeleting  = deletingId   === task.task_id
  const fileExists  = 'file_exists' in task ? task.file_exists === true : false

  // ── Expiry countdown (inline — not extracted to a separate hook file) ───────

  // Client-side fallback: record the moment this task first became ready in this
  // browser session, so we can compute an expiry even without server timestamps.
  const readyAtRef = useRef<number | null>(null)

  useEffect(() => {
    if (isReady && readyAtRef.current === null) {
      readyAtRef.current = Date.now()
    }
  }, [isReady])

  const [expiryMs, setExpiryMs] = useState<number | null>(null)

  useEffect(() => {
    if (!isReady) {
      setExpiryMs(null)
      return
    }

    function calcRemaining(): number {
      // Prefer completed_at (most accurate anchor), then created_at, then client-side
      const anchor = task.completed_at ?? task.created_at
      const startMs = anchor
        ? (() => {
            // Treat timezone-naive SQLite strings as UTC
            const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(anchor) ? anchor : anchor + 'Z'
            return new Date(normalized).getTime()
          })()
        : (readyAtRef.current ?? Date.now())
      return Math.max(0, FILE_TTL_MS - (Date.now() - startMs))
    }

    setExpiryMs(calcRemaining())

    // Re-calculate once per minute — fine-grained enough for a "Xч Yм" display
    const id = setInterval(() => setExpiryMs(calcRemaining()), 60_000)
    return () => clearInterval(id)
  }, [isReady, task.created_at, task.completed_at])

  const expiryWarning = expiryMs !== null && expiryMs < 60 * 60 * 1000 // < 1 hour
  const isExpired     = expiryMs !== null && expiryMs <= 0

  // ── Progress value (HistoryTask has no progress field) ──────────────────────

  const progress = 'progress' in task ? task.progress : 0

  // ── CSS class composition ──────────────────────────────────────────────────

  const cardClass = [
    styles.card,
    isReady     ? styles.ready     : '',
    isError     ? styles.error     : '',
    isCancelled ? styles.cancelled : '',
    isHistory   ? styles.history   : '',
  ]
    .filter(Boolean)
    .join(' ')

  const badgeClass = (() => {
    switch (task.status) {
      case 'uploading':   return styles.badgeUploading
      case 'converting':  return styles.badgeConverting
      case 'ready':       return styles.badgeReady
      case 'error':       return styles.badgeError
      case 'cancelled':   return styles.badgeCancelled
      default:            return styles.badgePending   // pending
    }
  })()

  const progressFillClass = [
    styles.progressFill,
    isReady     ? styles.ready     : '',
    isError     ? styles.error     : '',
    isCancelled ? styles.cancelled : '',
  ]
    .filter(Boolean)
    .join(' ')

  // Aria label for the card region
  const cardLabel = `${task.original_filename} → ${(task.target_format || '').toUpperCase()}`

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className={cardClass} role="region" aria-label={cardLabel}>

      {/* Header: icon + filename → format, category · size */}
      <div className={styles.header}>
        <span className={styles.categoryIcon}>
          <CategoryIcon category={task.category} />
        </span>

        <div className={styles.titleRow}>
          <div className={styles.title} title={cardLabel}>
            <span className={styles.originalName}>{task.original_filename}</span>
            <span className={styles.arrow} aria-hidden="true"> → </span>
            <span className={styles.targetFormat}>{(task.target_format || '').toUpperCase()}</span>
          </div>

          <div className={styles.metaRow}>
            {/* Status badge */}
            <span className={`${styles.badge} ${badgeClass}`} aria-label={`Статус: ${STATUS_LABELS[task.status]}`}>
              {isActive && <span className={styles.spinnerInline} aria-hidden="true" />}
              {STATUS_LABELS[task.status]}
            </span>

            {/* Category · file size */}
            <span className={styles.fileMeta}>
              {CATEGORY_LABELS[task.category]}
              {task.file_size !== null && task.file_size > 0 && ` · ${formatFileSize(task.file_size)}`}
            </span>

            {/* Expiry countdown — only when ready and not expired */}
            {isReady && expiryMs !== null && !isExpired && (
              <span
                className={`${styles.expiryCountdown} ${expiryWarning ? styles.expiryWarning : ''}`}
                aria-label={`Осталось ${formatCountdown(expiryMs)}`}
              >
                <Clock size={11} aria-hidden="true" />
                Осталось {formatCountdown(expiryMs)}
              </span>
            )}

            {/* Expired notice — replaces countdown */}
            {isReady && isExpired && (
              <span className={styles.expiryExpired} aria-live="polite">
                Файл удалён
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

      {/* Progress bar — visible only during active/ready states */}
      {!isError && !isCancelled && (
        <div className={styles.progressWrap}>
          <div
            className={styles.progressBar}
            role="progressbar"
            aria-valuenow={isReady ? 100 : progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Прогресс конвертации"
          >
            <div
              className={progressFillClass}
              style={{ width: `${isReady ? 100 : progress}%` }}
            />
          </div>
          <span className={styles.progressText}>
            {isReady ? '100%' : `${Math.round(progress)}%`}
          </span>
        </div>
      )}

      {/* Error message */}
      {'error' in task && isError && task.error && (
        <div className={styles.errorMsg}>
          <AlertCircle size={12} aria-hidden="true" />
          {task.error}
        </div>
      )}

      {/* Action buttons */}
      <div className={styles.actions}>

        {/* Download — only when ready; disabled when expired or file gone */}
        {isReady && !isHistory && (
          <button
            type="button"
            className={styles.btnDownload}
            onClick={() => onDownload(task.task_id)}
            disabled={isFetching || isExpired || !fileExists}
            aria-busy={isFetching}
            aria-label="Скачать файл"
          >
            {isFetching ? (
              <Loader size={16} aria-hidden="true" className={styles.iconSpin} />
            ) : (
              <Download size={16} aria-hidden="true" />
            )}
            Скачать
          </button>
        )}

        {/* Cancel — only while task is active */}
        {isActive && !isHistory && (
          <button
            type="button"
            className={styles.btnCancel}
            onClick={() => onCancel(task.task_id)}
            aria-label="Отменить конвертацию"
          >
            <X size={14} aria-hidden="true" />
            Отменить
          </button>
        )}

        {/* Dismiss (✕) — terminal states, non-history only */}
        {isTerminal && !isHistory && (
          <button
            type="button"
            className={styles.btnDismiss}
            onClick={() => onDismiss(task.task_id)}
            aria-label="Скрыть задачу"
          >
            <X size={14} aria-hidden="true" />
            Скрыть
          </button>
        )}

        {/* Restore — history mode only */}
        {isHistory && onRestore && (
          <button
            type="button"
            className={styles.btnRestore}
            onClick={() => onRestore(task.task_id)}
            disabled={isRestoring}
            aria-busy={isRestoring}
            aria-label="Восстановить задачу"
          >
            {isRestoring ? (
              <Loader size={14} aria-hidden="true" className={styles.iconSpin} />
            ) : (
              <RotateCcw size={14} aria-hidden="true" />
            )}
            Восстановить
          </button>
        )}

        {/* Permanent delete — terminal tasks (active + history) */}
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
