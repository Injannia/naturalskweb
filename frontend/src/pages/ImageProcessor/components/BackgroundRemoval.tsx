import { useState, useEffect, useRef, useCallback } from 'react'
import { Download, RotateCcw, Loader2, Wand2 } from 'lucide-react'
import { toast } from 'react-toastify'

import { imageApi } from '../imageApi'
import type { BgPhase, ImageUploadResponse } from '../types'
import { ImageUploader } from './ImageUploader'
import { ImageCompare } from './ImageCompare'
import styles from './BackgroundRemoval.module.css'

interface BackgroundRemovalProps {
  onQuotaChange?: () => void
}

export default function BackgroundRemoval({ onQuotaChange }: BackgroundRemovalProps) {
  const [phase, setPhase] = useState<BgPhase>('idle')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [resultPreviewUrl, setResultPreviewUrl] = useState('')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [originalFilename, setOriginalFilename] = useState('')

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollCountRef = useRef(0)
  const MAX_POLL_COUNT = 150 // 5 minutes at 2s interval

  // ── Cleanup polling and revoke blob URLs on unmount ──
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Handlers ──

  const handleUploaded = useCallback(async (response: ImageUploadResponse) => {
    setTaskId(response.task_id)
    setOriginalFilename(response.original_filename)
    try {
      const url = await imageApi.getPreview(response.task_id)
      setPreviewUrl(url)
      setPhase('preview')
    } catch {
      setError('Не удалось загрузить превью')
      setPhase('error')
    }
  }, [])

  const handleRemoveBg = useCallback(async () => {
    if (!taskId) return
    setPhase('processing')
    setProgress(0)

    try {
      await imageApi.removeBg(taskId)

      // Start polling
      pollCountRef.current = 0
      pollRef.current = setInterval(async () => {
        pollCountRef.current += 1
        if (pollCountRef.current > MAX_POLL_COUNT) {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = null
          setError('Обработка заняла слишком много времени')
          setPhase('error')
          return
        }
        try {
          const status = await imageApi.getStatus(taskId)
          setProgress(status.progress)

          if (status.status === 'ready') {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            try {
              const resultUrl = await imageApi.getResultPreview(taskId)
              setResultPreviewUrl(resultUrl)
            } catch { /* preview load failed, proceed anyway */ }
            setPhase('result')
            onQuotaChange?.()
          } else if (status.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setError(status.error ?? 'Неизвестная ошибка')
            setPhase('error')
          }
        } catch {
          // Transient network error — keep polling
        }
      }, 2000)
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Не удалось запустить обработку'
      setError(message)
      setPhase('error')
    }
  }, [taskId, onQuotaChange])

  const handleDownload = useCallback(async () => {
    if (!taskId) return
    try {
      const { blob } = await imageApi.downloadResult(taskId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const baseName = originalFilename.replace(/\.[^.]+$/, '')
      a.download = `${baseName}_no_bg.png`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Не удалось скачать результат.')
    }
  }, [taskId, originalFilename])

  const handleReset = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
    setPhase('idle')
    setTaskId(null)
    setPreviewUrl('')
    setResultPreviewUrl('')
    setProgress(0)
    setError(null)
    setOriginalFilename('')
  }, [previewUrl, resultPreviewUrl])

  // ── Render by phase ──

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
          <p className={styles.processingText}>Обработка... {progress}%</p>
          <div className={styles.progressBarWrap}>
            <div
              className={styles.progressBarFill}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {phase === 'result' && (
        <div className={styles.resultSection}>
          <ImageCompare beforeSrc={previewUrl} afterSrc={resultPreviewUrl} />
          <div className={styles.resultActions}>
            <button className={styles.successBtn} onClick={handleDownload}>
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
          <p className={styles.errorMessage}>{error}</p>
          <button className={styles.secondaryBtn} onClick={handleReset}>
            <RotateCcw size={16} aria-hidden="true" />
            Попробовать снова
          </button>
        </div>
      )}
    </div>
  )
}
