import { ListVideo, Clock } from 'lucide-react'
import VideoCard from './VideoCard'
import type { PlaylistInfo, VideoFormat, VideoQuality } from './types'
import styles from './PlaylistView.module.css'

/**
 * Formats a total number of seconds into a human-readable Russian string.
 * E.g. 9240 → "2ч 34м", 45 → "45с", 3600 → "1ч 0м"
 */
function formatTotalDuration(totalSeconds: number): string {
  if (totalSeconds <= 0) return '—'
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = Math.floor(totalSeconds % 60)
  if (h > 0) return `${h}ч ${m}м`
  if (m > 0) return `${m}м ${s}с`
  return `${s}с`
}

interface PlaylistViewProps {
  playlist: PlaylistInfo
  selectedIds: Set<string>
  onToggle: (id: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  selectedFormat?: VideoFormat
  selectedQuality?: VideoQuality
}

export default function PlaylistView({
  playlist,
  selectedIds,
  onToggle,
  onSelectAll,
  onDeselectAll,
  selectedFormat,
  selectedQuality,
}: PlaylistViewProps) {
  const total = playlist.videos.length
  const selected = selectedIds.size
  const allSelected = selected === total && total > 0

  // Aggregate total duration across all videos in the playlist
  const totalSeconds = playlist.videos.reduce((acc, v) => acc + (v.duration ?? 0), 0)

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.playlistTitle}>
            <ListVideo size={18} aria-hidden="true" />
            {playlist.title}
          </div>
          <div className={styles.playlistMeta}>
            {playlist.channel && `${playlist.channel} · `}
            {total} видео
          </div>
          <div className={styles.playlistStats}>
            <span className={styles.statItem}>
              <Clock size={11} aria-hidden="true" />
              Общая длительность: {formatTotalDuration(totalSeconds)}
            </span>
          </div>
        </div>

        <div className={styles.controls}>
          <span className={styles.selectedCount}>
            <span className={styles.selectedCountAccent}>{selected}</span>
            {' из '}
            {total} выбрано
          </span>
          {allSelected ? (
            <button
              type="button"
              className={styles.btnText}
              onClick={onDeselectAll}
            >
              Снять всё
            </button>
          ) : (
            <button
              type="button"
              className={styles.btnText}
              onClick={onSelectAll}
            >
              Выбрать всё
            </button>
          )}
        </div>
      </div>

      <div className={styles.videoList} role="list">
        {playlist.videos.map((video) => (
          <div key={video.id} role="listitem">
            <VideoCard
              video={video}
              selectable
              selected={selectedIds.has(video.id)}
              onToggle={onToggle}
              selectedFormat={selectedFormat}
              selectedQuality={selectedQuality}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
