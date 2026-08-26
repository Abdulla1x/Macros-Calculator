import { useWarmup } from '../hooks/useWarmup'
import WakingNotice from './WakingNotice'

/** Live cold-start state for the logged-out pages.
 *
 * One component rather than the same conditional in both Login and Signup —
 * mounting it is what fires the warm-up ping, so the two pages can't drift into
 * warming the server differently. The waking wording itself lives in
 * WakingNotice, which the authenticated pages share. */
export default function WarmupNotice() {
  const state = useWarmup()

  if (state === 'ready') {
    return (
      <p className="mt-4 text-center text-xs text-ink-faint">
        {/* Deliberately not "logging in": four logged-out pages share this
            component now, and only one of them is a login. A wording prop would
            reopen exactly the drift this component exists to prevent. */}
        <span className="text-emerald-500">●</span> Server is awake — this should
        be quick.
      </p>
    )
  }

  if (state === 'unavailable') {
    // Deliberately not a WakingNotice: that component's whole job is to turn
    // "the app is broken" into "the app is waking up", and saying that during
    // an actual outage is the failure this state was added to stop. The form
    // is still usable — a user who wants to try anyway should be able to.
    return (
      <p className="mt-4 text-center text-xs text-ink-faint">
        <span className="text-amber-500">●</span> The server isn&apos;t
        responding. This looks like a temporary outage rather than the usual
        cold start, so it is not something to fix on your end — try again in a
        few minutes.
      </p>
    )
  }

  return (
    <WakingNotice> Fill in the form; it will be ready by the time you submit.</WakingNotice>
  )
}
