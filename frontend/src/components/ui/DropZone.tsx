import { useRef, useState, DragEvent, ChangeEvent, ReactNode } from 'react'
import { UploadCloud } from 'lucide-react'
import styles from './DropZone.module.css'

export interface DropZoneProps {
  onFiles: (files: File[]) => void
  accept?: string
  multiple?: boolean
  disabled?: boolean
  label?: ReactNode
  hint?: ReactNode
  className?: string
}

export default function DropZone({
  onFiles,
  accept,
  multiple = true,
  disabled = false,
  label,
  hint,
  className = '',
}: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [active, setActive] = useState(false)

  const handleFiles = (files: FileList | null) => {
    if (!files || disabled) return
    onFiles(Array.from(files))
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setActive(false)
    handleFiles(e.dataTransfer.files)
  }

  const onClick = () => { if (!disabled) inputRef.current?.click() }
  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files)
    e.target.value = ''
  }

  return (
    <div
      className={`${styles.zone} ${active ? styles.zoneActive : ''} ${className}`}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setActive(true) }}
      onDragLeave={() => setActive(false)}
      onDrop={onDrop}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !disabled) onClick() }}
      aria-disabled={disabled}
    >
      <UploadCloud className={styles.zoneIcon} aria-hidden="true" />
      <div>{label ?? 'Перетащите файлы или нажмите для выбора'}</div>
      {hint && <div className={styles.hint}>{hint}</div>}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={onChange}
        style={{ display: 'none' }}
        disabled={disabled}
      />
    </div>
  )
}
