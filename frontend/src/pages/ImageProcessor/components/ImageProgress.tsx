import { Wand2, Droplets, Download, RotateCcw, Trash2, X } from 'lucide-react'
import type { ImageTaskListItem, ImageStatus } from '../types'
import Thumbnail from './Thumbnail'
import styles from './ImageProgress.module.css'

const STATUS_LABELS: Record<ImageStatus, string> = {
  pending: 'Ожидание',
  uploading: 'Загрузка',
  processing: 'Обработка',
  ready: 'Готово',
  error: 'Ошибка',
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return ''
  try {
    const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z'
    const d = new Date(normalized)
    return d.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

interface ImageProgressProps {
  task: ImageTaskListItem
  isHistory?: boolean
  onDismiss: (taskId: string) => void
  onRestore: (taskId: string) => void
  onDownload: (taskId: string) => void
  onDelete: (taskId: string) => void
  downloadingId?: string | null
  restoringId?: string | null
  deletingId?: string | null
}

export default function ImageProgress({
  task,
  isHistory = false,
  onDismiss,
  onRestore,
  onDownload,
  onDelete,
  downloadingId,
  restoringId,
  deletingId,
}: ImageProgressProps) {
  const isReady = task.status === 'ready'
  const isError = task.status === 'error'
  const isProcessing = task.status === 'processing' || task.status === 'uploading'
  const isTerminal = isReady || isError
  const canDownload = isReady && task.file_exists

  const OperationIcon = task.operation === 'remove_bg' ? Wand2 : Droplets

  const badgeClass = (() => {
    switch (task.status) {
      case 'ready':      return styles.badgeReady
      case 'error':      return styles.badgeError
      case 'processing': return styles.badgeProcessing
      case 'uploading':  return styles.badgeProcessing
      default:           return styles.badgePending
    }
  })()

  const cardClass = [
    styles.card,
    isHistory ? styles.history : '',
    isReady ? styles.ready : '',
    isError ? styles.error : '',
  ].filter(Boolean).join(' ')

  return (
    <div
      className={cardClass}
      role="region"
      aria-label={`Задача ${task.original_filename}`}
    >
      <Thumbnail
        taskId={task.task_id}
        status={task.status}
        fileExists={task.file_exists}
        operation={task.operation}
      />

      <div className={styles.info}>
        <div className={styles.filename} title={task.original_filename}>
          {task.original_filename}
        </div>
        <div className={styles.meta}>
          <OperationIcon size={14} className={styles.operationIcon} aria-hidden="true" />
          <span className={`${styles.badge} ${badgeClass}`}>
            {STATUS_LABELS[task.status]}
          </span>
          <span className={styles.timestamp}>
            {formatTimestamp(task.completed_at ?? task.created_at)}
          </span>
        </div>
        {isProcessing && (
          <div
            className={styles.progressWrap}
            role="progressbar"
            aria-valuenow={task.progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className={styles.progressFill} style={{ width: `${task.progress}%` }} />
          </div>
        )}
      </div>

      <div className={styles.actions}>
        {canDownload && (
          <button
            type="button"
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={() => onDownload(task.task_id)}
            disabled={downloadingId === task.task_id}
            aria-busy={downloadingId === task.task_id}
          >
            <Download size={13} aria-hidden="true" />
            Скачать
          </button>
        )}

        {isTerminal && !isHistory && (
          <button
            type="button"
            className={styles.btn}
            onClick={() => onDismiss(task.task_id)}
            aria-label="Скрыть задачу в историю"
          >
            <X size={13} aria-hidden="true" />
            Скрыть
          </button>
        )}

        {isTerminal && isHistory && (
          <button
            type="button"
            className={styles.btn}
            onClick={() => onRestore(task.task_id)}
            disabled={restoringId === task.task_id}
            aria-busy={restoringId === task.task_id}
            aria-label="Восстановить задачу"
          >
            <RotateCcw size={13} aria-hidden="true" />
            Восстановить
          </button>
        )}

        {isTerminal && (
          <button
            type="button"
            className={`${styles.btn} ${styles.btnDanger}`}
            onClick={() => onDelete(task.task_id)}
            disabled={deletingId === task.task_id}
            aria-busy={deletingId === task.task_id}
            aria-label="Удалить задачу навсегда"
          >
            <Trash2 size={13} aria-hidden="true" />
            Удалить
          </button>
        )}
      </div>
    </div>
  )
}
