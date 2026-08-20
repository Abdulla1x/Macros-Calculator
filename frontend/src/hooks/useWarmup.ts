import { useEffect, useState } from 'react'
import { api } from '../api/client'

export type WarmupState = 'waking' | 'ready' | 'unavailable'

/** How long a ping has to survive before its failure counts as a cold start.
 *
 * A sleeping free-tier instance *holds* the request while it boots — that wait
 * is the cold start. So a ping that fails in well under a second never reached
 * a waking server: something refused it immediately. Five seconds is a
 * deliberately generous floor, because being slow to admit an outage is a much
 * cheaper mistake than announcing one that isn't happening. */
const COLD_START_FLOOR_MS = 5000

/** Wakes the sleeping free-tier server while the user is still typing.
 *
 * The logged-out pages used to only warn that the first request can take ~30
 * seconds. Pinging the unauthenticated health endpoint on mount spends that
 * cold start against the time it takes to fill in a form, so submitting is
 * usually instant by the time the user gets there.
 *
 * This hook used to be fire-and-forget, on the reasoning that "a failed ping
 * means the server is still on its way up, not that anything is wrong". That
 * assumption broke on 2026-08-20: Render disabled spin-up for free services
 * during a Google Cloud incident, every ping failed instantly, and the page
 * went on telling people the server would be ready by the time they submitted
 * — for hours. A failure that arrives too fast to be a boot is now reported as
 * 'unavailable' instead of being swallowed.
 *
 * It still never blocks the form. A user who wants to try anyway should be
 * able to, and the state exists only to describe the wait honestly. */
export function useWarmup(): WarmupState {
  const [state, setState] = useState<WarmupState>('waking')

  useEffect(() => {
    let cancelled = false
    const startedAt = Date.now()
    api
      .health()
      .then(() => {
        if (!cancelled) setState('ready')
      })
      .catch(() => {
        if (cancelled) return
        // `navigator.onLine` is only trustworthy when it says *false* — the
        // browser knows there is no route out. Attributing that to the server
        // would swap one wrong diagnosis for another.
        const isOffline =
          typeof navigator !== 'undefined' && navigator.onLine === false
        if (Date.now() - startedAt < COLD_START_FLOOR_MS && !isOffline) {
          setState('unavailable')
        }
        /* otherwise still waking — the request itself will wait it out */
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
