import { useEffect, useRef, useState } from 'react'
import { toast } from 'react-toastify'
import axios from 'axios'
import { Download } from 'lucide-react'
import { Button, Card, Input } from '../../components/ui'
import { multidlApi } from './multidlApi'
import type { DownloadStatus } from './types'
import DownloadCard from './DownloadCard'
import styles from './MultiDownloader.module.css'

const ACTIVE = new Set(['pending', 'downloading', 'converting'])
const PLACEHOLDER = 'Ссылка с Pinterest, Twitter/X, TikTok или VK'

export default function MultiDownloaderPage() {
  const [url, setUrl] = useState('')
  const [audioOnly, setAudioOnly] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [tasks, setTasks] = useState<DownloadStatus[]>([])
  // Mirror the latest tasks into a ref so the single poll interval can read the
  // current active set without being torn down and rebuilt on every state change.
  const tasksRef = useRef<DownloadStatus[]>([])
  tasksRef.current = tasks

  useEffect(() => {
    multidlApi.getTasks().then(setTasks).catch(() => undefined)
  }, [])

  // One steady 1.5s interval, mounted once. Reads the live task list via the ref
  // and refreshes any active task. setTasks here uses a pure map updater (no side
  // effects inside the updater), so it is StrictMode-safe.
  useEffect(() => {
    const id = window.setInterval(() => {
      const active = tasksRef.current.filter((t) => ACTIVE.has(t.status))
      for (const t of active) {
        multidlApi
          .getStatus(t.task_id)
          .then((s) => setTasks((cur) => cur.map((p) => (p.task_id === s.task_id ? s : p))))
          .catch(() => undefined)
      }
    }, 1500)
    return () => window.clearInterval(id)
  }, [])

  async function handleSubmit() {
    if (!url.trim()) return
    setSubmitting(true)
    try {
      let title: string | null = null
      try {
        const info = await multidlApi.getInfo(url.trim())
        title = info.title
      } catch {
        title = null
      }
      const task = await multidlApi.startDownload(url.trim(), audioOnly, title)
      setTasks((prev) => [task, ...prev])
      setUrl('')
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 429) {
        toast.error('Достигнут дневной лимит загрузок')
      } else if (axios.isAxiosError(err) && err.response?.data?.detail) {
        toast.error(String(err.response.data.detail))
      } else {
        toast.error('Не удалось начать загрузку')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCancel(id: string) {
    await multidlApi.cancelDownload(id).catch(() => undefined)
    setTasks((prev) => prev.map((t) => (t.task_id === id ? { ...t, status: 'cancelled' } : t)))
  }

  async function handleRetry(id: string) {
    try {
      const task = await multidlApi.retryDownload(id)
      setTasks((prev) => [task, ...prev.filter((t) => t.task_id !== id)])
    } catch {
      toast.error('Не удалось повторить загрузку')
    }
  }

  async function handleDismiss(id: string) {
    await multidlApi.dismissTask(id).catch(() => undefined)
    setTasks((prev) => prev.filter((t) => t.task_id !== id))
  }

  return (
    <div className={styles.wrapper}>
      <h1 className={styles.heading}>Multi downloader</h1>
      <p className={styles.subheading}>
        Скачивание видео с Pinterest, Twitter/X, TikTok (без водяного знака) и VK
      </p>

      <Card variant="elevated" className={styles.inputCard}>
        <Input
          label="Ссылка на видео"
          placeholder={PLACEHOLDER}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <label className={styles.toggleRow}>
          <input type="checkbox" checked={audioOnly} onChange={(e) => setAudioOnly(e.target.checked)} />
          Только аудио (mp3)
        </label>
        <Button variant="primary" leftIcon={<Download size={16} />} loading={submitting} onClick={handleSubmit}>
          Скачать
        </Button>
      </Card>

      <div className={styles.tasks}>
        {tasks.map((t) => (
          <DownloadCard
            key={t.task_id}
            task={t}
            onCancel={handleCancel}
            onRetry={handleRetry}
            onDismiss={handleDismiss}
          />
        ))}
      </div>
    </div>
  )
}
