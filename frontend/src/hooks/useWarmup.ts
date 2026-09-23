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

/** How long consecutive fast failures must persist before this is called an
 * outage.
 *
 * ⚠️ A single fast failure is NOT evidence of one, and treating it as such is
 * the bug this constant fixes. Two things produce it that have nothing to do
 * with the server being broken: a phone whose radio is still waking answers
 * the first request out of a dead connection, and — measured on this service
 * every morning since 2026-09-11 — a sleeping instance is refused at the edge
 * in about 1.3 s rather than being held while it boots. Both used to land
 * straight on 'unavailable', so the app told its visitors it was down.
 *
 * The 2026-08-20 guard below still holds, which is the point: during a real
 * outage every ping still fails instantly, so this elapses and the page still
 * says so. It says so around a minute later instead of 1.3 seconds — inside
 * the window a 52 s boot would have occupied anyway, so nothing true is lost.
 *
 * ⚠️ A FLOOR, NOT A DEADLINE. The state can only change when an attempt comes
 * back, and by the time this elapses the backoff is 20 s wide, so the flip
 * lands on the first failure at or after 45 s — measured at ~62 s in the
 * browser. That is deliberate rather than tolerated: WakingNotice promises
 * "up to a minute", and declaring an outage before its own estimate had run
 * out is the shape of the bug being fixed here. Do not tighten it by adding a
 * timer that fires independently of an attempt — the message would then
 * contradict a request that is still in flight. */
const OUTAGE_AFTER_MS = 45_000

/** When to stop pinging a page nobody is looking at any more.
 *
 * Not politeness — instance hours. Render bills 750 a month per workspace and
 * the 16-hour keep-warm window already costs ~496 of them, so a login tab left
 * open would otherwise hold the free instance awake all night on its own. See
 * point 2 in .github/workflows/keep-warm.yml. */
const GIVE_UP_AFTER_MS = 5 * 60_000

/** Backoff between attempts; the last value repeats until GIVE_UP_AFTER_MS.
 *
 * Front-loaded because the failure this is most likely to be recovering from —
 * a connection that wasn't ready yet — clears in a second or two, and a first
 * retry 20 seconds out would miss it entirely. */
const RETRY_DELAYS_MS = [1_500, 3_000, 6_000, 12_000, 20_000]

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
 * ⚠️ It then did that on the FIRST such failure, with no retry, which is its
 * own way of being wrong — see OUTAGE_AFTER_MS. It now retries on a backoff
 * and only reports an outage once the refusals have persisted. Each retry is
 * also another chance to wake the instance, from the one client profile known
 * to manage it: an ordinary browser on a home connection.
 *
 * It still never blocks the form. A user who wants to try anyway should be
 * able to, and the state exists only to describe the wait honestly. */
export function useWarmup(): WarmupState {
  const [state, setState] = useState<WarmupState>('waking')

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    const mountedAt = Date.now()
    /** When the current run of consecutive fast failures began, or null if the
     * last attempt was not one. Reset rather than accumulated, because it is
     * *sustained* refusal that means an outage — a fast failure either side of
     * a slow one is two unrelated bad moments, not 45 seconds of downtime. */
    let fastFailingSince: number | null = null

    const scheduleNext = () => {
      if (cancelled || Date.now() - mountedAt >= GIVE_UP_AFTER_MS) return
      const delay = RETRY_DELAYS_MS[Math.min(attempt, RETRY_DELAYS_MS.length - 1)]
      attempt += 1
      timer = setTimeout(ping, delay)
    }

    const ping = () => {
      const startedAt = Date.now()
      api
        .health()
        // No timeout override: the client's 90 s default is what lets a ping
        // the server is HOLDING run to completion, and that request finishing
        // at ~53 s is the success path. Shortening it here would abort exactly
        // the boots this hook exists to wait out — the bug that DEFAULT_TIMEOUT_MS
        // being 60 s already caused once, recorded in api/client.ts.
        .then(() => {
          if (cancelled) return
          // Deliberately terminal: once it is awake there is nothing left to
          // find out, and a poll on a form page would hold the instance up.
          setState('ready')
        })
        .catch(() => {
          if (cancelled) return
          // `navigator.onLine` is only trustworthy when it says *false* — the
          // browser knows there is no route out. Attributing that to the server
          // would swap one wrong diagnosis for another.
          const isOffline =
            typeof navigator !== 'undefined' && navigator.onLine === false
          const wasFast = Date.now() - startedAt < COLD_START_FLOOR_MS
          if (isOffline || !wasFast) {
            /* Still waking: the request either reached a server that held it,
               or never left this device. Neither is evidence about the API. */
            fastFailingSince = null
          } else {
            fastFailingSince ??= startedAt
            if (Date.now() - fastFailingSince >= OUTAGE_AFTER_MS) {
              setState('unavailable')
            }
          }
          scheduleNext()
        })
    }

    ping()
    return () => {
      cancelled = true
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [])

  return state
}
