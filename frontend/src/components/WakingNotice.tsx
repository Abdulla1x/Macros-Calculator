import type { ReactNode } from 'react'

/** The one sentence that explains the free-tier cold start.
 *
 * It appears in two places that have nothing else in common — the logged-out
 * auth pages and the authenticated first load — and the wording is the whole
 * point: it turns "the app is broken" into "the app is waking up". Kept in one
 * component so the two copies can't drift into saying different things about
 * the same wait.
 *
 * "Up to a minute" is measured, not hedging: 52.5s, 52.6s, 52.7s and 64.0s on
 * the live service across 2026. It said "~30 seconds" until 2026-09-03, which
 * no measurement has ever supported.
 *
 * `children` is the caller's context-specific tail (the auth pages tell you to
 * keep filling in the form); everything before it is shared. */
export default function WakingNotice({
  children,
  className = 'mt-4 text-center text-xs text-ink-faint',
}: {
  children?: ReactNode
  className?: string
}) {
  return (
    <p className={className}>
      <span className="animate-pulse text-amber-500">●</span> Waking the
      free-tier server — it sleeps when idle, so this can take up to a minute.
      {children}
    </p>
  )
}
