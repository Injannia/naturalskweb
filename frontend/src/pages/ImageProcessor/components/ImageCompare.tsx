// ── ImageCompare — before/after slider comparison component ──
//
// Displays two images side-by-side with a draggable vertical divider.
// The "after" image is clipped by a wrapper whose width follows the slider.

import { useRef, useState, useCallback } from 'react'
import styles from './ImageCompare.module.css'

interface ImageCompareProps {
  beforeSrc: string
  afterSrc: string
  beforeLabel?: string
  afterLabel?: string
}

export function ImageCompare({
  beforeSrc,
  afterSrc,
  beforeLabel = 'До',
  afterLabel = 'После',
}: ImageCompareProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState(50) // percentage 0-100
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
      isDragging.current = true
      ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
      updatePosition(e.clientX)
    },
    [updatePosition],
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

  return (
    <div
      ref={containerRef}
      className={styles.container}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      {/* Before image — full width, sits behind */}
      <img
        src={beforeSrc}
        alt={beforeLabel}
        className={styles.image}
        draggable={false}
      />

      {/* After image — clipped by wrapper width */}
      <div
        className={styles.afterWrapper}
        style={{ width: `${position}%` }}
      >
        <img
          src={afterSrc}
          alt={afterLabel}
          className={styles.image}
          draggable={false}
        />
      </div>

      {/* Labels */}
      <span className={`${styles.label} ${styles.labelBefore}`}>
        {beforeLabel}
      </span>
      <span className={`${styles.label} ${styles.labelAfter}`}>
        {afterLabel}
      </span>

      {/* Slider line + handle */}
      <div
        className={styles.slider}
        style={{ left: `${position}%` }}
      >
        <div className={styles.sliderLine} />
        <div className={styles.sliderHandle}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M3 1L0 6l3 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M9 1l3 5-3 5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
    </div>
  )
}
