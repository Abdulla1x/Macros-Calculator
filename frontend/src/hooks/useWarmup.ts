import { useEffect, useState } from 'react'
import { api } from '../api/client'

export type WarmupState = 'waking' | 'ready'

/** Wakes the sleeping free-tier server while the user is still typing.
 *
 * The logged-out pages used to only warn that the first request can take ~30
 * seconds. Pinging the unauthenticated health endpoint on mount spends that
 * cold start against the time it takes to fill in a form, so submitting is
 * usually instant by the time the user gets there.
 *
 * Deliberately fire-and-forget: a failed ping means the server is still on its
 * way up, not that anything is wrong, so it reports 'waking' rather than an
 * error. The state exists to describe the wait, never to block the form. */
export function useWarmup(): WarmupState {
  const [state, setState] = useState<WarmupState>('waking')

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then(() => {
        if (!cancelled) setState('ready')
      })
      .catch(() => {
        /* still waking — the login attempt itself will wait it out */
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
