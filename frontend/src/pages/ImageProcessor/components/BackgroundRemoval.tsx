import { useState, useEffect, useCallback } from 'react'
import { Download, RotateCcw, Loader2, Wand2 } from 'lucide-react'
import { toast } from 'react-toastify'

import { imageApi } from '../imageApi'
import type { ImageTaskListItem, ImageUploadResponse } from '../types'
import { ImageUploader } from './ImageUploader'
import { ImageCompare } from './ImageCompare'
import styles from './BackgroundRemoval.module.css'

type LocalPhase = 'idle' | 'preview' | 'error'

interface BackgroundRemovalProps {
  currentTask: ImageTaskListItem | null
  onProcessStart: (task: ImageTaskListItem) => void
  onReset: () => void
  onQuotaChange?: () => void
}

export default function BackgroundRemoval({
  currentTask,
  onProcessStart,
  onReset,
}: BackgroundRemovalProps) {
  const [localPhase, setLocalPhase] = useState<LocalPhase>('idle')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [resultPreviewUrl, setResultPreviewUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [originalFilename, setOriginalFilename] = useState('')

  // Статус из внешнего источника (список задач в родителе)
  const processing = currentTask?.status === 'processing' || currentTask?.status === 'uploading'
  const ready = currentTask?.status === 'ready'
  const errored = currentTask?.status === 'error'

  // Отображаемая фаза: если есть currentTask — управляет она, иначе локальная
  const phase: 'idle' | 'preview' | 'processing' | 'result' | 'error' = processing
    ? 'processing'
    : ready
      ? 'result'
      : errored
        ? 'error'
        : localPhase

  // Revoke blob URLs on unmount
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Когда задача становится ready — подтягиваем result-preview для ImageCompare
  useEffect(() => {
    if (ready && currentTask && !resultPreviewUrl) {
      imageApi.getResultPreview(currentTask.task_id)
        .then(setResultPreviewUrl)
        .catch(() => undefined)
    }
  }, [ready, currentTask, resultPreviewUrl])

  // Когда задача становится error — показываем сообщение
  useEffect(() => {
    if (errored && currentTask?.error) {
      setError(currentTask.error)
    }
  }, [errored, currentTask])

  const handleUploaded = useCallback(async (response: ImageUploadResponse) => {
    setTaskId(response.task_id)
    setOriginalFilename(response.original_filename)
    try {
      const url = await imageApi.getPreview(response.task_id)
      setPreviewUrl(url)
      setLocalPhase('preview')
    } catch {
      setError('Не удалось загрузить превью')
      setLocalPhase('error')
    }
  }, [])

  const handleRemoveBg = useCallback(async () => {
    if (!taskId) return
    try {
      const task = await imageApi.removeBg(taskId)
      // Передаём родителю — он добавит карточку и запустит polling
      onProcessStart({
        ...task,
        file_exists: false,
      })
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Не удалось запустить обработку'
      setError(message)
      setLocalPhase('error')
    }
  }, [taskId, onProcessStart])

  const handleDownload = useCallback(async () => {
    if (!currentTask) return
    try {
      const { blob } = await imageApi.downloadResult(currentTask.task_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const baseName = currentTask.original_filename.replace(/\.[^.]+$/, '')
      a.download = `${baseName}_no_bg.png`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Не удалось скачать результат.')
    }
  }, [currentTask])

  const handleReset = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
    setLocalPhase('idle')
    setTaskId(null)
    setPreviewUrl('')
    setResultPreviewUrl('')
    setError(null)
    setOriginalFilename('')
    onReset()
  }, [previewUrl, resultPreviewUrl, onReset])

  // Когда родитель сбрасывает currentTask извне (permanent-delete, dismiss из списка) —
  // синхронизируем локальное состояние
  useEffect(() => {
    if (currentTask === null && (localPhase === 'preview' || localPhase === 'error')) {
      // Уже отдыхаем в idle или ещё в работе — ничего не делаем
    }
  }, [currentTask, localPhase])

  // ── Render ──

  return (
    <div className={styles.container}>
      {phase === 'idle' && (
        <ImageUploader operation="remove_bg" onUploaded={handleUploaded} />
      )}

      {phase === 'preview' && (
        <div className={styles.previewSection}>
          <img src={previewUrl} alt="Превью" className={styles.previewImage} />
          <div className={styles.resultActions}>
            <button className={styles.primaryBtn} onClick={handleRemoveBg}>
              <Wand2 size={16} aria-hidden="true" />
              Удалить фон
            </button>
            <button className={styles.secondaryBtn} onClick={handleReset}>
              <RotateCcw size={16} aria-hidden="true" />
              Загрузить другое
            </button>
          </div>
        </div>
      )}

      {phase === 'processing' && (
        <div className={styles.processingSection}>
          <Loader2 size={32} className={styles.iconSpin} aria-hidden="true" />
          <p className={styles.processingText}>
            Обработка... {currentTask?.progress ?? 0}%
          </p>
          <div className={styles.progressBarWrap}>
            <div
              className={styles.progressBarFill}
              style={{ width: `${currentTask?.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {phase === 'result' && currentTask && (
        <div className={styles.resultSection}>
          <ImageCompare
            beforeSrc={previewUrl}
            afterSrc={resultPreviewUrl}
            transparencyGrid
          />
          <div className={styles.resultActions}>
            <button
              className={styles.successBtn}
              onClick={handleDownload}
              disabled={!currentTask.file_exists}
            >
              <Download size={16} aria-hidden="true" />
              Скачать PNG
            </button>
            <button className={styles.secondaryBtn} onClick={handleReset}>
              <RotateCcw size={16} aria-hidden="true" />
              Загрузить другое
            </button>
          </div>
        </div>
      )}

      {phase === 'error' && (
        <div className={styles.errorSection}>
          <p className={styles.errorMessage}>{error ?? currentTask?.error}</p>
          <button className={styles.secondaryBtn} onClick={handleReset}>
            <RotateCcw size={16} aria-hidden="true" />
            Попробовать снова
          </button>
        </div>
      )}

      {/* originalFilename используется где-то ещё? — держим в state для download-имени через currentTask */}
      {originalFilename && null}
    </div>
  )
}
