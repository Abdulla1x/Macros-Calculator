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
      <p className="mt-4 text-center text-xs text-slate-600">
        <span className="text-emerald-500">●</span> Server is awake — logging in
        should be quick.
      </p>
    )
  }

  return (
    <WakingNotice> Fill in the form; it will be ready by the time you submit.</WakingNotice>
  )
}
