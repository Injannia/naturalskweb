import { useState, useEffect, useCallback } from 'react'
import { Image as ImageIcon, Wand2, Droplets, History, ChevronDown, ChevronUp } from 'lucide-react'
import { toast } from 'react-toastify'

import { imageApi } from './imageApi'
import type { ImageTaskListItem, ImageQuota } from './types'
import BackgroundRemoval from './components/BackgroundRemoval'
import WatermarkRemoval from './components/WatermarkRemoval'
import TaskHistory from './components/TaskHistory'
import styles from './ImageProcessorPage.module.css'

export default function ImageProcessorPage() {
  const [activeTab, setActiveTab] = useState<'bg' | 'watermark'>('bg')
  const [historyTasks, setHistoryTasks] = useState<ImageTaskListItem[]>([])
  const [quota, setQuota] = useState<ImageQuota | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  // ── Fetch quota on mount ──
  useEffect(() => {
    imageApi.getQuota().then(setQuota).catch(() => undefined)
  }, [])

  // ── Fetch history on mount ──
  useEffect(() => {
    imageApi.getHistory().then(setHistoryTasks).catch(() => undefined)
  }, [])

  // ── Refresh quota after processing ──
  const refreshQuota = useCallback(() => {
    imageApi.getQuota().then(setQuota).catch(() => undefined)
  }, [])

  // ── History actions ──
  const handleRestore = useCallback(async (taskId: string) => {
    try {
      await imageApi.restoreTask(taskId)
      setHistoryTasks((prev) => prev.filter((t) => t.task_id !== taskId))
      toast.info('Задача восстановлена.')
    } catch {
      toast.error('Не удалось восстановить задачу.')
    }
  }, [])

  const handleHistoryDownload = useCallback(async (taskId: string, _filename: string) => {
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
    }
  }, [])

  const toggleHistory = useCallback(() => {
    setShowHistory((v) => !v)
  }, [])

  return (
    <div className={styles.page}>
      {/* ── Page header ── */}
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

      {/* ── Tabs ── */}
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

      {/* ── Content ── */}
      <div className={styles.content}>
        {activeTab === 'bg' ? (
          <BackgroundRemoval onQuotaChange={refreshQuota} />
        ) : (
          <WatermarkRemoval onQuotaChange={refreshQuota} />
        )}
      </div>

      {/* ── History ── */}
      {historyTasks.length > 0 && (
        <div className={styles.historySection}>
          <button
            className={styles.historyToggle}
            onClick={toggleHistory}
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
            <TaskHistory
              tasks={historyTasks}
              onRestore={handleRestore}
              onDownload={handleHistoryDownload}
            />
          )}
        </div>
      )}
    </div>
  )
}
