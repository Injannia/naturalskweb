import { useEffect, useRef, useState } from 'react'
import { Wand2, Droplets } from 'lucide-react'
import { imageApi } from '../imageApi'
import type { ImageOperation, ImageStatus } from '../types'
import styles from './Thumbnail.module.css'

interface ThumbnailProps {
  taskId: string
  status: ImageStatus
  fileExists: boolean
  operation: ImageOperation
}

export default function Thumbnail({ taskId, status, fileExists, operation }: ThumbnailProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
          break
        }
      }
    })
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!visible) return
    let cancelled = false

    const loader = status === 'ready' && fileExists
      ? imageApi.getResultPreview
      : imageApi.getPreview

    loader(taskId)
      .then((blobUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(blobUrl)
          return
        }
        setUrl(blobUrl)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
    }
  }, [visible, taskId, status, fileExists])

  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [url])

  if (url && !failed) {
    return (
      <div className={styles.container} ref={ref}>
        <img src={url} alt="" className={styles.image} />
      </div>
    )
  }

  const Icon = operation === 'remove_bg' ? Wand2 : Droplets
  return (
    <div className={styles.container} ref={ref}>
      <span className={styles.fallback} data-testid="thumbnail-fallback">
        <Icon size={24} aria-hidden="true" />
      </span>
    </div>
  )
}
