import { useWarmup } from '../hooks/useWarmup'

/** Live cold-start state for the logged-out pages.
 *
 * One component rather than the same conditional in both Login and Signup —
 * mounting it is what fires the warm-up ping, so the two pages can't drift into
 * warming the server differently. */
export default function WarmupNotice() {
  const state = useWarmup()
  return (
    <p className="mt-4 text-center text-xs text-slate-600">
      {state === 'ready' ? (
        <>
          <span className="text-emerald-500">●</span> Server is awake — logging
          in should be quick.
        </>
      ) : (
        <>
          <span className="animate-pulse text-amber-500">●</span> Waking the
          free-tier server — it sleeps when idle, so this can take ~30 seconds.
          Fill in the form; it will be ready by the time you submit.
        </>
      )}
    </p>
  )
}
