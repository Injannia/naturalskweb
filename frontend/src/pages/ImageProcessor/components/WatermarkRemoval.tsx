import { useState, useEffect, useRef, useCallback } from 'react'
import { Download, RotateCcw, Loader2, Paintbrush, Square, Eraser, Undo2, Trash2, Play } from 'lucide-react'
import { toast } from 'react-toastify'

import { imageApi } from '../imageApi'
import type { WmPhase, ImageUploadResponse, MaskShape, MaskTool, InpaintMethod } from '../types'
import { ImageUploader } from './ImageUploader'
import { ImageCompare } from './ImageCompare'
import MaskCanvas from './MaskCanvas'
import styles from './WatermarkRemoval.module.css'

interface WatermarkRemovalProps {
  onQuotaChange?: () => void
}

export default function WatermarkRemoval({ onQuotaChange }: WatermarkRemovalProps) {
  const [phase, setPhase] = useState<WmPhase>('idle')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [resultPreviewUrl, setResultPreviewUrl] = useState('')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [originalFilename, setOriginalFilename] = useState('')
  const [originalExt, setOriginalExt] = useState('')

  // Canvas state
  const [shapes, setShapes] = useState<MaskShape[]>([])
  const [tool, setTool] = useState<MaskTool>('brush')
  const [brushSize, setBrushSize] = useState(15)
  const [inpaintMethod, setInpaintMethod] = useState<InpaintMethod>('telea')
  const [imageNaturalSize, setImageNaturalSize] = useState({ width: 0, height: 0 })

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

  // ── Load image natural dimensions when preview URL changes ──
  useEffect(() => {
    if (!previewUrl) return
    const img = new Image()
    img.onload = () => {
      setImageNaturalSize({ width: img.naturalWidth, height: img.naturalHeight })
    }
    img.src = previewUrl
  }, [previewUrl])

  // ── Handlers ──

  const handleUploaded = useCallback(async (response: ImageUploadResponse) => {
    setTaskId(response.task_id)
    setOriginalFilename(response.original_filename)
    setOriginalExt(response.original_ext)
    try {
      const url = await imageApi.getPreview(response.task_id)
      setPreviewUrl(url)
      setShapes([])
      setPhase('editing')
    } catch {
      setError('Не удалось загрузить превью')
      setPhase('error')
    }
  }, [])

  const handleProcess = useCallback(async () => {
    if (!taskId || shapes.length === 0) return
    setPhase('processing')
    setProgress(0)

    try {
      await imageApi.removeWatermark(taskId, shapes, inpaintMethod, imageNaturalSize.width)

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
  }, [taskId, shapes, inpaintMethod, imageNaturalSize.width, onQuotaChange])

  const handleDownload = useCallback(async () => {
    if (!taskId) return
    try {
      const { blob } = await imageApi.downloadResult(taskId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const baseName = originalFilename.replace(/\.[^.]+$/, '')
      a.download = `${baseName}_cleaned.${originalExt || 'png'}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Не удалось скачать результат.')
    }
  }, [taskId, originalFilename, originalExt])

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
    setOriginalExt('')
    setShapes([])
    setImageNaturalSize({ width: 0, height: 0 })
  }, [previewUrl, resultPreviewUrl])

  const handleUndo = useCallback(() => {
    setShapes((prev) => prev.slice(0, -1))
  }, [])

  const handleClearShapes = useCallback(() => {
    setShapes([])
  }, [])

  // ── Render by phase ──

  return (
    <div className={styles.container}>
      {phase === 'idle' && (
        <ImageUploader operation="remove_watermark" onUploaded={handleUploaded} />
      )}

      {phase === 'editing' && (
        <div className={styles.editingSection}>
          {/* Toolbar */}
          <div className={styles.toolbar}>
            <div className={styles.toolGroup}>
              <button
                className={`${styles.toolBtn} ${tool === 'brush' ? styles.toolBtnActive : ''}`}
                onClick={() => setTool('brush')}
                title="Кисть"
              >
                <Paintbrush size={16} />
              </button>
              <button
                className={`${styles.toolBtn} ${tool === 'rect' ? styles.toolBtnActive : ''}`}
                onClick={() => setTool('rect')}
                title="Прямоугольник"
              >
                <Square size={16} />
              </button>
              <button
                className={`${styles.toolBtn} ${tool === 'eraser' ? styles.toolBtnActive : ''}`}
                onClick={() => setTool('eraser')}
                title="Ластик"
              >
                <Eraser size={16} />
              </button>
            </div>

            {(tool === 'brush' || tool === 'eraser') && (
              <>
                <div className={styles.separator} />
                <div className={styles.sliderGroup}>
                  <span className={styles.sliderLabel}>Размер:</span>
                  <input
                    type="range"
                    min={5}
                    max={50}
                    value={brushSize}
                    onChange={(e) => setBrushSize(Number(e.target.value))}
                    className={styles.slider}
                  />
                  <span className={styles.sliderValue}>{brushSize}</span>
                </div>
              </>
            )}

            <div className={styles.separator} />

            <select
              className={styles.methodSelect}
              value={inpaintMethod}
              onChange={(e) => setInpaintMethod(e.target.value as InpaintMethod)}
              title="Метод инпейнтинга"
            >
              <option value="telea">TELEA</option>
              <option value="ns">Navier-Stokes</option>
            </select>

            <div className={styles.actionGroup}>
              <button
                className={styles.smallBtn}
                onClick={handleUndo}
                disabled={shapes.length === 0}
                title="Отменить последнее действие"
              >
                <Undo2 size={14} />
                Отменить
              </button>
              <button
                className={styles.smallBtn}
                onClick={handleClearShapes}
                disabled={shapes.length === 0}
                title="Очистить все маски"
              >
                <Trash2 size={14} />
                Очистить
              </button>
            </div>
          </div>

          {/* Canvas */}
          <div className={styles.canvasWrap}>
            <MaskCanvas
              imageUrl={previewUrl}
              naturalWidth={imageNaturalSize.width}
              naturalHeight={imageNaturalSize.height}
              tool={tool}
              brushSize={brushSize}
              shapes={shapes}
              onShapesChange={setShapes}
            />
          </div>

          {/* Process button */}
          <div className={styles.resultActions}>
            <button
              className={styles.primaryBtn}
              onClick={handleProcess}
              disabled={shapes.length === 0}
            >
              <Play size={16} aria-hidden="true" />
              Обработать
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
              Скачать результат
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
