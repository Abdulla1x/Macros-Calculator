import { useEffect, useRef, useState } from 'react'

/** How long a cold boot actually takes, measured rather than guessed.
 *
 * 10/10 genuinely cold samples on 2026-09-03, the app untouched all night:
 * median 52.303s, fastest 52.253, slowest 62.398. The distribution is BIMODAL,
 * not noisy — eight samples inside 52.25–52.47 (a 0.22s spread) and two at
 * 62.2/62.4. The ~10s gap is a discrete extra step that happens roughly one run
 * in five, not variance to average away.
 *
 * That is why this is the median and never a mean: the mean of those ten
 * samples is ~54.3s, and no boot has ever taken 54 seconds. A bar animating
 * toward a number that never happens is wrong twice — early for the fast
 * cluster and late for the slow one. */
const BOOT_MS = 52_300

/** Where the bar is when the *typical* boot finishes. Not 100%: the remaining
 * 10% is the room the slow cluster needs, and a bar that hits full while the
 * user is still waiting is the one thing a progress bar must never do. */
const LINEAR_TARGET = 0.9

/** The bar's asymptote. It is approached and never reached — only the request
 * actually completing ends the wait, and this component unmounts when it does.
 * Completing on a timer would be a guess presented as a fact. */
const CEILING = 0.99

/** The creep's time constant, set so the +10s step closes exactly two thirds of
 * the gap left after BOOT_MS: 10_000 / ln(3).
 *
 * That lands the bar at 96% at 62.3s — the slow cluster, which reads as nearly
 * done because it is — and at 98.9% by 90s, which is DEFAULT_TIMEOUT_MS in
 * api/client.ts. The bar stops predicting at the moment the client stops
 * waiting, which is the only place a ceiling could honestly go. */
const CREEP_TAU_MS = 10_000 / Math.log(3)

/** Nothing is shown before this. A warm server answers in well under a second,
 * and a bar that appears and vanishes reads as a glitch rather than as
 * progress. Same idiom as COLD_START_NOTICE_AFTER_MS in Layout and
 * RETRY_NOTICE_AFTER_MS in MealAnalyzer: say nothing until the wait stops
 * looking normal. */
const BAR_AFTER_MS = 3_000

/** 4Hz. Slow enough to be free, fast enough that the CSS tween below it never
 * has to cover more than a quarter second. */
const TICK_MS = 250

/** Fraction complete after `elapsedMs`, in [0, CEILING).
 *
 * Two phases, because the measurement has two parts.
 *
 * **Linear to 90% over 52.3s.** Eight of ten cold starts landed inside a 0.22s
 * band, so for the overwhelming majority of boots the remaining time is
 * genuinely known — and a straight line is what "we know how long this takes"
 * looks like. An eased first phase would invent uncertainty the data does not
 * have, and a decelerating bar reads as stuck, which is the exact impression
 * this whole notice exists to prevent.
 *
 * **Exponential creep from 90% to 99% after that.** All the real uncertainty is
 * in the ~10s extra step, so that is the only place the curve bends. */
export function wakeProgress(elapsedMs: number): number {
  if (elapsedMs <= 0) return 0
  if (elapsedMs < BOOT_MS) return LINEAR_TARGET * (elapsedMs / BOOT_MS)
  return (
    CEILING -
    (CEILING - LINEAR_TARGET) * Math.exp(-(elapsedMs - BOOT_MS) / CREEP_TAU_MS)
  )
}

/** Live wake-up progress, or `null` while it is too early to say anything.
 *
 * `startedAt` is the moment the request being waited on actually began, which
 * is NOT always this component's mount time. Layout only renders the notice
 * three seconds into its settings fetch, so a bar started at mount would run
 * three seconds behind the wait it claims to describe. The logged-out pages do
 * mount at the ping, and pass nothing.
 *
 * The mount fallback is held in a ref so it stays fixed across re-renders,
 * while an explicitly passed `startedAt` still wins on every render. */
export function useWakeProgress(startedAt?: number): number | null {
  const mountedAt = useRef(Date.now())
  const start = startedAt ?? mountedAt.current
  const [elapsed, setElapsed] = useState(() => Date.now() - start)

  useEffect(() => {
    setElapsed(Date.now() - start)
    const id = setInterval(() => {
      const next = Date.now() - start
      setElapsed(next)
      // Once the rendered percentage can no longer change there is nothing left
      // to animate, so the timer stops and the bar visibly stops with it. That
      // is honest — past this point the app has stopped predicting — and it
      // ends a 4Hz render loop on a page that may sit here for a while.
      if (Math.round(wakeProgress(next) * 100) >= Math.round(CEILING * 100)) {
        clearInterval(id)
      }
    }, TICK_MS)
    return () => clearInterval(id)
  }, [start])

  return elapsed < BAR_AFTER_MS ? null : wakeProgress(elapsed)
}
