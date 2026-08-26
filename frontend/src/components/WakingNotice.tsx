import type { ReactNode } from 'react'

/** The one sentence that explains the free-tier cold start.
 *
 * It appears in two places that have nothing else in common — the logged-out
 * auth pages and the authenticated first load — and the wording is the whole
 * point: it turns "the app is broken" into "the app is waking up". Kept in one
 * component so the two copies can't drift into saying different things about
 * the same 30 seconds.
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
      free-tier server — it sleeps when idle, so this can take ~30 seconds.
      {children}
    </p>
  )
}
