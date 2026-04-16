// ── File Converter utilities ──

import type { ConvertCategory } from './types'

/** File is available for this many milliseconds after the task becomes ready (6 hours) */
export const FILE_TTL_MS = 6 * 60 * 60 * 1000

export const MAX_FILE_SIZE = 500 * 1024 * 1024  // 500 MB
export const MAX_BATCH_SIZE = 20

/** Maps a lowercase file extension to its converter category */
export const CATEGORY_MAP: Record<string, ConvertCategory> = {
  // video
  mp4: 'video', avi: 'video', mkv: 'video', mov: 'video',
  wmv: 'video', flv: 'video', webm: 'video',
  // audio
  mp3: 'audio', wav: 'audio', ogg: 'audio', flac: 'audio',
  aac: 'audio', wma: 'audio', m4a: 'audio',
  // image
  jpg: 'image', jpeg: 'image', png: 'image', bmp: 'image',
  tiff: 'image', webp: 'image', gif: 'image', ico: 'image',
  // document
  docx: 'document', doc: 'document', odt: 'document', rtf: 'document',
  txt: 'document', xlsx: 'document', xls: 'document', csv: 'document',
  pptx: 'document', ppt: 'document',
}

/** Available target formats for each category */
export const FORMAT_OPTIONS: Record<ConvertCategory, string[]> = {
  video:    ['mp4', 'avi', 'mkv', 'mov', 'webm'],
  audio:    ['mp3', 'wav', 'ogg', 'flac', 'aac'],
  image:    ['jpg', 'png', 'bmp', 'tiff', 'webp', 'gif', 'ico'],
  document: ['pdf', 'docx', 'odt', 'txt', 'html', 'xlsx', 'csv'],
}

/** Russian display names for each category */
export const CATEGORY_LABELS: Record<ConvertCategory, string> = {
  video:    'Видео',
  audio:    'Аудио',
  image:    'Изображение',
  document: 'Документ',
}

/** Extract the lowercase extension from a filename */
export function getFileExtension(filename: string): string {
  return filename.split('.').pop()?.toLowerCase() ?? ''
}

/** Detect the converter category for a filename; returns null for unsupported types */
export function detectCategory(filename: string): ConvertCategory | null {
  const ext = getFileExtension(filename)
  return CATEGORY_MAP[ext] ?? null
}

/**
 * Returns the first available target format that differs from the source extension.
 * Falls back to the first option in the list if all formats match (unlikely).
 */
export function getDefaultTargetFormat(ext: string, category: ConvertCategory): string {
  const options = FORMAT_OPTIONS[category]
  const normalized = ext.toLowerCase()
  return options.find((f) => f !== normalized) ?? options[0]
}

/** Format bytes into a human-readable Russian size string */
export function formatFileSize(bytes: number | null): string {
  if (bytes === null || bytes <= 0) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} ГБ`
}

/** Trigger a browser file download from a Blob */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** Returns true when the file extension is supported by the converter */
export function isAllowedExtension(filename: string): boolean {
  const ext = getFileExtension(filename)
  return ext in CATEGORY_MAP
}

/** Returns an empty options object — all conversion options are optional */
export function getDefaultOptions(): Record<string, never> {
  return {}
}
