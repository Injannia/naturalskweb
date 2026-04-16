// ── FileDropZone — drag-and-drop upload area for the File Converter ──
//
// Why a standalone component: the drop zone has its own drag state and validation
// logic that would otherwise bloat ConverterPage. Isolating it also lets us test
// validation rules in isolation.

import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { toast } from 'react-toastify'

import { MAX_FILE_SIZE, MAX_BATCH_SIZE, isAllowedExtension, formatFileSize } from './utils'
import styles from './FileDropZone.module.css'

interface FileDropZoneProps {
  onFilesSelected: (files: File[]) => void
  disabled?: boolean
  currentFileCount: number
}

export function FileDropZone({ onFilesSelected, disabled = false, currentFileCount }: FileDropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // How many more files the user is allowed to add right now
  const remainingSlots = MAX_BATCH_SIZE - currentFileCount
  const isAtCapacity = remainingSlots <= 0
  const isDisabled = disabled || isAtCapacity

  // ── Validation ──────────────────────────────────────────────────────────────

  /**
   * Filters the raw FileList/Array against all client-side rules.
   * Invalid files are rejected with individual toast messages — valid ones are
   * passed straight to the parent without duplicating state here.
   */
  function validateAndDispatch(rawFiles: File[]): void {
    if (rawFiles.length === 0) return

    const accepted: File[] = []
    let rejectedUnsupported = 0
    let rejectedTooLarge = 0

    for (const file of rawFiles) {
      if (!isAllowedExtension(file.name)) {
        rejectedUnsupported++
        continue
      }
      if (file.size > MAX_FILE_SIZE) {
        rejectedTooLarge++
        continue
      }
      accepted.push(file)
    }

    // Batch-size guard: only take as many as there are free slots
    const clipped = accepted.slice(0, remainingSlots)
    const rejectedOverflow = accepted.length - clipped.length

    // Report all rejection reasons up front so the user understands what happened
    if (rejectedUnsupported > 0) {
      toast.error(
        rejectedUnsupported === 1
          ? 'Файл не поддерживается. Принимаются видео, аудио, изображения и документы.'
          : `${rejectedUnsupported} файлов не поддерживаются и пропущены.`,
      )
    }
    if (rejectedTooLarge > 0) {
      toast.error(
        rejectedTooLarge === 1
          ? `Файл превышает лимит ${formatFileSize(MAX_FILE_SIZE)}.`
          : `${rejectedTooLarge} файлов превышают лимит ${formatFileSize(MAX_FILE_SIZE)} и пропущены.`,
      )
    }
    if (rejectedOverflow > 0) {
      toast.error(
        `Добавлено только ${clipped.length} из ${accepted.length} файлов — достигнут лимит в ${MAX_BATCH_SIZE} файлов.`,
      )
    }

    if (clipped.length > 0) {
      onFilesSelected(clipped)
    }
  }

  // ── Drag handlers ───────────────────────────────────────────────────────────

  function handleDragOver(e: React.DragEvent<HTMLDivElement>): void {
    // Allow drop by preventing the default "no-drop" browser behaviour
    e.preventDefault()
    e.stopPropagation()
  }

  function handleDragEnter(e: React.DragEvent<HTMLDivElement>): void {
    e.preventDefault()
    e.stopPropagation()
    if (!isDisabled) setIsDragOver(true)
  }

  function handleDragLeave(e: React.DragEvent<HTMLDivElement>): void {
    e.preventDefault()
    e.stopPropagation()
    // Only clear the highlight when leaving the zone itself, not a child element
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setIsDragOver(false)
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>): void {
    e.preventDefault()
    e.stopPropagation()
    setIsDragOver(false)

    if (isDisabled) return

    const files = Array.from(e.dataTransfer.files)
    validateAndDispatch(files)
  }

  // ── Click-to-browse ─────────────────────────────────────────────────────────

  function handleClick(): void {
    if (isDisabled) return
    inputRef.current?.click()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>): void {
    if (isDisabled) return
    // Keyboard activation: Space and Enter both trigger the file picker
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      inputRef.current?.click()
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const files = Array.from(e.target.files ?? [])
    validateAndDispatch(files)
    // Reset so the same file can be re-selected after being removed from the list
    e.target.value = ''
  }

  // ── Derive CSS class string ─────────────────────────────────────────────────

  const zoneClasses = [
    styles.dropZone,
    isDragOver && !isDisabled ? styles.dragOver : '',
    isDisabled ? styles.disabled : '',
  ]
    .filter(Boolean)
    .join(' ')

  // ── Subtitle line: reflects remaining capacity ──────────────────────────────

  const subtitleText = isAtCapacity
    ? `Достигнут лимит в ${MAX_BATCH_SIZE} файлов`
    : disabled
      ? 'Дождитесь завершения конвертации'
      : 'или нажмите для выбора'

  return (
    <div
      className={zoneClasses}
      role="button"
      tabIndex={isDisabled ? -1 : 0}
      aria-label="Зона загрузки файлов. Перетащите файлы сюда или нажмите для выбора"
      aria-disabled={isDisabled}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Hidden native file input — triggered programmatically */}
      <input
        ref={inputRef}
        type="file"
        multiple
        aria-label="Выбор файлов для конвертации"
        className={styles.hiddenInput}
        tabIndex={-1}
        disabled={isDisabled}
        onChange={handleInputChange}
      />

      <div className={styles.content}>
        <div className={`${styles.iconWrap}${isDragOver && !isDisabled ? ` ${styles.iconWrapActive}` : ''}`}>
          <Upload size={32} aria-hidden="true" />
        </div>

        <p className={styles.mainText}>Перетащите файлы сюда</p>
        <p className={styles.subText}>{subtitleText}</p>

        <p className={styles.hint}>
          Видео, аудио, изображения, документы · до {formatFileSize(MAX_FILE_SIZE)}
        </p>
      </div>
    </div>
  )
}
