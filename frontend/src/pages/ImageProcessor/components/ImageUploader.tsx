// ── ImageUploader — single-file drag-and-drop upload for the Image Processor ──
//
// Adapted from the Converter's FileDropZone pattern. Validates a single image
// file on the client side, uploads it via imageApi, and calls onUploaded on success.

import { useRef, useState } from 'react'
import { Upload, Image, AlertCircle } from 'lucide-react'
import { toast } from 'react-toastify'

import { imageApi } from '../imageApi'
import { extractApiError } from '../../../utils/apiError'
import type { ImageOperation, ImageUploadResponse } from '../types'
import styles from './ImageUploader.module.css'

const DEFAULT_ACCEPTED_EXTS = ['jpg', 'jpeg', 'png', 'webp', 'bmp', 'tiff']
const DEFAULT_MAX_SIZE = 20 * 1024 * 1024 // 20 MB

interface ImageUploaderProps {
  onUploaded: (response: ImageUploadResponse) => void
  operation: ImageOperation
  disabled?: boolean
  acceptedExts?: string[]
  maxSize?: number
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function getExtension(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot === -1 ? '' : filename.slice(dot + 1).toLowerCase()
}

export function ImageUploader({
  onUploaded,
  operation,
  disabled = false,
  acceptedExts = DEFAULT_ACCEPTED_EXTS,
  maxSize = DEFAULT_MAX_SIZE,
}: ImageUploaderProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const isDisabled = disabled || isUploading

  // ── Validation & upload ─────────────────────────────────────────────────────

  function validateAndUpload(file: File): void {
    const ext = getExtension(file.name)
    if (!ext || !acceptedExts.includes(ext)) {
      toast.error(
        `Формат .${ext || '?'} не поддерживается. Допустимые: ${acceptedExts.join(', ')}.`,
      )
      return
    }
    if (file.size > maxSize) {
      toast.error(`Файл превышает лимит ${formatFileSize(maxSize)}.`)
      return
    }

    setIsUploading(true)
    setUploadProgress(0)

    imageApi
      .upload(file, operation, (loaded, total) => {
        setUploadProgress(Math.round((loaded / total) * 100))
      })
      .then((response) => {
        onUploaded(response)
      })
      .catch((err) => {
        toast.error(extractApiError(err, 'Ошибка загрузки'))
      })
      .finally(() => {
        setIsUploading(false)
        setUploadProgress(0)
      })
  }

  // ── Drag handlers ─────────────────────────────────────────────────────────

  function handleDragOver(e: React.DragEvent<HTMLDivElement>): void {
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
    if (files.length === 0) return

    if (files.length > 1) {
      toast.error('Можно загрузить только одно изображение за раз.')
      return
    }

    validateAndUpload(files[0])
  }

  // ── Click-to-browse ─────────────────────────────────────────────────────────

  function handleClick(): void {
    if (isDisabled) return
    inputRef.current?.click()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>): void {
    if (isDisabled) return
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      inputRef.current?.click()
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const files = Array.from(e.target.files ?? [])
    if (files.length > 0) {
      validateAndUpload(files[0])
    }
    e.target.value = ''
  }

  // ── CSS classes ─────────────────────────────────────────────────────────────

  const zoneClasses = [
    styles.dropZone,
    isDragOver && !isDisabled ? styles.dragOver : '',
    isDisabled ? styles.disabled : '',
  ]
    .filter(Boolean)
    .join(' ')

  // ── Render ──────────────────────────────────────────────────────────────────

  const acceptAttr = acceptedExts.map((ext) => `.${ext}`).join(',')

  return (
    <div
      className={zoneClasses}
      role="button"
      tabIndex={isDisabled ? -1 : 0}
      aria-label="Зона загрузки изображения. Перетащите файл сюда или нажмите для выбора"
      aria-disabled={isDisabled}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept={acceptAttr}
        aria-label="Выбор изображения"
        className={styles.hiddenInput}
        tabIndex={-1}
        disabled={isDisabled}
        onChange={handleInputChange}
      />

      {isUploading ? (
        <div className={styles.content}>
          <div className={styles.iconWrap}>
            <Upload size={32} aria-hidden="true" />
          </div>
          <p className={styles.mainText}>Загрузка... {uploadProgress}%</p>
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      ) : (
        <div className={styles.content}>
          <div
            className={`${styles.iconWrap}${isDragOver && !isDisabled ? ` ${styles.iconWrapActive}` : ''}`}
          >
            <Image size={32} aria-hidden="true" />
          </div>
          <p className={styles.mainText}>Перетащите изображение сюда</p>
          <p className={styles.subText}>
            {disabled ? 'Дождитесь завершения обработки' : 'или нажмите для выбора'}
          </p>
          <p className={styles.hint}>
            {acceptedExts.join(', ')} &middot; до {formatFileSize(maxSize)}
          </p>
        </div>
      )}
    </div>
  )
}
