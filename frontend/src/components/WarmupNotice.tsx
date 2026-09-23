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
    //
    // ⚠️ It used to assert the opposite — "this looks like a temporary outage
    // rather than the usual cold start" — and on this service that assertion
    // was wrong most mornings: a sleeping instance refused at the edge in
    // ~1.3 s is indistinguishable from a dead one, from here. The state now
    // means only "sustained fast refusals", so the copy names both causes
    // instead of picking one. Neither this component nor the user can tell
    // them apart, and pretending otherwise is what sent people away.
    return (
      <p className="mt-4 text-center text-xs text-ink-faint">
        <span className="text-amber-500">●</span> The server isn&apos;t
        answering. From here an outage and a free instance that will not wake
        look identical, so this is not something to fix on your end — try
        submitting anyway, or come back in a few minutes.
      </p>
    )
  }

  return (
    <WakingNotice> Fill in the form; it will be ready by the time you submit.</WakingNotice>
  )
}
