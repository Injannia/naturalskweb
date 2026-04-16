import { Download, RefreshCw, TriangleAlert } from 'lucide-react'
import type { VideoFormat, VideoQuality } from './types'
import styles from './DownloadOptions.module.css'

const FORMATS: { value: VideoFormat; label: string }[] = [
  { value: 'mp4', label: 'MP4' },
  { value: 'mp3', label: 'MP3' },
  { value: 'wav', label: 'WAV' },
]

const QUALITIES: { value: VideoQuality; label: string }[] = [
  { value: '360p', label: '360p' },
  { value: '480p', label: '480p' },
  { value: '720p', label: '720p HD' },
  { value: '1080p', label: '1080p Full HD' },
  { value: 'best', label: 'Наилучшее' },
]

interface DownloadOptionsProps {
  format: VideoFormat
  quality: VideoQuality
  onFormatChange: (f: VideoFormat) => void
  onQualityChange: (q: VideoQuality) => void
  onDownload: () => void
  disabled: boolean
  loading: boolean
  // When defined, a secondary "Перекачать" button is shown next to the main one
  onForceDownload?: () => void
  forceDownloadLoading?: boolean
}

export default function DownloadOptions({
  format,
  quality,
  onFormatChange,
  onQualityChange,
  onDownload,
  disabled,
  loading,
  onForceDownload,
  forceDownloadLoading,
}: DownloadOptionsProps) {
  const isAudio = format === 'mp3' || format === 'wav'

  return (
    <div className={styles.container}>
      {/* Format */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>Формат</div>
        <div className={styles.formatGroup} role="group" aria-label="Формат файла">
          {FORMATS.map((f) => (
            <button
              key={f.value}
              type="button"
              className={`${styles.formatBtn} ${
                format === f.value ? styles.formatBtnActive : ''
              }`}
              onClick={() => onFormatChange(f.value)}
              aria-pressed={format === f.value}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Quality — hidden for audio formats */}
      {!isAudio && (
        <div className={styles.section}>
          <label className={styles.sectionLabel} htmlFor="quality-select">
            Качество
          </label>
          <select
            id="quality-select"
            className={styles.qualitySelect}
            value={quality}
            onChange={(e) => onQualityChange(e.target.value as VideoQuality)}
          >
            {QUALITIES.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </select>
          {format === 'mp4' && quality === 'best' && (
            <p className={styles.qualityWarning}>
              <TriangleAlert size={12} aria-hidden="true" />
              «Best» может загрузить файл &gt;2 ГБ. Выберите конкретное качество для ограничения размера.
            </p>
          )}
        </div>
      )}

      {/* Primary download button + optional "Перекачать" secondary button */}
      <div className={styles.actionRow}>
        <button
          type="button"
          className={styles.downloadBtn}
          onClick={onDownload}
          disabled={disabled || loading}
          aria-busy={loading}
        >
          {loading ? (
            <>
              <span className={styles.spinner} aria-hidden="true" />
              Запуск...
            </>
          ) : (
            <>
              <Download size={18} aria-hidden="true" />
              Скачать
            </>
          )}
        </button>

        {/* Shown only after a cache hit — lets the user bypass the cache */}
        {onForceDownload && (
          <button
            type="button"
            className={styles.redownloadBtn}
            onClick={onForceDownload}
            disabled={disabled || loading || forceDownloadLoading}
            aria-busy={forceDownloadLoading}
            title="Скачать заново, игнорируя кэш"
          >
            {forceDownloadLoading ? (
              <span className={styles.spinnerSmall} aria-hidden="true" />
            ) : (
              <RefreshCw size={14} aria-hidden="true" />
            )}
            Перекачать
          </button>
        )}
      </div>
    </div>
  )
}
