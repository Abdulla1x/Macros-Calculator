import type { ReactNode } from 'react'
import { useWakeProgress } from '../hooks/useWakeProgress'

/** The one sentence that explains the free-tier cold start, and a bar showing
 * how far through it we are.
 *
 * It appears in two places that have nothing else in common — the logged-out
 * auth pages and the authenticated first load — and the wording is the whole
 * point: it turns "the app is broken" into "the app is waking up". Kept in one
 * component so the two copies can't drift into saying different things about
 * the same wait.
 *
 * "Up to a minute" is measured, not hedging: a median of 52.3s over ten
 * consecutive cold starts, with a slower cluster at 62.4s. It said "~30
 * seconds" until 2026-09-03, which no measurement has ever supported.
 *
 * The bar is calibrated against those same numbers — see useWakeProgress. It
 * only appears once the wait stops looking normal, and it never fills, because
 * only the request completing can end the wait and this component unmounts when
 * it does.
 *
 * `startedAt` is when the request being waited on began. Layout must pass it;
 * the logged-out pages mount at their ping and can leave it out. See the hook.
 *
 * `children` is the caller's context-specific tail (the auth pages tell you to
 * keep filling in the form); everything before it is shared. */
export default function WakingNotice({
  children,
  className = 'mt-4 text-center text-xs text-ink-faint',
  startedAt,
}: {
  children?: ReactNode
  className?: string
  startedAt?: number
}) {
  const progress = useWakeProgress(startedAt)

  return (
    <p className={className}>
      <span className="animate-pulse text-amber-500">●</span> Waking the
      free-tier server — it sleeps when idle, so this can take up to a minute.
      {children}
      {progress !== null && (
        // Spans, not divs: this is inside a <p>, where a <div> is invalid HTML,
        // and `display: block` on a span is valid either way. Keeping the
        // paragraph as the only block element also means this addition does not
        // restructure the five routes that render the notice.
        //
        // role="progressbar" is deliberately NOT a live region, so a value
        // changing four times a second is never announced. aria-label rather
        // than aria-labelledby: the bar's name should be what the bar measures,
        // not the whole sentence read out again on every focus.
        <span
          role="progressbar"
          aria-label="Server wake-up progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
          className="mt-2 block h-1 overflow-hidden rounded-full bg-amber-500/20"
        >
          {/* Amber, matching the pulsing dot that already means "waiting" here.
              motion-reduce drops the tween but keeps the steps: the movement is
              information, only its smoothing is decoration. The duration equals
              the hook's tick, so each step is still travelling when the next
              one arrives and the bar reads as continuous. */}
          <span
            className="block h-full rounded-full bg-amber-500 transition-[width] duration-[250ms] ease-linear motion-reduce:transition-none"
            style={{ width: `${progress * 100}%` }}
          />
        </span>
      )}
    </p>
  )
}
