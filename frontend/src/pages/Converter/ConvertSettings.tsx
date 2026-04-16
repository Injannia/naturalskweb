import type { ConvertCategory, ConvertOptions } from './types'
import styles from './ConvertSettings.module.css'

interface ConvertSettingsProps {
  category: ConvertCategory
  options: ConvertOptions
  onChange: (options: ConvertOptions) => void
  disabled?: boolean
  /** Used to generate unique HTML id attributes when multiple panels could coexist. */
  taskId?: string
}

// ── Option definitions ───────────────────────────────────────────────────────

const VIDEO_RESOLUTIONS = [
  { value: '', label: 'Без изменений' },
  { value: '1920x1080', label: '1920×1080 (Full HD)' },
  { value: '1280x720', label: '1280×720 (HD)' },
  { value: '854x480', label: '854×480 (480p)' },
  { value: '640x360', label: '640×360 (360p)' },
] as const

const VIDEO_CODECS = [
  { value: '', label: 'Авто' },
  { value: 'h264', label: 'H.264' },
  { value: 'h265', label: 'H.265 (HEVC)' },
  { value: 'vp9', label: 'VP9' },
] as const

const VIDEO_BITRATES = [
  { value: '', label: 'Авто' },
  { value: '1M', label: '1 Мбит/с' },
  { value: '2M', label: '2 Мбит/с' },
  { value: '5M', label: '5 Мбит/с' },
  { value: '10M', label: '10 Мбит/с' },
  { value: '20M', label: '20 Мбит/с' },
] as const

const VIDEO_FPS = [
  { value: '', label: 'Без изменений' },
  { value: '24', label: '24 кадр/с' },
  { value: '30', label: '30 кадр/с' },
  { value: '60', label: '60 кадр/с' },
] as const

const AUDIO_CODECS = [
  { value: '', label: 'Авто' },
  { value: 'aac', label: 'AAC' },
  { value: 'mp3', label: 'MP3' },
  { value: 'copy', label: 'Копировать' },
] as const

const AUDIO_BITRATES = [
  { value: '', label: 'Авто' },
  { value: '64k', label: '64 кбит/с' },
  { value: '128k', label: '128 кбит/с' },
  { value: '192k', label: '192 кбит/с' },
  { value: '256k', label: '256 кбит/с' },
  { value: '320k', label: '320 кбит/с' },
] as const

const SAMPLE_RATES = [
  { value: '', label: 'Авто' },
  { value: '22050', label: '22 050 Гц' },
  { value: '44100', label: '44 100 Гц' },
  { value: '48000', label: '48 000 Гц' },
  { value: '96000', label: '96 000 Гц' },
] as const

const AUDIO_CHANNELS = [
  { value: '', label: 'Авто' },
  { value: '1', label: 'Моно (1)' },
  { value: '2', label: 'Стерео (2)' },
] as const

// ── Helpers ──────────────────────────────────────────────────────────────────

// Returns `undefined` for "auto"/"no-change" sentinel values so the key is
// omitted from the options object entirely (cleaner API payload).
function strOrUndefined(val: string): string | undefined {
  return val === '' ? undefined : val
}

function numOrUndefined(val: string): number | undefined {
  if (val === '') return undefined
  const n = Number(val)
  return Number.isNaN(n) ? undefined : n
}

// ── Sub-panels ────────────────────────────────────────────────────────────────

interface RowProps {
  label: string
  htmlFor: string
  children: React.ReactNode
}

function Row({ label, htmlFor, children }: RowProps) {
  return (
    <div className={styles.row}>
      <label className={styles.rowLabel} htmlFor={htmlFor}>
        {label}
      </label>
      <div className={styles.rowControl}>{children}</div>
    </div>
  )
}

// ── Video settings ────────────────────────────────────────────────────────────

function VideoSettings({
  options,
  onChange,
  disabled,
  idPrefix,
}: {
  options: ConvertOptions
  onChange: (opts: ConvertOptions) => void
  disabled: boolean
  idPrefix: string
}) {
  return (
    <>
      <Row label="Разрешение" htmlFor={`${idPrefix}-resolution`}>
        <select
          id={`${idPrefix}-resolution`}
          className={styles.select}
          value={options.resolution ?? ''}
          onChange={(e) => onChange({ ...options, resolution: strOrUndefined(e.target.value) })}
          disabled={disabled}
          aria-label="Разрешение видео"
        >
          {VIDEO_RESOLUTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>

      <Row label="Видеокодек" htmlFor={`${idPrefix}-vcodec`}>
        <select
          id={`${idPrefix}-vcodec`}
          className={styles.select}
          value={options.codec ?? ''}
          onChange={(e) => onChange({ ...options, codec: strOrUndefined(e.target.value) })}
          disabled={disabled}
          aria-label="Видеокодек"
        >
          {VIDEO_CODECS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>

      <Row label="Битрейт видео" htmlFor={`${idPrefix}-vbitrate`}>
        <select
          id={`${idPrefix}-vbitrate`}
          className={styles.select}
          value={options.bitrate ?? ''}
          onChange={(e) => onChange({ ...options, bitrate: strOrUndefined(e.target.value) })}
          disabled={disabled}
          aria-label="Битрейт видео"
        >
          {VIDEO_BITRATES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>

      <Row label="FPS" htmlFor={`${idPrefix}-fps`}>
        <select
          id={`${idPrefix}-fps`}
          className={styles.select}
          value={options.fps !== undefined ? String(options.fps) : ''}
          onChange={(e) => onChange({ ...options, fps: numOrUndefined(e.target.value) })}
          disabled={disabled}
          aria-label="Частота кадров"
        >
          {VIDEO_FPS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>

      <Row label="Аудиокодек" htmlFor={`${idPrefix}-acodec`}>
        <select
          id={`${idPrefix}-acodec`}
          className={styles.select}
          value={options.audio_codec ?? ''}
          onChange={(e) => onChange({ ...options, audio_codec: strOrUndefined(e.target.value) })}
          disabled={disabled}
          aria-label="Аудиокодек"
        >
          {AUDIO_CODECS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>
    </>
  )
}

// ── Audio settings ────────────────────────────────────────────────────────────

function AudioSettings({
  options,
  onChange,
  disabled,
  idPrefix,
}: {
  options: ConvertOptions
  onChange: (opts: ConvertOptions) => void
  disabled: boolean
  idPrefix: string
}) {
  return (
    <>
      <Row label="Битрейт" htmlFor={`${idPrefix}-abitrate`}>
        <select
          id={`${idPrefix}-abitrate`}
          className={styles.select}
          value={options.bitrate ?? ''}
          onChange={(e) => onChange({ ...options, bitrate: strOrUndefined(e.target.value) })}
          disabled={disabled}
          aria-label="Битрейт аудио"
        >
          {AUDIO_BITRATES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>

      <Row label="Частота дискретизации" htmlFor={`${idPrefix}-samplerate`}>
        <select
          id={`${idPrefix}-samplerate`}
          className={styles.select}
          value={options.sample_rate !== undefined ? String(options.sample_rate) : ''}
          onChange={(e) =>
            onChange({ ...options, sample_rate: numOrUndefined(e.target.value) })
          }
          disabled={disabled}
          aria-label="Частота дискретизации"
        >
          {SAMPLE_RATES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>

      <Row label="Каналы" htmlFor={`${idPrefix}-channels`}>
        <select
          id={`${idPrefix}-channels`}
          className={styles.select}
          value={options.channels !== undefined ? String(options.channels) : ''}
          onChange={(e) => onChange({ ...options, channels: numOrUndefined(e.target.value) })}
          disabled={disabled}
          aria-label="Количество аудиоканалов"
        >
          {AUDIO_CHANNELS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </Row>
    </>
  )
}

// ── Image settings ────────────────────────────────────────────────────────────

function ImageSettings({
  options,
  onChange,
  disabled,
  idPrefix,
}: {
  options: ConvertOptions
  onChange: (opts: ConvertOptions) => void
  disabled: boolean
  idPrefix: string
}) {
  // Default quality to 85 when not yet set
  const quality = options.quality ?? 85

  function handleQualityChange(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ ...options, quality: Number(e.target.value) })
  }

  function handleDimensionChange(
    field: 'width' | 'height',
    e: React.ChangeEvent<HTMLInputElement>,
  ) {
    const raw = e.target.value.trim()
    onChange({ ...options, [field]: raw === '' ? undefined : Number(raw) })
  }

  function handleKeepAspectChange(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ ...options, keep_aspect: e.target.checked })
  }

  return (
    <>
      {/* Quality slider */}
      <Row label="Качество" htmlFor={`${idPrefix}-quality`}>
        <div className={styles.sliderWrapper}>
          <input
            id={`${idPrefix}-quality`}
            type="range"
            min={1}
            max={100}
            value={quality}
            onChange={handleQualityChange}
            disabled={disabled}
            className={styles.slider}
            aria-label="Качество изображения"
            aria-valuemin={1}
            aria-valuemax={100}
            aria-valuenow={quality}
            // Inline style is permitted here: it's a dynamically computed CSS
            // custom property used for the accent-fill gradient on the track.
            style={{ '--slider-pct': `${quality}%` } as React.CSSProperties}
          />
          <span className={styles.sliderValue}>{quality}</span>
        </div>
      </Row>

      {/* Width */}
      <Row label="Ширина" htmlFor={`${idPrefix}-width`}>
        <input
          id={`${idPrefix}-width`}
          type="number"
          className={styles.numberInput}
          value={options.width ?? ''}
          min={1}
          placeholder="Авто"
          onChange={(e) => handleDimensionChange('width', e)}
          disabled={disabled}
          aria-label="Ширина изображения в пикселях"
        />
      </Row>

      {/* Height */}
      <Row label="Высота" htmlFor={`${idPrefix}-height`}>
        <input
          id={`${idPrefix}-height`}
          type="number"
          className={styles.numberInput}
          value={options.height ?? ''}
          min={1}
          placeholder="Авто"
          onChange={(e) => handleDimensionChange('height', e)}
          disabled={disabled}
          aria-label="Высота изображения в пикселях"
        />
      </Row>

      {/* Keep aspect ratio checkbox */}
      <div className={styles.checkboxRow}>
        <input
          id={`${idPrefix}-keep-aspect`}
          type="checkbox"
          className={styles.checkbox}
          // Default to checked (true) when not explicitly set to false
          checked={options.keep_aspect !== false}
          onChange={handleKeepAspectChange}
          disabled={disabled}
          aria-label="Сохранить пропорции изображения"
        />
        <label htmlFor={`${idPrefix}-keep-aspect`} className={styles.checkboxLabel}>
          Сохранить пропорции
        </label>
      </div>
    </>
  )
}

// ── Root component ────────────────────────────────────────────────────────────

export default function ConvertSettings({
  category,
  options,
  onChange,
  disabled = false,
  taskId = '',
}: ConvertSettingsProps) {
  const idPrefix = `cs-${taskId || 'default'}`

  return (
    <div className={styles.panel} role="region" aria-label="Настройки конвертации">
      <div className={styles.heading}>Настройки конвертации</div>

      <div className={styles.grid}>
        {category === 'video' && (
          <VideoSettings options={options} onChange={onChange} disabled={disabled} idPrefix={idPrefix} />
        )}

        {category === 'audio' && (
          <AudioSettings options={options} onChange={onChange} disabled={disabled} idPrefix={idPrefix} />
        )}

        {category === 'image' && (
          <ImageSettings options={options} onChange={onChange} disabled={disabled} idPrefix={idPrefix} />
        )}

        {category === 'document' && (
          <p className={styles.noSettings}>
            Настройки для документов не требуются
          </p>
        )}
      </div>
    </div>
  )
}
