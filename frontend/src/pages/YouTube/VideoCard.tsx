import { User, Clock, HardDrive, ImageOff, ExternalLink, Calendar } from 'lucide-react'
import { formatDuration, formatFileSize, formatUploadDate } from './utils'
import type { VideoInfo, VideoFormat, VideoQuality } from './types'
import styles from './VideoCard.module.css'

interface VideoCardProps {
  video: VideoInfo
  selectable?: boolean
  selected?: boolean
  onToggle?: (id: string) => void
  /** When provided, the estimated file size is tailored to the selected format/quality */
  selectedFormat?: VideoFormat
  selectedQuality?: VideoQuality
}

/**
 * Estimates the download file size from the available format list.
 *
 * For audio-only formats (mp3/wav) the backend does not return audio-only
 * stream data, so we estimate based on duration and typical bitrates:
 *   MP3 ~128 kbps ≈ 1 MB/min, WAV ~1411 kbps ≈ 10.6 MB/min.
 *
 * For video (mp4) we try to match the resolution label (e.g. "720p").
 * Falls back to the single largest filesize available.
 */
function estimateFileSize(
  formats: VideoInfo['formats'],
  format: VideoFormat | undefined,
  quality: VideoQuality | undefined,
  duration?: number,
): number | null {
  if (!formats.length && !duration) return null

  const isAudio = format === 'mp3' || format === 'wav'

  // Audio: estimate from duration since backend only returns video-stream sizes
  if (isAudio && duration && duration > 0) {
    const minutes = duration / 60
    if (format === 'wav') return Math.round(minutes * 10.6 * 1024 * 1024)
    return Math.round(minutes * 1.0 * 1024 * 1024) // mp3 ~128kbps
  }

  if (!formats.length) return null

  // Video: match the height from the quality label when possible
  const candidates = formats.filter((f) => {
    const hasSize = f.filesize !== null && f.filesize > 0
    if (!hasSize) return false
    if (quality && quality !== 'best') {
      const height = quality.replace('p', '') // e.g. "720"
      return f.resolution.includes(`x${height}`) || f.resolution.includes(`${height}p`)
    }
    return true
  })

  const pool = candidates.length ? candidates : formats.filter((f) => f.filesize !== null && f.filesize > 0)
  if (!pool.length) return null

  // Return the largest filesize from the pool as a conservative upper-bound estimate
  return pool.reduce((max, f) => Math.max(max, f.filesize ?? 0), 0) || null
}

export default function VideoCard({
  video,
  selectable = false,
  selected = false,
  onToggle,
  selectedFormat,
  selectedQuality,
}: VideoCardProps) {
  const estimatedSize = estimateFileSize(video.formats, selectedFormat, selectedQuality, video.duration)
  const uploadDate = formatUploadDate(video.upload_date)

  function handleClick() {
    if (selectable && onToggle) {
      onToggle(video.id)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.key === 'Enter' || e.key === ' ') && selectable && onToggle) {
      e.preventDefault()
      onToggle(video.id)
    }
  }

  const cardClass = [
    styles.card,
    selectable ? styles.selectable : '',
    selected ? styles.selected : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div
      className={cardClass}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role={selectable ? 'checkbox' : undefined}
      aria-checked={selectable ? selected : undefined}
      tabIndex={selectable ? 0 : undefined}
    >
      {selectable && (
        <div className={styles.checkboxWrap}>
          <input
            type="checkbox"
            className={styles.checkbox}
            checked={selected}
            onChange={() => onToggle?.(video.id)}
            onClick={(e) => e.stopPropagation()}
            aria-label={`Выбрать видео: ${video.title}`}
          />
        </div>
      )}

      {video.thumbnail ? (
        <img
          className={styles.thumbnail}
          src={video.thumbnail}
          alt={video.title}
          loading="lazy"
        />
      ) : (
        <div className={styles.thumbnailPlaceholder} aria-hidden="true">
          <ImageOff size={20} />
        </div>
      )}

      <div className={styles.info}>
        <div className={styles.titleRow}>
          <div className={styles.title} title={video.title}>
            {video.title}
          </div>
          <a
            className={styles.externalLink}
            href={`https://youtube.com/watch?v=${video.id}`}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Открыть «${video.title}» на YouTube`}
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink size={13} aria-hidden="true" />
          </a>
        </div>
        <div className={styles.meta}>
          {video.channel && (
            <span className={styles.metaItem}>
              <User size={12} />
              {video.channel}
            </span>
          )}
          {video.duration > 0 && (
            <span className={styles.metaItem}>
              <Clock size={12} />
              {formatDuration(video.duration)}
            </span>
          )}
          {estimatedSize !== null && (
            <span className={styles.metaItem} title="Приблизительный размер файла">
              <HardDrive size={12} aria-hidden="true" />
              ~{formatFileSize(estimatedSize)}
            </span>
          )}
          {uploadDate !== null && (
            <span className={styles.metaItem} title="Дата публикации">
              <Calendar size={12} aria-hidden="true" />
              {uploadDate}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
