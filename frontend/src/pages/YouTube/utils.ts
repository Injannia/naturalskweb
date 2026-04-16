// ── YouTube utilities ──

/** Validates that a URL is a YouTube video or playlist */
export function isValidYouTubeUrl(url: string): boolean {
  if (!url.trim()) return false
  try {
    const parsed = new URL(url.trim())
    const host = parsed.hostname.replace(/^www\./, '')
    return host === 'youtube.com' || host === 'youtu.be' || host === 'm.youtube.com'
  } catch {
    return false
  }
}

/** Format seconds as mm:ss or hh:mm:ss */
export function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

/** Format bytes into human-readable size */
export function formatFileSize(bytes: number | null): string {
  if (bytes === null || bytes <= 0) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} ГБ`
}

/** Format bytes-per-second into a human-readable speed string */
export function formatSpeed(bytesPerSec: number): string {
  if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} Б/с`
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(0)} КБ/с`
  return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} МБ/с`
}

/** Format remaining seconds into a short Russian ETA string, e.g. "~1м 20с" or "~5с" */
export function formatEta(seconds: number): string {
  if (seconds <= 0) return '~0с'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m > 0) return `~${m}м ${s}с`
  return `~${s}с`
}

/**
 * Rough per-video size heuristic (MB) keyed by quality.
 * Based on typical YouTube bitrates for a 5-minute video — intentionally
 * conservative so the estimate errs on the side of "might be larger".
 */
const SIZE_MB_PER_VIDEO: Record<string, number> = {
  '360p': 50,
  '480p': 90,
  '720p': 180,
  '1080p': 400,
  best: 400,
  mp3: 10,
  wav: 80,
}

/**
 * Returns a rough size estimate string for a playlist download,
 * e.g. "~2.5 ГБ" or "~900 МБ". Uses per-video heuristic values.
 */
export function estimatePlaylistSize(
  videoCount: number,
  quality: string,
  format: string,
): string {
  // Audio formats ignore quality — use the format key
  const key = format === 'mp3' || format === 'wav' ? format : quality
  const mbPerVideo = SIZE_MB_PER_VIDEO[key] ?? 180
  const totalMb = mbPerVideo * videoCount
  if (totalMb >= 1024) {
    return `~${(totalMb / 1024).toFixed(1)} ГБ`
  }
  return `~${Math.round(totalMb)} МБ`
}

/**
 * Format a yt-dlp upload date string (YYYYMMDD) into a short Russian date,
 * e.g. "12 мар. 2024". Returns null for empty or unparseable input so callers
 * can conditionally render.
 */
export function formatUploadDate(raw: string | null | undefined): string | null {
  if (!raw || raw.length !== 8) return null
  const year = parseInt(raw.slice(0, 4), 10)
  const month = parseInt(raw.slice(4, 6), 10) - 1 // Date months are 0-indexed
  const day = parseInt(raw.slice(6, 8), 10)
  if (isNaN(year) || isNaN(month) || isNaN(day)) return null
  const date = new Date(year, month, day)
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

/** File is available for this many milliseconds after the task becomes ready (6 hours) */
export const FILE_TTL_MS = 6 * 60 * 60 * 1000

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
