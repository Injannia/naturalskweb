import { useRef, useEffect, useCallback } from 'react'
import type { MaskShape } from '../types'
import styles from './MaskCanvas.module.css'

interface MaskCanvasProps {
  imageUrl: string
  naturalWidth: number
  naturalHeight: number
  tool: 'brush' | 'rect' | 'eraser'
  brushSize: number
  shapes: MaskShape[]
  onShapesChange: (shapes: MaskShape[]) => void
}

export default function MaskCanvas({
  imageUrl,
  naturalWidth,
  naturalHeight,
  tool,
  brushSize,
  shapes,
  onShapesChange,
}: MaskCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)

  // Drawing state stored in refs to avoid re-renders during drawing
  const isDrawing = useRef(false)
  const currentPoints = useRef<number[][]>([])
  const startPoint = useRef<number[]>([0, 0])

  // Keep latest props in refs for use inside pointer handlers
  const shapesRef = useRef(shapes)
  shapesRef.current = shapes
  const toolRef = useRef(tool)
  toolRef.current = tool
  const brushSizeRef = useRef(brushSize)
  brushSizeRef.current = brushSize
  const onShapesChangeRef = useRef(onShapesChange)
  onShapesChangeRef.current = onShapesChange

  // ── Coordinate helpers ──

  const getCanvasPoint = useCallback((e: PointerEvent): [number, number] => {
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    return [Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))]
  }, [])

  // ── Rendering ──

  const redraw = useCallback(
    (extraShape?: MaskShape) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const w = canvas.width
      const h = canvas.height

      ctx.clearRect(0, 0, w, h)

      const allShapes = extraShape
        ? [...shapesRef.current, extraShape]
        : shapesRef.current

      for (const shape of allShapes) {
        if (shape.isEraser) {
          ctx.globalCompositeOperation = 'destination-out'
        } else {
          ctx.globalCompositeOperation = 'source-over'
        }

        if (shape.type === 'brush') {
          if (shape.points.length < 1) continue
          ctx.beginPath()
          ctx.strokeStyle = shape.isEraser
            ? 'rgba(0, 0, 0, 1)'
            : 'rgba(255, 0, 0, 0.4)'
          ctx.lineWidth = (shape.brushSize ?? 10) * (w / (naturalWidth || w))
          ctx.lineCap = 'round'
          ctx.lineJoin = 'round'

          const [sx, sy] = shape.points[0]
          ctx.moveTo(sx * w, sy * h)
          for (let i = 1; i < shape.points.length; i++) {
            ctx.lineTo(shape.points[i][0] * w, shape.points[i][1] * h)
          }
          // Single point – draw a dot
          if (shape.points.length === 1) {
            ctx.lineTo(sx * w + 0.1, sy * h)
          }
          ctx.stroke()
        } else if (shape.type === 'rect') {
          if (shape.points.length < 2) continue
          const [x1, y1] = shape.points[0]
          const [x2, y2] = shape.points[1]
          ctx.fillStyle = 'rgba(255, 0, 0, 0.4)'
          ctx.fillRect(
            x1 * w,
            y1 * h,
            (x2 - x1) * w,
            (y2 - y1) * h,
          )
        }

        // Reset composite operation
        ctx.globalCompositeOperation = 'source-over'
      }
    },
    [naturalWidth],
  )

  // ── Pointer handlers ──

  const handlePointerDown = useCallback(
    (e: PointerEvent) => {
      const canvas = canvasRef.current
      if (!canvas) return
      canvas.setPointerCapture(e.pointerId)

      isDrawing.current = true
      const pt = getCanvasPoint(e)
      startPoint.current = pt
      currentPoints.current = [pt]
    },
    [getCanvasPoint],
  )

  const handlePointerMove = useCallback(
    (e: PointerEvent) => {
      if (!isDrawing.current) return
      const pt = getCanvasPoint(e)

      const currentTool = toolRef.current

      if (currentTool === 'brush' || currentTool === 'eraser') {
        currentPoints.current.push(pt)
        const inProgress: MaskShape = {
          type: 'brush',
          points: [...currentPoints.current],
          brushSize: brushSizeRef.current,
          isEraser: currentTool === 'eraser',
        }
        redraw(inProgress)
      } else if (currentTool === 'rect') {
        const inProgress: MaskShape = {
          type: 'rect',
          points: [startPoint.current, pt],
          brushSize: null,
        }
        redraw(inProgress)
      }
    },
    [getCanvasPoint, redraw],
  )

  const handlePointerUp = useCallback(
    (e: PointerEvent) => {
      if (!isDrawing.current) return
      isDrawing.current = false

      const currentTool = toolRef.current
      const pt = getCanvasPoint(e)
      let newShape: MaskShape

      if (currentTool === 'brush' || currentTool === 'eraser') {
        currentPoints.current.push(pt)
        newShape = {
          type: 'brush',
          points: [...currentPoints.current],
          brushSize: brushSizeRef.current,
          isEraser: currentTool === 'eraser',
        }
      } else {
        newShape = {
          type: 'rect',
          points: [startPoint.current, pt],
          brushSize: null,
        }
      }

      currentPoints.current = []
      onShapesChangeRef.current([...shapesRef.current, newShape])
    },
    [getCanvasPoint],
  )

  // ── Attach / detach pointer events ──

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    canvas.addEventListener('pointerdown', handlePointerDown)
    canvas.addEventListener('pointermove', handlePointerMove)
    canvas.addEventListener('pointerup', handlePointerUp)
    canvas.addEventListener('pointercancel', handlePointerUp)

    return () => {
      canvas.removeEventListener('pointerdown', handlePointerDown)
      canvas.removeEventListener('pointermove', handlePointerMove)
      canvas.removeEventListener('pointerup', handlePointerUp)
      canvas.removeEventListener('pointercancel', handlePointerUp)
    }
  }, [handlePointerDown, handlePointerMove, handlePointerUp])

  // ── Resize observer: keep canvas pixel dimensions in sync with display size ──

  useEffect(() => {
    const img = imgRef.current
    const canvas = canvasRef.current
    if (!img || !canvas) return

    const syncSize = () => {
      const displayW = img.clientWidth
      const displayH = img.clientHeight
      if (canvas.width !== displayW || canvas.height !== displayH) {
        canvas.width = displayW
        canvas.height = displayH
        redraw()
      }
    }

    // Initial sync once image loads
    if (img.complete) {
      syncSize()
    } else {
      img.addEventListener('load', syncSize, { once: true })
    }

    const ro = new ResizeObserver(() => {
      syncSize()
    })
    ro.observe(img)

    return () => {
      ro.disconnect()
      img.removeEventListener('load', syncSize)
    }
  }, [imageUrl, redraw])

  // ── Redraw when shapes change externally ──

  useEffect(() => {
    redraw()
  }, [shapes, redraw])

  return (
    <div className={styles.container}>
      <img
        ref={imgRef}
        src={imageUrl}
        alt="Preview"
        className={styles.image}
        draggable={false}
      />
      <canvas ref={canvasRef} className={styles.canvas} />
    </div>
  )
}
