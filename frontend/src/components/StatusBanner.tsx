import { useEffect, useState } from 'react'
import { dismissBanner, isBannerDismissed } from '../lib/dismissals'

/** The live status notice, when the server has one set.
 *
 * Presentational: the text comes from whoever already fetched
 * `/api/announcements`, so the logged-in shell and the login page can each show
 * it without a second request. */
export default function StatusBanner({ banner }: { banner: string | null }) {
  const [dismissed, setDismissed] = useState(false)

  // A banner that arrives (or changes) after mount has to be re-checked, or a
  // new notice would stay hidden behind the previous one's dismissal.
  useEffect(() => {
    setDismissed(banner !== null && isBannerDismissed(banner))
  }, [banner])

  if (!banner || dismissed) return null

  return (
    <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
      <span aria-hidden="true">⚠️</span>
      <p className="flex-1">{banner}</p>
      <button
        onClick={() => {
          dismissBanner(banner)
          setDismissed(true)
        }}
        aria-label="Dismiss notice"
        className="shrink-0 text-amber-300/70 hover:text-amber-100"
      >
        ✕
      </button>
    </div>
  )
}
