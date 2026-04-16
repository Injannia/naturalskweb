import { Film, Music, ImageIcon, FileText, X, Settings } from 'lucide-react'
import type { ConvertCategory, ConvertOptions, UploadedFile } from './types'
import { FORMAT_OPTIONS, CATEGORY_LABELS, formatFileSize } from './utils'
import styles from './FileItem.module.css'

// ── Icon mapping per category ──
const CATEGORY_ICONS: Record<ConvertCategory, React.ReactNode> = {
  video:    <Film    size={18} aria-hidden="true" />,
  audio:    <Music   size={18} aria-hidden="true" />,
  image:    <ImageIcon size={18} aria-hidden="true" />,
  document: <FileText  size={18} aria-hidden="true" />,
}

interface FileItemProps {
  file: UploadedFile
  onTargetFormatChange: (taskId: string, format: string) => void
  onOptionsChange: (taskId: string, options: ConvertOptions) => void
  onRemove: (taskId: string) => void
  onToggleSettings: (taskId: string) => void
  showSettings: boolean
  disabled?: boolean
}

export default function FileItem({
  file,
  onTargetFormatChange,
  // Consumed by the ConvertSettings panel rendered by the parent when
  // showSettings is true — not used inside this card directly.
  onOptionsChange: _onOptionsChange,
  onRemove,
  onToggleSettings,
  showSettings,
  disabled = false,
}: FileItemProps) {
  // Formats available for this category, excluding the source extension so the
  // user is never offered a no-op conversion.
  const formatOptions = FORMAT_OPTIONS[file.category].filter(
    (fmt) => fmt !== file.original_ext.toLowerCase(),
  )

  const subtitle = `${CATEGORY_LABELS[file.category]} · ${formatFileSize(file.file_size)}`
  const isUploading = file.uploadProgress < 100

  function handleFormatChange(e: React.ChangeEvent<HTMLSelectElement>) {
    onTargetFormatChange(file.task_id, e.target.value)
  }

  return (
    <div className={styles.card}>
      {/* ── Header row: icon + filename + remove ── */}
      <div className={styles.header}>
        <span className={`${styles.categoryIcon} ${styles[file.category]}`}>
          {CATEGORY_ICONS[file.category]}
        </span>

        <div className={styles.fileInfo}>
          {/* title attr ensures the full name is accessible via tooltip on truncation */}
          <span className={styles.filename} title={file.original_filename}>
            {file.original_filename}
          </span>
          <span className={styles.subtitle}>{subtitle}</span>
        </div>

        <button
          type="button"
          className={styles.removeBtn}
          onClick={() => onRemove(file.task_id)}
          disabled={disabled}
          aria-label={`Удалить файл ${file.original_filename}`}
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>

      {/* ── Controls row: format select + settings toggle ── */}
      <div className={styles.controls}>
        <label
          className={styles.formatLabel}
          htmlFor={`format-${file.task_id}`}
        >
          Конвертировать в:
        </label>

        <select
          id={`format-${file.task_id}`}
          className={styles.formatSelect}
          value={file.target_format}
          onChange={handleFormatChange}
          disabled={disabled}
          aria-label={`Целевой формат для ${file.original_filename}`}
        >
          {formatOptions.map((fmt) => (
            <option key={fmt} value={fmt}>
              {fmt.toUpperCase()}
            </option>
          ))}
        </select>

        <button
          type="button"
          className={`${styles.settingsBtn} ${showSettings ? styles.settingsBtnActive : ''}`}
          onClick={() => onToggleSettings(file.task_id)}
          disabled={disabled}
          aria-label={`Настройки конвертации для ${file.original_filename}`}
          aria-pressed={showSettings}
          title="Параметры конвертации"
        >
          <Settings size={15} aria-hidden="true" />
        </button>
      </div>

      {/* ── Upload progress bar (hidden once upload is complete) ── */}
      {isUploading && (
        <div className={styles.progressTrack} role="progressbar" aria-valuenow={file.uploadProgress} aria-valuemin={0} aria-valuemax={100} aria-label={`Загрузка ${file.original_filename}`}>
          <div
            className={styles.progressFill}
            style={{ width: `${file.uploadProgress}%` }}
          />
        </div>
      )}
    </div>
  )
}
