import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Announcements } from '../types'

/** Release notes plus the live status banner, or null while/if unavailable.
 *
 * Fails silently by design: announcements are decoration, and a failed fetch
 * must never surface an error over the app the user came here to use. */
export function useAnnouncements(): Announcements | null {
  const [data, setData] = useState<Announcements | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getAnnouncements()
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch(() => {
        /* nothing to announce is the safe assumption */
      })
    return () => {
      cancelled = true
    }
  }, [])

  return data
}
