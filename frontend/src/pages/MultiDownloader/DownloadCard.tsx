import { Download, X, RotateCcw, Trash2, Film, Music } from 'lucide-react'
import { Button, Card } from '../../components/ui'
import { useAuthedMedia } from '../../hooks/useAuthedMedia'
import { multidlApi } from './multidlApi'
import type { DownloadStatus } from './types'
import styles from './MultiDownloader.module.css'

interface Props {
  task: DownloadStatus
  onCancel: (id: string) => void
  onRetry: (id: string) => void
  onDismiss: (id: string) => void
}

const ACTIVE = new Set(['pending', 'downloading', 'converting'])

export default function DownloadCard({ task, onCancel, onRetry, onDismiss }: Props) {
  const mediaUrl = task.status === 'ready' && task.file_exists ? `/multidl/file/${task.task_id}` : null
  const src = useAuthedMedia(mediaUrl)

  async function handleSave() {
    const { blob, filename } = await multidlApi.downloadFile(task.task_id)
    const a = document.createElement('a')
    const objectUrl = URL.createObjectURL(blob)
    a.href = objectUrl
    a.download = filename
    a.click()
    URL.revokeObjectURL(objectUrl)
  }

  return (
    <Card variant="glass" className={styles.card}>
      <div className={styles.cardHead}>
        {task.audio_only ? <Music size={18} /> : <Film size={18} />}
        <span className={styles.cardTitle}>{task.title || task.url}</span>
        {task.platform && <span className={styles.platformChip}>{task.platform}</span>}
      </div>

      {ACTIVE.has(task.status) && (
        <div className={styles.progressTrack}>
          <div className={styles.progressFill} style={{ width: `${task.progress}%` }} />
        </div>
      )}

      {task.status === 'ready' && (
        <div className={styles.preview}>
          {src ? (
            task.audio_only ? (
              <audio controls src={src} className={styles.player} />
            ) : (
              <video controls src={src} poster={task.thumbnail ?? undefined} className={styles.player} />
            )
          ) : (
            task.thumbnail && <img src={task.thumbnail} alt="" className={styles.posterFallback} />
          )}
        </div>
      )}

      {task.status === 'error' && <div className={styles.errorText}>{task.error}</div>}

      <div className={styles.cardActions}>
        {ACTIVE.has(task.status) && (
          <Button variant="ghost" size="sm" leftIcon={<X size={14} />} onClick={() => onCancel(task.task_id)}>
            Отмена
          </Button>
        )}
        {task.status === 'ready' && (
          <Button variant="primary" size="sm" leftIcon={<Download size={14} />} onClick={handleSave}>
            Скачать файл
          </Button>
        )}
        {(task.status === 'error' || task.status === 'cancelled') && (
          <Button variant="secondary" size="sm" leftIcon={<RotateCcw size={14} />} onClick={() => onRetry(task.task_id)}>
            Повторить
          </Button>
        )}
        {!ACTIVE.has(task.status) && (
          <Button variant="ghost" size="sm" leftIcon={<Trash2 size={14} />} onClick={() => onDismiss(task.task_id)}>
            Убрать
          </Button>
        )}
      </div>
    </Card>
  )
}
