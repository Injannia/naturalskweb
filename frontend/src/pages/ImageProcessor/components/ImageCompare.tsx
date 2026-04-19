// ── ImageCompare — before/after comparison with three modes ──
//
// Modes: 'before' (show original only), 'compare' (draggable shutter),
// 'after' (show result only). In 'compare' mode the left half shows
// the original ("До"), right half shows the result ("После"), matching
// conventional visual comparison.

import { useRef, useState, useCallback } from 'react'
import { Eye, Columns2, Sparkles } from 'lucide-react'
import styles from './ImageCompare.module.css'

type CompareMode = 'before' | 'compare' | 'after'

interface ImageCompareProps {
  beforeSrc: string
  afterSrc: string
  beforeLabel?: string
  afterLabel?: string
  transparencyGrid?: boolean
}

export function ImageCompare({
  beforeSrc,
  afterSrc,
  beforeLabel = 'До',
  afterLabel = 'После',
  transparencyGrid = false,
}: ImageCompareProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [mode, setMode] = useState<CompareMode>('compare')
  const [position, setPosition] = useState(50)
  const isDragging = useRef(false)

  const updatePosition = useCallback((clientX: number) => {
    const container = containerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    const x = clientX - rect.left
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100))
    setPosition(pct)
  }, [])

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (mode !== 'compare') return
      isDragging.current = true
      ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
      updatePosition(e.clientX)
    },
    [mode, updatePosition],
  )

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging.current) return
      updatePosition(e.clientX)
    },
    [updatePosition],
  )

  const handlePointerUp = useCallback(() => {
    isDragging.current = false
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    const big = e.shiftKey ? 10 : 2
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      setPosition((p) => Math.max(0, p - big))
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      setPosition((p) => Math.min(100, p + big))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setPosition(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      setPosition(100)
    }
  }, [])

  const containerClass = [
    styles.container,
    transparencyGrid ? styles.grid : '',
    mode === 'compare' ? styles.cursorCompare : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={styles.wrap}>
      {/* Mode switcher */}
      <div className={styles.modeSwitcher} role="radiogroup" aria-label="Режим сравнения">
        <button
          type="button"
          role="radio"
          aria-checked={mode === 'before'}
          className={mode === 'before' ? styles.modeBtnActive : styles.modeBtn}
          onClick={() => setMode('before')}
        >
          <Eye size={14} aria-hidden="true" />
          Только {beforeLabel.toLowerCase()}
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={mode === 'compare'}
          className={mode === 'compare' ? styles.modeBtnActive : styles.modeBtn}
          onClick={() => setMode('compare')}
        >
          <Columns2 size={14} aria-hidden="true" />
          Сравнить
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={mode === 'after'}
          className={mode === 'after' ? styles.modeBtnActive : styles.modeBtn}
          onClick={() => setMode('after')}
        >
          <Sparkles size={14} aria-hidden="true" />
          Только {afterLabel.toLowerCase()}
        </button>
      </div>

      {/* Image area */}
      <div
        ref={containerRef}
        className={containerClass}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {mode === 'before' && (
          <>
            <img src={beforeSrc} alt={beforeLabel} className={styles.image} draggable={false} />
            <span className={`${styles.label} ${styles.labelTopLeft}`}>{beforeLabel}</span>
          </>
        )}

        {mode === 'after' && (
          <>
            <img src={afterSrc} alt={afterLabel} className={styles.image} draggable={false} />
            <span className={`${styles.label} ${styles.labelTopLeft}`}>{afterLabel}</span>
          </>
        )}

        {mode === 'compare' && (
          <>
            {/* After as background */}
            <img src={afterSrc} alt={afterLabel} className={styles.image} draggable={false} />

            {/* Before clipped from the left by wrapper width */}
            <div className={styles.beforeWrapper} style={{ width: `${position}%` }}>
              <img src={beforeSrc} alt={beforeLabel} className={styles.image} draggable={false} />
            </div>

            {/* Labels in top corners */}
            <span className={`${styles.label} ${styles.labelTopLeft}`}>{beforeLabel}</span>
            <span className={`${styles.label} ${styles.labelTopRight}`}>{afterLabel}</span>

            {/* Slider handle */}
            <div className={styles.slider} style={{ left: `${position}%` }}>
              <div className={styles.sliderLine} />
              <div
                className={styles.sliderHandle}
                role="slider"
                tabIndex={0}
                aria-label="Позиция сравнения"
                aria-valuenow={Math.round(position)}
                aria-valuemin={0}
                aria-valuemax={100}
                onKeyDown={handleKeyDown}
              >
                <svg width="14" height="14" viewBox="0 0 12 12" aria-hidden="true">
                  <path d="M3 1L0 6l3 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M9 1l3 5-3 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
