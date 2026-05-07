import { useState, useEffect, useRef, useCallback } from 'react'
import { Download, RotateCcw, Loader2, Paintbrush, Square, Eraser, Undo2, Trash2, Play } from 'lucide-react'
import { toast } from 'react-toastify'

import { imageApi } from '../imageApi'
import type {
  ImageTaskListItem,
  ImageUploadResponse,
  MaskShape,
  MaskTool,
  InpaintMethod,
} from '../types'
import { ImageUploader } from './ImageUploader'
import { ImageCompare } from './ImageCompare'
import MaskCanvas from './MaskCanvas'
import styles from './WatermarkRemoval.module.css'

type LocalPhase = 'idle' | 'editing' | 'error'

interface WatermarkRemovalProps {
  currentTask: ImageTaskListItem | null
  onProcessStart: (task: ImageTaskListItem) => void
  onReset: () => void
  onQuotaChange?: () => void
}

export default function WatermarkRemoval({
  currentTask,
  onProcessStart,
  onReset,
}: WatermarkRemovalProps) {
  const [localPhase, setLocalPhase] = useState<LocalPhase>('idle')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [resultPreviewUrl, setResultPreviewUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [originalExt, setOriginalExt] = useState('')

  // Canvas state — остаётся локальным
  const [shapes, setShapes] = useState<MaskShape[]>([])
  const [tool, setTool] = useState<MaskTool>('brush')
  const [brushSize, setBrushSize] = useState(30)
  const [inpaintMethod, setInpaintMethod] = useState<InpaintMethod>('lama')
  const [imageNaturalSize, setImageNaturalSize] = useState({ width: 0, height: 0 })

  // Статус из внешнего источника (список задач в родителе)
  const processing = currentTask?.status === 'processing' || currentTask?.status === 'uploading'
  const ready = currentTask?.status === 'ready'
  const errored = currentTask?.status === 'error'

  // Отображаемая фаза
  const phase: 'idle' | 'editing' | 'processing' | 'result' | 'error' = processing
    ? 'processing'
    : ready
      ? 'result'
      : errored
        ? 'error'
        : localPhase

  // ── Cleanup blob URLs on unmount ──
  useEffect(() => {
    return () => {
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

  // ── Когда задача становится ready — подтягиваем result-preview для ImageCompare ──
  useEffect(() => {
    if (ready && currentTask && !resultPreviewUrl) {
      imageApi.getResultPreview(currentTask.task_id)
        .then(setResultPreviewUrl)
        .catch(() => undefined)
    }
  }, [ready, currentTask, resultPreviewUrl])

  // ── После F5 локальный previewUrl пуст, но задача уже ready — подтягиваем оригинал ──
  useEffect(() => {
    if (ready && currentTask && !previewUrl) {
      imageApi.getPreview(currentTask.task_id)
        .then(setPreviewUrl)
        .catch(() => undefined)
    }
  }, [ready, currentTask, previewUrl])

  // ── Когда задача становится error — показываем сообщение ──
  useEffect(() => {
    if (errored && currentTask?.error) {
      setError(currentTask.error)
    }
  }, [errored, currentTask])

  // ── Когда родитель отвязывает currentTask (dismiss / permanent-delete карточки),
  // сбрасываем локальную фазу + маску — иначе редактор остаётся с устаревшим
  // blob и shape-state предыдущей задачи. ──
  const lastBoundTaskIdRef = useRef<string | null>(null)
  useEffect(() => {
    if (currentTask) {
      lastBoundTaskIdRef.current = currentTask.task_id
    } else if (lastBoundTaskIdRef.current !== null) {
      lastBoundTaskIdRef.current = null
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
      setLocalPhase('idle')
      setTaskId(null)
      setPreviewUrl('')
      setResultPreviewUrl('')
      setError(null)
      setOriginalExt('')
      setShapes([])
      setImageNaturalSize({ width: 0, height: 0 })
    }
  }, [currentTask, previewUrl, resultPreviewUrl])

  // ── Handlers ──

  const handleUploaded = useCallback(async (response: ImageUploadResponse) => {
    setTaskId(response.task_id)
    setOriginalExt(response.original_ext)
    try {
      const url = await imageApi.getPreview(response.task_id)
      setPreviewUrl(url)
      setShapes([])
      setLocalPhase('editing')
    } catch {
      setError('Не удалось загрузить превью')
      setLocalPhase('error')
    }
  }, [])

  const handleProcess = useCallback(async () => {
    if (!taskId || shapes.length === 0) return
    try {
      const task = await imageApi.removeWatermark(
        taskId,
        shapes,
        inpaintMethod,
        imageNaturalSize.width,
      )
      onProcessStart({ ...task, file_exists: false })
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Не удалось запустить обработку'
      setError(message)
      setLocalPhase('error')
    }
  }, [taskId, shapes, inpaintMethod, imageNaturalSize.width, onProcessStart])

  const handleDownload = useCallback(async () => {
    if (!currentTask) return
    try {
      const { blob } = await imageApi.downloadResult(currentTask.task_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const baseName = currentTask.original_filename.replace(/\.[^.]+$/, '')
      const ext = originalExt || currentTask.original_ext || 'png'
      a.download = `${baseName}_cleaned.${ext}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch {
      toast.error('Не удалось скачать результат.')
    }
  }, [currentTask, originalExt])

  const handleReset = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    if (resultPreviewUrl) URL.revokeObjectURL(resultPreviewUrl)
    setLocalPhase('idle')
    setTaskId(null)
    setPreviewUrl('')
    setResultPreviewUrl('')
    setError(null)
    setOriginalExt('')
    setShapes([])
    setImageNaturalSize({ width: 0, height: 0 })
    onReset()
  }, [previewUrl, resultPreviewUrl, onReset])

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
                    max={80}
                    value={brushSize}
                    onChange={(e) => setBrushSize(Number(e.target.value))}
                    className={styles.slider}
                  />
                  <span className={styles.sliderValue}>{brushSize}</span>
                </div>
              </>
            )}

            <div className={styles.separator} />

            <div className={styles.methodWrap}>
              <select
                className={styles.methodSelect}
                value={inpaintMethod}
                onChange={(e) => setInpaintMethod(e.target.value as InpaintMethod)}
                title="Метод инпейнтинга"
              >
                <option value="lama">LaMa (нейросеть, рекомендуется)</option>
                <option value="telea">TELEA (быстрый классический)</option>
                <option value="ns">Navier-Stokes (классический)</option>
              </select>
              <p className={styles.methodHint}>
                LaMa даёт лучший результат для крупных и сложных знаков.
                Классические методы работают быстрее на мелких дефектах.
              </p>
            </div>

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
          <p className={styles.processingText}>
            Обработка... {currentTask?.progress ?? 0}%
          </p>
          <div className={styles.progressBarWrap}>
            <div
              className={styles.progressBarFill}
              style={{ width: `${currentTask?.progress ?? 0}%` }}
            />
          </div>
          {(currentTask?.inpaint_method ?? inpaintMethod) === 'lama' && (
            <p className={styles.processingHint}>
              LaMa работает локально на CPU и может занять до минуты.
            </p>
          )}
        </div>
      )}

      {phase === 'result' && currentTask && (
        <div className={styles.resultSection}>
          <ImageCompare beforeSrc={previewUrl} afterSrc={resultPreviewUrl} />
          <div className={styles.resultActions}>
            <button
              className={styles.successBtn}
              onClick={handleDownload}
              disabled={!currentTask.file_exists}
            >
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
          <p className={styles.errorMessage}>{error ?? currentTask?.error}</p>
          <button className={styles.secondaryBtn} onClick={handleReset}>
            <RotateCcw size={16} aria-hidden="true" />
            Попробовать снова
          </button>
        </div>
      )}
    </div>
  )
}
