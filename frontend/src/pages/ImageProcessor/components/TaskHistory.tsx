import { Wand2, Droplets, Download, RotateCcw } from 'lucide-react'
import type { ImageTaskListItem } from '../types'
import styles from './TaskHistory.module.css'

interface TaskHistoryProps {
  tasks: ImageTaskListItem[]
  onRestore: (taskId: string) => void
  onDownload: (taskId: string, filename: string) => void
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
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

function getStatusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case 'ready':
      return { label: 'Готово', className: styles.statusReady }
    case 'error':
      return { label: 'Ошибка', className: styles.statusError }
    default:
      return { label: status, className: styles.statusOther }
  }
}

export default function TaskHistory({ tasks, onRestore, onDownload }: TaskHistoryProps) {
  if (tasks.length === 0) {
    return (
      <div className={styles.container}>
        <p className={styles.empty}>История пуста</p>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <div className={styles.list}>
        {tasks.map((task) => {
          const badge = getStatusBadge(task.status)
          const OperationIcon = task.operation === 'remove_bg' ? Wand2 : Droplets

          return (
            <div key={task.task_id} className={styles.card}>
              <OperationIcon size={18} className={styles.operationIcon} aria-hidden="true" />

              <div className={styles.info}>
                <div className={styles.filename} title={task.original_filename}>
                  {task.original_filename}
                </div>
                <div className={styles.meta}>
                  <span className={`${styles.statusBadge} ${badge.className}`}>
                    {badge.label}
                  </span>
                  <span className={styles.timestamp}>
                    {formatTimestamp(task.completed_at ?? task.created_at)}
                  </span>
                </div>
              </div>

              <div className={styles.actions}>
                <button
                  className={styles.actionBtn}
                  onClick={() => onRestore(task.task_id)}
                  title="Восстановить"
                >
                  <RotateCcw size={13} />
                  Восстановить
                </button>
                {task.file_exists && (
                  <button
                    className={`${styles.actionBtn} ${styles.downloadBtn}`}
                    onClick={() => onDownload(task.task_id, task.original_filename)}
                    title="Скачать"
                  >
                    <Download size={13} />
                    Скачать
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
