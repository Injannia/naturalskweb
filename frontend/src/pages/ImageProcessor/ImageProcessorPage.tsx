import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Image as ImageIcon,
  Wand2,
  Droplets,
  History,
  ChevronDown,
  ChevronUp,
  Clock,
} from 'lucide-react'
import { toast } from 'react-toastify'
import axios from 'axios'

import { imageApi } from './imageApi'
import type { ImageTaskListItem, ImageQuota } from './types'
import BackgroundRemoval from './components/BackgroundRemoval'
import WatermarkRemoval from './components/WatermarkRemoval'
import ImageProgress from './components/ImageProgress'
import styles from './ImageProcessorPage.module.css'

const POLL_INTERVAL = 2000
const TERMINAL_STATUSES = new Set<string>(['ready', 'error'])
const ACTIVE_STATUSES = new Set<string>(['pending', 'uploading', 'processing'])

type TabKey = 'bg' | 'watermark'

export default function ImageProcessorPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('bg')

  const [tasks, setTasks] = useState<ImageTaskListItem[]>([])
  const [historyTasks, setHistoryTasks] = useState<ImageTaskListItem[]>([])
  const [quota, setQuota] = useState<ImageQuota | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  const [currentTaskIds, setCurrentTaskIds] = useState<{ bg: string | null; watermark: string | null }>({
    bg: null,
    watermark: null,
  })

  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // Polling — паттерн из ConverterPage.tsx:140-262
  const pollRefs = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map())
  const isPausedRef = useRef(false)

  // Cleanup всех интервалов при unmount
  useEffect(() => {
    return () => {
      pollRefs.current.forEach((id) => clearInterval(id))
    }
  }, [])

  // Пауза polling-а когда вкладка браузера скрыта
  useEffect(() => {
    function handle() {
      isPausedRef.current = document.hidden
    }
    document.addEventListener('visibilitychange', handle)
    return () => document.removeEventListener('visibilitychange', handle)
  }, [])

  const refreshQuota = useCallback(() => {
    imageApi.getQuota().then(setQuota).catch(() => undefined)
  }, [])

  const startPolling = useCallback((taskId: string) => {
    if (pollRefs.current.has(taskId)) return
    let consecutiveErrors = 0

    const intervalId = setInterval(async () => {
      if (isPausedRef.current) return
      try {
        const status = await imageApi.getStatus(taskId)
        consecutiveErrors = 0

        setTasks((prev) =>
          prev.map((t) =>
            t.task_id === taskId
              ? { ...t, ...status, file_exists: status.status === 'ready' ? true : t.file_exists }
              : t,
          ),
        )

        if (TERMINAL_STATUSES.has(status.status)) {
          clearInterval(intervalId)
          pollRefs.current.delete(taskId)
          if (status.status === 'ready') {
            toast.success(`Обработка завершена: ${status.original_filename}`)
            refreshQuota()
          } else if (status.status === 'error') {
            toast.error(`Ошибка обработки: ${status.original_filename}`)
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
          toast.error('Потеряна связь с сервером. Обновите страницу для проверки статуса обработки.')
        }
      }
    }, POLL_INTERVAL)

    pollRefs.current.set(taskId, intervalId)
  }, [refreshQuota])

  // Начальная загрузка
  useEffect(() => {
    imageApi.getTasks()
      .then((items) => {
        setTasks(items)
        items.forEach((t) => {
          if (ACTIVE_STATUSES.has(t.status)) startPolling(t.task_id)
        })
      })
      .catch(() => undefined)
    imageApi.getHistory().then(setHistoryTasks).catch(() => undefined)
    refreshQuota()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Handlers ──

  const handleProcessStart = useCallback((task: ImageTaskListItem) => {
    setTasks((prev) => [task, ...prev])
    setCurrentTaskIds((prev) => ({ ...prev, [activeTab]: task.task_id }))
    startPolling(task.task_id)
  }, [activeTab, startPolling])

  const handleEditorReset = useCallback(() => {
    setCurrentTaskIds((prev) => ({ ...prev, [activeTab]: null }))
  }, [activeTab])

  const handleDismiss = useCallback((taskId: string) => {
    imageApi.dismissTask(taskId).catch(() => undefined)
    const interval = pollRefs.current.get(taskId)
    if (interval) {
      clearInterval(interval)
      pollRefs.current.delete(taskId)
    }
    setTasks((prev) => {
      const dismissed = prev.find((t) => t.task_id === taskId)
      if (dismissed) {
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            if (h.some((i) => i.task_id === taskId)) return h
            return [dismissed, ...h]
          })
        })
      }
      return prev.filter((t) => t.task_id !== taskId)
    })
    setCurrentTaskIds((prev) => {
      const next = { ...prev }
      if (next.bg === taskId) next.bg = null
      if (next.watermark === taskId) next.watermark = null
      return next
    })
  }, [])

  const handleDismissCompleted = useCallback(async () => {
    try {
      await imageApi.dismissCompleted()
    } catch {
      // игнорируем — чистим UI всё равно
    }
    setTasks((prev) => {
      const terminal = prev.filter((t) => TERMINAL_STATUSES.has(t.status))
      const remaining = prev.filter((t) => !TERMINAL_STATUSES.has(t.status))
      if (terminal.length > 0) {
        const remainingIds = new Set(remaining.map((t) => t.task_id))
        queueMicrotask(() => {
          setHistoryTasks((h) => {
            const existing = new Set(h.map((i) => i.task_id))
            const deduped = terminal.filter((t) => !existing.has(t.task_id))
            return [...deduped, ...h]
          })
          setCurrentTaskIds((cur) => ({
            bg: cur.bg && remainingIds.has(cur.bg) ? cur.bg : null,
            watermark: cur.watermark && remainingIds.has(cur.watermark) ? cur.watermark : null,
          }))
        })
      }
      return remaining
    })
  }, [])

  const handleRestore = useCallback(async (taskId: string) => {
    setRestoringId(taskId)
    try {
      await imageApi.restoreTask(taskId)
      const restored = historyTasks.find((h) => h.task_id === taskId)
      if (restored) {
        setTasks((prev) => [restored, ...prev])
        setHistoryTasks((prev) => prev.filter((h) => h.task_id !== taskId))
      }
      toast.info('Задача восстановлена.')
    } catch {
      toast.error('Не удалось восстановить задачу.')
    } finally {
      setRestoringId(null)
    }
  }, [historyTasks])

  const handleDownload = useCallback(async (taskId: string) => {
    setDownloadingId(taskId)
    try {
      const { blob, filename } = await imageApi.downloadResult(taskId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Не удалось скачать файл. Возможно, он уже удалён.')
    } finally {
      setDownloadingId(null)
    }
  }, [])

  const handlePermanentDelete = useCallback(async (taskId: string) => {
    setDeletingId(taskId)
    try {
      await imageApi.deleteTaskPermanent(taskId)
      const interval = pollRefs.current.get(taskId)
      if (interval) {
        clearInterval(interval)
        pollRefs.current.delete(taskId)
      }
      setTasks((prev) => prev.filter((t) => t.task_id !== taskId))
      setHistoryTasks((prev) => prev.filter((h) => h.task_id !== taskId))
      setCurrentTaskIds((prev) => {
        const next = { ...prev }
        if (next.bg === taskId) next.bg = null
        if (next.watermark === taskId) next.watermark = null
        return next
      })
    } catch {
      toast.error('Не удалось удалить задачу.')
    } finally {
      setDeletingId(null)
    }
  }, [])

  // Derived

  const currentBgTask = tasks.find((t) => t.task_id === currentTaskIds.bg) ?? null
  const currentWmTask = tasks.find((t) => t.task_id === currentTaskIds.watermark) ?? null
  const hasCompleted = tasks.some((t) => TERMINAL_STATUSES.has(t.status))

  // Render

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div className={styles.pageTitleRow}>
          <h1 className={styles.pageTitle}>
            <ImageIcon size={24} aria-hidden="true" />
            Image Processor
          </h1>
          {quota && (
            <span className={styles.quotaBadge}>
              {quota.used} / {quota.limit} сегодня
            </span>
          )}
        </div>
      </div>

      <div className={styles.tabs}>
        <button
          className={activeTab === 'bg' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('bg')}
        >
          <Wand2 size={16} aria-hidden="true" />
          Удаление фона
        </button>
        <button
          className={activeTab === 'watermark' ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab('watermark')}
        >
          <Droplets size={16} aria-hidden="true" />
          Удаление водяных знаков
        </button>
      </div>

      <div className={styles.content}>
        {activeTab === 'bg' ? (
          <BackgroundRemoval
            currentTask={currentBgTask}
            onProcessStart={handleProcessStart}
            onReset={handleEditorReset}
            onQuotaChange={refreshQuota}
          />
        ) : (
          <WatermarkRemoval
            currentTask={currentWmTask}
            onProcessStart={handleProcessStart}
            onReset={handleEditorReset}
            onQuotaChange={refreshQuota}
          />
        )}
      </div>

      {tasks.length > 0 && (
        <div className={styles.tasksSection}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>
              <Clock size={14} aria-hidden="true" />
              Активные задачи
              <span className={styles.countBadge}>{tasks.length}</span>
            </span>
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
              <ImageProgress
                key={task.task_id}
                task={task}
                onDismiss={handleDismiss}
                onRestore={handleRestore}
                onDownload={handleDownload}
                onDelete={handlePermanentDelete}
                downloadingId={downloadingId}
                restoringId={restoringId}
                deletingId={deletingId}
              />
            ))}
          </div>
        </div>
      )}

      {historyTasks.length > 0 && (
        <div className={styles.historySection}>
          <button
            type="button"
            className={styles.historyToggle}
            onClick={() => setShowHistory((v) => !v)}
            aria-expanded={showHistory}
          >
            <History size={13} aria-hidden="true" />
            История обработки
            <span className={styles.countBadge}>{historyTasks.length}</span>
            {showHistory
              ? <ChevronUp size={13} aria-hidden="true" />
              : <ChevronDown size={13} aria-hidden="true" />
            }
          </button>

          {showHistory && (
            <div className={styles.historyList} aria-live="polite">
              {historyTasks.map((task) => (
                <ImageProgress
                  key={task.task_id}
                  task={task}
                  isHistory
                  onDismiss={handleDismiss}
                  onRestore={handleRestore}
                  onDownload={handleDownload}
                  onDelete={handlePermanentDelete}
                  downloadingId={downloadingId}
                  restoringId={restoringId}
                  deletingId={deletingId}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
