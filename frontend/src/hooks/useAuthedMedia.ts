import { useEffect, useState } from 'react'
import api from '../api/client'

// Grace period before a superseded/torn-down object URL is freed. A <video>/
// <audio> element consumes the blob URL asynchronously (it opens its own channel
// on the next tick), so revoking synchronously in the effect cleanup races that
// load — if the cleanup wins, the media element is left pointing at a freed URL
// and Firefox fails with "Failed to open channel". Deferring the revoke lets the
// consumer open its channel first; memory is still reclaimed, just slightly later.
const REVOKE_GRACE_MS = 30_000

/** Fetch an authed binary resource (video/audio/image) as an object URL. */
export function useAuthedMedia(url: string | null): string | null {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    if (!url) {
      setSrc(null)
      return
    }
    let cancelled = false
    let objectUrl: string | null = null

    api
      .get<Blob>(url, { responseType: 'blob' })
      .then(({ data }) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(data)
        setSrc(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setSrc(null)
      })

    return () => {
      cancelled = true
      if (objectUrl) {
        const toRevoke = objectUrl
        window.setTimeout(() => URL.revokeObjectURL(toRevoke), REVOKE_GRACE_MS)
      }
    }
  }, [url])

  return src
}
