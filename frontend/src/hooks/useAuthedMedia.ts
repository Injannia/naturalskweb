import { useEffect, useState } from 'react'
import api from '../api/client'

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
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url])

  return src
}
